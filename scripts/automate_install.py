#!/usr/bin/env python3
"""Automate the interactive MS-DOS 6.22 QEMU install."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISKS = ROOT / "disks"
BUILD = ROOT / "build"
DEFAULT_IMAGE = BUILD / "msdos622-cf-2047m-auto.img"
DEFAULT_SIZE_MIB = 2047
DEFAULT_LAYOUT = "plain"
DEFAULT_DIAGNOSTICS_SIZE_MIB = 8
MONITOR = BUILD / "qemu-auto-monitor.sock"


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def require_tools() -> None:
    missing = [
        tool
        for tool in ("qemu-system-i386", "mcopy", "mdir", "qemu-img")
        if shutil.which(tool) is None
    ]
    if missing:
        raise RuntimeError("Missing required tool(s): " + ", ".join(missing))


def wait_for_monitor(path: Path, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    sock.connect(str(path))
                    sock.recv(4096)
                    return
            except OSError:
                pass
        time.sleep(0.1)
    raise RuntimeError(f"QEMU monitor did not become ready: {path}")


def monitor(cmd: str) -> str:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(str(MONITOR))
        greeting = sock.recv(4096)
        sock.sendall((cmd + "\n").encode("ascii"))
        time.sleep(0.15)
        chunks = [greeting]
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
            if b"(qemu)" in chunk:
                break
        return b"".join(chunks).decode("ascii", errors="ignore")


def sendkey(key: str, delay: float = 0.35) -> None:
    monitor(f"sendkey {key}")
    time.sleep(delay)


def type_keys(keys: list[str], delay: float = 0.08) -> None:
    for key in keys:
        sendkey(key, delay)


def change_floppy(path: Path) -> None:
    quoted = str(path).replace("\\", "\\\\").replace('"', '\\"')
    monitor(f'change floppy0 "{quoted}"')
    time.sleep(0.5)


def eject_floppy() -> None:
    monitor("eject floppy0")
    time.sleep(0.5)


def quit_qemu(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        monitor("quit")
    except OSError:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def start_qemu(image: Path, *, floppy: Path | None, boot: str) -> subprocess.Popen[bytes]:
    MONITOR.unlink(missing_ok=True)
    args = [
        "qemu-system-i386",
        "-M",
        "pc",
        "-cpu",
        "pentium",
        "-m",
        "64",
        "-rtc",
        "base=localtime",
        "-drive",
        f"file={image},format=raw,if=ide,index=0,media=disk",
        "-boot",
        boot,
        "-monitor",
        f"unix:{MONITOR},server,nowait",
        "-display",
        "none",
        "-netdev",
        "user,id=net0",
        "-device",
        "ne2k_isa,netdev=net0,iobase=0x300,irq=3",
    ]
    if floppy is not None:
        args.extend(["-drive", f"file={floppy},format=raw,if=floppy,index=0,media=disk"])
    proc = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    wait_for_monitor(MONITOR)
    return proc


def create_image(
    image: Path,
    force: bool,
    size_mib: int,
    size_bytes: int | None,
    layout: str,
    diagnostics_size_mib: int,
) -> None:
    args = ["scripts/create-image", "-o", str(image)]
    if size_bytes is not None:
        args.extend(["--size-bytes", str(size_bytes)])
    else:
        args.extend(["--size-mib", str(size_mib)])
    args.extend(["--layout", layout, "--diagnostics-size-mib", str(diagnostics_size_mib)])
    if force:
        args.append("--force")
    subprocess.run(args, cwd=ROOT, check=True)


def image_spec(image: Path, dos_partition: int | None) -> str:
    args = ["python3", "scripts/msdos_image.py", "spec", "-i", str(image)]
    if dos_partition is not None:
        args.extend(["--dos-partition", str(dos_partition)])
    return run(args, cwd=ROOT).stdout.strip()


def verify_installed(image: Path, dos_partition: int | None) -> None:
    spec = image_spec(image, dos_partition)
    run(["mdir", "-i", spec, "::COMMAND.COM"])
    run(["mdir", "-i", spec, "::DOS"])


def run_setup(image: Path, timings_scale: float, dos_partition: int | None) -> None:
    disk1 = DISKS / "Disk 1 - Setup - 1.44mb.img"
    disk2 = DISKS / "Disk 2 - 1.44mb.img"
    disk3 = DISKS / "Disk 3 - 1.45mb.img"
    proc = start_qemu(image, floppy=disk1, boot="a")
    try:
        time.sleep(3 * timings_scale)
        # Welcome.
        sendkey("ret")
        time.sleep(3 * timings_scale)
        # Format C:. This is the slowest pre-copy screen and may still be busy
        # while Setup writes the FAT and initial system files.
        sendkey("ret")
        time.sleep(15 * timings_scale)
        # Accept locale settings.
        sendkey("ret")
        time.sleep(3 * timings_scale)
        # Accept C:\DOS.
        sendkey("ret")
        time.sleep(60 * timings_scale)
        change_floppy(disk2)
        sendkey("ret")
        time.sleep(70 * timings_scale)
        change_floppy(disk3)
        sendkey("ret")
        time.sleep(80 * timings_scale)
        eject_floppy()
        sendkey("ret")
        time.sleep(4 * timings_scale)
    finally:
        quit_qemu(proc)
    verify_installed(image, dos_partition)


def run_mbr_repair(image: Path, timings_scale: float) -> None:
    disk1 = DISKS / "Disk 1 - Setup - 1.44mb.img"
    proc = start_qemu(image, floppy=disk1, boot="a")
    try:
        time.sleep(3 * timings_scale)
        sendkey("f3")
        time.sleep(1 * timings_scale)
        sendkey("f3")
        time.sleep(1 * timings_scale)
        type_keys(["f", "d", "i", "s", "k", "spc", "slash", "m", "b", "r", "ret"])
        time.sleep(5 * timings_scale)
    finally:
        quit_qemu(proc)


def inject_tools(image: Path, packet_driver: str | None, usb_options: str, dos_partition: int | None) -> None:
    args = ["scripts/inject-tools", "-i", str(image)]
    if dos_partition is not None:
        args.extend(["--dos-partition", str(dos_partition)])
    if packet_driver is None and (DISKS / "nic" / "NE2000.COM").is_file():
        args.extend(["--packet-driver", r"C:\PKTDRV\NE2000.COM 0x60 3 0x300"])
    elif packet_driver:
        args.extend(["--packet-driver", packet_driver])
    args.extend(["--usb-options", usb_options])
    subprocess.run(args, cwd=ROOT, check=True)


def boot_verify(image: Path, timings_scale: float, usb_options: str, dos_partition: int | None) -> None:
    proc = start_qemu(image, floppy=None, boot="c")
    try:
        time.sleep(6 * timings_scale)
        if "/W" in usb_options.upper().split():
            # CONFIG.SYS uses USBASPI /W, so boot waits for Enter before the USB
            # scan. Continue the boot without an attached USB device.
            sendkey("ret")
        time.sleep(8 * timings_scale)
        # A bootable DOS image should keep QEMU running. Host-side file checks
        # verify the installed files and injected config.
        if proc.poll() is not None:
            raise RuntimeError("QEMU exited during hard-disk boot verification")
    finally:
        quit_qemu(proc)
    spec = image_spec(image, dos_partition)
    run(["mdir", "-i", spec, "::USB"])
    run(["mdir", "-i", spec, "::MTCP"])
    run(["mdir", "-i", spec, "::PKZIP"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", default=str(DEFAULT_IMAGE))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--size-mib", type=int, default=DEFAULT_SIZE_MIB)
    parser.add_argument(
        "--size-bytes",
        type=int,
        default=None,
        help="exact raw image size in bytes; overrides --size-mib",
    )
    parser.add_argument(
        "--timings-scale",
        type=float,
        default=1.0,
        help="multiply sleeps for slower hosts",
    )
    parser.add_argument(
        "--layout",
        choices=("blank", "plain", "compaq-reserved", "compaq-diagnostics", "compaq-f10"),
        default=DEFAULT_LAYOUT,
        help="partition layout to pass to scripts/create-image",
    )
    parser.add_argument(
        "--diagnostics-size-mib",
        type=int,
        default=DEFAULT_DIAGNOSTICS_SIZE_MIB,
        help="leading diagnostics/reserved area size for Compaq layouts",
    )
    parser.add_argument(
        "--dos-partition",
        type=int,
        default=None,
        help="explicit DOS partition number; by default the active FAT16 partition is used",
    )
    parser.add_argument(
        "--packet-driver",
        default=None,
        help="AUTOEXEC packet-driver line; pass an empty string to disable autoload",
    )
    parser.add_argument(
        "--usb-options",
        default="/W /V",
        help=r"Options for USBASPI.SYS; use /V on real hardware to avoid the boot pause",
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="use an existing blank/precreated image",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="skip MS-DOS Setup and FDISK /MBR; still inject and boot-verify",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image = Path(args.output).resolve()
    try:
        require_tools()
        if not args.skip_create:
            create_image(
                image,
                args.force,
                args.size_mib,
                args.size_bytes,
                args.layout,
                args.diagnostics_size_mib,
            )
        if not args.skip_setup:
            print(f"Installing MS-DOS 6.22 into {image}", flush=True)
            run_setup(image, args.timings_scale, args.dos_partition)
            print("Writing MS-DOS MBR with FDISK /MBR", flush=True)
            run_mbr_repair(image, args.timings_scale)
        print("Injecting USB, PKZIP, mTCP, and CD-ROM support", flush=True)
        inject_tools(image, args.packet_driver, args.usb_options, args.dos_partition)
        print("Boot-verifying final image", flush=True)
        boot_verify(image, args.timings_scale, args.usb_options, args.dos_partition)
        print(f"Automated install complete: {image}", flush=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"automate-install failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
