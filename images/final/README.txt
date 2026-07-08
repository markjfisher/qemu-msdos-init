Final protected raw image copy.

Current CF target: 2048901120 bytes, matching the measured Multi-Card device.
Source: build/msdos622-cf-1954m-auto.img, created from scratch with scripts/automate-install --size-bytes 2048901120.
Image: msdos622-cf-2048901120b-final.img
Status: Boots MS-DOS 6.22 in QEMU, includes USBASPI/DI1000DD, PKZIP, mTCP, OAKCDROM/MSCDEX, and NE2000.COM packet driver loaded at INT 0x60 for QEMU networking.
USB test: build/usb-stick-128m.img was detected by USBASPI/DI1000DD as E: and README.TXT was readable.
mTCP test: DHCP succeeded on QEMU user NAT, and mTCP FTP retrieved PROOF.TXT to C:\MTCP\FTPGOT.TXT.

Use this copy as the master fallback for the measured CF card. Experiment on build/msdos622-cf-1954m-auto.img or on a restored copy.
Verify with: sha256sum -c SHA256SUMS

Real-hardware test image:
msdos622-cf-2048901120b-hwtest.img

This is the same exact-size image adjusted for the Compaq boot test:
- CONFIG.SYS loads C:\USB\USBASPI.SYS /V, without /W, so boot does not pause for Enter.
- AUTOEXEC.BAT does not load NE2000.COM. The NE2000 line is only valid for QEMU unless the real NIC is NE2000-compatible at IRQ 3, I/O 0x300.
- Add the real Compaq NIC packet driver under disks/nic/ and reinject with --packet-driver once the NIC model, IRQ, and I/O base are known.
- C:\COMPAQ\SP15674 contains the HP Compaq Computer Setup/VP and PC Diagnostics SoftPaq files.

Prior larger final image retained for reference:
msdos622-cf-2047m-final.img
