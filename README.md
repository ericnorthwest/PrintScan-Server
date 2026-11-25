# PrintScan Server

PrintScan Server is a self-hosted print and scan gateway for a trusted local network. It combines a browser interface, authenticated management API, CUPS printing, IPP sharing through CUPS, and SANE scanner backends.

The project uses upstream CUPS and SANE rather than attempting to replace the mature Linux driver ecosystems.

## Current implementation

- FastAPI application and a responsive browser UI.
- SQLite user and session storage.
- PBKDF2-HMAC-SHA256 password hashing, HttpOnly cookies, SameSite protection, CSRF checks and login throttling.
- Read-only CUPS printer discovery and authenticated print submission.
- Read-only SANE scanner discovery.
- Upload size limits and a document type allow-list.
- Samsung SCX-4100 SANE compatibility patch and pinned source metadata.

## Not implemented yet

- Privileged USB broker for temporary usblp detach/reattach.
- Actual scanner job orchestration and scan download UI.
- Background job history, queue control, and printer administration.
- First-run setup wizard and multi-user administration UI.
- Full scanner job orchestration and USB broker.
- One-command production installer for the complete application stack.

The SCX-4100 was successfully detected and used for a real scan with the custom SANE build. Remaining integration work is to coordinate its shared USB interface safely with CUPS. The web service does not currently detach kernel drivers or run privileged USB operations.

## Requirements

Linux, Python 3.11+, uv, CUPS client tools (lp and lpstat), SANE tools (scanimage), and a configured CUPS printer queue.

## Development setup

~~~bash
git clone https://github.com/ericnorthwest/PrintScan-Server.git
cd PrintScan-Server
uv sync
cp .env.example .env
./scripts/install-sane-dev.sh
~~~

The development SANE installer automatically downloads the pinned upstream source, verifies it, applies the SCX-4100 patch, builds SANE into your user-local directory, and updates .env with the custom scanimage and library paths. Run it as the same unprivileged user that starts uv; do not use sudo. Restart the web server after it completes.

Edit .env and add the LAN IP or DNS name used to access the server to PRINTSCAN_ALLOWED_HOSTS. The project loads this file at startup.

Create the first administrator interactively:

~~~bash
uv run printscan init-admin
~~~

Start the application:

~~~bash
uv run printscan serve --host 0.0.0.0 --port 8090
~~~

Open http://SERVER-LAN-IP:8090/. There is no built-in default password and no unauthenticated setup endpoint.

## Printing and IPP

The web interface submits supported documents to an existing CUPS queue through lp. IPP remains provided by CUPS itself. Configure and secure CUPS sharing separately; do not expose the CUPS administration interface to untrusted networks. Firewall IPP access to the intended LAN and follow the host distribution's CUPS access-control guidance.

## Samsung SCX-4100

The SANE patch is in drivers/sane/patches and is pinned in drivers/sane/version.lock. Hardware validation is documented in drivers/sane/README.md.

The device presents a bidirectional Printer Class USB interface. On the validated system, usblp must be temporarily detached for scanner access. That must be implemented by a dedicated, narrowly scoped privileged broker. The API process must not run as root and must never receive arbitrary command execution capability.

## Security

Keep the service on a trusted LAN. Use HTTPS when credentials cross networks you do not fully trust, set PRINTSCAN_COOKIE_SECURE=true behind HTTPS, keep PRINTSCAN_ALLOWED_HOSTS explicit, restrict CUPS administration, and run the web process as a dedicated unprivileged account. Do not expose the application directly to the public internet.

Install the patched SANE backends automatically with sudo ./scripts/install-sane.sh after setting up the service; the source and patch are checksum-pinned. See docs/deployment.md and docs/sane-build.md. GitHub Actions runs compile, unit-test, and application-import checks on pushes and pull requests.

See docs/architecture.md and docs/security.md.
