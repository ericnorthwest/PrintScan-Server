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

## 7. Optional: install the pinned SANE build

The regular distro scanimage can remain configured for other scanners. To make
the patched SCX-4100 backend available to this service, build SANE as the
unprivileged service account into its data directory:

~~~bash
sudo -u printscan env \
  PRINTSCAN_BUILD_DIR=/var/lib/printscan-server/sane-build \
  PRINTSCAN_SANE_PREFIX=/var/lib/printscan-server/sane \
  bash /opt/printscan-server/scripts/build-sane.sh
~~~

Then edit server.env and set:

~~~ini
PRINTSCAN_SCANIMAGE_BIN=/var/lib/printscan-server/sane/bin/scanimage
LD_LIBRARY_PATH=/var/lib/printscan-server/sane/lib
SANE_CONFIG_DIR=/var/lib/printscan-server/sane/etc/sane.d
~~~

Restart the service after changing the environment. This makes the patched
backend discoverable by the application, but it does not yet release the
SCX-4100's usblp interface. Actual web scanning remains disabled until the
separate USB broker is installed.

## 8. IPP access

IPP is served by CUPS, not proxied through the FastAPI application. Configure
printer sharing and CUPS access controls separately, then restrict TCP port
631 to the intended local network with the host firewall. Keep CUPS remote
administration disabled unless there is a specific secured management need.

Do not expose either port 8090 or 631 directly to the public internet.
