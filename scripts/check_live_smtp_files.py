#!/usr/bin/env python3
"""Canlı config/contact FTP indirme — teşhis; şifre değeri stdout'a yazılmaz."""
from __future__ import annotations

import os
import re
import sys
from ftplib import FTP_TLS
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".tmp" / "live-check"


def main() -> int:
    host = os.environ.get("FTP_HOST", "").strip()
    user = os.environ.get("FTP_USER", "").strip()
    password = os.environ.get("FTP_PASS", "").strip()
    if not all((host, user, password)):
        print("FTP env missing", file=sys.stderr)
        return 1

    ftp = FTP_TLS()
    ftp.connect(host, 21, timeout=60)
    ftp.auth()
    ftp.prot_p()
    ftp.login(user, password)
    ftp.set_pasv(True)
    OUT.mkdir(parents=True, exist_ok=True)
    for remote, name in (("httpdocs/config.php", "config.php"), ("httpdocs/api/contact.php", "contact.php")):
        buf = BytesIO()
        ftp.retrbinary(f"RETR {remote}", buf.write)
        (OUT / name).write_bytes(buf.getvalue())
    for remote in (
        "httpdocs/api/lib/phpmailer/PHPMailer.php",
        "httpdocs/api/lib/phpmailer/SMTP.php",
        "httpdocs/api/lib/phpmailer/Exception.php",
    ):
        buf = BytesIO()
        try:
            ftp.retrbinary(f"RETR {remote}", buf.write)
            exists = buf.tell() > 0
        except Exception:  # noqa: BLE001
            exists = False
        print(f"remote_{remote.rsplit('/', 1)[-1]}", exists)
    ftp.quit()

    text = (OUT / "config.php").read_text(encoding="utf-8", errors="replace")
    checks = {
        "mail_mode_smtp": bool(re.search(r"'mail_mode'\s*=>\s*'smtp'", text)),
        "smtp_host_kurumsal": bool(re.search(r"'smtp_host'\s*=>\s*'mail\.kurumsaleposta\.com'", text)),
        "smtp_port_465": bool(re.search(r"'smtp_port'\s*=>\s*465", text)),
        "smtp_secure_ssl": bool(re.search(r"'smtp_secure'\s*=>\s*'ssl'", text)),
        "smtp_pass_nonempty": bool(re.search(r"'smtp_pass'\s*=>\s*'[^']+'", text)),
        "admin_hash_present": "admin_password_hash" in text,
    }
    contact = (OUT / "contact.php").read_bytes()
    print("config_checks", checks)
    print("contact_has_smtp_fn", b"contact_send_via_smtp" in contact)
    print("contact_bytes", len(contact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
