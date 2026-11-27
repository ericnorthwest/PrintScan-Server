# Deployment on Debian or Ubuntu

This guide installs the scanner-only web application as an unprivileged systemd service.

## 1. Install prerequisites

Install Python 3.11 or newer, uv, and SANE tools from your distribution. For the Samsung SCX-4100 patched build, install its build dependencies and follow docs/sane-build.md.

## 2. Install the application

~~~bash
sudo install -d -o "$USER" -g "$(id -gn)" -m 0755 /opt/printscan-server
git clone https://github.com/ericnorthwest/PrintScan-Server.git /opt/printscan-server
cd /opt/printscan-server
uv sync --no-dev
sudo chown -R root:root /opt/printscan-server
sudo chmod -R go+rX /opt/printscan-server
~~~

If the target directory already exists, confirm that it is empty before cloning.

## 3. Create the service account and data directory

~~~bash
sudo groupadd --system printscan
sudo useradd --system --gid printscan --home-dir /var/lib/printscan-server \
  --no-create-home --shell /usr/sbin/nologin printscan
sudo install -d -o printscan -g printscan -m 0700 /var/lib/printscan-server
sudo install -d -o printscan -g printscan -m 0700 /var/lib/printscan-server/scans
~~~

The service account must have read/write access to the scanner through the distribution's SANE/udev permissions. Do not solve USB access by running FastAPI as root.

## 4. Configure the service

~~~bash
sudo install -d -m 0750 /etc/printscan-server
sudo cp deploy/server.env.example /etc/printscan-server/server.env
sudo chown root:printscan /etc/printscan-server/server.env
sudo chmod 0640 /etc/printscan-server/server.env
sudoedit /etc/printscan-server/server.env
~~~

Set PRINTSCAN_ALLOWED_HOSTS to the hostnames and LAN addresses used by clients. Set PRINTSCAN_COOKIE_SECURE=true only when HTTPS is enabled.

## 5. Create the administrator

~~~bash
sudo -u printscan bash -c 'set -a; . /etc/printscan-server/server.env; set +a; cd /opt/printscan-server; .venv/bin/printscan init-admin'
~~~

Use a unique password of at least 12 characters. No default account is created.

## 6. Enable the service

~~~bash
sudo cp deploy/printscan-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now printscan-server
sudo systemctl status printscan-server
~~~

Open http://SERVER-LAN-IP:8090/ from a device on the same network.

## 7. Install the patched SANE build

For the service account deployment, run:

~~~bash
sudo ./scripts/install-sane.sh
~~~

The installer builds the pinned SANE source, applies the SCX-4100 patch, and configures the service to use the custom scanimage and matching libraries. It does not change USB driver binding.

For a development run started with uv run printscan serve, use ./scripts/install-sane-dev.sh as the same unprivileged user.

The SCX-4100 may still report Resource busy when usblp owns its interface. The privileged USB broker that safely releases and restores that interface is not part of this initial scanner application. Do not permanently disable usblp.

## Network exposure

Keep TCP port 8090 restricted to the intended LAN. Do not expose the application directly to the public internet.
