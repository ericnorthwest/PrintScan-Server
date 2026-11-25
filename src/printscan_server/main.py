from __future__ import annotations

import os
import re
import secrets
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import Settings
from .database import (clear_login_failures, create_session, delete_session, get_session,
                       get_user, init_database, is_rate_limited, record_login_failure)
from .security import verify_password
from .services.cups import IntegrationUnavailable, list_printers, submit_print
from .services.sane import list_scanners

settings = Settings.from_env()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.spool_dir.mkdir(parents=True, exist_ok=True)
init_database(settings.database_path)
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
SESSION_COOKIE = "printscan_session"
ALLOWED_EXTENSIONS = {".pdf", ".ps", ".jpg", ".jpeg", ".png", ".txt"}


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def create_app() -> FastAPI:
    app = FastAPI(title="PrintScan Server", version=__version__, docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_session(request: Request) -> dict:
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")
        session = get_session(settings.database_path, token)
        if session is None:
            raise HTTPException(status_code=401, detail="Session expired")
        return session

    def csrf_session(request: Request, session: dict = Depends(current_session),
                     csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")) -> dict:
        if not csrf_token or not secrets.compare_digest(csrf_token, session["csrf_token"]):
            raise HTTPException(status_code=403, detail="CSRF validation failed")
        return session

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "name": "PrintScan Server", "version": __version__}

    @app.post("/api/v1/auth/login")
    async def login(payload: LoginPayload, request: Request, response: Response):
        remote_addr = request.client.host if request.client else "unknown"
        if is_rate_limited(settings.database_path, remote_addr):
            raise HTTPException(status_code=429, detail="Too many login attempts")
        user = get_user(settings.database_path, payload.username.strip())
        if user is None or not verify_password(payload.password, user["password_hash"]):
            record_login_failure(settings.database_path, remote_addr)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        clear_login_failures(settings.database_path, remote_addr)
        token, csrf_token, expires_at = create_session(
            settings.database_path, user["id"], settings.session_ttl_seconds
        )
        response.set_cookie(
            key=SESSION_COOKIE, value=token, max_age=settings.session_ttl_seconds,
            expires=expires_at, httponly=True, secure=settings.cookie_secure,
            samesite="strict", path="/",
        )
        return {"authenticated": True, "username": user["username"],
                "role": user["role"], "csrf_token": csrf_token}

    @app.get("/api/v1/auth/me")
    async def me(session: dict = Depends(current_session)):
        return {"authenticated": True, "username": session["username"],
                "role": session["role"], "csrf_token": session["csrf_token"]}

    @app.post("/api/v1/auth/logout")
    async def logout(response: Response, session: dict = Depends(csrf_session)):
        delete_session(settings.database_path, session["token_hash"])
        response.delete_cookie(key=SESSION_COOKIE, path="/", httponly=True,
                               secure=settings.cookie_secure, samesite="strict")
        return {"authenticated": False}

    @app.get("/api/v1/printers")
    async def printers(session: dict = Depends(current_session)):
        try:
            return await run_in_threadpool(list_printers, settings.lpstat_bin)
        except IntegrationUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/scanners")
    async def scanners(session: dict = Depends(current_session)):
        try:
            return await run_in_threadpool(list_scanners, settings.scanimage_bin)
        except IntegrationUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/v1/print")
    async def print_document(printer: str = Form(...), file: UploadFile = File(...),
                             session: dict = Depends(csrf_session)):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Allowed formats: PDF, PS, JPEG, PNG and TXT")
        try:
            cups_state = await run_in_threadpool(list_printers, settings.lpstat_bin)
        except IntegrationUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if printer not in {item["name"] for item in cups_state["printers"]}:
            raise HTTPException(status_code=404, detail="Unknown CUPS printer")

        file_descriptor, temp_path = tempfile.mkstemp(
            prefix="printscan-", suffix=suffix, dir=settings.spool_dir
        )
        try:
            total = 0
            with os.fdopen(file_descriptor, "wb") as output:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > settings.max_upload_bytes:
                        raise HTTPException(status_code=413, detail="Upload is too large")
                    output.write(chunk)
            if total == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            with open(temp_path, "rb") as source:
                header = source.read(16)
            signatures = {
                ".pdf": (b"%PDF-", "PDF"),
                ".jpg": (b"\xff\xd8\xff", "JPEG"),
                ".jpeg": (b"\xff\xd8\xff", "JPEG"),
                ".png": (b"\x89PNG\r\n\x1a\n", "PNG"),
                ".ps": (b"%!PS", "PostScript"),
            }
            if suffix in signatures and not header.startswith(signatures[suffix][0]):
                raise HTTPException(status_code=415, detail="File content does not match its extension")
            if suffix == ".txt" and b"\x00" in header:
                raise HTTPException(status_code=415, detail="Binary files are not accepted as TXT")
            original_name = Path(file.filename or "document").name
            safe_title = re.sub(r"[^A-Za-z0-9_. -]", "_", original_name).strip()[:120] or "Print job"
            try:
                output_text = await run_in_threadpool(
                    submit_print, settings.lp_bin, printer, safe_title, temp_path
                )
            except IntegrationUnavailable as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            return {"submitted": True, "printer": printer, "message": output_text}
        finally:
            await file.close()
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
