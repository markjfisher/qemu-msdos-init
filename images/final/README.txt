Final protected raw image copies.

Current CF target: 2048901120 bytes, matching the measured Multi-Card device.
Verify with: sha256sum -c SHA256SUMS

Compaq F10 final image:
msdos622-cf-2048901120b-compaq-f10.img

This is the preferred Compaq Deskpro CF image when F10 setup should work from
the hard disk.

Build outline:
- scripts/automate-install --size-bytes 2048901120 --layout compaq-f10 --usb-options /V --packet-driver ''
- python3 scripts/msdos_image.py copy-compaq-f10 -i build/msdos622-cf-1954m-compaq-f10.img --partition-image images/compaq-setup/deskpro-f10-partition.img

Layout:
- Partition 1: active FAT16 DOS, start sector 16128, byte offset 8257536, CHS 4/0/1.
- Partition 3: type 12h Compaq diagnostics, start sector 63, size 16065 sectors, CHS 0/1/1 to 1/0/63.
- The DOS partition CHS fields are patched for the Deskpro's 64-head, 63-sector geometry.
- C:\COMPAQ\SP15674 contains the HP Compaq Computer Setup/VP and PC Diagnostics SoftPaq files.
- The diagnostics partition volume label is DIAGS and contains both Diagnostics plus Computer Setup/VP files, including US\WINDOWS\CPQWIN.

Compaq F10 RTL8139/SMC1211TX NIC test image:
msdos622-cf-2048901120b-compaq-f10-rtl8139.img

This is copied from the preferred Compaq F10 image and reinjected with:
scripts/inject-tools -i images/final/msdos622-cf-2048901120b-compaq-f10-rtl8139.img --dos-partition 1 --packet-driver 'C:\PKTDRV\RTSPKT.COM 0x60' --usb-options /V --cdrom never

It copies the Realtek RTL8139-family packet driver to C:\PKTDRV\RTSPKT.COM
for the Accton/SMC1211TX PCI card and loads it at packet interrupt 0x60.
CD-ROM lines are intentionally omitted for testing without a CD-ROM attached.

Compaq F10 SMC PKTPWR NIC test image:
msdos622-cf-2048901120b-compaq-f10-pktpwr.img

This is copied from the preferred Compaq F10 image and reinjected with:
scripts/inject-tools -i images/final/msdos622-cf-2048901120b-compaq-f10-pktpwr.img --dos-partition 1 --packet-driver 'C:\PKTDRV\PKTPWR.COM 0x60' --usb-options /V --cdrom never

It copies the SMC PKTPWR packet driver from pktp1162.zip to
C:\PKTDRV\PKTPWR.COM and loads it at packet interrupt 0x60. The driver
documentation says it supports SMC 8432, 8432 Enhanced, and 9332 Ethernet
adapters. This is a plausible but not exact test for the Accton/SMC1211TX
PCI card.

Compaq F10 SMC1211TX SMCPKT NIC test image:
msdos622-cf-2048901120b-compaq-f10-smcpkt.img

This is copied from the preferred Compaq F10 image and reinjected with:
scripts/inject-tools -i images/final/msdos622-cf-2048901120b-compaq-f10-smcpkt.img --dos-partition 1 --packet-driver 'C:\PKTDRV\SMCPKT.COM 0x60' --usb-options /V --cdrom never

It uses SMC1211TX_all.zip from DriverGuide driver id 146990. PKTDRV/PACKET.TXT
identifies this as the packet driver for SMC EZ Card 10/100 (SMC1211TX), and
its sample AUTOEXEC.BAT command is SMCPKT 0x60. The NDIS fallback driver
NDIS/DOS/SMC1211.DOS is also copied to C:\PKTDRV.

Compaq F10 SMC1211TX QoL image:
msdos622-cf-2048901120b-compaq-f10-smcpkt-qol.img

This is copied from the SMC1211TX SMCPKT image with these extra startup
changes:
- CONFIG.SYS sets COUNTRY=044,437,C:\DOS\COUNTRY.SYS.
- AUTOEXEC.BAT loads LH C:\DOS\KEYB.COM UK,,C:\DOS\KEYBOARD.SYS.
- AUTOEXEC.BAT loads LH C:\DOS\DOSKEY.COM /INSERT.
- PATH includes C:\TOOLS.

C:\TOOLS contains small mTCP wrappers:
- DHCP.BAT runs DHCP.EXE.
- PINGGW.BAT runs PING.EXE.
- FTPD.BAT starts FTPSRV.EXE from C:\MTCP.
- HTTPD.BAT starts HTTPSERV.EXE from C:\.
- GET.BAT runs HTGET.EXE.
- TIME.BAT runs SNTP.EXE.
