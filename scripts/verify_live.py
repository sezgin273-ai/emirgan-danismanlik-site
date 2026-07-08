#!/usr/bin/env python3
"""Canlı site doğrulaması — https://emirgandanismanlik.com"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from ftplib import FTP, FTP_TLS, error_perm
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs/screenshots/verify-live-report.json"
BASE = "https://emirgandanismanlik.com"
HERO_TAGLINE = "Güvenilir Çözüm Ortağınız"
PROBE_REMOTE = "assets/img/uploads/__probe.php"
PROBE_BODY = b'<?php echo "PHP_EXEC";'
SECRET_PATTERNS = ("$2y$", "admin_password_hash", "smtp_pass", "mail_password", "smtp_host", "kurumsaleposta")

ACCEPTANCE: dict[str, dict] = {}


def record(name: str, measured, limit: str, passed: bool) -> None:
    ACCEPTANCE[name] = {"measured": measured, "limit": limit, "passed": passed}


def assert_metric(name: str, measured, limit: str, passed: bool) -> None:
    record(name, measured, limit, passed)
    if not passed:
        print(f"FAIL {name}: measured={measured!r}, limit={limit}", file=sys.stderr)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "EmirganVerifyLive/1.0"})
    return s


def require_ftp_env() -> tuple[str, str, str]:
    host = os.environ.get("FTP_HOST", "").strip()
    user = os.environ.get("FTP_USER", "").strip()
    password = os.environ.get("FTP_PASS", "").strip()
    if not all((host, user, password)):
        raise RuntimeError("FTP_HOST / FTP_USER / FTP_PASS gerekli (probe testi için).")
    return host, user, password


def connect_ftp(host: str, user: str, password: str) -> FTP:
    for factory in (FTP_TLS, FTP):
        try:
            ftp = factory()
            ftp.connect(host, 21, timeout=60)
            if isinstance(ftp, FTP_TLS):
                ftp.auth()
                ftp.prot_p()
            ftp.login(user, password)
            ftp.set_pasv(True)
            return ftp
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("FTP bağlantısı kurulamadı.")


def detect_web_root(ftp: FTP) -> str:
    for candidate in ("httpdocs", "public_html", "www"):
        try:
            names = {n.lower() for n in ftp.nlst(candidate)}
        except error_perm:
            continue
        if "index.php" in names or names:
            return candidate
    raise RuntimeError("Web kökü tespit edilemedi.")


def assert_homepage(sess: requests.Session) -> bool:
    resp = sess.get(BASE + "/", timeout=30)
    has_hero = HERO_TAGLINE in resp.text
    ok = resp.status_code == 200 and has_hero
    assert_metric("live_home_status", resp.status_code, "200", resp.status_code == 200)
    assert_metric("live_home_hero_tagline", 1 if has_hero else 0, "present", has_hero)
    return ok


def assert_static_pages(sess: requests.Session) -> bool:
    ok = True
    for path in ("/kvkk.php", "/robots.txt", "/sitemap.xml"):
        resp = sess.get(BASE + path, timeout=30)
        passed = resp.status_code == 200
        key = "live_" + path.strip("/").replace(".", "_") + "_status"
        assert_metric(key, resp.status_code, "200", passed)
        ok = ok and passed
    return ok


def assert_not_found(sess: requests.Session) -> bool:
    resp = sess.get(BASE + "/yok-boyle-bir-sayfa-qa", timeout=30, allow_redirects=True)
    ok = resp.status_code == 404
    assert_metric("live_missing_page_status", resp.status_code, "404", ok)
    return ok


def assert_content_private(sess: requests.Session) -> bool:
    ok = True
    for path in ("/content/content.json", "/content/"):
        resp = sess.get(BASE + path, timeout=30, allow_redirects=True)
        private = resp.status_code in (403, 404)
        key = "live_content_private" + path.replace("/", "_").rstrip("_")
        assert_metric(key, resp.status_code, "403 or 404", private)
        ok = ok and private
    return ok


def assert_admin_redirect(sess: requests.Session) -> bool:
    resp = sess.get(BASE + "/admin/", timeout=30, allow_redirects=False)
    location = resp.headers.get("Location", "")
    ok = resp.status_code == 302 and "login" in location.lower()
    assert_metric("live_admin_redirect_status", resp.status_code, "302", resp.status_code == 302)
    assert_metric("live_admin_redirect_login", 1 if "login" in location.lower() else 0, "login in Location", "login" in location.lower())
    return ok


def assert_redirects(sess: requests.Session) -> bool:
    ok = True
    http_resp = sess.get("http://emirgandanismanlik.com/", timeout=30, allow_redirects=False)
    http_redirect = http_resp.status_code in (301, 302) and http_resp.headers.get("Location", "").startswith("https://")
    assert_metric("live_http_to_https_status", http_resp.status_code, "301 or 302", http_resp.status_code in (301, 302))
    assert_metric("live_http_to_https_location", http_resp.headers.get("Location", ""), "https://…", http_redirect)
    ok = ok and http_redirect

    www_location = ""
    www_status = 0
    for www_url in ("https://www.emirgandanismanlik.com/", "http://www.emirgandanismanlik.com/"):
        try:
            www_resp = sess.get(www_url, timeout=30, allow_redirects=False)
            www_status = www_resp.status_code
            www_location = www_resp.headers.get("Location", "")
            if www_status in (301, 302):
                break
        except requests.RequestException as exc:
            www_status = type(exc).__name__
            continue
    www_redirect = isinstance(www_status, int) and www_status in (301, 302) and "emirgandanismanlik.com" in www_location and "www." not in urlparse(www_location).netloc
    assert_metric("live_www_to_apex_status", www_status, "301 or 302", isinstance(www_status, int) and www_status in (301, 302))
    assert_metric("live_www_to_apex_location", www_location, "apex https", www_redirect)
    ok = ok and www_redirect

    for label, url in (("apex", BASE + "/"), ("www", "http://www.emirgandanismanlik.com/")):
        try:
            final = sess.get(url, timeout=30, allow_redirects=True)
            has_hero = HERO_TAGLINE in final.text
            final_ok = final.status_code == 200 and "text/html" in final.headers.get("Content-Type", "") and has_hero
        except requests.RequestException as exc:
            assert_metric(f"live_final_200_{label}", type(exc).__name__, "200 HTML + hero", False)
            ok = False
            continue
        assert_metric(f"live_final_200_{label}", final.status_code if has_hero else f"{final.status_code} no-hero", "200 HTML + hero", final_ok)
        ok = ok and final_ok
    return ok


def assert_tls_preflight() -> bool:
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            resp = requests.get(BASE + "/", timeout=30, verify=True)
            ok = resp.status_code == 200
            assert_metric("live_tls_valid", 1 if ok else resp.status_code, "valid cert", ok)
            return ok
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(8)
    assert_metric("live_tls_valid", type(last_exc).__name__ if last_exc else "unknown", "valid cert", False)
    return False


def assert_config_not_leaked(sess: requests.Session) -> bool:
    resp = sess.get(BASE + "/config.php", timeout=30, allow_redirects=True)
    body = resp.text.lower()
    leaked = any(p.lower() in body for p in SECRET_PATTERNS)
    ok = not leaked
    assert_metric("live_config_no_secret_in_body", 1 if leaked else 0, "0", ok)
    assert_metric("live_config_status", resp.status_code, "not 200 with secrets", ok)
    return ok


def assert_uploads_php_blocked(sess: requests.Session) -> bool:
    host, user, password = require_ftp_env()
    ftp = connect_ftp(host, user, password)
    web_root = detect_web_root(ftp)
    remote = f"{web_root}/{PROBE_REMOTE}"
    try:
        ftp.storbinary(f"STOR {remote}", BytesIO(PROBE_BODY))
        url = BASE + "/" + PROBE_REMOTE
        resp = sess.get(url, timeout=30, allow_redirects=True)
        executed = "PHP_EXEC" in resp.text
        assert_metric("live_uploads_probe_no_exec", 1 if executed else 0, "0", not executed)
        assert_metric("live_uploads_probe_status", resp.status_code, "403 or raw", resp.status_code in (403, 200))
        ok = not executed
    finally:
        deleted = False
        try:
            ftp.delete(remote)
            deleted = True
        except error_perm:
            deleted = False
        try:
            names = {n.lower() for n in ftp.nlst(f"{web_root}/assets/img/uploads")}
            remaining = "__probe.php" in names
        except error_perm:
            remaining = True
        assert_metric("live_uploads_probe_deleted", 0 if remaining else 1, "deleted", not remaining)
        ftp.quit()
    return ok


def assert_faz54_contact_hours_live() -> bool:
    from playwright.sync_api import sync_playwright

    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/#contact", wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_selector(".contact-hours-card", timeout=30_000)
        page.wait_for_timeout(800)
        layout = page.evaluate(
            """() => {
              const leftCol = document.querySelector('.contact-form-col');
              const info = document.querySelector('.contact-info');
              const hours = document.querySelector('.contact-hours-card');
              if (!leftCol || !info) return null;
              const lr = leftCol.getBoundingClientRect();
              const ir = info.getBoundingClientRect();
              return {
                columnDelta: Math.round(Math.abs(lr.bottom - ir.bottom)),
                hoursVisible: !!hours,
                hoursTitle: hours ? (hours.querySelector('h3')?.textContent || '').trim() : '',
                rowCount: hours ? hours.querySelectorAll('.contact-hours-row').length : 0,
              };
            }"""
        )
        browser.close()

    if layout is None:
        assert_metric("live_contact_hours_layout", 0, "present", False)
        return False

    delta_ok = layout["columnDelta"] <= 16
    visible_ok = (
        layout["hoursVisible"]
        and layout["hoursTitle"] == "Çalışma Saatleri"
        and layout["rowCount"] == 2
    )
    assert_metric("live_contact_hours_column_delta_px", layout["columnDelta"], "<= 16", delta_ok)
    assert_metric("live_contact_hours_card_visible", 1 if visible_ok else 0, "title + 2 rows", visible_ok)
    return ok and delta_ok and visible_ok


def assert_mail_test(sess: requests.Session) -> tuple[bool, str]:
    subject = f"SMTP CANLI TESTİ — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    payload = {
        "name": "Canlı QA",
        "email": "canli.qa@example.com",
        "phone": "",
        "subject": subject,
        "message": "Faz 5.2 canlı mail doğrulama — tek istek.",
        "website": "",
    }
    resp = sess.post(
        BASE + "/api/contact.php",
        data=payload,
        headers={"Accept": "application/json"},
        timeout=60,
        allow_redirects=False,
    )
    ok_status = resp.status_code in (200, 303)
    body_ok = True
    if resp.headers.get("content-type", "").startswith("application/json"):
        body_ok = bool(resp.json().get("ok"))
    ok = ok_status and (body_ok or resp.status_code == 303)
    assert_metric("live_mail_test_status", resp.status_code, "200 or 303", ok_status)
    assert_metric("live_mail_test_ok", 1 if ok else 0, "success", ok)
    assert_metric("live_mail_test_subject", subject, "recorded", True)
    return ok, subject


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    skip_mail = "--skip-mail" in sys.argv
    faz54_only = "--faz54-only" in sys.argv
    ok = True
    mail_subject = ""
    sess = session()

    try:
        if faz54_only:
            ok = assert_homepage(sess) and ok
            ok = assert_content_private(sess) and ok
            ok = assert_faz54_contact_hours_live() and ok
        else:
            ok = assert_tls_preflight() and ok
        if not faz54_only and ACCEPTANCE.get("live_tls_valid", {}).get("passed"):
            ok = assert_homepage(sess) and ok
            ok = assert_static_pages(sess) and ok
            ok = assert_not_found(sess) and ok
            ok = assert_content_private(sess) and ok
            ok = assert_admin_redirect(sess) and ok
            ok = assert_redirects(sess) and ok
            ok = assert_config_not_leaked(sess) and ok
            ok = assert_uploads_php_blocked(sess) and ok
            ok = assert_faz54_contact_hours_live() and ok
            if skip_mail:
                existing = {}
                if REPORT_PATH.is_file():
                    try:
                        existing = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        pass
                mail_subject = str(existing.get("mail_test_subject", ""))
                if mail_subject:
                    assert_metric("live_mail_test_subject", mail_subject, "recorded (skip-mail)", True)
            else:
                mail_ok, mail_subject = assert_mail_test(sess)
                ok = mail_ok and ok
    except Exception as exc:  # noqa: BLE001
        assert_metric("live_unhandled_error", type(exc).__name__, "none", False)
        ok = False

    results = {
        "base": BASE,
        "acceptance": ACCEPTANCE,
        "mail_test_subject": mail_subject,
        "all_passed": ok and all(v["passed"] for v in ACCEPTANCE.values()),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if results["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
