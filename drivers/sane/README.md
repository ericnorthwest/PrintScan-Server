# SANE Driver Integration

PrintScan Server uses upstream SANE backends for universal scanner
support.

## Samsung SCX-4100 compatibility patch

Target:
- USB VID: 04e8
- USB PID: 3413
- Interface class: Printer (0x07)
- SANE backend: xerox_mfp

The patch modifies the libusb-1.0 device discovery logic in
sanei/sanei_usb.c. It allows this specific Samsung device to pass
the scanner-interface filter.

Other USB devices retain the original SANE discovery behavior.

## Build policy

The development validation build used only xerox_mfp to isolate
and test the SCX-4100 integration.

The final PrintScan Server build must retain the standard upstream
SANE backend collection rather than restricting the build to
xerox_mfp.

## USB interface coordination

The SCX-4100 exposes a bidirectional Printer Class USB interface.

On the validated Linux system, usblp must be temporarily detached
during scanner access. PrintScan Server must manage this through
a dedicated privileged USB broker, with guaranteed restoration
of the kernel driver.

Do not permanently disable usblp.

## Validation

Successfully tested on:
- Ubuntu 25.04
- x86_64
- SANE 1.3.1
- libusb-1.0
- Samsung SCX-4100

Verified:
- USB discovery with the custom SANE build
- Device option enumeration
- Actual image scanning
- usblp restoration after scanner access

This patch is a targeted compatibility extension, not a claim
that every SANE-supported device has been hardware-tested.
