"""Faz 4 QA kabul kriterleri doğrulaması."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from email import message_from_bytes
from email.header import decode_header
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PATH = ROOT / "content/content.json"
MAIL_LOG_DIR = ROOT / "content/mail-log"
SHOT_DIR = ROOT / "docs/screenshots"
QA_SHOT_DIR = SHOT_DIR / "qa"
REPORT_PATH = SHOT_DIR / "verify-qa-report.json"
HTACCESS_PATH = ROOT / "public_html/.htaccess"
BASE = "http://localhost:8080"
MAIL_TEST_BASE = "http://localhost:8081"
MAIL_TEST_PORT = 8081
CONFIG_PATH = ROOT / "public_html/config.php"
STUB_SCRIPT = ROOT / "scripts/mail_capture_stub.py"
CSS_DIR = ROOT / "public_html/assets/css"
CREDENTIAL_PATTERNS = ("smtp_pass", "mail_password", "smtp_user", "smtp_password")
TEST_PASSWORD = ".eE951623"
CONTACT_SECTION_BASELINE_HEIGHT_PX = 956
CONTACT_SECTION_MAX_HEIGHT_PX = 790
CONTACT_RIGHT_COL_BASELINE_RATIO = 1 / 2.618
PHP_BIN = ROOT / ".tools/php/php.exe"
PHP_INI = ROOT / ".tools/php/php.ini"

PROTECTED_ASSETS = [
    ROOT / "public_html/assets/img/logo-full.png",
    ROOT / "public_html/assets/img/logo-full-dark.png",
    ROOT / "public_html/assets/img/favicon.png",
    ROOT / "public_html/assets/img/apple-touch-icon.png",
    ROOT / "public_html/assets/img/emblem.png",
    ROOT / "public_html/assets/img/emblem-dark.png",
]

VIEWPORTS = [
    ("mobile", 360, 740),
    ("tablet", 768, 1024),
    ("desktop", 1440, 900),
]

ACCEPTANCE: dict[str, dict] = {}


def record(name: str, measured, limit: str, passed: bool) -> None:
    ACCEPTANCE[name] = {"measured": measured, "limit": limit, "passed": passed}


def assert_metric(name: str, measured, limit: str, passed: bool) -> None:
    record(name, measured, limit, passed)
    if not passed:
        print(f"FAIL {name}: measured={measured}, limit={limit}", file=sys.stderr)


def php_cmd(*args: str) -> list[str]:
    cmd = [str(PHP_BIN)]
    if PHP_INI.exists():
        cmd.extend(["-c", str(PHP_INI)])
    cmd.extend(args)
    return cmd


def setup_admin_config() -> None:
    subprocess.run(
        php_cmd(str(ROOT / "scripts/create_admin_config.php"), f"--password={TEST_PASSWORD}"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def load_content() -> dict:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def head_content_json() -> dict:
    raw = subprocess.run(
        ["git", "show", "HEAD:content/content.json"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return json.loads(raw.decode("utf-8"))


def deep_equal_except_allowed(head: object, current: object, path: str = "") -> tuple[bool, str]:
    if isinstance(head, dict):
        if not isinstance(current, dict):
            return False, f"{path or 'root'} type changed"
        for key, value in head.items():
            child_path = f"{path}.{key}" if path else key
            if key not in current:
                return False, f"missing key {child_path}"
            ok, reason = deep_equal_except_allowed(value, current[key], child_path)
            if not ok:
                return False, reason
        return True, ""
    if isinstance(head, list):
        if not isinstance(current, list) or len(head) != len(current):
            return False, f"{path} list length/type changed"
        for i, item in enumerate(head):
            ok, reason = deep_equal_except_allowed(item, current[i], f"{path}[{i}]")
            if not ok:
                return False, reason
        return True, ""
    if head != current:
        return False, f"{path} value changed"
    return True, ""


def assert_content_json_scope() -> bool:
    head = head_content_json()
    current = load_content()
    head_cmp = json.loads(json.dumps(head))
    current_cmp = json.loads(json.dumps(current))
    for cmp_obj in (head_cmp, current_cmp):
        if "site" in cmp_obj:
            cmp_obj["site"].pop("url", None)
            if "meta" in cmp_obj["site"]:
                cmp_obj["site"]["meta"].pop("og_image", None)
    ok, reason = deep_equal_except_allowed(head_cmp, current_cmp)
    assert_metric("content_json_existing_values_unchanged", 1 if ok else 0, "unchanged", ok)
    if not ok:
        print(f"content diff: {reason}", file=sys.stderr)

    process_ok = (
        "process" in current
        and isinstance(current["process"], dict)
        and current["process"].get("title") == "Nasıl Çalışıyoruz"
        and len(current["process"].get("steps", [])) == 4
    )
    assert_metric("content_json_process_added", 1 if process_ok else 0, "process key with 4 steps", process_ok)

    watermark_ok = current.get("hero", {}).get("watermark_enabled") is True
    assert_metric("content_json_watermark_enabled_added", 1 if watermark_ok else 0, "true", watermark_ok)

    process_section_ok = (
        current.get("site", {}).get("sections", {}).get("process", {}).get("visible") is True
    )
    assert_metric("content_json_process_section_visible_added", 1 if process_section_ok else 0, "true", process_section_ok)

    url_ok = current.get("site", {}).get("url") == "https://emirgandanismanlik.com"
    og_ok = current.get("site", {}).get("meta", {}).get("og_image") == "/assets/img/og-image.png"
    assert_metric("content_json_site_url_added", current.get("site", {}).get("url", ""), "https://emirgandanismanlik.com", url_ok)
    assert_metric(
        "content_json_og_image_added",
        current.get("site", {}).get("meta", {}).get("og_image", ""),
        "/assets/img/og-image.png",
        og_ok,
    )

    display_ok = current.get("display") == {
        "header_logo": "medium",
        "footer_logo": "medium",
        "team_avatar": "medium",
        "service_icon": "medium",
        "hero_emblem": "medium",
    }
    assert_metric("content_json_display_added", 1 if display_ok else 0, "medium defaults", display_ok)

    head_contact = head_cmp.get("contact", {})
    info_items = current.get("contact", {}).get("info_items", [])
    seeded_ok = (
        len(info_items) >= 3
        and info_items[0].get("value") == head_contact.get("addresses", [{}])[0].get("text")
        and info_items[1].get("value") == head_contact.get("addresses", [{}, {}])[1].get("text")
        and info_items[2].get("value") == head_contact.get("email")
    )
    assert_metric("content_json_info_items_seeded", 1 if seeded_ok else 0, "byte-identical seed", seeded_ok)

    return ok and process_ok and watermark_ok and process_section_ok and url_ok and og_ok and display_ok and seeded_ok


def assert_scope_unchanged() -> bool:
    ok = True
    for path in PROTECTED_ASSETS:
        rel = path.relative_to(ROOT).as_posix()
        head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
        if head.returncode != 0:
            assert_metric(f"scope_unchanged_{path.name}", 0, "unchanged", False)
            ok = False
            continue
        passed = hashlib.sha256(head.stdout).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest()
        assert_metric(f"scope_unchanged_{path.name}", 1 if passed else 0, "unchanged", passed)
        ok = ok and passed
    return ok


def snapshot_mail_log() -> set[str]:
    if not MAIL_LOG_DIR.is_dir():
        return set()
    return {p.name for p in MAIL_LOG_DIR.iterdir() if p.is_file()}


def restore_mail_log(before: set[str]) -> None:
    if not MAIL_LOG_DIR.is_dir():
        return
    for path in MAIL_LOG_DIR.iterdir():
        if path.is_file() and path.name not in before:
            path.unlink(missing_ok=True)


def contact_post(session: requests.Session, data: dict, headers: dict | None = None) -> tuple[int, dict]:
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    resp = session.post(BASE + "/api/contact.php", data=data, headers=hdrs, timeout=30)
    try:
        body = resp.json()
    except json.JSONDecodeError:
        body = {}
    return resp.status_code, body


def assert_contact_api() -> bool:
    ok = True
    before_logs = snapshot_mail_log()

    valid = {
        "name": "QA Test Kullanıcı",
        "email": "qa@example.com",
        "phone": "5551234567",
        "subject": "QA konusu",
        "message": "Faz 4 iletişim formu test mesajı.",
    }
    status, body = contact_post(requests.Session(), valid)
    after_logs = snapshot_mail_log()
    new_logs = after_logs - before_logs
    log_created = len(new_logs) >= 1
    assert_metric("contact_valid_post_status", status, "200", status == 200)
    assert_metric("contact_valid_post_ok", 1 if body.get("ok") else 0, "true", bool(body.get("ok")))
    assert_metric("contact_valid_log_created", len(new_logs), ">= 1", log_created)
    ok = ok and status == 200 and body.get("ok") and log_created

    status, _ = contact_post(requests.Session(), {"email": "qa@example.com", "message": "eksik"})
    assert_metric("contact_missing_required_status", status, "422", status == 422)
    ok = ok and status == 422

    status, _ = contact_post(requests.Session(), {"name": "X", "email": "not-an-email", "message": "test"})
    assert_metric("contact_invalid_email_status", status, "422", status == 422)
    ok = ok and status == 422

    honeypot_before = snapshot_mail_log()
    status, body = contact_post(
        requests.Session(),
        {**valid, "website": "http://spam.example", "message": "honeypot mesaj"},
    )
    honeypot_after = snapshot_mail_log()
    honeypot_no_log = honeypot_after == honeypot_before
    assert_metric("contact_honeypot_status", status, "200", status == 200)
    assert_metric("contact_honeypot_no_log", 1 if honeypot_no_log else 0, "no new log", honeypot_no_log)
    ok = ok and status == 200 and body.get("ok") and honeypot_no_log

    rate_session = requests.Session()
    rate_data = {
        "name": "Rate Test",
        "email": "rate@example.com",
        "subject": "Rate",
        "message": "Rate limit test mesajı.",
    }
    status1, _ = contact_post(rate_session, rate_data)
    status2, _ = contact_post(rate_session, rate_data)
    assert_metric("contact_rate_limit_second_status", status2, "429", status2 == 429)
    ok = ok and status1 == 200 and status2 == 429

    restore_mail_log(before_logs)
    return ok


def snapshot_config() -> bytes | None:
    if CONFIG_PATH.is_file():
        return CONFIG_PATH.read_bytes()
    return None


def restore_config(data: bytes | None) -> None:
    if data is None:
        if CONFIG_PATH.is_file():
            CONFIG_PATH.unlink()
    else:
        CONFIG_PATH.write_bytes(data)


def set_config_mail_mode(mode: str) -> None:
    setup_admin_config()
    text = CONFIG_PATH.read_text(encoding="utf-8")
    text = re.sub(r"('mail_mode'\s*=>\s*)'[^']*'", rf"\1'{mode}'", text, count=1)
    CONFIG_PATH.write_text(text, encoding="utf-8")


def write_mail_send_cmd(stub_dir: Path, *, fail: bool = False) -> Path:
    cmd_path = stub_dir / ("mail_send_fail.cmd" if fail else "mail_send.cmd")
    args = f'"{sys.executable}" "{STUB_SCRIPT}" "{stub_dir}"'
    if fail:
        args += " --fail"
    cmd_path.write_text(f"@echo off\r\n{args}\r\n", encoding="utf-8")
    return cmd_path


def start_mail_test_server(stub_dir: Path, *, fail: bool = False) -> subprocess.Popen:
    ini_path = stub_dir / "php-sendmail.ini"
    cmd_path = write_mail_send_cmd(stub_dir, fail=fail)
    sendmail_line = f'sendmail_path="{cmd_path}"'
    if PHP_INI.exists():
        base_ini = PHP_INI.read_text(encoding="utf-8")
        ini_path.write_text(
            base_ini.rstrip() + "\n"
            + sendmail_line + "\n",
            encoding="utf-8",
        )
    else:
        ini_path.write_text(
            "[PHP]\n"
            + sendmail_line + "\n",
            encoding="utf-8",
        )
    cmd = [str(PHP_BIN), "-c", str(ini_path), "-S", f"localhost:{MAIL_TEST_PORT}", "-t", "public_html", "public_html/router.php"]
    return subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_http_ready(base: str, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(base + "/", timeout=2)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return False


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def decode_mime_header(value: str) -> str:
    chunks: list[str] = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            chunks.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            chunks.append(fragment)
    return "".join(chunks)


def parse_mail_file(path: Path) -> dict[str, str]:
    msg = message_from_bytes(path.read_bytes())
    return {
        "to": msg.get("To", ""),
        "reply_to": msg.get("Reply-To", ""),
        "subject": decode_mime_header(msg.get("Subject", "")),
        "body": msg.get_payload(decode=True).decode("utf-8", errors="replace") if msg.get_payload(decode=True) else "",
    }


def assert_faz51_contact_mail() -> bool:
    ok = True
    config_before = snapshot_config()
    server: subprocess.Popen | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="mail-stub-") as tmp:
            stub_dir = Path(tmp)
            set_config_mail_mode("mail")
            server = start_mail_test_server(stub_dir, fail=False)
            ready = wait_http_ready(MAIL_TEST_BASE)
            assert_metric("mail_stub_server_ready", 1 if ready else 0, "HTTP 200", ready)
            ok = ok and ready
            if not ready:
                return ok

            payload = {
                "name": "Mail Stub QA",
                "email": "stub.sender@example.com",
                "phone": "5550001122",
                "subject": "UTF-8 konu: İletişim testi",
                "message": "Stub gövde mesajı doğrulama metni.",
            }
            session = requests.Session()
            resp = session.post(
                MAIL_TEST_BASE + "/api/contact.php",
                data=payload,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            captured = sorted(stub_dir.glob("mail-*.eml"))
            count_ok = len(captured) == 1
            assert_metric("mail_mode_valid_post_status", resp.status_code, "200", resp.status_code == 200)
            assert_metric("mail_mode_stub_file_count", len(captured), "1", count_ok)
            assert_metric("mail_mode_valid_post_ok", 1 if body.get("ok") else 0, "true", bool(body.get("ok")))
            ok = ok and resp.status_code == 200 and count_ok and bool(body.get("ok"))

            if captured:
                mail = parse_mail_file(captured[0])
                to_ok = "info@emirgandanismanlik.com" in mail["to"]
                reply_ok = mail["reply_to"] == payload["email"]
                subject_ok = mail["subject"] == payload["subject"]
                body_ok = payload["name"] in mail["body"] and payload["message"] in mail["body"]
                assert_metric("mail_mode_captured_to", mail["to"], "info@emirgandanismanlik.com", to_ok)
                assert_metric("mail_mode_captured_reply_to", mail["reply_to"], payload["email"], reply_ok)
                assert_metric("mail_mode_captured_subject", mail["subject"], payload["subject"], subject_ok)
                assert_metric("mail_mode_captured_body", 1 if body_ok else 0, "name+message present", body_ok)
                ok = ok and to_ok and reply_ok and subject_ok and body_ok

            stop_server(server)
            server = None

            fail_dir = stub_dir / "fail"
            fail_dir.mkdir()
            set_config_mail_mode("mail")
            server = start_mail_test_server(fail_dir, fail=True)
            fail_ready = wait_http_ready(MAIL_TEST_BASE)
            assert_metric("mail_stub_fail_server_ready", 1 if fail_ready else 0, "HTTP 200", fail_ready)
            ok = ok and fail_ready
            if fail_ready:
                logs_before = snapshot_mail_log()
                fail_session = requests.Session()
                fail_resp = fail_session.post(
                    MAIL_TEST_BASE + "/api/contact.php",
                    data={
                        "name": "Fail Stub",
                        "email": "fail.stub@example.com",
                        "subject": "Fail",
                        "message": "Stub fail senaryosu.",
                    },
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                logs_after = snapshot_mail_log()
                fail_files = list(fail_dir.glob("mail-*.eml"))
                status_ok = fail_resp.status_code == 500
                no_log_ok = logs_after == logs_before
                no_stub_ok = len(fail_files) == 0
                assert_metric("mail_mode_stub_fail_status", fail_resp.status_code, "500", status_ok)
                assert_metric("mail_mode_stub_fail_no_log", 1 if no_log_ok else 0, "no new mail-log", no_log_ok)
                assert_metric("mail_mode_stub_fail_no_capture", len(fail_files), "0", no_stub_ok)
                ok = ok and status_ok and no_log_ok and no_stub_ok
    finally:
        stop_server(server)
        restore_config(config_before)

    return ok


def assert_mail_security() -> bool:
    ok = True
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    config_tracked = "public_html/config.php" in tracked
    assert_metric("security_config_not_tracked", 0 if config_tracked else 1, "absent from git ls-files", not config_tracked)
    ok = ok and not config_tracked

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    ignore_ok = "config.php" in gitignore
    assert_metric("security_gitignore_config_php", 1 if ignore_ok else 0, "listed", ignore_ok)
    ok = ok and ignore_ok

    credential_hits = 0
    for rel in tracked:
        if rel.replace("\\", "/") == "scripts/verify_qa.py":
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for pattern in CREDENTIAL_PATTERNS:
            if pattern in text:
                credential_hits += 1
                break
    cred_ok = credential_hits == 0
    assert_metric("security_no_credential_keys_in_repo", credential_hits, "0", cred_ok)
    ok = ok and cred_ok
    return ok


def assert_faz51_scope_css() -> bool:
    ok = True
    for name in ("tokens.css", "main.css"):
        path = CSS_DIR / name
        rel = path.relative_to(ROOT).as_posix()
        head = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True)
        if head.returncode != 0:
            assert_metric(f"scope_unchanged_css_{name}", 0, "unchanged", False)
            ok = False
            continue
        passed = hashlib.sha256(head.stdout).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest()
        assert_metric(f"scope_unchanged_css_{name}", 1 if passed else 0, "unchanged", passed)
        ok = ok and passed
    return ok


def assert_seo_files() -> bool:
    ok = True
    home = requests.get(BASE + "/", timeout=30).text
    checks = {
        "canonical": 'rel="canonical"' in home,
        "og_title": 'property="og:title"' in home,
        "og_description": 'property="og:description"' in home,
        "og_image": 'property="og:image"' in home,
        "twitter_card": 'name="twitter:card" content="summary_large_image"' in home,
    }
    for key, passed in checks.items():
        assert_metric(f"homepage_meta_{key}", 1 if passed else 0, "present", passed)
        ok = ok and passed

    og_path = ROOT / "public_html/assets/img/og-image.png"
    with Image.open(og_path) as img:
        w, h = img.size
    size_ok = w == 1200 and h == 630
    assert_metric("og_image_width", w, "1200", w == 1200)
    assert_metric("og_image_height", h, "630", h == 630)
    ok = ok and size_ok

    robots = requests.get(BASE + "/robots.txt", timeout=30)
    robots_ok = robots.status_code == 200 and "Disallow: /admin/" in robots.text and "Sitemap:" in robots.text
    assert_metric("robots_txt_status", robots.status_code, "200", robots.status_code == 200)
    assert_metric("robots_txt_rules", 1 if robots_ok else 0, "admin/api disallowed + sitemap", robots_ok)
    ok = ok and robots_ok

    sitemap = requests.get(BASE + "/sitemap.xml", timeout=30)
    sitemap_ok = sitemap.status_code == 200
    url_count = 0
    if sitemap_ok:
        try:
            root = ET.fromstring(sitemap.text)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            locs = [el.text for el in root.findall(".//sm:loc", ns)]
            if not locs:
                locs = [el.text for el in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
            if not locs:
                locs = [el.text for el in root.iter() if el.tag.endswith("loc") and el.text]
            url_count = len(locs)
            sitemap_ok = url_count == 2 and all(
                u.startswith("https://emirgandanismanlik.com/") for u in locs if u
            )
        except ET.ParseError:
            sitemap_ok = False
    assert_metric("sitemap_xml_status", sitemap.status_code, "200", sitemap.status_code == 200)
    assert_metric("sitemap_xml_url_count", url_count, "2", url_count == 2)
    ok = ok and sitemap_ok
    return ok


def collect_local_urls(html: str, page_url: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r"""(?:href|src)=["']([^"']+)["']""", html):
        raw = match.group(1).strip()
        if raw.startswith("#") or raw.startswith("mailto:") or raw.startswith("tel:"):
            continue
        if raw.startswith("http://") or raw.startswith("https://"):
            if raw.startswith(BASE):
                urls.append(raw[len(BASE) :])
            continue
        urls.append(urljoin(page_url, raw))
    return urls


def assert_page_health() -> bool:
    ok = True
    pages = [("/", "home"), ("/kvkk.php", "kvkk")]
    broken_total = 0
    imgs_without_alt_total = 0
    console_errors_total = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for path, label in pages:
            page = browser.new_page()
            errors: list[str] = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(BASE + path, wait_until="networkidle")
            html = page.content()
            broken = 0
            for rel in collect_local_urls(html, path):
                if rel.startswith("/"):
                    st = requests.get(BASE + rel, timeout=30).status_code
                    if st == 404:
                        broken += 1
            broken_total += broken
            imgs_without_alt = page.evaluate(
                """() => Array.from(document.images).filter(img => !img.hasAttribute('alt')).length"""
            )
            imgs_without_alt_total += imgs_without_alt
            err_count = len(errors)
            console_errors_total += err_count
            assert_metric(f"{label}_broken_resources", broken, "0", broken == 0)
            assert_metric(f"{label}_imgs_without_alt", imgs_without_alt, "0", imgs_without_alt == 0)
            assert_metric(f"{label}_console_errors", err_count, "0", err_count == 0)
            ok = ok and broken == 0 and imgs_without_alt == 0 and err_count == 0
            page.close()
        browser.close()

    kvkk_html = requests.get(BASE + "/kvkk.php", timeout=30).text
    note_hidden = "Detaylı KVKK metni" not in kvkk_html
    assert_metric("kvkk_note_not_rendered", 1 if note_hidden else 0, "absent on frontend", note_hidden)
    ok = ok and note_hidden

    missing_status = requests.get(BASE + "/yok-boyle-bir-sayfa", timeout=30).status_code
    assert_metric("missing_page_status", missing_status, "404", missing_status == 404)
    ok = ok and missing_status == 404
    return ok


def assert_htaccess() -> bool:
    text = HTACCESS_PATH.read_text(encoding="utf-8")
    has_cache = "max-age=2592000" in text and "mod_expires" in text
    has_deflate = "mod_deflate" in text and "DEFLATE" in text
    assert_metric("htaccess_cache_block", 1 if has_cache else 0, "present", has_cache)
    assert_metric("htaccess_deflate_block", 1 if has_deflate else 0, "present", has_deflate)
    return has_cache and has_deflate


def measure_homepage_total_bytes() -> int:
    session = requests.Session()
    total = 0
    html_resp = session.get(BASE + "/", timeout=30)
    total += len(html_resp.content)
    for match in re.finditer(r"""(?:href|src)=["']([^"']+)["']""", html_resp.text):
        raw = match.group(1).strip()
        if raw.startswith("#") or raw.startswith("mailto:") or raw.startswith("http"):
            continue
        path = urljoin("/", raw)
        if not path.startswith("/"):
            continue
        try:
            resp = session.get(BASE + path, timeout=30)
            if resp.status_code == 200:
                total += len(resp.content)
        except requests.RequestException:
            pass
    limit_ok = total <= 650_000
    assert_metric("homepage_total_resource_bytes", total, "<= 650000", limit_ok)
    return total


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError("CSRF token bulunamadı")
    return m.group(1)


def admin_login(session: requests.Session) -> None:
    html = session.get(BASE + "/admin/login.php", timeout=30).text
    csrf = extract_csrf(html)
    session.post(
        BASE + "/admin/login.php",
        data={"csrf_token": csrf, "password": TEST_PASSWORD},
        timeout=30,
    )


def assert_team_reorder_delete_guard() -> bool:
    ok = True
    content_before = load_content()
    names_before = [m.get("name", "") for m in content_before["team"]["members"]]
    if len(names_before) < 2:
        assert_metric("team_reorder_delete_guard", 0, "skipped", False)
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE + "/admin/login.php", wait_until="networkidle")
        page.fill("#password", TEST_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url("**/admin/dashboard.php")

        first_label = page.locator("#team-list [data-item-label]").first.inner_text()
        page.locator("#team-list [data-sort-down]").first.click()
        page.wait_for_timeout(300)
        label_after_sort = page.locator("#team-list [data-item-label]").first.inner_text()
        label_ok = label_after_sort.startswith("Üye")
        assert_metric("team_label_after_sort", 1 if label_ok else 0, "starts with Üye", label_ok)
        ok = ok and label_ok

        dialog_seen = False

        def accept_dialog(dialog) -> None:
            nonlocal dialog_seen
            dialog_seen = True
            dialog.accept()

        page.once("dialog", accept_dialog)
        with page.expect_response(lambda r: "/admin/actions.php" in r.url) as resp_info:
            page.locator("#team-list [data-delete-team-member]").first.click()
        response = resp_info.value
        status = response.status
        page.wait_for_timeout(500)

        names_after = [m.get("name", "") for m in load_content()["team"]["members"]]
        unchanged = names_after == names_before
        guard_ok = status == 409 and unchanged
        assert_metric("team_reorder_delete_status", status, "409", status == 409)
        assert_metric("team_reorder_delete_list_unchanged", 1 if unchanged else 0, "unchanged", unchanged)
        ok = ok and guard_ok and dialog_seen
        browser.close()

    return ok


def assert_visual_enrichment() -> bool:
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(1200)

        service_data = page.evaluate(
            """() => {
              const cards = document.querySelectorAll('.service-card');
              const svgs = Array.from(cards).map(c => c.querySelector('svg'));
              const signatures = svgs.map(svg => {
                if (!svg) return '';
                return Array.from(svg.querySelectorAll('path'))
                  .map(p => p.getAttribute('d'))
                  .filter(Boolean)
                  .join('|');
              }).filter(Boolean);
              const uniqueSignatures = new Set(signatures);
              return {
                cardCount: cards.length,
                svgCount: svgs.filter(Boolean).length,
                uniqueSignatureCount: uniqueSignatures.size,
              };
            }"""
        )
        svc_count = service_data["svgCount"]
        svc_ok = svc_count == 7 and service_data["uniqueSignatureCount"] == 7
        assert_metric("service_card_inline_svg_count", svc_count, "7", svc_count == 7)
        assert_metric("service_icon_unique_paths", service_data["uniqueSignatureCount"], "7", service_data["uniqueSignatureCount"] == 7)
        ok = ok and svc_ok

        page.emulate_media(reduced_motion="no-preference")
        card = page.locator(".service-card").first
        shadow_before = card.evaluate("el => getComputedStyle(el).boxShadow")
        card.hover()
        page.wait_for_timeout(300)
        hover_after = card.evaluate(
            """el => {
              const style = getComputedStyle(el);
              let translateY = 0;
              const t = style.transform;
              if (t && t !== 'none') {
                const m = t.match(/matrix\\(([^)]+)\\)/);
                if (m) {
                  const vals = m[1].split(',').map(s => parseFloat(s.trim()));
                  translateY = vals.length === 6 ? vals[5] : (vals[13] || 0);
                }
              }
              return { translateY, boxShadow: style.boxShadow };
            }"""
        )
        hover_y_ok = hover_after["translateY"] <= -2
        shadow_changed = hover_after["boxShadow"] != shadow_before
        assert_metric("service_card_hover_translate_y", hover_after["translateY"], "<= -2px", hover_y_ok)
        assert_metric("service_card_hover_shadow_changed", 1 if shadow_changed else 0, "changed", shadow_changed)
        ok = ok and hover_y_ok and shadow_changed

        watermark = page.evaluate(
            """() => {
              const el = document.querySelector('.hero-watermark');
              if (!el) return { exists: false, opacity: 0, pointerEvents: '' };
              const s = getComputedStyle(el);
              return {
                exists: true,
                opacity: parseFloat(s.opacity),
                pointerEvents: s.pointerEvents,
              };
            }"""
        )
        wm_ok = (
            watermark.get("exists")
            and 0.03 <= watermark.get("opacity", 0) <= 0.08
            and watermark.get("pointerEvents") == "none"
        )
        assert_metric("hero_watermark_opacity", watermark.get("opacity", 0), "0.03-0.08", wm_ok)
        assert_metric("hero_watermark_pointer_events", watermark.get("pointerEvents", ""), "none", watermark.get("pointerEvents") == "none")
        ok = ok and wm_ok

        title_color = page.evaluate(
            """() => {
              const el = document.querySelector('.hero-title');
              return el ? getComputedStyle(el).color : '';
            }"""
        )
        title_ok = title_color == "rgb(248, 244, 240)"
        assert_metric("hero_title_color_unchanged", title_color, "rgb(248, 244, 240)", title_ok)
        ok = ok and title_ok

        process_data = page.evaluate(
            """() => {
              const section = document.querySelector('#process');
              if (!section) return { bg: '', steps: 0, contrast: 0 };
              const bg = getComputedStyle(section).backgroundColor;
              const steps = section.querySelectorAll('.process-step').length;
              const body = section.querySelector('.process-step-description');
              const textColor = body ? getComputedStyle(body).color : '';
              function parseRgb(c) {
                const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [+m[1], +m[2], +m[3]] : [0,0,0];
              }
              function lum(rgb) {
                const a = rgb.map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
                return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
              }
              const l1 = lum(parseRgb(bg));
              const l2 = lum(parseRgb(textColor));
              const contrast = (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
              return { bg, steps, contrast };
            }"""
        )
        bg_ok = process_data.get("bg") == "rgb(16, 24, 44)"
        steps_ok = process_data.get("steps") == 4
        contrast_ok = process_data.get("contrast", 0) >= 4.5
        assert_metric("process_section_bg_color", process_data.get("bg", ""), "rgb(16, 24, 44)", bg_ok)
        assert_metric("process_step_count", process_data.get("steps", 0), "4", steps_ok)
        assert_metric("process_section_contrast_ratio", round(process_data.get("contrast", 0), 2), ">= 4.5", contrast_ok)
        ok = ok and bg_ok and steps_ok and contrast_ok

        rhythm = page.evaluate(
            """() => {
              const ids = ['intro', 'services', 'about', 'process', 'team', 'contact'];
              const colors = ids.map(id => {
                const el = document.getElementById(id);
                return el ? getComputedStyle(el).backgroundColor : null;
              }).filter(Boolean);
              let consecutive = false;
              for (let i = 1; i < colors.length; i++) {
                if (colors[i] === colors[i-1]) consecutive = true;
              }
              const unique = new Set(colors);
              return { colors, consecutive, uniqueCount: unique.size };
            }"""
        )
        rhythm_ok = not rhythm.get("consecutive") and rhythm.get("uniqueCount", 0) >= 3
        assert_metric("section_bg_no_consecutive_same", 1 if not rhythm.get("consecutive") else 0, "no pairs", not rhythm.get("consecutive"))
        assert_metric("section_bg_unique_count", rhythm.get("uniqueCount", 0), ">= 3", rhythm.get("uniqueCount", 0) >= 3)
        ok = ok and rhythm_ok

        reveal = page.evaluate(
            """() => {
              const els = document.querySelectorAll('.reveal');
              let v = 0;
              els.forEach(el => { if (parseFloat(getComputedStyle(el).opacity) > 0.5) v++; });
              return { total: els.length, visible: v };
            }"""
        )
        reveal_ok = reveal["visible"] == reveal["total"] and reveal["total"] > 24
        assert_metric("homepage_reveal_visible", f"{reveal['visible']}/{reveal['total']}", "all visible", reveal_ok)
        ok = ok and reveal_ok

        page.close()

        mobile = browser.new_page(viewport={"width": 360, "height": 740})
        mobile.goto(BASE + "/", wait_until="networkidle")
        mobile.wait_for_timeout(500)
        overflow = mobile.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
        assert_metric("overflow_mobile_home_process", 1 if overflow else 0, "no horizontal overflow", overflow)
        ok = ok and overflow

        browser.close()

    return ok


def assert_faz47_contact_layout() -> bool:
    """Faz 4.7/4.8: kompakt iletişim yerleşimi, genişletilmiş sağ sütun ve harita embed."""
    ok = True
    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    info_items = content["contact"].get("info_items", [])
    turkey_address = info_items[0]["value"] if info_items else content["contact"]["addresses"][0]["text"]
    encoded_address = quote(turkey_address, safe="")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(BASE + "/#contact", wait_until="networkidle")
        page.wait_for_timeout(500)

        height = page.evaluate(
            """() => Math.round(document.getElementById('contact').getBoundingClientRect().height)"""
        )
        height_ok = height <= CONTACT_SECTION_MAX_HEIGHT_PX
        assert_metric("contact_section_height_baseline_px", CONTACT_SECTION_BASELINE_HEIGHT_PX, "baseline", True)
        assert_metric("contact_section_height_px", height, f"<= {CONTACT_SECTION_MAX_HEIGHT_PX}", height_ok)
        ok = ok and height_ok

        layout = page.evaluate(
            f"""() => {{
              const grid = document.querySelector('.contact-grid');
              const info = document.querySelector('.contact-info');
              const cards = Array.from(document.querySelectorAll('.contact-info-grid .address-card'));
              const r0 = cards[0].getBoundingClientRect();
              const r1 = cards[1].getBoundingClientRect();
              const topDiff = Math.abs(r0.top - r1.top);
              const sideBySide = r0.right <= r1.left || r1.right <= r0.left;
              const email = document.querySelector('.contact-info-email');
              const emailRect = email ? email.getBoundingClientRect() : {{ top: 0, left: 0, width: 0 }};
              const gridRect = grid.getBoundingClientRect();
              const infoRect = info.getBoundingClientRect();
              const rightRatio = infoRect.width / gridRect.width;
              const baselineMin = {CONTACT_RIGHT_COL_BASELINE_RATIO} * 1.2;
              const emailFullWidth = email ? Math.abs(emailRect.width - infoRect.width) <= 8 : false;
              const emailBelow = email ? emailRect.top >= Math.max(r0.bottom, r1.bottom) - 4 : false;
              const iframe = document.querySelector('.contact-map-iframe');
              const iframeRect = iframe ? iframe.getBoundingClientRect() : {{ height: 0 }};
              const overflow = document.documentElement.scrollWidth <= window.innerWidth;
              return {{
                topDiff,
                sideBySide,
                rightRatio,
                emailFullWidth,
                emailBelow,
                iframeHeight: iframeRect.height,
                src: iframe ? iframe.getAttribute('src') || '' : '',
                overflow,
              }};
            }}"""
        )
        cards_ok = layout["topDiff"] <= 8 and layout["sideBySide"]
        right_ok = layout["rightRatio"] >= CONTACT_RIGHT_COL_BASELINE_RATIO * 1.2
        assert_metric("contact_address_cards_top_delta_px", round(layout["topDiff"], 2), "<= 8", layout["topDiff"] <= 8)
        assert_metric("contact_address_cards_side_by_side", 1 if layout["sideBySide"] else 0, "no horizontal overlap", layout["sideBySide"])
        assert_metric(
            "contact_right_column_width_ratio",
            round(layout["rightRatio"], 4),
            f">= {round(CONTACT_RIGHT_COL_BASELINE_RATIO * 1.2, 4)}",
            right_ok,
        )
        ok = ok and cards_ok and right_ok

        email_ok = layout["emailBelow"] and layout["emailFullWidth"]
        assert_metric("contact_email_full_width", 1 if layout["emailFullWidth"] else 0, "full column", layout["emailFullWidth"])
        assert_metric("contact_email_below_cards", 1 if layout["emailBelow"] else 0, "below cards", layout["emailBelow"])
        ok = ok and email_ok

        map_h = layout["iframeHeight"]
        map_h_ok = 240 <= map_h <= 320
        src = layout["src"]
        map_src_ok = (
            "google.com/maps" in src
            and encoded_address in src
            and "output=embed" in src
        )
        assert_metric("contact_map_iframe_height_px", round(map_h, 2), "240-320", map_h_ok)
        assert_metric("contact_map_iframe_src", 1 if map_src_ok else 0, "encoded address + output=embed", map_src_ok)
        overflow_ok = layout["overflow"]
        assert_metric("contact_section_no_overflow", 1 if overflow_ok else 0, "no horizontal overflow", overflow_ok)
        ok = ok and map_h_ok and map_src_ok and overflow_ok

        console_ok = len(errors) == 0
        assert_metric("contact_section_console_errors", len(errors), "0", console_ok)
        ok = ok and console_ok

        mobile = browser.new_page(viewport={"width": 360, "height": 740})
        mobile.goto(BASE + "/#contact", wait_until="networkidle")
        mobile.wait_for_timeout(400)
        mobile_layout = mobile.evaluate(
            """() => {
              const cards = Array.from(document.querySelectorAll('.contact-info-grid .address-card'));
              let stacked = true;
              for (let i = 1; i < cards.length; i++) {
                if (cards[i].getBoundingClientRect().top < cards[i-1].getBoundingClientRect().bottom - 4) stacked = false;
              }
              const overflow = document.documentElement.scrollWidth <= window.innerWidth;
              return { stacked, overflow };
            }"""
        )
        mobile_ok = mobile_layout["stacked"] and mobile_layout["overflow"]
        assert_metric("contact_mobile_cards_stacked", 1 if mobile_layout["stacked"] else 0, "vertical stack", mobile_layout["stacked"])
        assert_metric("contact_mobile_no_overflow", 1 if mobile_layout["overflow"] else 0, "no horizontal overflow", mobile_layout["overflow"])
        ok = ok and mobile_ok
        mobile.close()
        browser.close()

    return ok


def assert_viewport_qa() -> tuple[bool, list[str]]:
    ok = True
    shots: list[str] = []
    QA_SHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for path, page_name in [("/", "home"), ("/kvkk.php", "kvkk")]:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + path, wait_until="networkidle")
                page.wait_for_timeout(800)
                overflow = page.evaluate(
                    """() => document.documentElement.scrollWidth <= window.innerWidth"""
                )
                assert_metric(
                    f"overflow_{label}_{page_name}",
                    1 if overflow else 0,
                    "no horizontal overflow",
                    overflow,
                )
                ok = ok and overflow
                shot_name = f"qa-{page_name}-{label}-{width}x{height}.png"
                shot_path = QA_SHOT_DIR / shot_name
                page.screenshot(path=str(shot_path), full_page=True)
                shots.append(f"docs/screenshots/qa/{shot_name}")
                page.close()

        browser.close()

    return ok, shots


def run_verify_admin() -> bool:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_admin.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    passed = proc.returncode == 0
    assert_metric("verify_admin_all_passed", proc.returncode, "0", passed)
    if not passed:
        print(proc.stderr or proc.stdout, file=sys.stderr)
    return passed


def main() -> int:
    QA_SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"screenshots": [], "acceptance": {}}
    ok = True

    content_bytes = CONTENT_PATH.read_bytes()
    mail_log_before = snapshot_mail_log()
    git_status_before = subprocess.run(
        ["git", "status", "--porcelain", "content/content.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()

    try:
        setup_admin_config()
        set_config_mail_mode("log")
        ok = assert_contact_api() and ok
        ok = assert_faz51_contact_mail() and ok
        ok = assert_mail_security() and ok
        ok = assert_seo_files() and ok
        ok = assert_page_health() and ok
        ok = assert_htaccess() and ok
        total_bytes = measure_homepage_total_bytes()
        results["homepage_total_resource_bytes"] = total_bytes
        ok = total_bytes <= 650_000 and ok
        ok = assert_team_reorder_delete_guard() and ok
        ok = assert_visual_enrichment() and ok
        ok = assert_faz47_contact_layout() and ok
        viewport_ok, shots = assert_viewport_qa()
        ok = viewport_ok and ok
        results["screenshots"] = shots
        ok = assert_scope_unchanged() and ok
        ok = assert_faz51_scope_css() and ok
        ok = assert_content_json_scope() and ok
        ok = run_verify_admin() and ok
    finally:
        CONTENT_PATH.write_bytes(content_bytes)
        restore_mail_log(mail_log_before)

    restored = CONTENT_PATH.read_bytes() == content_bytes
    assert_metric("content_json_byte_restored", 1 if restored else 0, "identical", restored)
    ok = ok and restored

    git_status_after = subprocess.run(
        ["git", "status", "--porcelain", "content/content.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    git_clean = git_status_after == git_status_before
    assert_metric("content_json_git_clean", 1 if git_clean else 0, "same as pre-test", git_clean)
    ok = ok and git_clean

    results["acceptance"] = ACCEPTANCE
    results["all_passed"] = ok and all(v["passed"] for v in ACCEPTANCE.values())
    REPORT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    if not results["all_passed"]:
        failed = [k for k, v in ACCEPTANCE.items() if not v["passed"]]
        print("FAILED:", failed, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
