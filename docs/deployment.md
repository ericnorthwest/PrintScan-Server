# Deployment on Debian or Ubuntu

This guide installs the current web/print milestone as an unprivileged
systemd service. It does not install or enable the privileged USB broker;
scanner jobs remain disabled until that component is implemented.

## 1. Install prerequisites

Install CUPS, SANE command-line tools, and uv using your distribution's
supported package/repository instructions. Ensure CUPS is configured with
at least one printer queue.

## 2. Install the application

~~~bash
sudo install -d -o "$USER" -g "$(id -gn)" -m 0755 /opt/printscan-server
git clone https://github.com/ericnorthwest/PrintScan-Server.git /opt/printscan-server
cd /opt/printscan-server
uv sync --no-dev
sudo chown -R root:root /opt/printscan-server
sudo chmod -R go+rX /opt/printscan-server
~~~

If the target directory already exists, clone into it only after confirming
that it is empty.

## 3. Create the service account and writable data directory

~~~bash
sudo groupadd --system printscan
sudo useradd --system --gid printscan --home-dir /var/lib/printscan-server \
  --no-create-home --shell /usr/sbin/nologin printscan
sudo install -d -o printscan -g printscan -m 0700 /var/lib/printscan-server
sudo install -d -o printscan -g printscan -m 0700 /var/lib/printscan-server/spool
~~~

Check the CUPS socket permissions:

~~~bash
stat -c '%A %U %G' /run/cups/cups.sock
~~~

On systems where the socket is group-readable by lp, add the service account
to that group and restart the service after the group change:

~~~bash
sudo usermod -aG lp printscan
~~~

If the socket uses a different group, use the group shown by stat instead.
Do not give the web service root privileges.

## 4. Configure the environment

~~~bash
sudo install -d -m 0750 /etc/printscan-server
sudo cp deploy/server.env.example /etc/printscan-server/server.env
sudo chmod 0640 /etc/printscan-server/server.env
sudo chown root:printscan /etc/printscan-server/server.env
sudoedit /etc/printscan-server/server.env
~~~

Set PRINTSCAN_ALLOWED_HOSTS to the actual LAN addresses and DNS names used
by browsers. For a plain trusted-LAN HTTP deployment, leave
PRINTSCAN_COOKIE_SECURE=false. Set it to true when HTTPS is terminated by a
trusted reverse proxy.

The service unit writes only to /var/lib/printscan-server.

## 5. Create the administrator

The CLI must use the same environment as the service:

~~~bash
sudo -u printscan bash -c 'set -a; . /etc/printscan-server/server.env; set +a; cd /opt/printscan-server; .venv/bin/printscan init-admin'
~~~

Use a unique password of at least 12 characters. No default account is
created automatically.

## 6. Install and start systemd unit

~~~bash
sudo cp deploy/printscan-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now printscan-server
sudo systemctl status printscan-server
~~~

Open the configured server address on TCP port 8090.

## 7. Automatically install the patched SANE build

For the systemd deployment in this guide, run this single command from the
cloned repository after the service account and systemd unit exist:

~~~bash
sudo ./scripts/install-sane.sh
~~~

For a development run started directly with `uv run printscan serve`, do not
use the system installer. Run the user-local installer instead:

~~~bash
./scripts/install-sane-dev.sh
~~~

It builds into `~/.local/opt/printscan-sane`, writes the three required SANE
environment variables into the repository's `.env`, and does not require
sudo. Run it as the same user and from the same checkout used to start uv.
Restart the development server after it finishes.

The installer automatically:
- downloads the exact SANE source archive pinned in version.lock;
- verifies its SHA256 checksum;
- verifies and applies the SCX-4100 patch;
- builds the upstream backend collection as the unprivileged printscan user;
- installs the custom SANE libraries and scanimage under
  /var/lib/printscan-server/sane;
- writes a dedicated systemd environment file so the web application uses
  the patched scanimage and its matching libraries;
- reloads the service unit and restarts PrintScan Server when it is active.

No manual patch copying, patch command, or hand-editing of LD_LIBRARY_PATH is
required. The installer does not overwrite the system SANE installation.

The patched SANE backend being installed does not by itself grant the service
account access to the SCX-4100 USB interface. This is a separate integration
step: the device currently requires usblp to be released for scanning. The
USB broker is the next implementation milestone; until then, the UI can
continue to report no available scanners.

If a build dependency is missing, install the distribution build dependencies
for sane-backends and rerun the same installer. The SANE source and patch are
pinned, so rerunning the installer is safe and repeatable.

## 8. IPP access

IPP is served by CUPS, not proxied through the FastAPI application. Configure
printer sharing and CUPS access controls separately, then restrict TCP port
631 to the intended local network with the host firewall. Keep CUPS remote
administration disabled unless there is a specific secured management need.

Do not expose either port 8090 or 631 directly to the public internet.
