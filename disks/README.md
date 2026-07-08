# Disk Files

This directory is intentionally gitignored except for documentation.

Expected local files:

- `Disk 1 - Setup - 1.44mb.img`
- `Disk 2 - 1.44mb.img`
- `Disk 3 - 1.45mb.img`
- `cdrom.img`
- `mTCP_2025-01-10.zip`
- `usbaspi-v2.20.zip`
- `DI1000DD.SYS`
- `PKZip2.04g.7z`

Optional NIC packet drivers can be placed in `disks/nic/`. The QEMU launcher
emulates an NE2000 ISA card at I/O `0x300`, IRQ `3`; mTCP expects the packet
driver to expose interrupt `0x60`.
