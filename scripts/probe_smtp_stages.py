#!/usr/bin/env python3
"""SMTP bağlantı probe — aşama bazlı (TCP / TLS / AUTH). Şifre yalnızca SMTP_PASS env."""
from __future__ import annotations

import json
import os
import socket
import ssl
import sys

SMTP_USER = "info@emirgandanismanlik.com"
HOSTS = ("mail.kurumsaleposta.com", "mail.emirgandanismanlik.com")
ATTEMPTS = ((465, "ssl"), (587, "tls"))


def probe_one(host: str, port: int, secure: str, user: str, password: str) -> dict:
    import smtplib

    row: dict[str, object] = {
        "host": host,
        "port": port,
        "secure": secure,
        "tcp": None,
        "tls": None,
        "auth": None,
        "passed": False,
    }

    try:
        socket.create_connection((host, port), timeout=20).close()
        row["tcp"] = "ok"
    except OSError as exc:
        row["tcp"] = type(exc).__name__
        return row

    server: smtplib.SMTP | None = None
    try:
        context = ssl.create_default_context()
        if secure == "ssl":
            server = smtplib.SMTP_SSL(host, port, context=context, timeout=20)
            row["tls"] = "ok"
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            code, _ = server.starttls(context=context)
            if code != 220:
                row["tls"] = f"starttls_code_{code}"
                server.close()
                return row
            row["tls"] = "ok"
    except ssl.SSLError as exc:
        row["tls"] = f"SSLError:{getattr(exc, 'reason', type(exc).__name__)}"
        return row
    except OSError as exc:
        row["tls"] = type(exc).__name__
        return row
    except smtplib.SMTPException as exc:
        row["tls"] = type(exc).__name__
        return row

    try:
        server.login(user, password)
        row["auth"] = "ok"
        row["passed"] = True
    except smtplib.SMTPAuthenticationError:
        row["auth"] = "authentication_failed"
    except smtplib.SMTPException as exc:
        row["auth"] = type(exc).__name__
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:  # noqa: BLE001
                server.close()
    return row


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    password = os.environ.get("SMTP_PASS", "").strip()
    if not password:
        print(json.dumps({"error": "SMTP_PASS required"}, ensure_ascii=False))
        return 1

    results: list[dict] = []
    winner: dict | None = None
    for host in HOSTS:
        for port, secure in ATTEMPTS:
            row = probe_one(host, port, secure, SMTP_USER, password)
            results.append(row)
            if row["passed"]:
                winner = row
                break
        if winner:
            break

    out = {
        "attempts": results,
        "winner": (
            {
                "host": winner["host"],
                "port": winner["port"],
                "secure": winner["secure"],
            }
            if winner
            else None
        ),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if winner else 1


if __name__ == "__main__":
    raise SystemExit(main())
