# Architecture

## Components

~~~text
Browser -> FastAPI / PrintScan Server -> CUPS client -> CUPS queues -> Printer
                                |-> SANE CLI (discovery only) -> SANE backends

Future SCX-4100 path:
FastAPI -> constrained USB broker -> temporary usblp detach
         -> SANE scan -> guaranteed usblp restoration
~~~

## Service boundaries

The FastAPI process is unprivileged. It owns authentication, sessions, API requests, upload validation, temporary spool files, calls to the unprivileged CUPS client, and read-only scanner discovery.

CUPS owns print queues, printer drivers/filters, and IPP. PrintScan Server does not implement a second print scheduler. SANE owns scanner backends and device-specific scan options.

A future USB broker must be a separate privileged component. It must expose only fixed operations for the configured USB device, acquire an exclusive lock, temporarily detach the usblp interface when required, execute the approved scan workflow, and restore the original kernel driver in a finally path. It must also recover stale state after broker termination or reboot. It must not accept arbitrary sysfs paths, shell commands, or executable names.

## Persistence

SQLite stores users, password hashes, browser sessions, and login throttling records. Temporary print uploads are written under PRINTSCAN_SPOOL_DIR and removed after the CUPS submission attempt. The database and spool directory must be writable only by the service account.

## Next milestones

1. Build and install pinned upstream SANE source with the SCX-4100 patch.
2. Implement and test the constrained USB broker.
3. Add serialized print/scan coordination for devices sharing one USB interface.
4. Implement scan profiles, job state, output storage, and downloads.
5. Add queue management and administrator UI.
