# Architecture

## Runtime flow

~~~text
Browser (desktop / phone)
  | HTTPS + authenticated WebSocket
  v
FastAPI application
  |-- SQLite authentication and sessions
  |-- SANE CLI discovery and option enumeration
  |-- scanimage subprocess
        |-- stdout: PNM image bytes
        |      |-- save temporary source image
        |      |-- stream binary chunks to browser
        |      '-- browser decodes rows into a live canvas
        '-- stderr: diagnostic messages
  '-- Pillow: final PNG / JPEG / PDF export
~~~

## Responsibilities

FastAPI owns authentication, CSRF validation, request validation, scanner discovery, option validation, scan process lifecycle, output storage, and downloads.

SANE owns hardware discovery and device-specific capabilities. PrintScan reads supported settings from scanimage -A --device-name DEVICE; it does not invent a global list of resolutions or modes. Scan arguments are passed as an argv list without a shell.

The browser receives binary PNM chunks over WebSocket. The preview decoder understands binary PBM/PGM/PPM (P4, P5, P6) and paints complete rows as they arrive. The progress bar is derived from image dimensions and bytes received.

Only one scan may run at a time in a server process. Cancelling or disconnecting the browser terminates the active scanimage process. Raw scan data is removed after conversion; the final export is stored under the configured scan directory.

## Samsung SCX-4100 and USB permissions

The repository retains the SANE patch for Samsung USB VID:PID 04e8:3413. The web process remains unprivileged and does not write to sysfs or detach kernel drivers.

Some SCX-4100 setups bind the bidirectional interface to usblp, which can make SANE discovery succeed while opening the device fails with Resource busy. The next hardware-integration component is a dedicated privileged broker scoped to the one configured USB device. It must acquire an exclusive lock, detach only the expected interface, execute the approved scan workflow, and restore the previous driver even after errors or termination. It must not expose arbitrary sysfs paths or shell commands.

## Limits

The initial streaming path targets single-frame PNM scans. Some SANE backends produce different frame layouts, unknown-length images, or non-PNM output; these require backend-specific handling. The browser canvas is scaled to a bounded preview size while the full-resolution image is saved and exported.
