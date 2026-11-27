# PrintScan Server

PrintScan Server is an authenticated scanner gateway for a trusted local network. Connect a USB scanner to a Linux computer, start the service there, and use its web interface from another computer, tablet, or phone.

The application uses FastAPI, SANE, SQLite, and a small vanilla JavaScript frontend. Python dependencies and project commands are managed with uv.

## Current implementation

- Existing username/password authentication and administrator CLI.
- PBKDF2-HMAC-SHA256 password hashes, HttpOnly session cookies, SameSite protection, CSRF validation, and login throttling.
- SANE scanner discovery.
- Scanner settings read from the selected SANE backend: scan mode, resolution, and source when supported.
- Live scan streaming over an authenticated WebSocket.
- Incremental PNM decoding in the browser so the preview is drawn while scan data arrives.
- Server-side export to PNG, JPEG, or PDF.
- A configurable maximum scan size and a single-scan lock.

## Samsung SCX-4100

The repository retains the targeted SANE 1.3.1 compatibility patch for USB VID:PID 04e8:3413 and the xerox_mfp backend. The patch allows this Samsung device's bidirectional Printer Class USB interface through SANE's libusb discovery filter.

The application does not run as root and does not detach kernel drivers. On systems where usblp holds the interface, the scanner may be discovered but fail when a scan is started. A narrowly scoped privileged USB broker with guaranteed driver restoration is a separate follow-up; do not permanently disable usblp.

Build/install scripts and the exact source checksum remain under drivers/sane/ and scripts/.

## Requirements

- Linux with a working SANE installation and scanimage.
- Python 3.11 or newer.
- uv.
- A USB scanner supported by the installed SANE backends.

For the Samsung SCX-4100, use the patched SANE build described below.

## Development setup

~~~bash
git clone https://github.com/ericnorthwest/PrintScan-Server.git
cd PrintScan-Server
uv sync
cp .env.example .env
./scripts/install-sane-dev.sh
~~~

Edit .env and add the LAN IP address or DNS name used by your browsers to PRINTSCAN_ALLOWED_HOSTS. The app loads this file at startup.

Create the first administrator interactively:

~~~bash
uv run printscan init-admin
~~~

Start the server on the LAN:

~~~bash
uv run printscan serve --host 0.0.0.0 --port 8090
~~~

Open http://SERVER-LAN-IP:8090/ from another device on the same network. There is no built-in default account or password.

## Live scanning

Choose a detected scanner. The interface queries SANE for its actual mode, resolution, and source options. Unsupported settings are not shown.

When scanning starts, the browser opens an authenticated WebSocket. The server runs scanimage without a shell, reads its PNM output in chunks, stores those bytes, and forwards each chunk to the browser. The browser decodes complete image rows and updates the canvas as they arrive. Completion creates the selected PNG, JPEG, or PDF download.

Progress is based on the received image dimensions and pixel rows. It is not a simulated timer. If the backend does not provide a fixed image height or returns an unsupported image format, the preview/progress behavior may need a backend-specific adjustment.

The default maximum raw scan size is 256 MiB. Change it with PRINTSCAN_MAX_SCAN_BYTES (allowed range: 1 MiB–1 GiB).

## Samsung SANE build

The SANE source version and checksum are pinned in drivers/sane/version.lock. The build script verifies the archive and patch before compiling.

For a development checkout:

~~~bash
./scripts/install-sane-dev.sh
~~~

For the systemd deployment, after creating the printscan service account:

~~~bash
sudo ./scripts/install-sane.sh
~~~

The installer does not overwrite the system SANE installation and does not modify USB kernel-driver binding.

## Security

Keep the service on a trusted local network. Use HTTPS when credentials cross networks you do not fully trust, set PRINTSCAN_COOKIE_SECURE=true behind HTTPS, and keep PRINTSCAN_ALLOWED_HOSTS explicit. Run the web process as a dedicated unprivileged account.

See docs/architecture.md, docs/security.md, docs/deployment.md, and docs/sane-build.md.
