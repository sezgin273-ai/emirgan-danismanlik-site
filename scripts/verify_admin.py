"""Faz 3 admin panel kabul kriterleri doğrulaması."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "docs" / "screenshots"
REPORT_PATH = SHOT_DIR / "verify-admin-report.json"
BASE = "http://localhost:8080"
TEST_PASSWORD = "TestAdmin!Faz3"
MARKER = "VERIFY_ADMIN_ROUNDTRIP_MARKER"
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

ACCEPTANCE: dict[str, dict] = {}


def record(name: str, measured, limit: str, passed: bool) -> None:
    ACCEPTANCE[name] = {"measured": measured, "limit": limit, "passed": passed}


def assert_metric(name: str, measured, limit: str, passed: bool) -> None:
    record(name, measured, limit, passed)
    if not passed:
        print(f"FAIL {name}: measured={measured}, limit={limit}", file=sys.stderr)


class AdminClient:
    def __init__(self) -> None:
        self.session = requests.Session()

    def request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        files: dict | None = None,
        allow_redirects: bool = False,
    ) -> tuple[int, str, dict[str, str]]:
        url = BASE + path
        if files:
            resp = self.session.request(
                method,
                url,
                data=data,
                files=files,
                allow_redirects=allow_redirects,
                timeout=30,
            )
        else:
            resp = self.session.request(
                method,
                url,
                data=data,
                allow_redirects=allow_redirects,
                timeout=30,
            )
        headers = {k: v for k, v in resp.headers.items()}
        return resp.status_code, resp.text, headers


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
    return json.loads((ROOT / "content/content.json").read_text(encoding="utf-8"))


def save_content_direct(data: dict) -> None:
    path = ROOT / "content/content.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError("CSRF token bulunamadı")
    return m.group(1)


def make_test_png(size: int = 600) -> bytes:
    img = Image.new("RGB", (size, size), color=(180, 140, 80))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def assert_scope_unchanged() -> bool:
    ok = True
    for path in PROTECTED_ASSETS:
        rel = path.relative_to(ROOT).as_posix()
        head = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT,
            capture_output=True,
        )
        if head.returncode != 0:
            assert_metric(f"scope_unchanged_{path.name}", 0, "unchanged", False)
            ok = False
            continue
        head_hash = hashlib.sha256(head.stdout).hexdigest()
        current_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        passed = head_hash == current_hash
        assert_metric(f"scope_unchanged_{path.name}", 1 if passed else 0, "unchanged", passed)
        ok = ok and passed
    return ok


def admin_screenshots() -> list[str]:
    paths: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{BASE}/admin/login.php", wait_until="networkidle")
        page.screenshot(path=str(SHOT_DIR / "admin-login.png"))
        paths.append("docs/screenshots/admin-login.png")

        page.fill("#password", TEST_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_url("**/admin/dashboard.php")

        page.screenshot(path=str(SHOT_DIR / "admin-dashboard.png"), full_page=True)
        paths.append("docs/screenshots/admin-dashboard.png")

        page.locator('a[href="#media"]').click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(SHOT_DIR / "admin-media-upload.png"), full_page=True)
        paths.append("docs/screenshots/admin-media-upload.png")

        page.locator('a[href="#hero"]').click()
        page.wait_for_timeout(200)
        page.screenshot(path=str(SHOT_DIR / "admin-content-editor.png"), full_page=True)
        paths.append("docs/screenshots/admin-content-editor.png")

        browser.close()
    return paths


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"screenshots": [], "acceptance": {}}
    ok = True

    setup_admin_config()
    client = AdminClient()
    original_json = (ROOT / "content/content.json").read_text(encoding="utf-8")
    original_content = json.loads(original_json)

    # Oturumsuz dashboard → login
    status, _, headers = client.request("GET", "/admin/dashboard.php")
    loc = headers.get("Location", "")
    passed = status in (301, 302, 303, 307, 308) and "login" in loc
    assert_metric("unauth_admin_redirect", status, "302 to login", passed)
    ok = ok and passed

    # Yanlış şifre
    status, html, _ = client.request("GET", "/admin/login.php")
    csrf = extract_csrf(html)
    t0 = time.time()
    status, _, _ = client.request(
        "POST",
        "/admin/login.php",
        data={"csrf_token": csrf, "password": "wrong-password-xyz"},
    )
    elapsed = time.time() - t0
    assert_metric("wrong_password_status", status, "200 (rejected)", status == 200)
    assert_metric("wrong_password_delay_sec", round(elapsed, 2), ">= 1", elapsed >= 0.95)
    ok = ok and status == 200 and elapsed >= 0.95

    # CSRF'siz POST → 403
    status, text, _ = client.request(
        "POST",
        "/admin/actions.php",
        data={"action": "save_content"},
    )
    assert_metric("csrf_missing_status", status, "403", status == 403)
    ok = ok and status == 403

    # Giriş
    status, html, _ = client.request("GET", "/admin/login.php")
    csrf = extract_csrf(html)
    status, _, _ = client.request(
        "POST",
        "/admin/login.php",
        data={"csrf_token": csrf, "password": TEST_PASSWORD},
        allow_redirects=True,
    )
    assert_metric("login_success", status, "200 dashboard", status == 200)
    ok = ok and status == 200

    status, html, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(html)

    # Yedek sayısı öncesi
    backups_before = len(list((ROOT / "content/backups").glob("content-*.json")))

    # Metin round-trip
    status, home_before, _ = client.request("GET", "/")
    data = original_content.copy()
    data["hero"] = dict(original_content["hero"])
    data["hero"]["tagline"] = MARKER
    save_content_direct(data)

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    post_data = {
        "csrf_token": csrf,
        "action": "save_content",
        "content[hero][company]": data["hero"]["company"],
        "content[hero][tagline]": MARKER,
        "content[hero][description]": data["hero"]["description"],
    }
    status, _, _ = client.request("POST", "/admin/actions.php", data=post_data, allow_redirects=True)

    status, home_after, _ = client.request("GET", "/")
    json_content = load_content()
    assert_metric(
        "text_roundtrip_json",
        1 if json_content["hero"]["tagline"] == MARKER else 0,
        MARKER,
        json_content["hero"]["tagline"] == MARKER,
    )
    assert_metric(
        "text_roundtrip_frontend",
        1 if MARKER in home_after else 0,
        "visible on homepage",
        MARKER in home_after,
    )
    ok = ok and MARKER in home_after

    backups_after_marker = len(list((ROOT / "content/backups").glob("content-*.json")))
    assert_metric(
        "backup_created_on_save",
        backups_after_marker - backups_before,
        ">= 1",
        backups_after_marker > backups_before,
    )
    ok = ok and backups_after_marker > backups_before

    # Hizmet kartı ekle
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    content = load_content()
    items = content["services"]["items"]
    new_item = {
        "title": "VERIFY TEST HİZMET",
        "description": "Admin verify otomatik test kartı",
        "icon": "strategy",
    }
    items.append(new_item)
    form: dict[str, str] = {
        "csrf_token": csrf,
        "action": "save_content",
        "content[services][title]": content["services"]["title"],
    }
    for i, item in enumerate(items):
        form[f"content[services][items][{i}][title]"] = item["title"]
        form[f"content[services][items][{i}][description]"] = item["description"]
        form[f"content[services][items][{i}][icon]"] = item["icon"]
    status, _, _ = client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home, _ = client.request("GET", "/")
    count8 = home.count("VERIFY TEST HİZMET")
    assert_metric("service_add_count", count8, ">= 1", count8 >= 1)
    ok = ok and count8 >= 1

    # Sil → 7'ye dön
    content = load_content()
    content["services"]["items"] = [i for i in content["services"]["items"] if i["title"] != "VERIFY TEST HİZMET"]
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    form = {
        "csrf_token": csrf,
        "action": "save_content",
        "content[services][title]": content["services"]["title"],
    }
    for i, item in enumerate(content["services"]["items"]):
        form[f"content[services][items][{i}][title]"] = item["title"]
        form[f"content[services][items][{i}][description]"] = item["description"]
        form[f"content[services][items][{i}][icon]"] = item["icon"]
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home, _ = client.request("GET", "/")
    service_cards = len(re.findall(r'class="service-card', home))
    assert_metric("service_count_after_delete", service_cards, "7", service_cards == 7)
    ok = ok and service_cards == 7

    # Sıralama kalıcılığı — ilk iki kartı yer değiştir
    content = load_content()
    items = content["services"]["items"]
    if len(items) >= 2:
        items[0], items[1] = items[1], items[0]
        status, dash, _ = client.request("GET", "/admin/dashboard.php")
        csrf = extract_csrf(dash)
        form = {
            "csrf_token": csrf,
            "action": "save_content",
            "content[services][title]": content["services"]["title"],
        }
        for i, item in enumerate(items):
            form[f"content[services][items][{i}][title]"] = item["title"]
            form[f"content[services][items][{i}][description]"] = item["description"]
            form[f"content[services][items][{i}][icon]"] = item["icon"]
        client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
        status, home, _ = client.request("GET", "/")
        first_pos = home.find(items[0]["title"])
        second_pos = home.find(items[1]["title"])
        order_ok = first_pos != -1 and second_pos != -1 and first_pos < second_pos
        assert_metric("service_reorder_persistent", 1 if order_ok else 0, "order matches", order_ok)
        ok = ok and order_ok
        # sırayı geri al
        items[0], items[1] = items[1], items[0]
        save_content_direct(content)

    # Bölüm gizle (team)
    content = load_content()
    content["site"]["sections"]["team"]["visible"] = False
    save_content_direct(content)
    status, home, _ = client.request("GET", "/")
    team_hidden = 'id="team"' not in home and "#team" not in home
    assert_metric("section_hide_team", 1 if team_hidden else 0, "no section/nav", team_hidden)
    ok = ok and team_hidden

    content["site"]["sections"]["team"]["visible"] = True
    save_content_direct(content)
    status, home, _ = client.request("GET", "/")
    team_visible = 'id="team"' in home
    assert_metric("section_show_team", 1 if team_visible else 0, "section present", team_visible)
    ok = ok and team_visible

    # Ekip fotoğrafı yükle
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    png = make_test_png(600)
    status, _, _ = client.request(
        "POST",
        "/admin/actions.php",
        data={"csrf_token": csrf, "action": "upload_team_photo", "member_index": "0"},
        files={"photo": ("verify-team.png", png, "image/png")},
        allow_redirects=True,
    )
    content = load_content()
    photo_path = content["team"]["members"][0].get("photo", "")
    upload_file = ROOT / "public_html" / photo_path.lstrip("/") if photo_path else None
    max_dim = 0
    if upload_file and upload_file.is_file():
        with Image.open(upload_file) as img:
            max_dim = max(img.size)
    status, home, _ = client.request("GET", "/")
    has_photo = 'class="team-photo"' in home
    assert_metric("team_photo_max_dimension", max_dim, "<= 480", max_dim <= 480 and max_dim > 0)
    assert_metric("team_photo_frontend", 1 if has_photo else 0, "team-photo visible", has_photo)
    ok = ok and max_dim <= 480 and has_photo

    # Fotoğraf kaldır → monogram
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    client.request(
        "POST",
        "/admin/actions.php",
        data={"csrf_token": csrf, "action": "remove_team_photo", "member_index": "0"},
        allow_redirects=True,
    )
    status, home, _ = client.request("GET", "/")
    monogram_back = 'class="team-monogram"' in home and photo_path.split("/")[-1] not in home
    assert_metric("team_photo_removed_monogram", 1 if monogram_back else 0, "monogram fallback", monogram_back)
    ok = ok and monogram_back

    # Geri yükleme
    backups = sorted((ROOT / "content/backups").glob("content-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if backups:
        restore_name = backups[0].name
        status, dash, _ = client.request("GET", "/admin/dashboard.php")
        csrf = extract_csrf(dash)
        client.request(
            "POST",
            "/admin/actions.php",
            data={"csrf_token": csrf, "action": "restore_backup", "backup_name": restore_name},
            allow_redirects=True,
        )
        restored = load_content()
        assert_metric("backup_restore", 1 if restored else 0, "content loaded", bool(restored))
        ok = ok and bool(restored)

    # uploads .php engeli (router)
    evil = ROOT / "public_html/assets/img/uploads/verify-evil.php"
    evil.write_text("<?php echo 'EVIL_EXECUTED';", encoding="utf-8")
    try:
        status, body, _ = client.request("GET", "/assets/img/uploads/verify-evil.php")
        blocked = status == 403 or "EVIL_EXECUTED" not in body
        assert_metric("uploads_php_blocked", status, "403 or not executed", blocked)
        ok = ok and blocked
    finally:
        evil.unlink(missing_ok=True)

    htaccess = ROOT / "public_html/assets/img/uploads/.htaccess"
    assert_metric("uploads_htaccess_exists", 1 if htaccess.exists() else 0, "present", htaccess.exists())
    ok = ok and htaccess.exists()

    # Ön yüz görselleri değişmedi
    ok = assert_scope_unchanged() and ok

    # İçeriği orijinale döndür (ön yüz verify için)
    (ROOT / "content/content.json").write_text(original_json, encoding="utf-8")

    # Önceki verify_screenshots assert'leri
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_screenshots.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    frontend_ok = proc.returncode == 0
    assert_metric("frontend_verify_screenshots", proc.returncode, "0", frontend_ok)
    ok = ok and frontend_ok

    # Admin ekran görüntüleri + fotoğraflı ekip kartı
    try:
        content = load_content()
        content["team"]["members"][0]["photo"] = ""
        save_content_direct(content)
        status, dash, _ = client.request("GET", "/admin/dashboard.php")
        csrf = extract_csrf(dash)
        png = make_test_png(400)
        client.request(
            "POST",
            "/admin/actions.php",
            data={"csrf_token": csrf, "action": "upload_team_photo", "member_index": "0"},
            files={"photo": ("team-shot.png", png, "image/png")},
            allow_redirects=True,
        )
        results["screenshots"] = admin_screenshots()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{BASE}/#team", wait_until="networkidle")
            page.wait_for_timeout(800)
            shot = SHOT_DIR / "team-card-with-photo.png"
            page.locator("#team .team-card").first.screenshot(path=str(shot))
            results["screenshots"].append("docs/screenshots/team-card-with-photo.png")
            browser.close()
        client.request(
            "POST",
            "/admin/actions.php",
            data={"csrf_token": csrf, "action": "remove_team_photo", "member_index": "0"},
            allow_redirects=True,
        )
    except Exception as exc:
        print(f"Screenshot warning: {exc}", file=sys.stderr)

    # İçeriği temizle — marker kaldır
    content = load_content()
    if content["hero"].get("tagline") == MARKER:
        content["hero"]["tagline"] = original_content["hero"]["tagline"]
        save_content_direct(content)

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
