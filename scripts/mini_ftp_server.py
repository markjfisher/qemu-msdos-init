#!/usr/bin/env python3
"""Tiny single-client passive FTP server for mTCP/QEMU smoke tests."""

from __future__ import annotations

import argparse
import socket
from pathlib import Path


def send_line(conn: socket.socket, line: str) -> None:
    conn.sendall((line + "\r\n").encode("ascii"))


def recv_line(conn: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = conn.recv(1)
        if not chunk:
            break
        data.extend(chunk)
    return data.decode("ascii", errors="ignore").strip()


def passive_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(1)
    return sock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--advertise-host", default="10.0.2.2")
    parser.add_argument("--port", type=int, default=2121)
    parser.add_argument("--passive-port", type=int, default=2020)
    parser.add_argument("--root", default="build/mtcp-proof-server")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    passive: socket.socket | None = None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(1)
        print(f"FTP listening on {args.host}:{args.port}, root={root}", flush=True)
        conn, addr = server.accept()
        with conn:
            print(f"FTP client connected from {addr}", flush=True)
            send_line(conn, "220 qemu-msdos-init test FTP server")
            while True:
                line = recv_line(conn)
                if not line:
                    break
                print(f"< {line}", flush=True)
                verb, _, rest = line.partition(" ")
                verb = verb.upper()
                rest = rest.strip()
                if verb == "USER":
                    send_line(conn, "331 password required")
                elif verb == "PASS":
                    send_line(conn, "230 logged in")
                elif verb == "SYST":
                    send_line(conn, "215 UNIX Type: L8")
                elif verb == "FEAT":
                    send_line(conn, "211 no-features")
                elif verb == "PWD":
                    send_line(conn, '257 "/"')
                elif verb == "TYPE":
                    send_line(conn, "200 type set")
                elif verb == "PASV":
                    if passive is not None:
                        passive.close()
                    passive = passive_socket(args.host, args.passive_port)
                    p1, p2 = divmod(args.passive_port, 256)
                    h = args.advertise_host.split(".")
                    send_line(conn, f"227 Entering Passive Mode ({','.join(h)},{p1},{p2})")
                elif verb == "LIST":
                    if passive is None:
                        send_line(conn, "425 use PASV first")
                        continue
                    send_line(conn, "150 opening data connection")
                    data, _ = passive.accept()
                    with data:
                        for path in sorted(root.iterdir()):
                            if path.is_file():
                                data.sendall(
                                    f"-rw-r--r-- 1 user group {path.stat().st_size:8d} Jan 01 00:00 {path.name}\r\n".encode(
                                        "ascii"
                                    )
                                )
                    passive.close()
                    passive = None
                    send_line(conn, "226 transfer complete")
                elif verb == "RETR":
                    name = Path(rest).name
                    path = root / name
                    if not path.is_file():
                        send_line(conn, "550 not found")
                        continue
                    if passive is None:
                        send_line(conn, "425 use PASV first")
                        continue
                    send_line(conn, "150 opening data connection")
                    data, _ = passive.accept()
                    with data:
                        data.sendall(path.read_bytes())
                    passive.close()
                    passive = None
                    send_line(conn, "226 transfer complete")
                elif verb in {"QUIT", "BYE", "EXIT"}:
                    send_line(conn, "221 bye")
                    break
                else:
                    send_line(conn, "502 command not implemented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
