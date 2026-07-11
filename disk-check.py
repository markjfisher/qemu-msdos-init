from pathlib import Path

mbr = Path("/dev/sdb").read_bytes()[:512]
print("MBR signature:", mbr[510:512].hex())

for i in range(4):
    e = mbr[446+i*16:446+(i+1)*16]
    boot = e[0]
    ptype = e[4]
    start = int.from_bytes(e[8:12], "little")
    size = int.from_bytes(e[12:16], "little")
    end = start + size - 1 if size else 0
    print(
        i + 1,
        f"boot=0x{boot:02x}",
        f"type=0x{ptype:02x}",
        f"start_chs={e[1:4].hex()}",
        f"end_chs={e[5:8].hex()}",
        f"start_lba={start}",
        f"sectors={size}",
        f"end_lba={end}",
    )