#!/usr/bin/env python3
"""Yerel SMTP test sunucusu — gelen mesajları dizine yazar (auth/şifreleme yok)."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from aiosmtpd.controller import Controller


class CaptureHandler:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.count = 0

    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        self.count += 1
        target = self.out_dir / f"mail-{self.count:04d}.eml"
        data = envelope.content
        if isinstance(data, memoryview):
            data = data.tobytes()
        elif not isinstance(data, (bytes, bytearray)):
            data = bytes(data)
        target.write_bytes(data)
        return "250 OK"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    handler = CaptureHandler(out_dir)
    controller = Controller(handler, hostname=args.host, port=args.port)
    controller.start()
    print(f"SMTP debug listening on {args.host}:{args.port}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
