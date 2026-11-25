# Security model

## Network boundary

PrintScan Server is intended for a trusted local network, not direct public-internet exposure. The application validates Host headers. Set PRINTSCAN_ALLOWED_HOSTS to the LAN IP addresses and DNS names clients actually use; do not use a wildcard in production.

Use HTTPS whenever passwords or session cookies cross an untrusted network. When HTTPS is enabled, set PRINTSCAN_COOKIE_SECURE=true.

## Authentication

There is no default account. An administrator is created from the local CLI. Passwords are stored as PBKDF2-HMAC-SHA256 hashes with random salts.

Browser sessions use random bearer values in HttpOnly cookies. Only a SHA-256 digest of each session token is stored in SQLite. Cookies use SameSite=Strict. State-changing authenticated requests also require the session's CSRF token. Failed logins are throttled by client address; this is a basic safeguard, not a substitute for firewalling or proxy rate limits.

## Uploads

Only PDF, PostScript, JPEG, PNG, and plain text files are accepted by the initial print endpoint. Uploads have a configurable size limit, use random server-side names, and are removed after the CUPS submission attempt. CUPS filters and printer drivers process submitted documents, so keep the host and CUPS packages updated.

## Privileges

Do not run FastAPI as root. It does not need permission to write sysfs or detach USB kernel drivers. A future USB broker must expose only narrowly defined scanner operations for the configured device; it must not expose arbitrary command execution or arbitrary device paths.

CUPS administration and IPP sharing are configured separately. Restrict their network access to the intended LAN.
