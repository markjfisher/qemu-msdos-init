# qemu-msdos-init

Create a bootable MS-DOS 6.22 raw disk image for a period-correct Pentium MMX
machine and for QEMU. The default image is a non-sparse 2047 MiB file, but real
"2 GB" CF cards vary. Measure the target card with `lsblk -b` and pass the
exact byte size when the card is smaller than the default.

The target hardware is a Compaq Deskpro/ProDesk-era Pentium MMX 166 MHz machine
with a CF-to-IDE adapter and a 2 GB SanDisk Extreme III card.

## Host Requirements

Install these host tools:

- `qemu-system-i386` and `qemu-img`
- `mtools`
- `fdisk`/`sfdisk`
- `unzip`
- `7z` or `7za`
- `socat` for the QEMU monitor helper scripts

Check the local setup:

```sh
scripts/check
```

## Local Disk Files

The `disks/` directory is gitignored. Put these files there:

- `Disk 1 - Setup - 1.44mb.img`
- `Disk 2 - 1.44mb.img`
- `Disk 3 - 1.45mb.img`
- `cdrom.img`
- `mTCP_2025-01-10.zip`
- `usbaspi-v2.20.zip`
- `DI1000DD.SYS`
- `PKZip2.04g.7z`

Optional packet drivers for the real Compaq NIC can go under `disks/nic/`.

## Build Workflow

For a mostly unattended rebuild from blank media, run:

```sh
scripts/automate-install --force
```

This creates `build/msdos622-cf-2047m-auto.img`, drives the MS-DOS installer
through QEMU monitor key events, swaps disks, runs `FDISK /MBR`, injects the
post-install tools, adds the QEMU NE2000 packet driver when
`disks/nic/NE2000.COM` is present, and performs host-side validation. It is
deterministic for the disk images named in `disks/`, but it still uses timed
waits around the MS-DOS installer screens because MS-DOS Setup does not expose a
clean automation API. If a host is slow, rerun with a larger delay multiplier:

```sh
scripts/automate-install --force --timings-scale 1.5
```

For the currently measured Multi-Card CF device, `lsblk -b` reported
`2048901120` bytes. Build an image that fits it exactly with:

```sh
scripts/automate-install --force \
  --size-bytes 2048901120 \
  -o build/msdos622-cf-1954m-auto.img
```

To reinject tools and boot-verify an existing installed image without rerunning
MS-DOS Setup:

```sh
scripts/automate-install --skip-create --skip-setup -o build/msdos622-cf-2047m-auto.img
```

For a real-hardware test image, avoid the USB boot pause and do not autoload the
QEMU NE2000 packet driver:

```sh
scripts/automate-install --skip-create --skip-setup \
  -o build/msdos622-cf-1954m-hwtest.img \
  --usb-options /V \
  --packet-driver ''
```

The manual workflow remains below for debugging or rebuilding step-by-step.

Create the raw hard disk image:

```sh
scripts/create-image
```

This writes `build/msdos622-cf-2047m.img`, creates an MBR partition table, and
marks the first FAT16 partition bootable. The file is fully allocated, not
sparse.

To create a blank image for the measured 2,048,901,120-byte CF card:

```sh
scripts/create-image --force \
  --size-bytes 2048901120 \
  -o build/msdos622-cf-1954m.img
```

Install MS-DOS 6.22 in QEMU:

```sh
scripts/install-msdos --display curses
```

When Setup asks for another disk, use a second terminal:

```sh
scripts/floppy 2
scripts/floppy 3
```

After MS-DOS boots from `C:`, inject the post-install files from the host:

```sh
scripts/inject-tools
```

If the installer completes but QEMU hangs at `Booting from Hard Disk...`, boot
Setup Disk 1 again, press `F3` twice to exit to `A:\>`, run:

```dos
FDISK /MBR
```

Then remove the floppy with `scripts/floppy eject` and reboot. This writes the
MS-DOS MBR bootstrap code while preserving the partition table.

This copies:

- USB storage support to `C:\USB`
- mTCP to `C:\MTCP`
- PKZIP 2.04g to `C:\PKZIP`
- the CD-ROM driver from `cdrom.img` to `C:\DOS`
- optional packet drivers from `disks/nic` to `C:\PKTDRV`

It also updates `CONFIG.SYS` and `AUTOEXEC.BAT` idempotently.

Archive the current image before experimenting:

```sh
scripts/stamp-image post-install-usb-mtcp-pkzip
```

This writes a compressed archive and checksum under
`build/stamps/post-install-usb-mtcp-pkzip/`. Restore it with:

```sh
scripts/restore-image post-install-usb-mtcp-pkzip --force
```

Boot the finished image:

```sh
scripts/run-qemu --display curses
```

## Protected Final Image

The current known-good final image is:

```text
images/final/msdos622-cf-2047m-final.img
```

It is a plain raw image copy of `build/msdos622-cf-2047m.img`, kept outside
`build/` so normal rebuilds and experiments do not overwrite it. Verify it with:

```sh
cd images/final
sha256sum -c SHA256SUMS
```

Use `images/final/msdos622-cf-2047m-final.img` for writing to CF, or copy it
back to `build/msdos622-cf-2047m.img` before experimenting.

There is also a compressed fallback stamp:

```text
build/stamps/post-install-usb-mtcp-pkzip/
```

That stamp can restore the working image with:

```sh
scripts/restore-image post-install-usb-mtcp-pkzip --force
```

The full process is not completely one-command repeatable yet. The scripted
parts are image creation, QEMU-driven MS-DOS setup, post-install file injection,
USB test-stick creation, QEMU launch, screen capture, stamping, and restore. The
remaining fragile part is that `scripts/automate-install` uses conservative
timed waits for the installer prompts rather than reading Setup state directly.
The manual steps are documented above and were used to create the protected
final image.

## USB Support

The DOS USB stack uses `USBASPI.SYS` plus `DI1000DD.SYS`, matching the common
DOS USB mass-storage method described at:

<https://www.dosdays.co.uk/topics/usb_support.php>

The generated `CONFIG.SYS` entries are:

```dos
DEVICE=C:\USB\USBASPI.SYS /W /V
DEVICE=C:\USB\DI1000DD.SYS
LASTDRIVE=Z
```

`/W` makes USBASPI wait for a device before scanning. `/V` prints the controller
and device details. If QEMU is booted without `--usb-disk`, USBASPI/DI1000DD
will report no controller or installable device; that is expected.

On real hardware, use `--usb-options /V` to remove `/W` and avoid the boot-time
Enter prompt while testing USB detection.

Create a DOS-compatible FAT16 USB-stick image:

```sh
scripts/create-usb
```

QEMU can test USB storage with that image:

```sh
scripts/run-qemu --display curses --usb-disk build/usb-stick-128m.img
```

At the USBASPI prompt, press Enter. The test image should be assigned a drive
letter, usually `E:`:

```dos
E:
DIR
TYPE README.TXT
```

## Networking

QEMU emulates an NE2000 ISA card at I/O `0x300`, IRQ `3`, with mTCP configured
for packet interrupt `0x60`.

mTCP does not include a hardware packet driver. For QEMU, `disks/nic/NE2000.COM`
is copied to `C:\PKTDRV` and loaded with:

```dos
C:\PKTDRV\NE2000.COM 0x60 3 0x300
```

The QEMU launcher currently uses user-mode NAT networking. Inside DOS, DHCP
therefore assigns a `10.0.2.x` address, usually:

- guest: `10.0.2.15`
- host gateway from the guest: `10.0.2.2`
- DNS helper: `10.0.2.3`

That is expected. Use TAP/bridge networking instead if the DOS guest needs to
appear directly on the physical LAN as `192.168.1.x`.

Run the mTCP FTP smoke test:

```sh
scripts/test-mtcp -i build/msdos622-cf-2047m-auto.img
```

This starts a tiny local passive FTP server, boots QEMU, runs DHCP in DOS, runs
mTCP `FTP`, retrieves `PROOF.TXT`, and verifies `C:\MTCP\FTPGOT.TXT` from the
disk image after QEMU exits.

For the physical Compaq, use the packet driver matching the installed NIC. Put
the driver in `disks/nic/` and pass the correct `--packet-driver` line for that
driver. After boot, run:

```dos
C:
CD \MTCP
DHCP
PING 8.8.8.8
```

## Writing to CF

Double-check the target block device before running `dd`.

```sh
sudo dd if=images/final/msdos622-cf-2047m-final.img of=/dev/sdX bs=4M conv=fsync status=progress
sync
```

Use the whole CF device, not a partition such as `/dev/sdX1`.

## QEMU Visibility

`scripts/run-qemu` creates a monitor socket at `build/qemu-monitor.sock`.

Capture the current VGA screen:

```sh
scripts/screendump build/screen.ppm
```

Swap floppies while the installer is running:

```sh
scripts/floppy 2
```
