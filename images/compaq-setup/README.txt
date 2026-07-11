Compaq Deskpro setup and diagnostics floppy images.

Source SoftPaq:
https://ftp.hp.com/pub/softpaq/sp15501-16000/sp15674.exe

SP15674 title:
Computer Setup/VP and PC Diagnostics

Applies to:
Deskpro 4000 Series, Deskpro 6000 Series, Deskpro 2000 Series models with an
MMX processor, Deskpro EP Series, Deskpro SB Series, and Deskpro EN Series.

Images:
diagnostics-10.28-rev-a.img
  Label: DIAGS
  Use first when creating or updating the diagnostics partition.

setup-vp-1.76-rev-b-disk1.img
  Label: CPQCS_VP1
  Boot this to run Computer Setup/VP directly from diskette.

setup-vp-1.76-rev-b-disk2.img
  Label: CPQCS_VP2
  Insert when prompted by Setup/VP.

deskpro-f10-partition.img
  Label: DIAGS
  Captured from the Compaq-created type 12h diagnostics partition.
  Partition geometry observed on CF: start sector 63, size 16065 sectors,
  MBR entry 3.

Notes:
- For Deskpro 2000 MMX/4000/6000, the diagnostics disk can create the hidden
  Compaq diagnostics partition on a new unpartitioned hard drive. After that,
  F10 should appear during boot.
- HP's notes say Deskpro EP/SB/EN systems must run Setup/VP and Diagnostics
  from diskette instead of relying on the diagnostics partition.
- Creating the diagnostics partition normally requires an unpartitioned disk.
  Do not run that step on a CF image you want to preserve unless you have a
  backup.
- The captured F10 partition contains the diagnostics files plus Computer
  Setup/VP under US\WINDOWS\CPQWIN.

Checksums:
8d692d37b5d1cca0b872653286f73fe7c54d92fe76458726249df30b8a1b25ba  deskpro-f10-partition.img
340255fd0ac35f2da7dd652b07e346336aea6b4f423efeabe2a2ec6459a4dfe3  diagnostics-10.28-rev-a.img
afd05a247923dccef8fa6d6e048329cc61741e1b6235ebfb3e84839af330ea6b  setup-vp-1.76-rev-b-disk1.img
fcbce910ddbc4d1941fb23d93f2c23a640ebd607ec83634252a0bb5aa1d14ca0  setup-vp-1.76-rev-b-disk2.img
