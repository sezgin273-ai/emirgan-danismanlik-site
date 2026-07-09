"""Faz 3 admin panel kabul kriterleri doğrulaması."""
from __future__ import annotations

import hashlib
import html
import json
import re
import subprocess
import sys
import shutil
import time
from io import BytesIO
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from urllib.parse import quote

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CONTENT_PATH = ROOT / "content/content.json"
CONTENT_EN_PATH = ROOT / "content/content.en.json"
CONTENT_DE_PATH = ROOT / "content/content.de.json"
CONTENT_RU_PATH = ROOT / "content/content.ru.json"
CONTENT_FA_PATH = ROOT / "content/content.fa.json"
UPLOADS_DIR = ROOT / "public_html/assets/img/uploads"
CSS_DIR = ROOT / "public_html/assets/css"
SHOT_DIR = ROOT / "docs/screenshots"
REPORT_PATH = SHOT_DIR / "verify-admin-report.json"
BASE = "http://localhost:8080"
TEST_PASSWORD = ".eE951623"
MARKER = "VERIFY_ADMIN_ROUNDTRIP_MARKER"
MARKER_EN = "VERIFY_ADMIN_EN_ROUNDTRIP_MARKER"
MARKER_DE = "VERIFY_ADMIN_DE_ROUNDTRIP_MARKER"
MARKER_RU = "VERIFY_ADMIN_RU_ROUNDTRIP_MARKER"
MARKER_FA = "VERIFY_ADMIN_FA_ROUNDTRIP_MARKER"
STRUCT_SERVICE_MARKER = "VERIFY_FAZ56_STRUCTURE_SERVICE"
STRUCT_HOURS_MARKER = "VERIFY_FAZ58_HOURS_ROW"
HOURS_ROUNDTRIP_MARKERS = {
    "en": "VERIFY_FAZ58_HOURS_EN",
    "de": "VERIFY_FAZ58_HOURS_DE",
    "ru": "VERIFY_FAZ58_HOURS_RU",
    "fa": "VERIFY_FAZ58_HOURS_FA",
}
HOURS_CLOSED_EXPECTED = {
    "tr": "Kapalı",
    "en": "Closed",
    "de": "Geschlossen",
    "ru": "Закрыто",
    "fa": "تعطیل",
}
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


def load_content_lang(lang: str) -> dict:
    paths = {
        "en": CONTENT_EN_PATH,
        "de": CONTENT_DE_PATH,
        "ru": CONTENT_RU_PATH,
        "fa": CONTENT_FA_PATH,
    }
    path = paths.get(lang, CONTENT_PATH)
    return json.loads(path.read_text(encoding="utf-8"))


def content_paths_set(obj: object, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                paths |= content_paths_set(value, child)
            else:
                paths.add(child)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            child = f"{prefix}[{i}]"
            if isinstance(value, (dict, list)):
                paths |= content_paths_set(value, child)
            else:
                paths.add(child)
    return paths


def assert_content_key_parity() -> bool:
    tr_paths = content_paths_set(load_content())
    ok = True
    for lang, path in (("en", CONTENT_EN_PATH), ("de", CONTENT_DE_PATH), ("ru", CONTENT_RU_PATH), ("fa", CONTENT_FA_PATH)):
        loc_paths = content_paths_set(json.loads(path.read_text(encoding="utf-8")))
        missing = len(tr_paths - loc_paths)
        extra = len(loc_paths - tr_paths)
        assert_metric(f"admin_lang_{lang}_missing_keys", missing, "0", missing == 0)
        assert_metric(f"admin_lang_{lang}_extra_keys", extra, "0", extra == 0)
        ok = ok and missing == 0 and extra == 0
    return ok


def lang_independent_values_match() -> bool:
    tr = load_content()
    ok = True
    for lang in ("en", "de", "ru", "fa"):
        loc = load_content_lang(lang)
        checks = [
            tr.get("site", {}).get("url") == loc.get("site", {}).get("url"),
            tr.get("site", {}).get("assets") == loc.get("site", {}).get("assets"),
            tr.get("display") == loc.get("display"),
            [i.get("icon") for i in tr.get("services", {}).get("items", [])]
            == [i.get("icon") for i in loc.get("services", {}).get("items", [])],
            [m.get("photo") for m in tr.get("team", {}).get("members", [])]
            == [m.get("photo") for m in loc.get("team", {}).get("members", [])],
        ]
        passed = all(checks)
        assert_metric(f"admin_lang_independent_match_{lang}", 1 if passed else 0, "byte-identical fields", passed)
        ok = ok and passed
    return ok


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
        "content[team][members_present]": "1",
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


def backups_created_since(since_mtime: float) -> int:
    return sum(
        1
        for path in (ROOT / "content/backups").glob("content-*.json")
        if path.stat().st_mtime > since_mtime
    )


SECTION_IDS = ["hero", "intro", "services", "about", "process", "team", "contact"]
NAV_SECTION_IDS = {"hero", "services", "about", "team", "contact"}
SAVE_ALL_BTN = "button.admin-btn--primary"
CONTACT_MAP_MARKER = "VERIFY_MAP_ADDR_MARKER"


def playwright_admin_login(page, test_password: str) -> None:
    page.goto(f"{BASE}/admin/login.php", wait_until="networkidle")
    page.fill("#password", test_password)
    page.click('button[type="submit"]')
    page.wait_for_url("**/admin/dashboard.php")


def click_save_all_content(page) -> None:
    page.locator(SAVE_ALL_BTN, has_text="Tüm İçeriği Kaydet").click()
    try:
        page.wait_for_url("**/admin/dashboard.php", timeout=15000)
    except Exception:
        page.wait_for_load_state("networkidle", timeout=5000)


def set_section_visible_checkbox(page, section_id: str, visible: bool) -> None:
    if "/admin/dashboard.php" not in page.url:
        page.goto(f"{BASE}/admin/dashboard.php", wait_until="networkidle")
    page.locator('a[href="#sections"]').click()
    cb = page.locator(f'input[name="content[site][sections][{section_id}][visible]"]')
    if visible:
        cb.check()
    else:
        cb.uncheck()


def assert_faz46b_checkbox_and_lists(test_password: str, original_content: dict) -> bool:
    ok = True
    original = json.loads(json.dumps(original_content))
    save_content_direct(original)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        playwright_admin_login(page, test_password)

        for sid in SECTION_IDS:
            set_section_visible_checkbox(page, sid, False)
            click_save_all_content(page)
            visible_json = load_content()["site"]["sections"][sid]["visible"] is False
            errors: list[str] = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(BASE + "/?lang=tr", wait_until="networkidle")
            html = page.content()
            section_gone = f'id="{sid}"' not in html
            nav_gone = sid not in NAV_SECTION_IDS or f'data-nav-link="{sid}"' not in html
            hide_ok = visible_json and section_gone and nav_gone and len(errors) == 0
            assert_metric(f"section_{sid}_hide_json", 1 if visible_json else 0, "false", visible_json)
            assert_metric(f"section_{sid}_hide_frontend", 1 if hide_ok else 0, "absent + console 0", hide_ok)
            ok = ok and hide_ok

            set_section_visible_checkbox(page, sid, True)
            click_save_all_content(page)
            visible_show = load_content()["site"]["sections"][sid]["visible"] is True
            page.goto(BASE + "/?lang=tr", wait_until="networkidle")
            html_show = page.content()
            section_back = f'id="{sid}"' in html_show
            nav_back = sid not in NAV_SECTION_IDS or f'data-nav-link="{sid}"' in html_show
            show_ok = visible_show and section_back and nav_back
            assert_metric(f"section_{sid}_show_json", 1 if visible_show else 0, "true", visible_show)
            assert_metric(f"section_{sid}_show_frontend", 1 if show_ok else 0, "present", show_ok)
            ok = ok and show_ok

        page.goto(f"{BASE}/admin/dashboard.php", wait_until="networkidle")
        page.locator('a[href="#hero"]').click()
        wm_cb = page.locator('input[name="content[hero][watermark_enabled]"][type="checkbox"]')
        wm_cb.uncheck()
        click_save_all_content(page)
        wm_off_json = not load_content()["hero"]["watermark_enabled"]
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        wm_off = page.evaluate(
            """() => ({
              watermark: document.querySelector('.hero-watermark'),
              titleColor: getComputedStyle(document.querySelector('.hero-title')).color,
            })"""
        )
        off_ok = (
            wm_off_json
            and wm_off["watermark"] is None
            and wm_off["titleColor"] == "rgb(248, 244, 240)"
        )
        assert_metric("hero_watermark_form_off_json", 1 if wm_off_json else 0, "false", wm_off_json)
        assert_metric("hero_watermark_form_off_frontend", 1 if off_ok else 0, "no layer + color", off_ok)
        ok = ok and off_ok

        page.goto(f"{BASE}/admin/dashboard.php", wait_until="networkidle")
        page.locator('a[href="#hero"]').click()
        wm_cb.check()
        click_save_all_content(page)
        wm_on_json = bool(load_content()["hero"]["watermark_enabled"])
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        wm_on = page.evaluate(
            """() => {
              const el = document.querySelector('.hero-watermark');
              if (!el) return { exists: false, display: '', pointerEvents: '' };
              const s = getComputedStyle(el);
              return { exists: true, display: s.display, pointerEvents: s.pointerEvents };
            }"""
        )
        on_ok = (
            wm_on_json
            and wm_on.get("exists")
            and wm_on.get("display") == "none"
            and wm_on.get("pointerEvents") == "none"
        )
        assert_metric("hero_watermark_form_on_json", 1 if wm_on_json else 0, "true", wm_on_json)
        assert_metric("hero_watermark_form_on_frontend", 1 if on_ok else 0, "display:none", on_ok)
        ok = ok and on_ok

        save_content_direct(original)
        page.goto(f"{BASE}/admin/dashboard.php", wait_until="networkidle")
        page.locator('a[href="#intro"]').click()
        while page.locator("#badges-list [data-remove-item]").count() > 0:
            page.locator("#badges-list [data-remove-item]").first.click()
        click_save_all_content(page)
        badges = load_content()["intro"]["badges"]
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        badge_count = page.locator(".badge-item").count()
        intro_html = page.content()
        badges_ok = badges == [] and badge_count == 0 and "Warning" not in intro_html and "Notice" not in intro_html
        assert_metric("intro_badges_empty_json", len(badges), "0", badges == [])
        assert_metric("intro_badges_empty_frontend", badge_count, "0", badges_ok)
        ok = ok and badges_ok

        save_content_direct(original)
        page.goto(f"{BASE}/admin/dashboard.php", wait_until="networkidle")
        page.locator('a[href="#process"]').click()
        page.evaluate(
            "() => document.querySelectorAll('#process-list [data-sortable-item]').forEach(el => el.remove())"
        )
        click_save_all_content(page)
        steps = load_content()["process"]["steps"]
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        process_html = page.content()
        steps_ok = (
            steps == []
            and 'id="process"' not in process_html
            and "Warning" not in process_html
            and "Notice" not in process_html
        )
        assert_metric("process_steps_empty_json", len(steps), "0", steps == [])
        assert_metric("process_steps_empty_frontend", 1 if steps_ok else 0, "absent + no PHP noise", steps_ok)
        ok = ok and steps_ok

        browser.close()

    save_content_direct(original)
    return ok


def assert_contact_hours_admin(test_password: str) -> bool:
    ok = True
    content = load_content()
    hours_rows = content.get("contact", {}).get("hours", {}).get("rows", [])
    if len(hours_rows) < 1:
        assert_metric("contact_hours_admin_seed", 0, ">=1 row", False)
        return False
    original_value = hours_rows[0]["value"]
    marked_value = original_value + " (QA)"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        playwright_admin_login(page, test_password)

        page.locator('a[href="#contact"]').click()
        page.locator('input[name="content[contact][hours][rows][0][value]"]').fill(marked_value)
        click_save_all_content(page)
        page.goto(BASE + "/?lang=tr#contact", wait_until="networkidle")
        shown = page.locator(".contact-hours-row").first.locator("dd").inner_text()
        round_ok = marked_value in shown
        assert_metric("contact_hours_value_roundtrip", 1 if round_ok else 0, "marked on frontend", round_ok)
        ok = ok and round_ok

        page.goto(f"{BASE}/admin/dashboard.php#contact", wait_until="networkidle")
        page.locator('a[href="#contact"]').click()
        page.locator('input[name="content[contact][hours][rows][0][value]"]').fill(original_value)
        click_save_all_content(page)
        restore_ok = page.locator('input[name="content[contact][hours][rows][0][value]"]').input_value() == original_value
        assert_metric("contact_hours_value_restore", 1 if restore_ok else 0, "original value", restore_ok)
        ok = ok and restore_ok

        page.locator("[data-add-contact-hours]").click()
        idx = page.locator("#contact-hours-list [data-sortable-item]").count() - 1
        page.locator(f'input[name="content[contact][hours][rows][{idx}][label]"]').fill("Test Gün")
        page.locator(f'input[name="content[contact][hours][rows][{idx}][value]"]').fill("10:00 – 12:00")
        click_save_all_content(page)
        page.goto(BASE + "/?lang=tr#contact", wait_until="networkidle")
        count3 = page.locator(".contact-hours-row").count()
        assert_metric("contact_hours_add_row_count", count3, "3", count3 == 3)
        ok = ok and count3 == 3

        page.goto(f"{BASE}/admin/dashboard.php#contact", wait_until="networkidle")
        page.locator('a[href="#contact"]').click()
        dialog_seen = False

        def accept_dialog(dialog) -> None:
            nonlocal dialog_seen
            dialog_seen = True
            dialog.accept()

        page.once("dialog", accept_dialog)
        page.locator("[data-delete-contact-hours]").last.click()
        page.wait_for_timeout(800)
        count2 = len(load_content()["contact"]["hours"]["rows"])
        assert_metric("contact_hours_delete_row_count", count2, "2", count2 == 2)
        assert_metric("contact_hours_delete_confirm", 1 if dialog_seen else 0, "confirm shown", dialog_seen)
        ok = ok and count2 == 2 and dialog_seen

        page.locator("#contact-hours-list [data-sort-down]").first.click()
        page.wait_for_timeout(200)
        page.once("dialog", lambda d: d.accept())
        with page.expect_response(lambda r: "/admin/actions.php" in r.url) as resp_info:
            page.locator("[data-delete-contact-hours]").first.click()
        status = resp_info.value.status
        rows_unchanged = len(load_content()["contact"]["hours"]["rows"]) == 2
        assert_metric("contact_hours_unsaved_delete_status", status, "409", status == 409)
        assert_metric("contact_hours_unsaved_delete_unchanged", 1 if rows_unchanged else 0, "unchanged", rows_unchanged)
        ok = ok and status == 409 and rows_unchanged

        browser.close()

    return ok


def assert_contact_map_roundtrip(test_password: str) -> bool:
    ok = True
    content = load_content()
    info_items = content["contact"].get("info_items", [])
    original_text = info_items[0]["value"] if info_items else content["contact"]["addresses"][0]["text"]
    marked_text = original_text + " " + CONTACT_MAP_MARKER

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        playwright_admin_login(page, test_password)
        page.locator('a[href="#contact"]').click()
        page.locator('textarea[name="content[contact][info_items][0][value]"]').fill(marked_text)
        click_save_all_content(page)
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        src = page.locator(".contact-map-iframe").get_attribute("src") or ""
        encoded_marked = quote(marked_text, safe="")
        marker_ok = encoded_marked in src and "output=embed" in src
        assert_metric("contact_map_address_roundtrip", 1 if marker_ok else 0, "marker in iframe src", marker_ok)
        ok = ok and marker_ok

        page.goto(f"{BASE}/admin/dashboard.php", wait_until="networkidle")
        page.locator('a[href="#contact"]').click()
        page.locator('textarea[name="content[contact][info_items][0][value]"]').fill(original_text)
        click_save_all_content(page)
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        src_restored = page.locator(".contact-map-iframe").get_attribute("src") or ""
        encoded_orig = quote(original_text, safe="")
        restored_ok = encoded_orig in src_restored and CONTACT_MAP_MARKER not in src_restored
        assert_metric("contact_map_address_restore", 1 if restored_ok else 0, "original src", restored_ok)
        ok = ok and restored_ok
        browser.close()

    return ok


def snapshot_backups() -> dict[str, bytes]:
    snap: dict[str, bytes] = {}
    backup_dir = ROOT / "content/backups"
    if not backup_dir.is_dir():
        return snap
    for path in backup_dir.iterdir():
        if path.is_file():
            snap[path.name] = path.read_bytes()
    return snap


def restore_backups(snap: dict[str, bytes]) -> None:
    backup_dir = ROOT / "content/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    keep = set(snap.keys())
    for path in backup_dir.iterdir():
        if path.is_file() and path.name not in keep:
            path.unlink()
    for name, data in snap.items():
        (backup_dir / name).write_bytes(data)


DISPLAY_GROUPS = [
    ("header_logo", ".brand-logo", "height"),
    ("footer_logo", ".footer-logo", "height"),
    ("team_avatar", ".team-avatar", "width"),
    ("service_icon", ".service-icon", "width"),
    ("hero_emblem", ".hero-medallion", "width"),
]


def assert_faz48_admin(test_password: str) -> bool:
    ok = True
    backup_dir = ROOT / "content/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    content_before = CONTENT_PATH.read_bytes()
    http = AdminClient()
    login_html = http.request("GET", "/admin/login.php")[1]
    login_csrf = extract_csrf(login_html)
    http.request(
        "POST",
        "/admin/login.php",
        data={"csrf_token": login_csrf, "password": test_password},
        allow_redirects=True,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        playwright_admin_login(page, test_password)

        test_name = "content-2099-01-01_120000.json"
        test_backup = backup_dir / test_name
        source_backup = next(iter(sorted(backup_dir.glob("content-*.json"), key=lambda p: p.stat().st_mtime)), None)
        if source_backup is not None:
            shutil.copy2(source_backup, test_backup)
        else:
            test_backup.write_text(CONTENT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        page.goto(f"{BASE}/admin/dashboard.php#backups", wait_until="networkidle")
        page.reload(wait_until="networkidle")
        listed = test_name in page.content()
        delete_btn = page.locator(f'[data-delete-backup][data-backup-name="{test_name}"]')
        assert_metric("backup_delete_test_listed", 1 if listed else 0, "test backup visible", listed)
        ok = ok and listed
        if listed:
            other_backups = [b.name for b in backup_dir.glob("content-*.json") if b.name != test_backup.name]
            page.once("dialog", lambda d: d.accept())
            delete_btn.click()
            page.wait_for_timeout(800)
            deleted_ok = not test_backup.exists()
            others_ok = all((backup_dir / name).exists() for name in other_backups[:3])
            assert_metric("backup_delete_ui_removed", 1 if deleted_ok else 0, "file gone", deleted_ok)
            assert_metric("backup_delete_others_preserved", 1 if others_ok else 0, "others exist", others_ok)
            ok = ok and deleted_ok and others_ok
        else:
            assert_metric("backup_delete_ui_removed", 0, "file gone", False)
            ok = False

        _, dash, _ = http.request("GET", "/admin/dashboard.php")
        csrf = extract_csrf(dash)
        trav_status, _, _ = http.request(
            "POST",
            "/admin/actions.php",
            data={"csrf_token": csrf, "action": "delete_backup", "backup_name": "../../content/content.json"},
            allow_redirects=False,
        )
        trav_ok = trav_status == 422 and CONTENT_PATH.read_bytes() == content_before
        assert_metric("backup_delete_path_traversal_status", trav_status, "422", trav_status == 422)
        ok = ok and trav_ok

        backups = sorted(backup_dir.glob("content-*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if backups:
            target = backups[0].name
            page.goto(f"{BASE}/admin/dashboard.php#backups", wait_until="networkidle")
            row = page.locator(f'.admin-backup-item:has(input[name="backup_name"][value="{target}"])')
            row.locator('input[name="backup_label"]').fill("Verify Etiket")
            row.locator('button:has-text("Etiket Kaydet")').click()
            page.wait_for_url("**/admin/dashboard.php**")
            labels_path = backup_dir / ".labels.json"
            label_ok = labels_path.is_file() and "Verify Etiket" in labels_path.read_text(encoding="utf-8")
            badge_ok = "En güncel" in page.content()
            assert_metric("backup_label_saved", 1 if label_ok else 0, "sidecar label", label_ok)
            assert_metric("backup_latest_badge_visible", 1 if badge_ok else 0, "En güncel", badge_ok)
            ok = ok and label_ok and badge_ok

            _, dash, _ = http.request("GET", "/admin/dashboard.php")
            csrf = extract_csrf(dash)
            bad_label_status, _, _ = http.request(
                "POST",
                "/admin/actions.php",
                data={"csrf_token": csrf, "action": "label_backup", "backup_name": target, "backup_label": "../evil"},
                allow_redirects=False,
            )
            bad_label_ok = bad_label_status == 422
            assert_metric("backup_label_traversal_status", bad_label_status, "422", bad_label_ok)
            ok = ok and bad_label_ok

        page.goto(f"{BASE}/admin/dashboard.php#media", wait_until="networkidle")
        png = make_test_png(400)
        _, dash, _ = http.request("GET", "/admin/dashboard.php")
        csrf = extract_csrf(dash)
        http.request(
            "POST",
            "/admin/actions.php",
            data={"csrf_token": csrf, "action": "upload_team_photo", "member_index": "0"},
            files={"photo": ("faz48-remove.png", png, "image/png")},
            allow_redirects=True,
        )
        content_after_upload = load_content()
        photo_path = content_after_upload["team"]["members"][0].get("photo", "")
        photo_file = ROOT / "public_html" / photo_path.lstrip("/") if photo_path else None
        uploaded_ok = bool(photo_path) and bool(photo_file and photo_file.is_file())
        assert_metric("team_photo_remove_upload_ready", 1 if uploaded_ok else 0, "photo on disk", uploaded_ok)
        ok = ok and uploaded_ok
        page.goto(f"{BASE}/admin/dashboard.php#team", wait_until="networkidle")
        page.reload(wait_until="networkidle")
        remove_count = page.locator("#team-list [data-remove-team-photo]").count()
        assert_metric("team_photo_remove_button_visible", remove_count, ">= 1", remove_count >= 1)
        ok = ok and remove_count >= 1
        if remove_count == 0:
            browser.close()
            return ok
        page.once("dialog", lambda d: d.dismiss())
        if page.locator("#team-list [data-remove-team-photo]").count() > 0:
            page.locator("#team-list [data-remove-team-photo]").first.click()
            page.wait_for_timeout(500)
        reject_photo = load_content()["team"]["members"][0].get("photo", "")
        reject_ok = reject_photo == photo_path
        assert_metric("team_photo_remove_reject_unchanged", 1 if reject_ok else 0, "photo kept", reject_ok)
        ok = ok and reject_ok

        page.once("dialog", lambda d: d.accept())
        page.locator("#team-list [data-remove-team-photo]").first.click()
        for _ in range(30):
            if load_content()["team"]["members"][0].get("photo", "") == "":
                break
            page.wait_for_timeout(200)
        photo_cleared = load_content()["team"]["members"][0].get("photo", "") == ""
        file_gone = bool(photo_file) and not photo_file.exists()
        page.goto(BASE + "/?lang=tr#team", wait_until="networkidle")
        monogram_ok = page.locator(".team-card").first.locator(".team-monogram").count() == 1
        assert_metric("team_photo_remove_cleared_json", 1 if photo_cleared else 0, "empty photo", photo_cleared)
        assert_metric("team_photo_remove_file_deleted", 1 if file_gone else 0, "orphan removed", file_gone)
        assert_metric("team_photo_remove_monogram_ui", 1 if monogram_ok else 0, "monogram", monogram_ok)
        ok = ok and photo_cleared and file_gone and monogram_ok

        no_photo_btn = page.locator("#team-list [data-remove-team-photo]").count() == 0
        assert_metric("team_photo_remove_button_hidden", 1 if no_photo_btn else 0, "no button", no_photo_btn)
        ok = ok and no_photo_btn

        page.goto(f"{BASE}/admin/dashboard.php#contact", wait_until="networkidle")
        page.locator("[data-add-contact-info]").click()
        idx = page.locator("#contact-info-list [data-sortable-item]").count() - 1
        page.locator(f'select[name="content[contact][info_items][{idx}][type]"]').select_option("phone")
        page.locator(f'input[name="content[contact][info_items][{idx}][title]"]').fill("Telefon")
        page.locator(f'textarea[name="content[contact][info_items][{idx}][value]"]').fill("+90 212 555 0101")
        click_save_all_content(page)
        page.goto(BASE + "/?lang=tr#contact", wait_until="networkidle")
        phone_layout = page.evaluate(
            """() => {
              const email = document.querySelector('.contact-info-email');
              const phone = Array.from(document.querySelectorAll('.contact-info-grid .address-card a[href^="tel:"]')).pop();
              if (!email || !phone) return { ok: false };
              const er = email.getBoundingClientRect();
              const pr = phone.closest('.address-card').getBoundingClientRect();
              const sideBySide = Math.abs(er.top - pr.top) <= 8;
              const href = phone.getAttribute('href') || '';
              const overflow = document.documentElement.scrollWidth <= window.innerWidth;
              return { ok: sideBySide && href.includes('tel:') && overflow, sideBySide, href };
            }"""
        )
        phone_ok = phone_layout.get("ok")
        assert_metric("contact_phone_add_side_by_side", 1 if phone_layout.get("sideBySide") else 0, "top <=8px", phone_layout.get("sideBySide"))
        assert_metric("contact_phone_tel_link", 1 if "tel:" in str(phone_layout.get("href", "")) else 0, "tel:", "tel:" in str(phone_layout.get("href", "")))
        ok = ok and phone_ok

        page.goto(f"{BASE}/admin/dashboard.php#contact", wait_until="networkidle")
        page.once("dialog", lambda d: d.accept())
        page.locator("#contact-info-list [data-delete-contact-info]").last.click()
        page.wait_for_timeout(800)
        restored_items = len(load_content()["contact"]["info_items"])
        assert_metric("contact_phone_delete_restored_count", restored_items, "3", restored_items == 3)
        ok = ok and restored_items == 3

        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        medium_sizes = page.evaluate("""() => document.querySelector('.brand-logo').getBoundingClientRect().height""")
        page.goto(f"{BASE}/admin/dashboard.php#display", wait_until="networkidle")
        page.select_option("#display-header_logo", "large")
        click_save_all_content(page)
        page.goto(BASE + "/?lang=tr", wait_until="networkidle")
        sizes = page.evaluate(
            """() => {
              const logo = document.querySelector('.brand-logo');
              const rect = logo.getBoundingClientRect();
              const header = document.querySelector('.site-header');
              const headerOverflow = header ? header.scrollWidth <= header.clientWidth + 1 : true;
              return { logoH: rect.height, headerH: header.getBoundingClientRect().height, overflow: headerOverflow };
            }"""
        )
        page.goto(f"{BASE}/admin/dashboard.php#display", wait_until="networkidle")
        page.select_option("#display-header_logo", "medium")
        click_save_all_content(page)
        logo_large_ok = sizes["logoH"] >= medium_sizes * 1.25
        header_ok = sizes["headerH"] <= 96
        large_ok = logo_large_ok and header_ok
        assert_metric(
            "display_header_logo_large_height_px",
            round(sizes["logoH"], 1),
            f">= {round(medium_sizes * 1.25, 1)}",
            logo_large_ok,
        )
        assert_metric("display_header_logo_header_height_px", round(sizes["headerH"], 1), "<= 96", header_ok)
        ok = ok and large_ok

        _, dash, _ = http.request("GET", "/admin/dashboard.php")
        csrf = extract_csrf(dash)
        invalid_display = http.request(
            "POST",
            "/admin/actions.php",
            data={
                "csrf_token": csrf,
                "action": "save_content",
                "content[display][header_logo]": "huge",
            },
            allow_redirects=False,
        )
        invalid_ok = invalid_display[0] == 422
        assert_metric("display_invalid_size_status", invalid_display[0], "422", invalid_ok)
        ok = ok and invalid_ok

        browser.close()

    return ok


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
    """Faz 4.7: tokens.css HEAD ile bayt-özdeş; main.css bu turda değişebilir."""
    ok = True
    for name in ("tokens.css",):
        path = CSS_DIR / name
        rel = path.relative_to(ROOT).as_posix()
        head = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT,
            capture_output=True,
        )
        if head.returncode != 0:
            assert_metric(f"scope_unchanged_css_{name}", 0, "unchanged", False)
            ok = False
            continue
        passed = hashlib.sha256(head.stdout).hexdigest() == hashlib.sha256(path.read_bytes()).hexdigest()
        assert_metric(f"scope_unchanged_css_{name}", 1 if passed else 0, "unchanged", passed)
        ok = ok and passed
    return ok


def build_process_save_form(content: dict) -> dict[str, str]:
    form: dict[str, str] = {
        "admin_lang": "tr",
        "content[process][title]": content.get("process", {}).get("title", ""),
        "content[process][steps_present]": "1",
    }
    for i, step in enumerate(content.get("process", {}).get("steps", [])):
        form[f"content[process][steps][{i}][title]"] = step.get("title", "")
        form[f"content[process][steps][{i}][description]"] = step.get("description", "")
    return form


def build_services_save_form(content: dict) -> dict[str, str]:
    form: dict[str, str] = {
        "admin_lang": "tr",
        "content[services][title]": content["services"]["title"],
        "content[services][items_present]": "1",
    }
    for i, item in enumerate(content["services"]["items"]):
        form[f"content[services][items][{i}][title]"] = item["title"]
        form[f"content[services][items][{i}][description]"] = item["description"]
        form[f"content[services][items][{i}][icon]"] = item.get("icon", "strategy")
    return form


def service_svg_signatures(html: str) -> list[str]:
    cards = re.findall(r'class="service-card[^"]*"[^>]*>(.*?)</article>', html, flags=re.DOTALL)
    sigs: list[str] = []
    for card in cards:
        paths = re.findall(r'<path[^>]+d="([^"]+)"', card)
        sigs.append("|".join(paths))
    return sigs


def process_step_titles(html: str) -> list[str]:
    return [
        html.unescape(m)
        for m in re.findall(r'class="process-step-title"[^>]*>\s*([^<]+?)\s*<', html)
    ]


def assert_faz46_admin(client: AdminClient, test_password: str, original_content: dict) -> bool:
    ok = True
    save_content_direct(json.loads(json.dumps(original_content)))
    original = json.loads(json.dumps(original_content))
    process_marker = "VERIFY_PROCESS_TITLE_MARKER"
    step_marker = "VERIFY_STEP_DESC_MARKER"

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)

    data = json.loads(json.dumps(original))
    data["process"]["title"] = process_marker
    data["process"]["steps"][0]["description"] = step_marker
    form = {"csrf_token": csrf, "action": "save_content", **build_process_save_form(data)}
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home, _ = client.request("GET", "/?lang=tr")
    roundtrip_ok = process_marker in home and step_marker in home
    assert_metric("process_text_roundtrip_frontend", 1 if roundtrip_ok else 0, "visible", roundtrip_ok)
    ok = ok and roundtrip_ok

    save_content_direct(original)
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)

    data = json.loads(json.dumps(load_content()))
    data["process"]["steps"].append(
        {
            "title": "VERIFY TEST ADIM",
            "description": "Admin verify otomasyon test adımı.",
        }
    )
    form = {"csrf_token": csrf, "action": "save_content", **build_process_save_form(data)}
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    steps_after_add = len(load_content()["process"]["steps"])
    status, home, _ = client.request("GET", "/?lang=tr")
    add_ok = steps_after_add == 5 and home.count("VERIFY TEST ADIM") >= 1
    assert_metric("process_add_step_count", steps_after_add, "5", steps_after_add == 5)
    assert_metric("process_add_step_home_visible", 1 if "VERIFY TEST ADIM" in home else 0, "visible", "VERIFY TEST ADIM" in home)
    ok = ok and add_ok

    save_content_direct(original)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"{BASE}/admin/login.php", wait_until="networkidle")
        page.fill("#password", test_password)
        page.click('button[type="submit"]')
        page.wait_for_url("**/admin/dashboard.php")

        steps_before = [s.get("title", "") for s in load_content()["process"]["steps"]]
        count_before_reject = len(steps_before)
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator("#process-list [data-delete-process-step]").first.click()
        page.wait_for_timeout(500)
        count_after_reject = len(load_content()["process"]["steps"])
        reject_ok = count_after_reject == count_before_reject
        assert_metric("process_delete_ui_reject_count_unchanged", count_after_reject, f"== {count_before_reject}", reject_ok)
        ok = ok and reject_ok

        dialog_seen = False

        def accept_dialog(dialog) -> None:
            nonlocal dialog_seen
            dialog_seen = True
            dialog.accept()

        page.once("dialog", accept_dialog)
        with page.expect_response(lambda r: "/admin/actions.php" in r.url) as resp_info:
            page.locator("#process-list [data-delete-process-step]").first.click()
        delete_resp = resp_info.value
        page.wait_for_timeout(500)
        steps_after_delete = [s.get("title", "") for s in load_content()["process"]["steps"]]
        expected_after = steps_before[1:]
        delete_ok = dialog_seen and steps_after_delete == expected_after and delete_resp.status in (200, 302)
        assert_metric("process_delete_ui_confirm_dialog", 1 if dialog_seen else 0, "shown", dialog_seen)
        assert_metric(
            "process_delete_ui_first_step_removed",
            1 if steps_after_delete == expected_after else 0,
            "index 0 removed only",
            steps_after_delete == expected_after,
        )
        ok = ok and delete_ok

        save_content_direct(original)
        page.reload(wait_until="networkidle")
        page.locator('a[href="#process"]').click()
        page.wait_for_timeout(300)

        steps_before_sort = [s.get("title", "") for s in load_content()["process"]["steps"]]
        page.locator("#process-list [data-sort-down]").first.click()
        page.wait_for_timeout(300)
        page.locator('#content-form button[type="submit"]').click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        reordered = load_content()["process"]["steps"]
        json_ok = (
            len(reordered) == len(steps_before_sort)
            and reordered[0]["title"] == steps_before_sort[1]
            and reordered[1]["title"] == steps_before_sort[0]
        )
        page.goto(f"{BASE}/?lang=tr#process", wait_until="networkidle")
        page.wait_for_timeout(1000)
        body_text = page.evaluate("() => document.getElementById('process')?.innerText ?? ''")
        first_idx = body_text.find(reordered[0]["title"]) if json_ok else -1
        second_idx = body_text.find(reordered[1]["title"]) if json_ok else -1
        home_ok = first_idx != -1 and second_idx != -1 and first_idx < second_idx
        reorder_ok = json_ok and home_ok
        assert_metric("process_reorder_json", 1 if json_ok else 0, "swapped", json_ok)
        assert_metric(
            "process_reorder_home",
            f"{first_idx},{second_idx}",
            "first before second",
            home_ok,
        )
        assert_metric("process_reorder_persistent", 1 if reorder_ok else 0, "order matches", reorder_ok)
        ok = ok and reorder_ok

        save_content_direct(original)
        page.goto(f"{BASE}/admin/dashboard.php#process", wait_until="networkidle")
        page.wait_for_timeout(300)

        unsaved_before = [s.get("title", "") for s in load_content()["process"]["steps"]]
        page.locator("#process-list [data-sort-down]").first.click()
        page.wait_for_timeout(300)
        guard_dialog = False

        def accept_guard(dialog) -> None:
            nonlocal guard_dialog
            guard_dialog = True
            dialog.accept()

        page.once("dialog", accept_guard)
        with page.expect_response(lambda r: "/admin/actions.php" in r.url) as guard_resp:
            page.locator("#process-list [data-delete-process-step]").first.click()
        guard_status = guard_resp.value.status
        page.wait_for_timeout(400)
        unsaved_after = [s.get("title", "") for s in load_content()["process"]["steps"]]
        guard_ok = guard_status == 409 and unsaved_after == unsaved_before
        assert_metric("process_delete_unsaved_sort_status", guard_status, "409", guard_status == 409)
        assert_metric(
            "process_delete_unsaved_sort_unchanged",
            1 if unsaved_after == unsaved_before else 0,
            "unchanged",
            unsaved_after == unsaved_before,
        )
        ok = ok and guard_ok

        browser.close()

    save_content_direct(original)
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    bad_status, _, _ = client.request(
        "POST",
        "/admin/actions.php",
        data={
            "csrf_token": csrf,
            "action": "delete_process_step",
            "step_index": "9999",
            "step_title": "x",
        },
        allow_redirects=False,
    )
    invalid_ok = bad_status == 422
    assert_metric("process_delete_invalid_index_status", bad_status, "422", invalid_ok)
    ok = ok and invalid_ok

    content_empty = load_content()
    content_empty["process"]["steps"] = []
    save_content_direct(content_empty)
    status, home, _ = client.request("GET", "/?lang=tr")
    empty_ok = 'id="process"' not in home and "Warning" not in home and "Notice" not in home
    assert_metric("process_all_steps_removed_no_section", 1 if empty_ok else 0, "absent + no PHP noise", empty_ok)
    ok = ok and empty_ok
    save_content_direct(original)

    status, home_before, _ = client.request("GET", "/?lang=tr")
    sigs_before = service_svg_signatures(home_before)
    content_icon = load_content()
    alt_icon = "legal" if content_icon["services"]["items"][0].get("icon") != "legal" else "finance"
    content_icon["services"]["items"][0]["icon"] = alt_icon
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    form = {"csrf_token": csrf, "action": "save_content", **build_services_save_form(content_icon)}
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home_after, _ = client.request("GET", "/?lang=tr")
    sigs_after = service_svg_signatures(home_after)
    icon_change_ok = (
        len(sigs_before) == len(sigs_after) == 7
        and sigs_before[0] != sigs_after[0]
        and sigs_before[1:] == sigs_after[1:]
    )
    assert_metric("service_icon_change_first_only", 1 if icon_change_ok else 0, "first svg changed", icon_change_ok)
    ok = ok and icon_change_ok
    save_content_direct(original)

    content_svc = load_content()
    content_svc["services"]["items"].append(
        {
            "title": "VERIFY ICON TEST HİZMET",
            "description": "İkon varsayılan testi",
            "icon": "strategy",
        }
    )
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    form = {"csrf_token": csrf, "action": "save_content", **build_services_save_form(content_svc)}
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home, _ = client.request("GET", "/?lang=tr")
    svg_count = home.count("<svg")
    service_cards = len(re.findall(r'class="service-card', home))
    add_svc_ok = service_cards == 8 and svg_count >= 8 and home.count("VERIFY ICON TEST HİZMET") >= 1
    assert_metric("service_add_icon_svg_count", service_cards, "8", service_cards == 8)
    assert_metric("service_add_no_iconless_card", 1 if add_svc_ok else 0, "all have svg", add_svc_ok)
    ok = ok and add_svc_ok
    save_content_direct(original)

    bytes_before = CONTENT_PATH.read_bytes()
    content_bad = load_content()
    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    form = {"csrf_token": csrf, "action": "save_content", **build_services_save_form(content_bad)}
    form["content[services][items][0][icon]"] = "not-a-valid-icon"
    bad_icon_status, _, _ = client.request("POST", "/admin/actions.php", data=form, allow_redirects=False)
    bytes_after = CONTENT_PATH.read_bytes()
    bad_icon_ok = bad_icon_status == 422 and bytes_before == bytes_after
    assert_metric("service_icon_invalid_post_status", bad_icon_status, "422", bad_icon_status == 422)
    assert_metric("service_icon_invalid_content_unchanged", 1 if bytes_before == bytes_after else 0, "unchanged", bytes_before == bytes_after)
    ok = ok and bad_icon_ok

    save_content_direct(original)
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

        page.locator('a[href="#process"]').click()
        page.wait_for_timeout(200)
        page.screenshot(path=str(SHOT_DIR / "admin-process-editor.png"), full_page=True)
        paths.append("docs/screenshots/admin-process-editor.png")

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
    status, home_after_add, _ = client.request("GET", "/?lang=tr")
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
    status, home_after_delete, _ = client.request("GET", "/?lang=tr")
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
        "admin_lang": "tr",
        "content[hero][company]": data["hero"]["company"],
        "content[hero][tagline]": MARKER,
        "content[hero][description]": data["hero"]["description"],
    }
    client.request("POST", "/admin/actions.php", data=post_data, allow_redirects=True)

    status, home_after, _ = client.request("GET", "/?lang=tr")
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
    measured_backups = len(new_backups) if new_backups else backups_created_since(latest_backup_before)
    backup_created = measured_backups >= 1
    assert_metric(
        "backup_created_on_save",
        measured_backups,
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
        "admin_lang": "tr",
        "content[services][title]": content["services"]["title"],
        "content[services][items_present]": "1",
    }
    for i, item in enumerate(items):
        form[f"content[services][items][{i}][title]"] = item["title"]
        form[f"content[services][items][{i}][description]"] = item["description"]
        form[f"content[services][items][{i}][icon]"] = item["icon"]
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home, _ = client.request("GET", "/?lang=tr")
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
        "content[services][items_present]": "1",
    }
    for i, item in enumerate(content["services"]["items"]):
        form[f"content[services][items][{i}][title]"] = item["title"]
        form[f"content[services][items][{i}][description]"] = item["description"]
        form[f"content[services][items][{i}][icon]"] = item["icon"]
    client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
    status, home, _ = client.request("GET", "/?lang=tr")
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
            "content[services][items_present]": "1",
        }
        for i, item in enumerate(items):
            form[f"content[services][items][{i}][title]"] = item["title"]
            form[f"content[services][items][{i}][description]"] = item["description"]
            form[f"content[services][items][{i}][icon]"] = item["icon"]
        client.request("POST", "/admin/actions.php", data=form, allow_redirects=True)
        status, home, _ = client.request("GET", "/?lang=tr")
        first_pos = home.find(items[0]["title"])
        second_pos = home.find(items[1]["title"])
        order_ok = first_pos != -1 and second_pos != -1 and first_pos < second_pos
        assert_metric("service_reorder_persistent", 1 if order_ok else 0, "order matches", order_ok)
        ok = ok and order_ok
        items[0], items[1] = items[1], items[0]
        content["services"]["items"] = items
        save_content_direct(content)

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
    status, home, _ = client.request("GET", "/?lang=tr")
    has_photo = 'class="team-photo"' in home
    assert_metric("team_photo_max_dimension", max_dim, "<= 480", max_dim <= 480 and max_dim > 0)
    assert_metric("team_photo_frontend", 1 if has_photo else 0, "team-photo visible", has_photo)
    ok = ok and max_dim <= 480 and has_photo

    status, dash, _ = client.request("GET", "/admin/dashboard.php")
    csrf = extract_csrf(dash)
    member0_name = load_content()["team"]["members"][0]["name"]
    client.request(
        "POST",
        "/admin/actions.php",
        data={
            "csrf_token": csrf,
            "action": "remove_team_photo",
            "member_index": "0",
            "member_name": member0_name,
        },
        allow_redirects=True,
    )
    status, home, _ = client.request("GET", "/?lang=tr")
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
    ok = assert_faz46_admin(client, TEST_PASSWORD, original_content) and ok
    ok = assert_faz46b_checkbox_and_lists(TEST_PASSWORD, original_content) and ok
    ok = assert_contact_hours_admin(TEST_PASSWORD) and ok
    ok = assert_contact_map_roundtrip(TEST_PASSWORD) and ok
    ok = assert_team_delete_ui(TEST_PASSWORD, baseline_members) and ok
    ok = assert_faz48_admin(TEST_PASSWORD) and ok
    ok = assert_faz56_admin_multilang(TEST_PASSWORD) and ok
    ok = assert_faz58_hours_multilang(TEST_PASSWORD) and ok

    return ok


def assert_faz58_hours_code() -> bool:
    ok = True
    src = (ROOT / "public_html/includes/admin_multilang.php").read_text(encoding="utf-8")
    override_count = len(re.findall(r"\$targetRows\[\$i\]\['value'\]\s*=\s*\$trRow\['value'\]", src))
    assert_metric("faz58_apply_hours_value_override", override_count, "0", override_count == 0)
    ok = ok and override_count == 0

    sync_ok = (
        "'value' => (is_array($locRow) && trim((string) ($locRow['value'] ?? '')) !== '')"
        in src
    )
    assert_metric("faz58_sync_hours_value_preserve", 1 if sync_ok else 0, "loc-first", sync_ok)
    ok = ok and sync_ok
    return ok


def contact_hours_paths_set(hours: object, prefix: str = "contact.hours") -> set[str]:
    return content_paths_set(hours, prefix) if isinstance(hours, dict) else set()


def assert_hours_key_parity() -> bool:
    ok = True
    tr_hours = load_content().get("contact", {}).get("hours", {})
    tr_paths = contact_hours_paths_set(tr_hours)
    for lang in ("en", "de", "ru", "fa"):
        loc_hours = load_content_lang(lang).get("contact", {}).get("hours", {})
        loc_paths = contact_hours_paths_set(loc_hours)
        missing = len(tr_paths - loc_paths)
        extra = len(loc_paths - tr_paths)
        assert_metric(f"faz58_hours_{lang}_missing_keys", missing, "0", missing == 0)
        assert_metric(f"faz58_hours_{lang}_extra_keys", extra, "0", extra == 0)
        ok = ok and missing == 0 and extra == 0
    return ok


def hours_closed_value(lang: str) -> str:
    if lang == "tr":
        return load_content()["contact"]["hours"]["rows"][1]["value"]
    return load_content_lang(lang)["contact"]["hours"]["rows"][1]["value"]


def assert_faz58_hours_multilang(test_password: str) -> bool:
    ok = assert_faz58_hours_code() and assert_hours_key_parity()
    all_bytes_before = {
        "tr": CONTENT_PATH.read_bytes(),
        "en": CONTENT_EN_PATH.read_bytes(),
        "de": CONTENT_DE_PATH.read_bytes(),
        "ru": CONTENT_RU_PATH.read_bytes(),
        "fa": CONTENT_FA_PATH.read_bytes(),
    }
    closed_before = {lang: HOURS_CLOSED_EXPECTED[lang] for lang in HOURS_CLOSED_EXPECTED}
    roundtrip_passed = {lang: False for lang in HOURS_ROUNDTRIP_MARKERS}
    isolation_passed = {lang: False for lang in HOURS_ROUNDTRIP_MARKERS}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{BASE}/admin/login.php", wait_until="networkidle")
            page.fill("#password", test_password)
            page.click('button[type="submit"]')
            page.wait_for_url("**/admin/dashboard.php")

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=tr", wait_until="networkidle")
            count_before = len(load_content()["contact"]["hours"]["rows"])
            page.click("[data-add-contact-hours]")
            page.wait_for_timeout(200)
            idx = page.locator("#contact-hours-list [data-sortable-item]").count() - 1
            page.locator(f'input[name="content[contact][hours][rows][{idx}][label]"]').fill(STRUCT_HOURS_MARKER)
            page.locator(f'input[name="content[contact][hours][rows][{idx}][value]"]').fill("09:00 – 12:00")
            page.click('#content-form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)

            counts = {
                "tr": len(load_content()["contact"]["hours"]["rows"]),
                "en": len(load_content_lang("en")["contact"]["hours"]["rows"]),
                "de": len(load_content_lang("de")["contact"]["hours"]["rows"]),
                "ru": len(load_content_lang("ru")["contact"]["hours"]["rows"]),
                "fa": len(load_content_lang("fa")["contact"]["hours"]["rows"]),
            }
            structure_count_ok = all(c == count_before + 1 for c in counts.values())
            assert_metric("faz58_hours_structure_row_parity", 1 if structure_count_ok else 0, str(count_before + 1), structure_count_ok)
            ok = ok and structure_count_ok

            for lang in ("en", "de", "ru", "fa"):
                closed_now = load_content_lang(lang)["contact"]["hours"]["rows"][1]["value"]
                seeded = any(
                    row.get("label") == STRUCT_HOURS_MARKER
                    for row in load_content_lang(lang)["contact"]["hours"]["rows"]
                )
                assert_metric(f"faz58_hours_structure_closed_{lang}", 1 if closed_now == closed_before[lang] else 0, closed_before[lang], closed_now == closed_before[lang])
                assert_metric(f"faz58_hours_structure_seed_{lang}", 1 if seeded else 0, STRUCT_HOURS_MARKER, seeded)
                ok = ok and closed_now == closed_before[lang] and seeded

            page.once("dialog", lambda d: d.accept())
            page.locator("[data-delete-contact-hours]").last.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)

            for lang, marker in HOURS_ROUNDTRIP_MARKERS.items():
                snap_before = {
                    "tr": CONTENT_PATH.read_bytes(),
                    "en": CONTENT_EN_PATH.read_bytes(),
                    "de": CONTENT_DE_PATH.read_bytes(),
                    "ru": CONTENT_RU_PATH.read_bytes(),
                    "fa": CONTENT_FA_PATH.read_bytes(),
                }
                page.goto(f"{BASE}/admin/dashboard.php?admin_lang={lang}", wait_until="networkidle")
                page.locator('input[name="content[contact][hours][rows][1][value]"]').fill(marker)
                page.click('#content-form button[type="submit"]')
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(800)

                saved = load_content_lang(lang)["contact"]["hours"]["rows"][1]["value"] == marker
                others_unchanged = all(
                    {
                        "tr": CONTENT_PATH,
                        "en": CONTENT_EN_PATH,
                        "de": CONTENT_DE_PATH,
                        "ru": CONTENT_RU_PATH,
                        "fa": CONTENT_FA_PATH,
                    }[other].read_bytes() == snap_before[other]
                    for other in snap_before
                    if other != lang
                )
                assert_metric(f"faz58_hours_roundtrip_{lang}", 1 if saved else 0, marker, saved)
                assert_metric(f"faz58_hours_isolation_{lang}", 1 if others_unchanged else 0, "4 files unchanged", others_unchanged)
                roundtrip_passed[lang] = saved
                isolation_passed[lang] = others_unchanged
                ok = ok and saved and others_unchanged

                page.goto(f"{BASE}/admin/dashboard.php?admin_lang={lang}", wait_until="networkidle")
                reloaded = page.locator('input[name="content[contact][hours][rows][1][value]"]').input_value() == marker
                assert_metric(f"faz58_hours_reload_{lang}", 1 if reloaded else 0, marker, reloaded)
                roundtrip_passed[lang] = roundtrip_passed[lang] and reloaded
                ok = ok and reloaded

            passed_roundtrip = sum(1 for v in roundtrip_passed.values() if v)
            assert_metric("faz58_hours_roundtrip_total", passed_roundtrip, "4", passed_roundtrip == 4)
            ok = ok and passed_roundtrip == 4

            browser.close()
    finally:
        CONTENT_PATH.write_bytes(all_bytes_before["tr"])
        CONTENT_EN_PATH.write_bytes(all_bytes_before["en"])
        CONTENT_DE_PATH.write_bytes(all_bytes_before["de"])
        CONTENT_RU_PATH.write_bytes(all_bytes_before["ru"])
        CONTENT_FA_PATH.write_bytes(all_bytes_before["fa"])

    tr_hours_head = json.loads(
        subprocess.run(
            ["git", "show", "HEAD:content/content.json"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
    )["contact"]["hours"]
    tr_hours_unchanged = load_content()["contact"]["hours"] == tr_hours_head
    assert_metric("faz58_tr_hours_block_unchanged", 1 if tr_hours_unchanged else 0, "unchanged", tr_hours_unchanged)
    ok = ok and tr_hours_unchanged

    return ok


def assert_faz56_admin_multilang(test_password: str) -> bool:
    ok = True
    tr_bytes_before = CONTENT_PATH.read_bytes()
    en_bytes_before = CONTENT_EN_PATH.read_bytes()
    de_bytes_before = CONTENT_DE_PATH.read_bytes()
    ru_bytes_before = CONTENT_RU_PATH.read_bytes()
    fa_bytes_before = CONTENT_FA_PATH.read_bytes()
    en_tagline_before = load_content_lang("en")["hero"]["tagline"]
    de_tagline_before = load_content_lang("de")["hero"]["tagline"]
    ru_tagline_before = load_content_lang("ru")["hero"]["tagline"]
    fa_tagline_before = load_content_lang("fa")["hero"]["tagline"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{BASE}/admin/login.php", wait_until="networkidle")
            page.fill("#password", test_password)
            page.click('button[type="submit"]')
            page.wait_for_url("**/admin/dashboard.php")

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=en", wait_until="networkidle")
            en_field = page.locator("#hero-tagline")
            en_loaded = en_field.input_value() == en_tagline_before
            assert_metric("admin_lang_switch_en_editor", 1 if en_loaded else 0, "EN hero tagline", en_loaded)
            ok = ok and en_loaded

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=de", wait_until="networkidle")
            de_field = page.locator("#hero-tagline")
            de_loaded = de_field.input_value() == de_tagline_before
            assert_metric("admin_lang_switch_de_editor", 1 if de_loaded else 0, "DE hero tagline", de_loaded)
            ok = ok and de_loaded

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=ru", wait_until="networkidle")
            ru_field = page.locator("#hero-tagline")
            ru_loaded = ru_field.input_value() == ru_tagline_before
            assert_metric("admin_lang_switch_ru_editor", 1 if ru_loaded else 0, "RU hero tagline", ru_loaded)
            ok = ok and ru_loaded

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=fa", wait_until="networkidle")
            fa_field = page.locator("#hero-tagline")
            fa_loaded = fa_field.input_value() == fa_tagline_before
            assert_metric("admin_lang_switch_fa_editor", 1 if fa_loaded else 0, "FA hero tagline", fa_loaded)
            ok = ok and fa_loaded

            structural_count = page.locator(
                '[data-add-service], [data-add-team], [data-add-process], '
                '[data-add-contact-info], [data-add-contact-hours], '
                '[data-sort-up], [data-delete-team-member]'
            ).count()
            assert_metric("admin_lang_fa_structural_controls", structural_count, "0", structural_count == 0)
            ok = ok and structural_count == 0

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=en", wait_until="networkidle")
            snap_before_en = {
                "tr": CONTENT_PATH.read_bytes(),
                "de": CONTENT_DE_PATH.read_bytes(),
                "ru": CONTENT_RU_PATH.read_bytes(),
                "fa": CONTENT_FA_PATH.read_bytes(),
            }
            page.fill("#hero-tagline", MARKER_EN)
            page.click('#content-form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)

            en_json_ok = load_content_lang("en")["hero"]["tagline"] == MARKER_EN
            assert_metric("admin_en_roundtrip_json", 1 if en_json_ok else 0, MARKER_EN, en_json_ok)
            assert_metric("admin_en_roundtrip_tr_bytes", 1 if CONTENT_PATH.read_bytes() == snap_before_en["tr"] else 0, "unchanged", CONTENT_PATH.read_bytes() == snap_before_en["tr"])
            assert_metric("admin_en_roundtrip_de_bytes", 1 if CONTENT_DE_PATH.read_bytes() == snap_before_en["de"] else 0, "unchanged", CONTENT_DE_PATH.read_bytes() == snap_before_en["de"])
            assert_metric("admin_en_roundtrip_ru_bytes", 1 if CONTENT_RU_PATH.read_bytes() == snap_before_en["ru"] else 0, "unchanged", CONTENT_RU_PATH.read_bytes() == snap_before_en["ru"])
            assert_metric("admin_en_roundtrip_fa_bytes", 1 if CONTENT_FA_PATH.read_bytes() == snap_before_en["fa"] else 0, "unchanged", CONTENT_FA_PATH.read_bytes() == snap_before_en["fa"])
            ok = ok and en_json_ok
            ok = ok and CONTENT_PATH.read_bytes() == snap_before_en["tr"]
            ok = ok and CONTENT_DE_PATH.read_bytes() == snap_before_en["de"]
            ok = ok and CONTENT_RU_PATH.read_bytes() == snap_before_en["ru"]
            ok = ok and CONTENT_FA_PATH.read_bytes() == snap_before_en["fa"]

            page.goto(f"{BASE}/?lang=en", wait_until="networkidle")
            en_frontend = MARKER_EN in page.content()
            assert_metric("admin_en_roundtrip_frontend", 1 if en_frontend else 0, "visible", en_frontend)
            ok = ok and en_frontend

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=de", wait_until="networkidle")
            snap_before_de = {
                "tr": CONTENT_PATH.read_bytes(),
                "en": CONTENT_EN_PATH.read_bytes(),
                "ru": CONTENT_RU_PATH.read_bytes(),
                "fa": CONTENT_FA_PATH.read_bytes(),
            }
            page.fill("#hero-tagline", MARKER_DE)
            page.click('#content-form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)
            de_json_ok = load_content_lang("de")["hero"]["tagline"] == MARKER_DE
            assert_metric("admin_de_roundtrip_json", 1 if de_json_ok else 0, MARKER_DE, de_json_ok)
            assert_metric("admin_de_roundtrip_tr_bytes", 1 if CONTENT_PATH.read_bytes() == snap_before_de["tr"] else 0, "unchanged", CONTENT_PATH.read_bytes() == snap_before_de["tr"])
            assert_metric("admin_de_roundtrip_en_bytes", 1 if CONTENT_EN_PATH.read_bytes() == snap_before_de["en"] else 0, "unchanged", CONTENT_EN_PATH.read_bytes() == snap_before_de["en"])
            assert_metric("admin_de_roundtrip_ru_bytes", 1 if CONTENT_RU_PATH.read_bytes() == snap_before_de["ru"] else 0, "unchanged", CONTENT_RU_PATH.read_bytes() == snap_before_de["ru"])
            assert_metric("admin_de_roundtrip_fa_bytes", 1 if CONTENT_FA_PATH.read_bytes() == snap_before_de["fa"] else 0, "unchanged", CONTENT_FA_PATH.read_bytes() == snap_before_de["fa"])
            ok = ok and de_json_ok
            ok = ok and CONTENT_PATH.read_bytes() == snap_before_de["tr"]
            ok = ok and CONTENT_EN_PATH.read_bytes() == snap_before_de["en"]
            ok = ok and CONTENT_RU_PATH.read_bytes() == snap_before_de["ru"]
            ok = ok and CONTENT_FA_PATH.read_bytes() == snap_before_de["fa"]

            page.goto(f"{BASE}/?lang=de", wait_until="networkidle")
            de_frontend = MARKER_DE in page.content()
            assert_metric("admin_de_roundtrip_frontend", 1 if de_frontend else 0, "visible", de_frontend)
            ok = ok and de_frontend

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=ru", wait_until="networkidle")
            snap_before_ru = {
                "tr": CONTENT_PATH.read_bytes(),
                "en": CONTENT_EN_PATH.read_bytes(),
                "de": CONTENT_DE_PATH.read_bytes(),
                "fa": CONTENT_FA_PATH.read_bytes(),
            }
            page.fill("#hero-tagline", MARKER_RU)
            page.click('#content-form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)
            ru_json_ok = load_content_lang("ru")["hero"]["tagline"] == MARKER_RU
            assert_metric("admin_ru_roundtrip_json", 1 if ru_json_ok else 0, MARKER_RU, ru_json_ok)
            assert_metric("admin_ru_roundtrip_tr_bytes", 1 if CONTENT_PATH.read_bytes() == snap_before_ru["tr"] else 0, "unchanged", CONTENT_PATH.read_bytes() == snap_before_ru["tr"])
            assert_metric("admin_ru_roundtrip_en_bytes", 1 if CONTENT_EN_PATH.read_bytes() == snap_before_ru["en"] else 0, "unchanged", CONTENT_EN_PATH.read_bytes() == snap_before_ru["en"])
            assert_metric("admin_ru_roundtrip_de_bytes", 1 if CONTENT_DE_PATH.read_bytes() == snap_before_ru["de"] else 0, "unchanged", CONTENT_DE_PATH.read_bytes() == snap_before_ru["de"])
            assert_metric("admin_ru_roundtrip_fa_bytes", 1 if CONTENT_FA_PATH.read_bytes() == snap_before_ru["fa"] else 0, "unchanged", CONTENT_FA_PATH.read_bytes() == snap_before_ru["fa"])
            ok = ok and ru_json_ok
            ok = ok and CONTENT_PATH.read_bytes() == snap_before_ru["tr"]
            ok = ok and CONTENT_EN_PATH.read_bytes() == snap_before_ru["en"]
            ok = ok and CONTENT_DE_PATH.read_bytes() == snap_before_ru["de"]
            ok = ok and CONTENT_FA_PATH.read_bytes() == snap_before_ru["fa"]

            page.goto(f"{BASE}/?lang=ru", wait_until="networkidle")
            ru_frontend = MARKER_RU in page.content()
            assert_metric("admin_ru_roundtrip_frontend", 1 if ru_frontend else 0, "visible", ru_frontend)
            ok = ok and ru_frontend

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=fa", wait_until="networkidle")
            snap_before_fa = {
                "tr": CONTENT_PATH.read_bytes(),
                "en": CONTENT_EN_PATH.read_bytes(),
                "de": CONTENT_DE_PATH.read_bytes(),
                "ru": CONTENT_RU_PATH.read_bytes(),
            }
            page.fill("#hero-tagline", MARKER_FA)
            page.click('#content-form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)
            fa_json_ok = load_content_lang("fa")["hero"]["tagline"] == MARKER_FA
            assert_metric("admin_fa_roundtrip_json", 1 if fa_json_ok else 0, MARKER_FA, fa_json_ok)
            assert_metric("admin_fa_roundtrip_tr_bytes", 1 if CONTENT_PATH.read_bytes() == snap_before_fa["tr"] else 0, "unchanged", CONTENT_PATH.read_bytes() == snap_before_fa["tr"])
            assert_metric("admin_fa_roundtrip_en_bytes", 1 if CONTENT_EN_PATH.read_bytes() == snap_before_fa["en"] else 0, "unchanged", CONTENT_EN_PATH.read_bytes() == snap_before_fa["en"])
            assert_metric("admin_fa_roundtrip_de_bytes", 1 if CONTENT_DE_PATH.read_bytes() == snap_before_fa["de"] else 0, "unchanged", CONTENT_DE_PATH.read_bytes() == snap_before_fa["de"])
            assert_metric("admin_fa_roundtrip_ru_bytes", 1 if CONTENT_RU_PATH.read_bytes() == snap_before_fa["ru"] else 0, "unchanged", CONTENT_RU_PATH.read_bytes() == snap_before_fa["ru"])
            ok = ok and fa_json_ok
            ok = ok and CONTENT_PATH.read_bytes() == snap_before_fa["tr"]
            ok = ok and CONTENT_EN_PATH.read_bytes() == snap_before_fa["en"]
            ok = ok and CONTENT_DE_PATH.read_bytes() == snap_before_fa["de"]
            ok = ok and CONTENT_RU_PATH.read_bytes() == snap_before_fa["ru"]

            page.goto(f"{BASE}/?lang=fa", wait_until="networkidle")
            fa_frontend = MARKER_FA in page.content()
            fa_dir = page.locator("html").get_attribute("dir") or ""
            assert_metric("admin_fa_roundtrip_frontend", 1 if fa_frontend else 0, "visible", fa_frontend)
            assert_metric("admin_fa_roundtrip_dir", fa_dir, "rtl", fa_dir == "rtl")
            ok = ok and fa_frontend and fa_dir == "rtl"

            page.goto(f"{BASE}/admin/dashboard.php?admin_lang=tr", wait_until="networkidle")
            service_count_before = len(load_content()["services"]["items"])
            page.click("[data-add-service]")
            page.wait_for_timeout(200)
            page.locator('#services-list input[name*="[title]"]').last.fill(STRUCT_SERVICE_MARKER)
            page.locator('#services-list textarea[name*="[description]"]').last.fill("Faz 5.7 yapısal senkron testi.")
            page.click('#content-form button[type="submit"]')
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(800)

            service_count_after = len(load_content()["services"]["items"])
            structure_added = service_count_after == service_count_before + 1
            assert_metric("admin_tr_structure_add_service_count", service_count_after, str(service_count_before + 1), structure_added)
            ok = ok and structure_added

            ok = assert_content_key_parity() and ok
            for lang in ("en", "de", "ru", "fa"):
                has_marker = any(
                    i.get("title") == STRUCT_SERVICE_MARKER
                    for i in load_content_lang(lang)["services"]["items"]
                )
                assert_metric(f"admin_tr_structure_seed_{lang}", 1 if has_marker else 0, "TR seeded", has_marker)
                ok = ok and has_marker

            page.goto(f"{BASE}/?lang=ru", wait_until="networkidle")
            ru_card_visible = STRUCT_SERVICE_MARKER in page.content()
            assert_metric("admin_tr_structure_ru_frontend", 1 if ru_card_visible else 0, "visible", ru_card_visible)
            ok = ok and ru_card_visible

            page.goto(f"{BASE}/?lang=fa", wait_until="networkidle")
            fa_card_visible = STRUCT_SERVICE_MARKER in page.content()
            assert_metric("admin_tr_structure_fa_frontend", 1 if fa_card_visible else 0, "visible", fa_card_visible)
            ok = ok and fa_card_visible

            page.goto(f"{BASE}/?lang=en", wait_until="networkidle")
            en_card_visible = STRUCT_SERVICE_MARKER in page.content()
            assert_metric("admin_tr_structure_en_frontend", 1 if en_card_visible else 0, "visible", en_card_visible)
            ok = ok and en_card_visible

            ok = lang_independent_values_match() and ok

            browser.close()
    finally:
        CONTENT_PATH.write_bytes(tr_bytes_before)
        CONTENT_EN_PATH.write_bytes(en_bytes_before)
        CONTENT_DE_PATH.write_bytes(de_bytes_before)
        CONTENT_RU_PATH.write_bytes(ru_bytes_before)
        CONTENT_FA_PATH.write_bytes(fa_bytes_before)

    return ok


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"screenshots": [], "acceptance": {}}
    ok = True

    content_bytes = CONTENT_PATH.read_bytes()
    content_en_bytes = CONTENT_EN_PATH.read_bytes()
    content_de_bytes = CONTENT_DE_PATH.read_bytes()
    content_ru_bytes = CONTENT_RU_PATH.read_bytes()
    content_fa_bytes = CONTENT_FA_PATH.read_bytes()
    uploads_snap = snapshot_uploads()
    backups_snap = snapshot_backups()
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
                data={"csrf_token": csrf, "action": "upload_team_photo", "member_index": "0", "admin_lang": "tr"},
                files={"photo": ("team-shot.png", png, "image/png")},
                allow_redirects=True,
            )
            results["screenshots"] = admin_screenshots()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.goto(f"{BASE}/?lang=tr#team", wait_until="networkidle")
                page.wait_for_timeout(800)
                shot = SHOT_DIR / "team-card-with-photo.png"
                page.locator("#team .team-card").first.screenshot(path=str(shot))
                results["screenshots"].append("docs/screenshots/team-card-with-photo.png")
                browser.close()
        except Exception as exc:
            print(f"Screenshot warning: {exc}", file=sys.stderr)
    finally:
        CONTENT_PATH.write_bytes(content_bytes)
        CONTENT_EN_PATH.write_bytes(content_en_bytes)
        CONTENT_DE_PATH.write_bytes(content_de_bytes)
        CONTENT_RU_PATH.write_bytes(content_ru_bytes)
        CONTENT_FA_PATH.write_bytes(content_fa_bytes)
        restore_uploads(uploads_snap)
        restore_backups(backups_snap)

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

    _, home_html, _ = client.request("GET", "/?lang=tr")
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
