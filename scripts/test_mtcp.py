#!/usr/bin/env python3
"""Run an mTCP FTP smoke test against QEMU user-mode networking."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import automate_install


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = ROOT / "build" / "msdos622-cf-2047m-auto.img"
FTP_ROOT = ROOT / "build" / "mtcp-proof-server"
PROOF_TEXT = "mTCP FTP proof from qemu-msdos-init\r\n"


def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True, **kwargs)


def write_dos_file(image: Path, dos_dest: str, contents: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="ascii",
        newline="",
        prefix="qemu-msdos-mtcp.",
        delete=False,
    ) as handle:
        tmp = Path(handle.name)
        handle.write(contents)
    try:
        run(["mcopy", "-o", "-i", f"{image}@@1048576", str(tmp), dos_dest])
    finally:
        tmp.unlink(missing_ok=True)


def prepare_image(image: Path) -> None:
    ne2000 = ROOT / "disks" / "nic" / "NE2000.COM"
    if not ne2000.is_file():
        raise RuntimeError(
            "Missing disks/nic/NE2000.COM. Download a DOS NE2000 packet driver first."
        )
    subprocess.run(
        [
            "scripts/inject-tools",
            "-i",
            str(image),
            "--packet-driver",
            r"C:\PKTDRV\NE2000.COM 0x60 3 0x300",
        ],
        cwd=ROOT,
        check=True,
    )
    write_dos_file(
        image,
        "::MTCP/FTPSCR.TXT",
        "anonymous\r\n"
        "test@example.com\r\n"
        "xfermode passive\r\n"
        "binary\r\n"
        "get PROOF.TXT FTPGOT.TXT\r\n"
        "quit\r\n",
    )
    write_dos_file(
        image,
        "::N.BAT",
        "CD \\MTCP\r\n"
        "DHCP\r\n"
        "FTP -port 2121 10.0.2.2 < FTPSCR.TXT\r\n",
    )


def fetch_result(image: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="qemu-msdos-mtcp-result.") as tmpdir:
        dest = Path(tmpdir) / "FTPGOT.TXT"
        run(["mcopy", "-o", "-i", f"{image}@@1048576", "::MTCP/FTPGOT.TXT", str(dest)])
        return dest.read_text(encoding="ascii", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--image", default=str(DEFAULT_IMAGE))
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image = Path(args.image).resolve()
    try:
        FTP_ROOT.mkdir(parents=True, exist_ok=True)
        (FTP_ROOT / "PROOF.TXT").write_text(PROOF_TEXT, encoding="ascii")
        prepare_image(image)

        ftp = subprocess.Popen(
            [
                sys.executable,
                "scripts/mini_ftp_server.py",
                "--root",
                str(FTP_ROOT),
                "--port",
                "2121",
                "--passive-port",
                "2020",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        qemu = automate_install.start_qemu(image, floppy=None, boot="c")
        try:
            time.sleep(6)
            automate_install.sendkey("ret")
            time.sleep(10)
            automate_install.type_keys(["n", "ret"])
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline and ftp.poll() is None:
                time.sleep(1)
            if ftp.poll() is None:
                raise RuntimeError("FTP server did not receive a complete session")
        finally:
            automate_install.quit_qemu(qemu)
            if ftp.poll() is None:
                ftp.terminate()
                try:
                    ftp.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    ftp.kill()
            ftp_log = ftp.stdout.read() if ftp.stdout is not None else ""

        result = fetch_result(image)
        if result.replace("\r\n", "\n") != PROOF_TEXT.replace("\r\n", "\n"):
            raise RuntimeError(f"Unexpected FTP result: {result!r}")
        print(ftp_log, end="")
        print("mTCP FTP proof OK: C:\\MTCP\\FTPGOT.TXT matches host PROOF.TXT")
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"test-mtcp failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
