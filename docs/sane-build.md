# Building the pinned SANE backends

The build script downloads the exact upstream archive recorded in
`drivers/sane/version.lock`, verifies SHA256, verifies and applies the SCX-4100
patch, and builds the configured backend collection.

On Debian or Ubuntu, install the distribution build dependencies first. When
source repositories are enabled, this is the most complete starting point:

~~~bash
sudo apt-get build-dep sane-backends
sudo apt-get install libusb-1.0-0-dev
~~~

Then run the build as an ordinary user:

~~~bash
./scripts/build-sane.sh
~~~

The default install prefix is `$HOME/opt/printscan-sane`. Override it with
`PRINTSCAN_SANE_PREFIX`. The build cache defaults to `.build/sane` and can be
changed with `PRINTSCAN_BUILD_DIR`. Set `PRINTSCAN_BUILD_JOBS` to limit parallel
build jobs.

The script does not use sudo, modify the system SANE installation, change USB
permissions, detach `usblp`, or install a privileged broker. Those operations
remain separate by design.

The initial validation build used only the `xerox_mfp` backend to isolate the
SCX-4100. The release build uses the pinned `BUILD_BACKENDS=all` policy.
