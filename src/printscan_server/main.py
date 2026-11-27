from __future__ import annotations

import asyncio
import secrets
import uuid
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .config import Settings
from .database import (
    clear_login_failures,
    create_session,
    delete_session,
    get_session,
    get_user,
    init_database,
    is_rate_limited,
    record_login_failure,
)
from .security import verify_password
from .services.sane import (
    SaneError,
    build_scan_arguments,
    get_scanner_options,
    list_scanners,
)

settings = Settings.from_env()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.scan_dir.mkdir(parents=True, exist_ok=True)
init_database(settings.database_path)

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
SESSION_COOKIE = "printscan_session"
SCAN_LOCK = asyncio.Lock()
SCAN_FORMATS = {
    "png": ("image/png", "PNG"),
    "jpg": ("image/jpeg", "JPEG"),
    "pdf": ("application/pdf", "PDF"),
}


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _convert_scan(source: Path, destination: Path, output_format: str, dpi: int) -> None:
    with Image.open(source) as image:
        image.load()
        image = image.convert("RGB")
        if output_format == "jpg":
            image.save(destination, format="JPEG", quality=94, optimize=True, dpi=(dpi, dpi))
        elif output_format == "pdf":
            image.save(destination, format="PDF", resolution=dpi)
        else:
            image.save(destination, format="PNG", optimize=True, dpi=(dpi, dpi))


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except asyncio.TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()


async def _drain_stderr(stream: asyncio.StreamReader) -> str:
    captured = bytearray()
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        if len(captured) < 24_000:
            captured.extend(chunk[: 24_000 - len(captured)])
    return captured.decode("utf-8", errors="replace").strip()


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
            "script-src 'self'; connect-src 'self' ws: wss:; object-src 'none'; "
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

    def csrf_session(
        request: Request,
        session: dict = Depends(current_session),
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict:
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
        return {
            "authenticated": True,
            "username": user["username"],
            "role": user["role"],
            "csrf_token": csrf_token,
        }

    @app.get("/api/v1/auth/me")
    async def me(session: dict = Depends(current_session)):
        return {
            "authenticated": True,
            "username": session["username"],
            "role": session["role"],
            "csrf_token": session["csrf_token"],
        }

    @app.post("/api/v1/auth/logout")
    async def logout(response: Response, session: dict = Depends(csrf_session)):
        delete_session(settings.database_path, session["token_hash"])
        response.delete_cookie(
            key=SESSION_COOKIE, path="/", httponly=True,
            secure=settings.cookie_secure, samesite="strict",
        )
        return {"authenticated": False}

    @app.get("/api/v1/scanners")
    async def scanners(session: dict = Depends(current_session)):
        try:
            return await run_in_threadpool(list_scanners, settings.scanimage_bin)
        except SaneError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/scanners/options")
    async def scanner_options(device: str, session: dict = Depends(current_session)):
        try:
            return await run_in_threadpool(get_scanner_options, settings.scanimage_bin, device)
        except SaneError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/scans/{scan_id}/download")
    async def download_scan(scan_id: str, session: dict = Depends(current_session)):
        if len(scan_id) != 32 or any(char not in "0123456789abcdef" for char in scan_id):
            raise HTTPException(status_code=404, detail="Scan not found")
        for suffix, (media_type, _) in SCAN_FORMATS.items():
            path = settings.scan_dir / f"{scan_id}.{suffix}"
            if path.is_file():
                return FileResponse(
                    path,
                    media_type=media_type,
                    filename=f"scan_{scan_id[:8]}.{suffix}",
                )
        raise HTTPException(status_code=404, detail="Scan not found")

    @app.websocket("/api/v1/scans/stream")
    async def scan_stream(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        if origin:
            origin_host = (urlsplit(origin).hostname or "").lower()
            allowed = {host.strip().strip("[]").lower() for host in settings.allowed_hosts}
            if origin_host not in allowed:
                await websocket.close(code=4403)
                return

        token = websocket.cookies.get(SESSION_COOKIE)
        session = get_session(settings.database_path, token) if token else None
        if session is None:
            await websocket.close(code=4401)
            return

        await websocket.accept()
        try:
            request_data = await asyncio.wait_for(websocket.receive_json(), timeout=15)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            with suppress(Exception):
                await websocket.close(code=4400)
            return
        except Exception:
            await websocket.send_json({"type": "error", "message": "Некорректный запрос."})
            await websocket.close(code=4400)
            return

        if not isinstance(request_data, dict):
            await websocket.send_json({"type": "error", "message": "Некорректный запрос."})
            await websocket.close(code=4400)
            return

        csrf_token = request_data.get("csrf_token")
        if not isinstance(csrf_token, str) or not secrets.compare_digest(
            csrf_token, session["csrf_token"]
        ):
            await websocket.send_json({"type": "error", "message": "Проверка CSRF не пройдена."})
            await websocket.close(code=4403)
            return
        if request_data.get("action") != "start":
            await websocket.send_json({"type": "error", "message": "Ожидалась команда start."})
            await websocket.close(code=4400)
            return

        device = request_data.get("device")
        if not isinstance(device, str) or not device or len(device) > 512:
            await websocket.send_json({"type": "error", "message": "Не выбран сканер."})
            await websocket.close(code=4400)
            return

        output_format = request_data.get("format", "png")
        if output_format not in SCAN_FORMATS:
            await websocket.send_json({"type": "error", "message": "Неподдерживаемый формат файла."})
            await websocket.close(code=4400)
            return

        try:
            details = await run_in_threadpool(
                get_scanner_options, settings.scanimage_bin, device
            )
            scan_args = build_scan_arguments(
                device,
                details["options"],
                {
                    "mode": request_data.get("mode"),
                    "resolution": request_data.get("resolution"),
                    "source": request_data.get("source"),
                },
            )
        except SaneError as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=4400)
            return

        if SCAN_LOCK.locked():
            await websocket.send_json({"type": "error", "message": "Сканер уже занят другим заданием."})
            await websocket.close(code=1013)
            return

        await SCAN_LOCK.acquire()
        scan_id = uuid.uuid4().hex
        raw_path = settings.scan_dir / f"{scan_id}.pnm"
        final_path = settings.scan_dir / f"{scan_id}.{output_format}"
        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task[str] | None = None
        pump_task: asyncio.Task[int] | None = None
        wait_task: asyncio.Task[int] | None = None
        control_task: asyncio.Task | None = None
        disconnected = False
        cancelled = False
        failure: str | None = None
        total_bytes = 0

        try:
            command = [settings.scanimage_bin, *scan_args]
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise SaneError(
                    f"scanimage не найден: {settings.scanimage_bin}. Проверьте PRINTSCAN_SCANIMAGE_BIN."
                ) from exc

            assert process.stdout is not None and process.stderr is not None

            async def pump_output() -> int:
                received = 0
                last_report = 0
                with raw_path.open("wb") as output:
                    while True:
                        chunk = await process.stdout.read(64 * 1024)
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > settings.max_scan_bytes:
                            raise SaneError(
                                "Скан превышает PRINTSCAN_MAX_SCAN_BYTES. "
                                "Уменьшите разрешение или увеличьте лимит."
                            )
                        output.write(chunk)
                        await websocket.send_bytes(chunk)
                        if received - last_report >= 1024 * 1024:
                            await websocket.send_json({"type": "bytes", "received": received})
                            last_report = received
                return received

            await websocket.send_json({
                "type": "started",
                "message": "Сканер начал передавать изображение.",
                "max_bytes": settings.max_scan_bytes,
            })

            stderr_task = asyncio.create_task(_drain_stderr(process.stderr))
            pump_task = asyncio.create_task(pump_output())
            wait_task = asyncio.create_task(process.wait())
            control_task = asyncio.create_task(websocket.receive_json())

            while not (pump_task.done() and wait_task.done()):
                watched = set()
                if not pump_task.done():
                    watched.add(pump_task)
                if not wait_task.done():
                    watched.add(wait_task)
                if control_task is not None and not control_task.done():
                    watched.add(control_task)
                if not watched:
                    break

                done, _ = await asyncio.wait(
                    watched,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if control_task in done:
                    try:
                        control = control_task.result()
                    except WebSocketDisconnect:
                        disconnected = True
                        break
                    except Exception:
                        failure = "Получена некорректная команда управления сканированием."
                        break
                    if isinstance(control, dict) and control.get("action") == "cancel":
                        cancelled = True
                        break
                    control_task = asyncio.create_task(websocket.receive_json())

                if pump_task.done() and not pump_task.cancelled():
                    pump_error = pump_task.exception()
                    if pump_error is not None:
                        failure = str(pump_error)
                        break

            if process.returncode is None and (cancelled or disconnected or failure):
                await _stop_process(process)

            if pump_task:
                result = await asyncio.gather(pump_task, return_exceptions=True)
                if result and isinstance(result[0], int):
                    total_bytes = result[0]
                elif result and isinstance(result[0], BaseException) and not failure:
                    failure = str(result[0])
            if wait_task:
                await wait_task
            stderr_text = await stderr_task if stderr_task else ""

            if cancelled:
                with suppress(FileNotFoundError):
                    raw_path.unlink()
                if not disconnected:
                    await websocket.send_json({"type": "cancelled", "message": "Сканирование отменено."})
                return
            if disconnected:
                return
            if failure:
                raise SaneError(failure)
            if process.returncode != 0:
                detail = stderr_text or f"scanimage завершился с кодом {process.returncode}."
                raise SaneError(detail)
            if total_bytes == 0:
                raise SaneError(stderr_text or "Сканер не вернул данные изображения.")

            resolution = request_data.get("resolution")
            try:
                dpi = int(resolution) if resolution is not None else 300
            except (TypeError, ValueError):
                dpi = 300
            dpi = min(max(dpi, 50), 9600)

            await run_in_threadpool(
                _convert_scan, raw_path, final_path, output_format, dpi
            )
            await websocket.send_json({
                "type": "complete",
                "scan_id": scan_id,
                "download_url": f"/api/v1/scans/{scan_id}/download",
                "bytes": total_bytes,
                "format": output_format,
            })
        except Exception as exc:
            with suppress(FileNotFoundError):
                raw_path.unlink()
            with suppress(FileNotFoundError):
                final_path.unlink()
            if not disconnected:
                with suppress(WebSocketDisconnect):
                    await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            disconnected = True
        finally:
            if control_task and not control_task.done():
                control_task.cancel()
                await asyncio.gather(control_task, return_exceptions=True)
            if process and process.returncode is None:
                await _stop_process(process)
            if stderr_task and not stderr_task.done():
                await asyncio.gather(stderr_task, return_exceptions=True)
            if disconnected or cancelled or failure:
                with suppress(FileNotFoundError):
                    raw_path.unlink()
                with suppress(FileNotFoundError):
                    final_path.unlink()
            SCAN_LOCK.release()

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
