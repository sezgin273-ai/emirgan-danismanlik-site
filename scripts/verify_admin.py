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
CONTENT_PATH = ROOT / "content/content.json"
UPLOADS_DIR = ROOT / "public_html/assets/img/uploads"
CSS_DIR = ROOT / "public_html/assets/css"
SHOT_DIR = ROOT / "docs/screenshots"
REPORT_PATH = SHOT_DIR / "verify-admin-report.json"
BASE = "http://localhost:8080"
TEST_PASSWORD = "TestAdmin!Faz3"
MARKER = "VERIFY_ADMIN_ROUNDTRIP_MARKER"
BASELINE_COMMIT = "543df4a"
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
        url = BASE + path if path.startswith("/") else path
        resp = self.session.request(
            method,
            url,
            data=data,
            files=files,
            allow_redirects=allow_redirects,
            timeout=30,
        )
        return resp.status_code, resp.text, dict(resp.headers)


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


def save_content_direct(data: dict) -> None:
    CONTENT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError("CSRF token bulunamadı")
    return m.group(1)


def nested_forms_in_content_form(html: str) -> int:
    m = re.search(
        r'<form[^>]*\bid=["\']content-form["\'][^>]*>(.*?)</form>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return -1
    return len(re.findall(r"<form\b", m.group(1), flags=re.IGNORECASE))


def member_names(members: list) -> list[str]:
    return [m.get("name", "") for m in members]


def assert_team_delete_ui(test_password: str, baseline_members: list) -> bool:
    ok = True
    expected_if_first_removed = baseline_members[1:]
    expected_names_if_first_removed = member_names(expected_if_first_removed)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{BASE}/admin/login.php", wait_until="networkidle")
        page.fill("#password", test_password)
        page.click('button[type="submit"]')
        page.wait_for_url("**/admin/dashboard.php")

        count_before_reject = len(load_content()["team"]["members"])
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#team-list [data-delete-team-member]").first.click()
        page.wait_for_timeout(500)
        count_after_reject = len(load_content()["team"]["members"])
        reject_ok = count_after_reject == count_before_reject
        assert_metric(
            "team_delete_ui_reject_count_unchanged",
            count_after_reject,
            f"== {count_before_reject}",
            reject_ok,
        )
        ok = ok and reject_ok

        dialog_seen = False

        def accept_dialog(dialog) -> None:
            nonlocal dialog_seen
            dialog_seen = True
            dialog.accept()

        page.once("dialog", accept_dialog)
        page.locator("#team-list [data-delete-team-member]").first.click()

        members_after_accept = load_content()["team"]["members"]
        for _ in range(40):
            members_after_accept = load_content()["team"]["members"]
            if len(members_after_accept) == len(baseline_members) - 1:
                break
            page.wait_for_timeout(250)
        names_after_accept = member_names(members_after_accept)
        accept_ok = dialog_seen and names_after_accept == expected_names_if_first_removed
        assert_metric("team_delete_ui_confirm_dialog", 1 if dialog_seen else 0, "shown", dialog_seen)
        assert_metric(
            "team_delete_ui_first_member_removed",
            1 if names_after_accept == expected_names_if_first_removed else 0,
            "index 0 removed only",
            names_after_accept == expected_names_if_first_removed,
        )
        ok = ok and accept_ok

        browser.close()

    return ok


def make_test_png(size: int = 600) -> bytes:
    img = Image.new("RGB", (size, size), color=(180, 140, 80))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_team_save_form(content: dict) -> dict[str, str]:
    form: dict[str, str] = {
        "content[team][title]": content["team"]["title"],
        "content[team][intro]": content["team"]["intro"],
    }
    for i, member in enumerate(content["team"]["members"]):
        form[f"content[team][members][{i}][name]"] = member.get("name", "")
        form[f"content[team][members][{i}][title]"] = member.get("title", "")
        form[f"content[team][members][{i}][description]"] = member.get("description", "")
        form[f"content[team][members][{i}][photo]"] = member.get("photo", "")
    return form


def original_tagline_543df4a() -> str:
    raw = subprocess.run(
        ["git", "show", f"{BASELINE_COMMIT}:content/content.json"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return json.loads(raw.decode("utf-8"))["hero"]["tagline"]


def backup_names() -> set[str]:
    return {p.name for p in (ROOT / "content/backups").glob("content-*.json")}


def backup_latest_mtime() -> float:
    files = list((ROOT / "content/backups").glob("content-*.json"))
    if not files:
        return 0.0
    return max(p.stat().st_mtime for p in files)


def snapshot_uploads() -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    if not UPLOADS_DIR.is_dir():
        return snap
    for path in UPLOADS_DIR.iterdir():
        if path.is_file() and path.name not in {".htaccess", ".gitignore"}:
            snap[path.name] = path.read_bytes()
    return snap


def restore_uploads(snap: dict[str, bytes]) -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    keep = {".htaccess", ".gitignore", *snap.keys()}
    for path in UPLOADS_DIR.iterdir():
        if path.is_file() and path.name not in keep:
            path.unlink()
    for name, data in snap.items():
        (UPLOADS_DIR / name).write_bytes(data)


def follow_redirects(client: AdminClient, start_path: str, max_hops: int = 6) -> tuple[int, str, list[str]]:
    path = start_path
    chain: list[str] = []
    for _ in range(max_hops):
        status, body, headers = client.request("GET", path)
        chain.append(f"{status} {path}")
        if status not in (301, 302, 303, 307, 308):
            return status, body, chain
        location = headers.get("Location", "")
        if not location:
            return status, body, chain
        path = location if location.startswith("/") else "/" + location.lstrip("/")
    raise RuntimeError(f"Redirect loop: {chain}")


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


def assert_css_unchanged() -> bool:
    ok = True
    for path in sorted(CSS_DIR.glob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        head = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT,
            capture_output=True,
        )
        if head.returncode != 0:
            assert_metric(f"scope_unchanged_css_{path.name}", 0, "unchanged", False)
            ok = False
            continue
        passed = hashlib.sha256(head.stdout).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest()
        assert_metric(f"scope_unchanged_css_{path.name}", 1 if passed else 0, "unchanged", passed)
        ok = ok and passed
    return ok


def admin_screenshots() -> list[str]:
    paths: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(f"{BASE}/admin/", wait_until="networkidle")
        page.wait_for_selector("#password", timeout=10000)
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


def run_admin_tests(client: AdminClient, original_content: dict) -> bool:
    ok = True

    status, _, headers = client.request("GET", "/admin/")
    loc = headers.get("Location", "")
    admin_slash_ok = status in (301, 302, 303, 307, 308) and "login" in loc.lower()
    assert_metric("admin_slash_redirect_status", status, "302 to login", admin_slash_ok)
    if admin_slash_ok:
        st2, html2, _ = client.request("GET", loc if loc.startswith("/") else "/admin/login.php")
        has_pw = 'id="password"' in html2
        assert_metric("admin_slash_login_password_field", 1 if has_pw else 0, "present", has_pw)
        ok = ok and admin_slash_ok and has_pw
    else:
        ok = False

    status, html, chain = follow_redirects(client, "/admin")
    admin_no_slash_ok = status == 200 and 'id="password"' in html
    assert_metric("admin_no_slash_reaches_login", 1 if admin_no_slash_ok else 0, "password field", admin_no_slash_ok)
    assert_metric("admin_no_slash_redirect_hops", len(chain), "<= 3", len(chain) <= 3)
    ok = ok and admin_no_slash_ok

    status, _, headers = client.request("GET", "/admin/dashboard.php")
    loc = headers.get("Location", "")
    passed = status in (301, 302, 303, 307, 308) and "login" in loc
    assert_metric("unauth_admin_redirect", status, "302 to login", passed)
    ok = ok and passed

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

    status, _, _ = client.request("POST", "/admin/actions.php", data={"action": "save_content"})
    assert_metric("csrf_missing_status", status, "403", status == 403)
    ok = ok and status == 403

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

    nested_count = nested_forms_in_content_form(html)
    nested_ok = nested_count == 0
    assert_metric("content_form_no_nested_forms", nested_count, "== 0", nested_ok)
    ok = ok and nested_ok

    team_members_before = load_content()["team"]["members"]
    team_names_before = [m.get("name", "") for m in team_members_before]
    team_delete_buttons = html.count("data-delete-team-member")
    buttons_ok = team_delete_buttons == len(team_members_before)
    assert_metric(
        "team_delete_button_per_member",
        team_delete_buttons,
        f"== {len(team_members_before)}",
        buttons_ok,
    )
    ok = ok and buttons_ok

    test_member_name = "VERIFY TEST ÜYE"
    content = load_content()
    content["team"]["members"].append(
        {
            "name": test_member_name,
            "title": "Verify Otomasyon Üyesi",
            "description": "Panel silme testi için eklendi.",
            "photo": "",
        }
    )
    add_form = {
        "csrf_token": csrf,
        "action": "save_content",
        **build_team_save_form(content),
    }
    client.request("POST", "/admin/actions.php", data=add_form, allow_redirects=True)

    content_after_add = load_content()
    member_count_after_add = len(content_after_add["team"]["members"])
    status, home_after_add, _ = client.request("GET", "/")
    test_member_visible = test_member_name in home_after_add
    assert_metric("team_add_member_count", member_count_after_add, "6", member_count_after_add == 6)
    assert_metric("team_add_member_home_visible", 1 if test_member_visible else 0, "visible", test_member_visible)
    ok = ok and member_count_after_add == 6 and test_member_visible

    test_member_index = member_count_after_add - 1
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    member_png = make_test_png(620)
    client.request(
        "POST",
        "/admin/actions.php",
        data={"csrf_token": csrf, "action": "upload_team_photo", "member_index": str(test_member_index)},
        files={"photo": ("verify-member.png", member_png, "image/png")},
        allow_redirects=True,
    )
    content_after_photo = load_content()
    test_photo_path = content_after_photo["team"]["members"][test_member_index].get("photo", "")
    test_photo_file = ROOT / "public_html" / test_photo_path.lstrip("/") if test_photo_path else None
    photo_uploaded = bool(test_photo_file and test_photo_file.is_file())
    assert_metric("team_member_photo_uploaded", 1 if photo_uploaded else 0, "file exists", photo_uploaded)
    ok = ok and photo_uploaded

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    del_status, _, _ = client.request(
        "POST",
        "/admin/actions.php",
        data={
            "csrf_token": csrf,
            "action": "delete_team_member",
            "member_index": str(test_member_index),
            "member_name": test_member_name,
        },
        allow_redirects=False,
    )
    content_after_delete = load_content()
    member_count_after_delete = len(content_after_delete["team"]["members"])
    remaining_names_after_delete = [m.get("name", "") for m in content_after_delete["team"]["members"]]
    status, home_after_delete, _ = client.request("GET", "/")
    member_removed_home = test_member_name not in home_after_delete
    photo_deleted = bool(test_photo_file) and (not test_photo_file.exists())
    names_unchanged = remaining_names_after_delete == team_names_before
    assert_metric("team_delete_post_status", del_status, "302", del_status == 302)
    assert_metric("team_delete_member_count", member_count_after_delete, "5", member_count_after_delete == 5)
    assert_metric("team_delete_member_home_absent", 1 if member_removed_home else 0, "absent", member_removed_home)
    assert_metric("team_delete_photo_removed", 1 if photo_deleted else 0, "file removed", photo_deleted)
    assert_metric("team_delete_remaining_names_preserved", 1 if names_unchanged else 0, "unchanged", names_unchanged)
    ok = ok and del_status == 302 and member_count_after_delete == 5 and member_removed_home and photo_deleted and names_unchanged

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    before_invalid_delete_count = len(load_content()["team"]["members"])
    bad_status, _, _ = client.request(
        "POST",
        "/admin/actions.php",
        data={"csrf_token": csrf, "action": "delete_team_member", "member_index": "9999"},
        allow_redirects=False,
    )
    after_invalid_delete_count = len(load_content()["team"]["members"])
    invalid_4xx = 400 <= bad_status < 500
    invalid_kept_count = before_invalid_delete_count == after_invalid_delete_count
    assert_metric("team_delete_invalid_index_status", bad_status, "4xx", invalid_4xx)
    assert_metric(
        "team_delete_invalid_index_member_count_unchanged",
        after_invalid_delete_count,
        f"== {before_invalid_delete_count}",
        invalid_kept_count,
    )
    ok = ok and invalid_4xx and invalid_kept_count

    backups_before = backup_names()
    latest_backup_before = backup_latest_mtime()

    data = json.loads(json.dumps(original_content))
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
    client.request("POST", "/admin/actions.php", data=post_data, allow_redirects=True)

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

    new_backups = backup_names() - backups_before
    latest_backup_after = backup_latest_mtime()
    backup_created = len(new_backups) >= 1 or latest_backup_after > latest_backup_before
    assert_metric(
        "backup_created_on_save",
        len(new_backups),
        ">= 1",
        backup_created,
    )
    ok = ok and backup_created

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    content = load_content()
    items = list(content["services"]["items"])
    items.append(
        {
            "title": "VERIFY TEST HİZMET",
            "description": "Admin verify otomatik test kartı",
            "icon": "strategy",
        }
    )
    form: dict[str, str] = {
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
    count8 = home.count("VERIFY TEST HİZMET")
    assert_metric("service_add_count", count8, ">= 1", count8 >= 1)
    ok = ok and count8 >= 1

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
        items[0], items[1] = items[1], items[0]
        content["services"]["items"] = items
        save_content_direct(content)

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

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    png = make_test_png(600)
    client.request(
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

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    client.request(
        "POST",
        "/admin/actions.php",
        data={"csrf_token": csrf, "action": "remove_team_photo", "member_index": "0"},
        allow_redirects=True,
    )
    status, home, _ = client.request("GET", "/")
    monogram_back = 'class="team-monogram"' in home
    assert_metric("team_photo_removed_monogram", 1 if monogram_back else 0, "monogram fallback", monogram_back)
    ok = ok and monogram_back

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

    evil = UPLOADS_DIR / "verify-evil.php"
    evil.write_text("<?php echo 'EVIL_EXECUTED';", encoding="utf-8")
    try:
        status, body, _ = client.request("GET", "/assets/img/uploads/verify-evil.php")
        blocked = status == 403 or "EVIL_EXECUTED" not in body
        assert_metric("uploads_php_blocked", status, "403 or not executed", blocked)
        ok = ok and blocked
    finally:
        evil.unlink(missing_ok=True)

    htaccess = UPLOADS_DIR / ".htaccess"
    assert_metric("uploads_htaccess_exists", 1 if htaccess.exists() else 0, "present", htaccess.exists())
    ok = ok and htaccess.exists()

    baseline_members = load_content()["team"]["members"]
    ok = assert_team_delete_ui(TEST_PASSWORD, baseline_members) and ok

    return ok


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"screenshots": [], "acceptance": {}}
    ok = True

    content_bytes = CONTENT_PATH.read_bytes()
    uploads_snap = snapshot_uploads()
    original_content = json.loads(content_bytes.decode("utf-8"))
    expected_tagline = original_tagline_543df4a()

    git_status_before = subprocess.run(
        ["git", "status", "--porcelain", "content/content.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()

    setup_admin_config()
    client = AdminClient()

    try:
        ok = run_admin_tests(client, original_content) and ok

        try:
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
        except Exception as exc:
            print(f"Screenshot warning: {exc}", file=sys.stderr)
    finally:
        CONTENT_PATH.write_bytes(content_bytes)
        restore_uploads(uploads_snap)

    restored_bytes = CONTENT_PATH.read_bytes()
    byte_ok = restored_bytes == content_bytes
    assert_metric("content_json_byte_restored", 1 if byte_ok else 0, "identical", byte_ok)
    ok = ok and byte_ok

    git_status_after = subprocess.run(
        ["git", "status", "--porcelain", "content/content.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    git_clean = git_status_after == git_status_before
    assert_metric("content_json_git_clean", 1 if git_clean else 0, "same as pre-test git status", git_clean)
    ok = ok and git_clean

    content_text = CONTENT_PATH.read_text(encoding="utf-8")
    no_marker_json = MARKER not in content_text
    assert_metric("content_json_no_marker", 1 if no_marker_json else 0, "no MARKER", no_marker_json)
    ok = ok and no_marker_json

    tagline_ok = load_content()["hero"]["tagline"] == expected_tagline
    assert_metric("hero_tagline_matches_543df4a", 1 if tagline_ok else 0, expected_tagline, tagline_ok)
    ok = ok and tagline_ok

    _, home_html, _ = client.request("GET", "/")
    no_marker_html = MARKER not in home_html
    tagline_in_html = expected_tagline in home_html
    assert_metric("homepage_no_marker", 1 if no_marker_html else 0, "no MARKER", no_marker_html)
    assert_metric("homepage_tagline_original", 1 if tagline_in_html else 0, expected_tagline, tagline_in_html)
    ok = ok and no_marker_html and tagline_in_html

    ok = assert_scope_unchanged() and ok
    ok = assert_css_unchanged() and ok

    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify_screenshots.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    frontend_ok = proc.returncode == 0
    assert_metric("frontend_verify_screenshots", proc.returncode, "0", frontend_ok)
    ok = ok and frontend_ok
    if not frontend_ok:
        print(proc.stderr or proc.stdout, file=sys.stderr)

    results["acceptance"] = ACCEPTANCE
    results["expected_tagline_543df4a"] = expected_tagline
    results["content_restore"] = {
        "byte_identical": byte_ok,
        "git_status_clean": git_clean,
    }
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
