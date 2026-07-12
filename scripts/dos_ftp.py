#!/usr/bin/env python3
"""Host-side FTP helpers for the MS-DOS/mTCP machine."""

from __future__ import annotations

import argparse
import ftplib
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
DEFAULT_HOST = os.environ.get("DOS_FTP_HOST", "MSDOS622.home")
DEFAULT_USER = os.environ.get("DOS_FTP_USER", "ftp")
DEFAULT_PASS = os.environ.get("DOS_FTP_PASS", "user@example.com")
DEFAULT_INCOMING = os.environ.get("DOS_FTP_INCOMING", "/incoming")
DEFAULT_FUJINET_SYS = WORKSPACE / "repos" / "fujinet-msdos" / "sys" / "fujinet.sys"
DEFAULT_NIO_APPS_BIN = WORKSPACE / "repos" / "nio-apps" / "build" / "msdos" / "bin"


def normalise_remote(path: str) -> str:
    return path.replace("\\", "/")


def dos_crlf_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    text = data.decode("ascii")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return ("\r\n".join(text.rstrip("\n").split("\n")) + "\r\n").encode("ascii")


def connect(args: argparse.Namespace) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(args.host, args.port, timeout=args.timeout)
    ftp.login(args.user, args.password)
    ftp.set_pasv(not args.active)
    if args.cwd:
        ftp.cwd(normalise_remote(args.cwd))
    return ftp


def ensure_remote_dir(ftp: ftplib.FTP, remote_dir: str) -> None:
    remote_dir = normalise_remote(remote_dir).strip("/")
    if not remote_dir:
        return
    original = ftp.pwd()
    try:
        if original != "/":
            ftp.cwd("/")
        for part in remote_dir.split("/"):
            if not part:
                continue
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                ftp.mkd(part)
                ftp.cwd(part)
    finally:
        ftp.cwd(original)


def upload_bytes(ftp: ftplib.FTP, data: bytes, remote: str) -> None:
    from io import BytesIO

    remote = normalise_remote(remote)
    parent = remote.rsplit("/", 1)[0] if "/" in remote else ""
    ensure_remote_dir(ftp, parent)
    try:
        ftp.delete(remote)
    except ftplib.error_perm:
        pass
    with BytesIO(data) as handle:
        ftp.storbinary(f"STOR {remote}", handle)


def upload_file(ftp: ftplib.FTP, local: Path, remote: str, crlf: bool = False) -> None:
    if crlf:
        upload_bytes(ftp, dos_crlf_bytes(local), remote)
        return
    remote = normalise_remote(remote)
    parent = remote.rsplit("/", 1)[0] if "/" in remote else ""
    ensure_remote_dir(ftp, parent)
    try:
        ftp.delete(remote)
    except ftplib.error_perm:
        pass
    with local.open("rb") as handle:
        ftp.storbinary(f"STOR {remote}", handle)


def download_file(ftp: ftplib.FTP, remote: str, local: Path) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    with local.open("wb") as handle:
        ftp.retrbinary(f"RETR {normalise_remote(remote)}", handle.write)


def command_ls(args: argparse.Namespace) -> None:
    with connect(args) as ftp:
        ftp.dir(normalise_remote(args.remote))


def command_mkdir(args: argparse.Namespace) -> None:
    with connect(args) as ftp:
        ensure_remote_dir(ftp, args.remote)
        print(f"created/verified {normalise_remote(args.remote)}")


def command_put(args: argparse.Namespace) -> None:
    local = Path(args.local).resolve()
    remote = args.remote
    if remote is None:
        remote = f"{args.incoming.rstrip('/')}/{local.name}"
    with connect(args) as ftp:
        upload_file(ftp, local, remote, crlf=args.crlf)
    print(f"{local} -> {normalise_remote(remote)}")


def command_get(args: argparse.Namespace) -> None:
    remote = normalise_remote(args.remote)
    local = Path(args.local) if args.local else Path(remote).name
    with connect(args) as ftp:
        download_file(ftp, remote, Path(local))
    print(f"{remote} -> {local}")


def command_push_config(args: argparse.Namespace) -> None:
    autoexec = Path(args.autoexec).resolve()
    config = Path(args.config).resolve()
    with connect(args) as ftp:
        upload_file(ftp, autoexec, args.remote_autoexec, crlf=True)
        upload_file(ftp, config, args.remote_config, crlf=True)
    print(f"{autoexec} -> {normalise_remote(args.remote_autoexec)}")
    print(f"{config} -> {normalise_remote(args.remote_config)}")


def command_push_fujinet(args: argparse.Namespace) -> None:
    source = Path(args.source).resolve()
    with connect(args) as ftp:
        upload_file(ftp, source, args.remote, crlf=False)
    print(f"{source} -> {normalise_remote(args.remote)}")


def command_push_apps(args: argparse.Namespace) -> None:
    source_dir = Path(args.source_dir).resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"Apps directory not found: {source_dir}")

    files = sorted(path for path in source_dir.iterdir() if path.is_file())
    if not files:
        raise SystemExit(f"No files found in apps directory: {source_dir}")

    remote_dir = normalise_remote(args.remote_dir).rstrip("/")
    with connect(args) as ftp:
        ensure_remote_dir(ftp, remote_dir)
        for source in files:
            remote = f"{remote_dir}/{source.name.upper()}"
            upload_file(ftp, source, remote, crlf=False)
            print(f"{source} -> {remote}")

    print(f"Uploaded {len(files)} file(s) to {remote_dir}")


def add_connection_args(parser: argparse.ArgumentParser, *, defaults: bool = True) -> None:
    default = None if defaults else argparse.SUPPRESS
    parser.add_argument("--host", default=DEFAULT_HOST if defaults else default)
    parser.add_argument("--port", type=int, default=21 if defaults else default)
    parser.add_argument("--user", default=DEFAULT_USER if defaults else default)
    parser.add_argument("--password", default=DEFAULT_PASS if defaults else default)
    parser.add_argument("--timeout", type=float, default=15.0 if defaults else default)
    parser.add_argument("--active", action="store_true", default=False if defaults else default, help="use active FTP instead of passive FTP")
    parser.add_argument("--cwd", default="" if defaults else default, help="remote working directory after login")


def build_parser() -> argparse.ArgumentParser:
    command_connection = argparse.ArgumentParser(add_help=False)
    add_connection_args(command_connection, defaults=False)

    parser = argparse.ArgumentParser(description=__doc__)
    add_connection_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("ls", parents=[command_connection], help="list a remote directory")
    ls.add_argument("remote", nargs="?", default=".")
    ls.set_defaults(func=command_ls)

    mkdir = sub.add_parser("mkdir", parents=[command_connection], help="create a remote directory path")
    mkdir.add_argument("remote")
    mkdir.set_defaults(func=command_mkdir)

    put = sub.add_parser("put", parents=[command_connection], help="upload one file")
    put.add_argument("local")
    put.add_argument("remote", nargs="?")
    put.add_argument("--incoming", default=DEFAULT_INCOMING)
    put.add_argument("--crlf", action="store_true", help="convert ASCII text to DOS CRLF while uploading")
    put.set_defaults(func=command_put)

    get = sub.add_parser("get", parents=[command_connection], help="download one file")
    get.add_argument("remote")
    get.add_argument("local", nargs="?")
    get.set_defaults(func=command_get)

    cfg = sub.add_parser("push-config", parents=[command_connection], help="upload host/dos-root AUTOEXEC.BAT and CONFIG.SYS with CRLF endings")
    cfg.add_argument("--autoexec", default=str(ROOT / "host" / "dos-root" / "AUTOEXEC.BAT"))
    cfg.add_argument("--config", default=str(ROOT / "host" / "dos-root" / "CONFIG.SYS"))
    cfg.add_argument("--remote-autoexec", default="/AUTOEXEC.BAT")
    cfg.add_argument("--remote-config", default="/CONFIG.SYS")
    cfg.set_defaults(func=command_push_config)

    fn = sub.add_parser("push-fujinet", parents=[command_connection], help="upload fujinet-msdos/sys/fujinet.sys")
    fn.add_argument("--source", default=str(DEFAULT_FUJINET_SYS))
    fn.add_argument("--remote", default="/FUJINET/FUJINET.SYS")
    fn.set_defaults(func=command_push_fujinet)

    apps = sub.add_parser("push-apps", parents=[command_connection], help="upload nio-apps MS-DOS build output to C:\\FNAPPS")
    apps.add_argument("--source-dir", default=str(DEFAULT_NIO_APPS_BIN))
    apps.add_argument("--remote-dir", default="/FNAPPS")
    apps.set_defaults(func=command_push_apps)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
