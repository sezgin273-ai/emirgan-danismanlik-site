#!/usr/bin/env python3
"""PHP mail() sendmail_path stub — stdin'deki ham maili dosyaya yazar veya --fail ile exit 1."""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        return 1

    if "--fail" in sys.argv:
        return 1

    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(out_dir.glob("mail-*.eml"))
    target = out_dir / f"mail-{len(existing):04d}.eml"
    target.write_bytes(sys.stdin.buffer.read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
