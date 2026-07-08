#!/usr/bin/env python3
"""Build and maintain the MS-DOS hard disk image."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISKS = ROOT / "disks"
BUILD = ROOT / "build"
DEFAULT_IMAGE = BUILD / "msdos622-cf-2047m.img"
DEFAULT_USB_IMAGE = BUILD / "usb-stick-128m.img"
DEFAULT_SIZE_MIB = 2047
DEFAULT_SIZE_BYTES: int | None = None
DEFAULT_USB_SIZE_MIB = 128
SECTOR_SIZE = 512
REQUIRED_TOOLS = (
    "fdisk",
    "mcopy",
    "mmd",
    "mdir",
    "qemu-img",
    "qemu-system-i386",
    "sfdisk",
    "socat",
    "unzip",
    "7z",
)


def run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        check=True,
        text=True,
        capture_output=True,
    )


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def require_tools(tools: tuple[str, ...] = REQUIRED_TOOLS) -> None:
    missing = [tool for tool in tools if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            "Missing required tool(s): "
            + ", ".join(missing)
            + ". Install qemu-utils, qemu-system-x86, mtools, dosfstools, "
            "util-linux, unzip, and p7zip."
        )


def create_non_sparse_bytes(path: Path, total: int) -> None:
    if total <= 0:
        raise RuntimeError("Image size must be positive")
    if total % SECTOR_SIZE != 0:
        raise RuntimeError(f"Image size must be a multiple of {SECTOR_SIZE} bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    chunk = b"\0" * (1024 * 1024)
    full_chunks, remainder = divmod(total, len(chunk))
    with path.open("wb") as handle:
        for _ in range(full_chunks):
            handle.write(chunk)
        if remainder:
            handle.write(b"\0" * remainder)
        handle.flush()
        os.fsync(handle.fileno())
    actual = path.stat().st_blocks * 512
    if actual < total:
        raise RuntimeError(f"{path} is sparse: allocated {actual} bytes, expected {total}")


def create_non_sparse(path: Path, size_mib: int) -> None:
    create_non_sparse_bytes(path, size_mib * 1024 * 1024)


def create_partition_table(path: Path) -> None:
    # Leave a conventional 1 MiB gap. Type 06 is FAT16 over 32 MiB.
    script = "label: dos\nunit: sectors\n\nstart=2048, type=06, bootable\n"
    run(["sfdisk", str(path)], input_text=script)


def create_fat16_image(path: Path, size_mib: int, label: str) -> None:
    create_non_sparse(path, size_mib)
    create_partition_table(path)
    run(["mformat", "-i", image_spec(path), "-v", label[:11], "::"])


def partition_start_sector(raw_image: Path) -> int:
    result = run(["fdisk", "-l", str(raw_image)])
    raw = str(raw_image)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        if parts[0] == f"{raw}1" and parts[1] == "*" and parts[2].isdigit():
            return int(parts[2])
        if parts[0] == f"{raw}1" and parts[1].isdigit():
            return int(parts[1])
        if parts[0].endswith("1") and parts[1] == "*" and parts[2].isdigit():
            return int(parts[2])
        if parts[0].endswith("1") and parts[1].isdigit():
            return int(parts[1])
    raise RuntimeError(f"Could not determine first partition start sector in {raw_image}")


def image_spec(raw_image: Path) -> str:
    return f"{raw_image}@@{partition_start_sector(raw_image) * SECTOR_SIZE}"


def dos_path(*parts: str) -> str:
    return "::" + "/".join(parts)


def mmd(spec: str, path: str) -> None:
    exists = subprocess.run(["mdir", "-i", spec, path], text=True, capture_output=True, timeout=30)
    if exists.returncode == 0:
        return
    result = subprocess.run(["mmd", "-i", spec, path], text=True, capture_output=True, timeout=30)
    if result.returncode == 0:
        return
    exists = subprocess.run(["mdir", "-i", spec, path], text=True, capture_output=True, timeout=30)
    if exists.returncode == 0:
        return
    raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def mcopy_file(spec: str, src: Path, dest: str) -> None:
    run(["mcopy", "-o", "-i", spec, str(src), dest])


def mcopy_tree(spec: str, src_dir: Path, dest: str) -> None:
    if not src_dir.is_dir():
        raise FileNotFoundError(src_dir)
    for child in sorted(src_dir.iterdir()):
        run(["mcopy", "-o", "-s", "-i", spec, str(child), dest])


def read_dos_text(spec: str, name: str) -> str:
    with tempfile.TemporaryDirectory(prefix="qemu-msdos-read.") as tmpdir:
        dest = Path(tmpdir) / name
        result = subprocess.run(
            ["mcopy", "-i", spec, f"::{name}", str(dest)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return ""
        return dest.read_text(encoding="ascii", errors="ignore")


def write_dos_text(spec: str, name: str, contents: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        newline="",
        prefix="qemu-msdos-text.",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        handle.write(contents.replace("\n", "\r\n"))
    try:
        mcopy_file(spec, tmp, f"::{name}")
    finally:
        tmp.unlink(missing_ok=True)


def normalize_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def update_lines(existing: str, managed: list[str], prefixes: list[str]) -> str:
    kept: list[str] = []
    upper_prefixes = [prefix.upper() for prefix in prefixes]
    for line in normalize_lines(existing):
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if any(upper.startswith(prefix) for prefix in upper_prefixes):
            continue
        if upper in (item.upper() for item in managed):
            continue
        kept.append(line)
    kept.extend(managed)
    return "\n".join(kept) + "\n"


def extract_zip_member(zip_path: Path, member_pattern: str, dest: Path, output_name: str) -> Path:
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    dest.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(member_pattern, re.IGNORECASE)
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if pattern.search(name) and not name.endswith("/"):
                output = dest / output_name
                output.write_bytes(archive.read(name))
                return output
    raise RuntimeError(f"{zip_path}: no member matching {member_pattern}")


def extract_zip_all(zip_path: Path, dest: Path) -> None:
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)


def extract_7z(archive: Path, dest: Path) -> None:
    if not archive.is_file():
        raise FileNotFoundError(archive)
    dest.mkdir(parents=True, exist_ok=True)
    run(["7z", "x", "-y", f"-o{dest}", str(archive)])


def stage_files(args: argparse.Namespace) -> Path:
    stage = BUILD / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "USB").mkdir(parents=True)
    (stage / "MTCP").mkdir()
    (stage / "PKZIP").mkdir()
    (stage / "PKTDRV").mkdir()
    (stage / "DOS").mkdir()

    extract_zip_member(DISKS / "usbaspi-v2.20.zip", r"(^|/)USBASPI\.SYS$", stage / "USB", "USBASPI.SYS")
    shutil.copy2(DISKS / "DI1000DD.SYS", stage / "USB" / "DI1000DD.SYS")

    extract_zip_all(DISKS / "mTCP_2025-01-10.zip", stage / "MTCP")
    (stage / "MTCP" / "MTCP.CFG").write_text(
        "PACKETINT 0x60\n"
        "HOSTNAME MSDOS622\n"
        "# Run DHCP.EXE after the packet driver is loaded to fill in IP settings.\n",
        encoding="ascii",
    )

    extract_7z(DISKS / "PKZip2.04g.7z", stage / "_pkzip")
    pkzip_img = stage / "_pkzip" / "DISK1.IMG"
    if pkzip_img.is_file():
        run(["mcopy", "-s", "-i", str(pkzip_img), "::", str(stage / "PKZIP")])

    cdrom_img = DISKS / "cdrom.img"
    if cdrom_img.is_file():
        run(["mcopy", "-i", str(cdrom_img), "::OAKCDROM.SYS", str(stage / "DOS" / "OAKCDROM.SYS")])

    nic_dir = Path(args.nic_dir)
    if nic_dir.is_dir():
        for child in sorted(nic_dir.iterdir()):
            if child.is_file():
                shutil.copy2(child, stage / "PKTDRV" / child.name.upper())

    return stage


def inject(args: argparse.Namespace) -> None:
    image = Path(args.image).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    spec = image_spec(image)
    stage = stage_files(args)

    for name in ("USB", "MTCP", "PKZIP", "PKTDRV", "DOS"):
        mmd(spec, dos_path(name))
    mcopy_tree(spec, stage / "USB", dos_path("USB"))
    mcopy_tree(spec, stage / "MTCP", dos_path("MTCP"))
    mcopy_tree(spec, stage / "PKZIP", dos_path("PKZIP"))
    if any((stage / "PKTDRV").iterdir()):
        mcopy_tree(spec, stage / "PKTDRV", dos_path("PKTDRV"))
    if (stage / "DOS" / "OAKCDROM.SYS").is_file():
        mcopy_file(spec, stage / "DOS" / "OAKCDROM.SYS", dos_path("DOS", "OAKCDROM.SYS"))

    usb_options = args.usb_options.strip()
    usbaspi_line = "DEVICE=C:\\USB\\USBASPI.SYS"
    if usb_options:
        usbaspi_line += f" {usb_options}"

    config_lines = [
        "DEVICE=C:\\DOS\\HIMEM.SYS",
        "DOS=HIGH",
        "FILES=40",
        "BUFFERS=30",
        "LASTDRIVE=Z",
        usbaspi_line,
        "DEVICE=C:\\USB\\DI1000DD.SYS",
    ]
    if (stage / "DOS" / "OAKCDROM.SYS").is_file():
        config_lines.append("DEVICE=C:\\DOS\\OAKCDROM.SYS /D:MSCD001")

    autoexec_lines = [
        "PATH C:\\DOS;C:\\PKZIP;C:\\MTCP",
        "SET TEMP=C:\\DOS",
        "SET MTCPCFG=C:\\MTCP\\MTCP.CFG",
    ]
    packet_driver = args.packet_driver.strip()
    if packet_driver:
        autoexec_lines.append(packet_driver)
    if (stage / "DOS" / "OAKCDROM.SYS").is_file():
        autoexec_lines.append("LH C:\\DOS\\MSCDEX.EXE /D:MSCD001 /L:R")

    config_prefixes = [
        "DOS=",
        "FILES=",
        "BUFFERS=",
        "DEVICE=C:\\DOS\\HIMEM.SYS",
        "DEVICEHIGH=C:\\DOS\\HIMEM.SYS",
        "DEVICE=C:\\USB\\USBASPI.SYS",
        "DEVICEHIGH=C:\\USB\\USBASPI.SYS",
        "DEVICE=C:\\USB\\DI1000DD.SYS",
        "DEVICEHIGH=C:\\USB\\DI1000DD.SYS",
        "DEVICE=C:\\DOS\\OAKCDROM.SYS",
        "DEVICEHIGH=C:\\DOS\\OAKCDROM.SYS",
        "LASTDRIVE=",
    ]
    autoexec_prefixes = [
        "PATH ",
        "PATH=",
        "SET MTCPCFG=",
        "LH C:\\DOS\\MSCDEX.EXE",
        "C:\\PKTDRV\\",
    ]

    write_dos_text(spec, "CONFIG.SYS", update_lines(read_dos_text(spec, "CONFIG.SYS"), config_lines, config_prefixes))
    write_dos_text(spec, "AUTOEXEC.BAT", update_lines(read_dos_text(spec, "AUTOEXEC.BAT"), autoexec_lines, autoexec_prefixes))
    run(["mdir", "-i", spec, "::"])


def check_disk_files() -> list[str]:
    required = [
        "Disk 1 - Setup - 1.44mb.img",
        "Disk 2 - 1.44mb.img",
        "Disk 3 - 1.45mb.img",
        "cdrom.img",
        "mTCP_2025-01-10.zip",
        "usbaspi-v2.20.zip",
        "DI1000DD.SYS",
        "PKZip2.04g.7z",
    ]
    return [name for name in required if not (DISKS / name).is_file()]


def cmd_check(_: argparse.Namespace) -> None:
    require_tools()
    missing_files = check_disk_files()
    if missing_files:
        raise RuntimeError("Missing disk file(s): " + ", ".join(missing_files))
    print("All required host tools and disk files are present.")


def cmd_create(args: argparse.Namespace) -> None:
    require_tools(("sfdisk", "qemu-img"))
    output = Path(args.output).resolve()
    if output.exists() and not args.force:
        raise RuntimeError(f"{output} already exists; pass --force to replace it")
    if output.exists():
        output.unlink()
    size_bytes = args.size_bytes if args.size_bytes is not None else args.size_mib * 1024 * 1024
    print(f"Creating non-sparse {size_bytes} byte image at {rel(output)}")
    create_non_sparse_bytes(output, size_bytes)
    create_partition_table(output)
    run(["qemu-img", "info", str(output)])
    print("Image created. Boot QEMU from MS-DOS Disk 1 and install to C:.")
    print("After setup, run FDISK /MBR from Setup Disk 1 if C: does not boot.")


def cmd_create_usb(args: argparse.Namespace) -> None:
    require_tools(("sfdisk", "mformat", "mcopy"))
    output = Path(args.output).resolve()
    if output.exists() and not args.force:
        raise RuntimeError(f"{output} already exists; pass --force to replace it")
    if output.exists():
        output.unlink()
    print(f"Creating FAT16 USB-stick image at {rel(output)}")
    create_fat16_image(output, args.size_mib, args.label)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        newline="",
        prefix="qemu-msdos-usb.",
        delete=False,
    ) as handle:
        readme = Path(handle.name)
        handle.write(
            "QEMU MS-DOS USB test stick\r\n"
            "If USBASPI and DI1000DD load correctly this image should receive\r\n"
            "a DOS drive letter during boot.\r\n"
        )
    try:
        mcopy_file(image_spec(output), readme, "::README.TXT")
    finally:
        readme.unlink(missing_ok=True)
    print(f"Created {rel(output)}. Use: scripts/run-qemu --usb-disk {rel(output)}")


def default_stamp_label() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def cmd_stamp(args: argparse.Namespace) -> None:
    require_tools(("zstd", "sha256sum", "qemu-img"))
    image = Path(args.image).resolve()
    if not image.is_file():
        raise FileNotFoundError(image)
    label = args.label or default_stamp_label()
    if not re.match(r"^[A-Za-z0-9._-]+$", label):
        raise RuntimeError("Stamp label may only contain letters, digits, dot, underscore, and hyphen")
    out_dir = (BUILD / "stamps" / label).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)
    archive = out_dir / f"{image.name}.zst"
    manifest = out_dir / "manifest.txt"
    print(f"Archiving {rel(image)} to {rel(archive)}")
    info = run(["qemu-img", "info", str(image)]).stdout
    run(["zstd", "-T0", "-19", "--force", str(image), "-o", str(archive)])
    sha = run(["sha256sum", str(archive)]).stdout
    (out_dir / "SHA256SUMS").write_text(sha, encoding="ascii")
    manifest.write_text(
        f"label={label}\n"
        f"created={dt.datetime.now(dt.timezone.utc).isoformat()}\n"
        f"source={image}\n"
        f"archive={archive.name}\n\n"
        f"{info}",
        encoding="ascii",
    )
    print(f"Wrote {rel(manifest)}")
    print(f"Wrote {rel(out_dir / 'SHA256SUMS')}")


def cmd_restore(args: argparse.Namespace) -> None:
    require_tools(("zstd", "sha256sum"))
    stamp_dir = (BUILD / "stamps" / args.label).resolve()
    archive = stamp_dir / f"{Path(args.output).name}.zst"
    if not archive.is_file():
        matches = sorted(stamp_dir.glob("*.img.zst"))
        if len(matches) != 1:
            raise RuntimeError(f"Could not choose archive in {stamp_dir}")
        archive = matches[0]
    checksum = stamp_dir / "SHA256SUMS"
    if checksum.is_file():
        run(["sha256sum", "-c", str(checksum)], input_text=None)
    output = Path(args.output).resolve()
    if output.exists() and not args.force:
        raise RuntimeError(f"{output} already exists; pass --force to replace it")
    print(f"Restoring {rel(archive)} to {rel(output)}")
    run(["zstd", "-d", "--force", str(archive), "-o", str(output)])


def cmd_info(args: argparse.Namespace) -> None:
    image = Path(args.image).resolve()
    print(run(["fdisk", "-l", str(image)]).stdout)
    print(f"mtools image spec: {image_spec(image)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True)

    check = sub.add_parser("check", help="check host tools and expected disk files")
    check.set_defaults(func=cmd_check)

    create = sub.add_parser("create", help="create a non-sparse CF-sized raw disk image")
    create.add_argument("-o", "--output", default=str(DEFAULT_IMAGE))
    create.add_argument("--size-mib", type=int, default=DEFAULT_SIZE_MIB)
    create.add_argument(
        "--size-bytes",
        type=int,
        default=DEFAULT_SIZE_BYTES,
        help="exact raw image size in bytes; overrides --size-mib",
    )
    create.add_argument("-f", "--force", action="store_true")
    create.set_defaults(func=cmd_create)

    usb = sub.add_parser("create-usb", help="create a small FAT16 USB-stick test image")
    usb.add_argument("-o", "--output", default=str(DEFAULT_USB_IMAGE))
    usb.add_argument("--size-mib", type=int, default=DEFAULT_USB_SIZE_MIB)
    usb.add_argument("--label", default="USBTEST")
    usb.add_argument("-f", "--force", action="store_true")
    usb.set_defaults(func=cmd_create_usb)

    inject_parser = sub.add_parser("inject", help="inject USB, PKZIP, mTCP, CD-ROM, and config files")
    inject_parser.add_argument("-i", "--image", default=str(DEFAULT_IMAGE))
    inject_parser.add_argument("--nic-dir", default=str(DISKS / "nic"))
    inject_parser.add_argument(
        "--packet-driver",
        default="",
        help=r"Optional AUTOEXEC line, e.g. C:\PKTDRV\NE2000.COM 0x60 3 0x300",
    )
    inject_parser.add_argument(
        "--usb-options",
        default="/W /V",
        help=r"Options for USBASPI.SYS; use /V on real hardware to avoid the boot pause",
    )
    inject_parser.set_defaults(func=inject)

    stamp = sub.add_parser("stamp", help="archive the current raw image as a restorable zstd stamp")
    stamp.add_argument("-i", "--image", default=str(DEFAULT_IMAGE))
    stamp.add_argument("label", nargs="?")
    stamp.set_defaults(func=cmd_stamp)

    restore = sub.add_parser("restore", help="restore a stamped image archive")
    restore.add_argument("label")
    restore.add_argument("-o", "--output", default=str(DEFAULT_IMAGE))
    restore.add_argument("-f", "--force", action="store_true")
    restore.set_defaults(func=cmd_restore)

    info = sub.add_parser("info", help="show partition information for an image")
    info.add_argument("-i", "--image", default=str(DEFAULT_IMAGE))
    info.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            sys.stderr.write(
                "Command failed: "
                + " ".join(exc.cmd if isinstance(exc.cmd, list) else [str(exc.cmd)])
                + "\n"
            )
            sys.stderr.write(exc.stderr or exc.stdout or str(exc))
        else:
            sys.stderr.write(f"{exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
