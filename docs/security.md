# Security model

## Network boundary

PrintScan Server is intended for a trusted local network, not direct public-internet exposure. The application validates Host headers and WebSocket Origin values. Set PRINTSCAN_ALLOWED_HOSTS to the LAN IP addresses and DNS names clients actually use; do not use a wildcard in production.

Use HTTPS whenever passwords or session cookies cross an untrusted network. When HTTPS is enabled, set PRINTSCAN_COOKIE_SECURE=true.

## Authentication

The existing administrator authentication is retained. There is no default account; create the first administrator from the local CLI. Passwords are stored as PBKDF2-HMAC-SHA256 hashes with random salts.

Browser sessions use random bearer values in HttpOnly cookies. Only a SHA-256 digest of each session token is stored in SQLite. Cookies use SameSite=Strict. State-changing HTTP requests require the session CSRF token. The WebSocket scan handshake also requires the same CSRF token in its first message. Failed logins are throttled by client address.

## Scanner process

The FastAPI application must not run as root. scanimage is launched with a fixed executable and an argument vector; user-controlled values are checked against the selected backend's advertised capabilities. No shell is used.

The application permits only one active scan per process, caps raw image size, drains subprocess stderr, and terminates the scan process when the user cancels or the WebSocket disconnects. Scanner output is stored under the private application data directory and downloads require authentication.

## USB privileges

The web process does not detach kernel drivers or write to sysfs. The future SCX-4100 USB broker must be narrow, auditable, and limited to the configured Samsung device. It must not accept arbitrary command execution or arbitrary device paths. Never permanently disable usblp as a workaround.
