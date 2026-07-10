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
CONTENT_EN_PATH = ROOT / "content/content.en.json"
CONTENT_DE_PATH = ROOT / "content/content.de.json"
CONTENT_RU_PATH = ROOT / "content/content.ru.json"
CONTENT_FA_PATH = ROOT / "content/content.fa.json"
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
SMTP_DEBUG_SCRIPT = ROOT / "scripts/smtp_debug_server.py"
SMTP_DEBUG_HOST = "127.0.0.1"
CSS_DIR = ROOT / "public_html/assets/css"
CREDENTIAL_PATTERNS = ("smtp_pass", "mail_password", "smtp_user", "smtp_password")
CREDENTIAL_VALUE_RE = re.compile(
    r"'(?:smtp_pass|mail_password|smtp_password)'\s*=>\s*'([^']+)'",
    re.IGNORECASE,
)
TEST_PASSWORD = ".eE951623"
CONTACT_SECTION_BASELINE_HEIGHT_PX = 956
CONTACT_SECTION_MAX_HEIGHT_PX = 790
CONTACT_SECTION_PRE_HOURS_HEIGHT_PX = 726
CONTACT_HOURS_COLUMN_ALIGN_MAX_PX = 16
CONTACT_HOURS_CARD_EDGE_MAX_PX = 2
CONTACT_HOURS_EXPECTED = {
    "title": "Çalışma Saatleri",
    "rows": [
        {"label": "Pazartesi – Cuma", "value": "09:00 – 18:00"},
        {"label": "Cumartesi – Pazar", "value": "Kapalı"},
    ],
}
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
SITE_LANGS = ("tr", "en", "de", "ru", "fa")
LANG_CONTENT_PATHS = {
    "en": CONTENT_EN_PATH,
    "de": CONTENT_DE_PATH,
    "ru": CONTENT_RU_PATH,
    "fa": CONTENT_FA_PATH,
}

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
    proc = subprocess.run(
        php_cmd(str(ROOT / "scripts/create_admin_config.php"), f"--password={TEST_PASSWORD}"),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or "create_admin_config failed")


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


def load_lang_content(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_paths(obj: object, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else key
            paths.add(child)
            paths |= collect_paths(value, child)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            child = f"{prefix}[{i}]"
            paths.add(child)
            paths |= collect_paths(value, child)
    return paths


def count_empty_strings(obj: object) -> int:
    if isinstance(obj, dict):
        return sum(count_empty_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(count_empty_strings(v) for v in obj)
    if isinstance(obj, str):
        return 1 if obj.strip() == "" else 0
    return 0


def count_translatable_empty_strings(base: object, localized: object) -> int:
    if isinstance(base, dict) and isinstance(localized, dict):
        total = 0
        for key, base_value in base.items():
            if key in localized:
                total += count_translatable_empty_strings(base_value, localized[key])
        return total
    if isinstance(base, list) and isinstance(localized, list):
        return sum(
            count_translatable_empty_strings(base[i], localized[i])
            for i in range(min(len(base), len(localized)))
        )
    if isinstance(localized, str) and localized.strip() == "":
        if isinstance(base, str) and base.strip() == "":
            return 0
        return 1
    return 0


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
    head_hours = head_cmp.get("contact", {}).pop("hours", None)
    hours_added = current_cmp.get("contact", {}).pop("hours", None)
    ok, reason = deep_equal_except_allowed(head_cmp, current_cmp)
    hours_ok = hours_added == CONTACT_HOURS_EXPECTED and head_hours == CONTACT_HOURS_EXPECTED
    assert_metric("content_json_contact_hours_added", 1 if hours_ok else 0, "hours seed only", hours_ok)
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

    return ok and process_ok and watermark_ok and process_section_ok and url_ok and og_ok and display_ok and seeded_ok and hours_ok


def assert_lang_content_parity() -> bool:
    ok = True
    tr_content = load_content()
    tr_paths = collect_paths(tr_content)
    for lang, path in LANG_CONTENT_PATHS.items():
        lang_content = load_lang_content(path)
        lang_paths = collect_paths(lang_content)
        missing = len(tr_paths - lang_paths)
        extra = len(lang_paths - tr_paths)
        empty_count = count_translatable_empty_strings(tr_content, lang_content)
        assert_metric(f"lang_{lang}_missing_keys", missing, "0", missing == 0)
        assert_metric(f"lang_{lang}_extra_keys", extra, "0", extra == 0)
        assert_metric(f"lang_{lang}_empty_strings", empty_count, "0", empty_count == 0)
        ok = ok and missing == 0 and extra == 0 and empty_count == 0
    return ok


def collect_page_asset_paths(html: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"""(?:href|src)=["']([^"']+)["']""", html):
        raw = match.group(1).strip()
        if raw.startswith("/") and raw not in seen:
            seen.add(raw)
            paths.append(raw)
    for match in re.finditer(r"""srcset=["']([^"']+)["']""", html):
        for part in match.group(1).split(","):
            token = part.strip().split()[0]
            if token.startswith("/") and token not in seen:
                seen.add(token)
                paths.append(token)
    return paths


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        v = value / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def parse_css_rgb(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", value.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def assert_faz61_hero_photo() -> bool:
    """Faz 6.1: hero arka plan fotoğrafı, LCP önceliği ve kontrast."""
    ok = True
    hero_assets = [
        ROOT / "public_html/assets/img/hero-1920.webp",
        ROOT / "public_html/assets/img/hero-1280.webp",
        ROOT / "public_html/assets/img/hero-768.webp",
        ROOT / "public_html/assets/img/hero-1280.jpg",
    ]
    for path in hero_assets:
        rel = path.relative_to(ROOT).as_posix()
        exists = path.is_file() and path.stat().st_size > 0
        assert_metric(f"faz61_asset_{path.name}_bytes", path.stat().st_size if exists else 0, "> 0", exists)
        ok = ok and exists

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(800)

        hero_data = page.evaluate(
            """() => {
              const photo = document.querySelector('.hero-photo');
              const img = photo ? photo.querySelector('img') : null;
              const source = photo ? photo.querySelector('source[type="image/webp"]') : null;
              const overlay = document.querySelector('.hero-overlay');
              const watermark = document.querySelector('.hero-watermark');
              function parseRgb(c) {
                const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
              }
              function lum(rgb) {
                const a = rgb.map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
                return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
              }
              function contrast(fg, bg) {
                const l1 = lum(parseRgb(fg));
                const l2 = lum(parseRgb(bg));
                return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
              }
              const titleEl = document.querySelector('.hero-title');
              const descEl = document.querySelector('.hero-description');
              const btnGold = document.querySelector('.hero-actions .btn-gold');
              const btnOutline = document.querySelector('.hero-actions .btn-outline-light');
              const eyebrow = document.querySelector('.hero-eyebrow');
              const heroBg = getComputedStyle(document.querySelector('.hero')).backgroundColor;
              const overlayBg = overlay ? getComputedStyle(overlay).backgroundImage : '';
              return {
                photoExists: !!photo,
                overlayExists: !!overlay,
                imgFetchPriority: img ? (img.getAttribute('fetchpriority') || '') : '',
                imgLoading: img ? (img.getAttribute('loading') || '') : '',
                imgSrc: img ? img.getAttribute('src') || '' : '',
                srcset: source ? source.getAttribute('srcset') || '' : '',
                titleContrast: titleEl ? contrast(getComputedStyle(titleEl).color, heroBg) : 0,
                descContrast: descEl ? contrast(getComputedStyle(descEl).color, heroBg) : 0,
                btnGoldContrast: btnGold ? contrast(getComputedStyle(btnGold).color, getComputedStyle(btnGold).backgroundColor) : 0,
                btnOutlineContrast: btnOutline ? contrast(getComputedStyle(btnOutline).color, getComputedStyle(btnOutline).backgroundColor) : 0,
                eyebrowContrast: eyebrow ? contrast(getComputedStyle(eyebrow).color, heroBg) : 0,
                watermarkExists: !!watermark,
                watermarkDisplay: watermark ? getComputedStyle(watermark).display : '',
                watermarkOpacity: watermark ? parseFloat(getComputedStyle(watermark).opacity) : 0,
                watermarkPointerEvents: watermark ? getComputedStyle(watermark).pointerEvents : '',
              };
            }"""
        )

        photo_ok = hero_data.get("photoExists") and hero_data.get("overlayExists")
        fetch_ok = hero_data.get("imgFetchPriority") == "high"
        lazy_ok = hero_data.get("imgLoading") != "lazy"
        src_ok = "/assets/img/hero-1280.jpg" in hero_data.get("imgSrc", "")
        srcset_ok = all(
            token in hero_data.get("srcset", "")
            for token in ("hero-768.webp", "hero-1280.webp", "hero-1920.webp")
        )
        title_c = round(float(hero_data.get("titleContrast", 0)), 2)
        desc_c = round(float(hero_data.get("descContrast", 0)), 2)
        btn_gold_c = round(float(hero_data.get("btnGoldContrast", 0)), 2)
        btn_outline_c = round(float(hero_data.get("btnOutlineContrast", 0)), 2)
        eyebrow_c = round(float(hero_data.get("eyebrowContrast", 0)), 2)
        wm_ok = (
            hero_data.get("watermarkExists")
            and hero_data.get("watermarkDisplay") == "none"
            and hero_data.get("watermarkPointerEvents") == "none"
        )

        assert_metric("faz61_hero_photo_layer", 1 if photo_ok else 0, "present", photo_ok)
        assert_metric("faz61_hero_img_fetchpriority", hero_data.get("imgFetchPriority", ""), "high", fetch_ok)
        assert_metric("faz61_hero_img_not_lazy", hero_data.get("imgLoading", ""), "not lazy", lazy_ok)
        assert_metric("faz61_hero_jpeg_fallback_src", 1 if src_ok else 0, "hero-1280.jpg", src_ok)
        assert_metric("faz61_hero_webp_srcset", 1 if srcset_ok else 0, "768/1280/1920", srcset_ok)
        assert_metric("faz61_hero_title_contrast_ratio", title_c, ">= 7.0", title_c >= 7.0)
        assert_metric("faz61_hero_description_contrast_ratio", desc_c, ">= 4.5", desc_c >= 4.5)
        assert_metric("faz61_hero_btn_gold_contrast_ratio", btn_gold_c, ">= 4.5", btn_gold_c >= 4.5)
        assert_metric("faz61_hero_btn_outline_contrast_ratio", btn_outline_c, ">= 4.5", btn_outline_c >= 4.5)
        assert_metric("faz61_hero_eyebrow_contrast_ratio", eyebrow_c, ">= 4.5", eyebrow_c >= 4.5)
        assert_metric("faz61_hero_watermark_hidden", hero_data.get("watermarkDisplay", ""), "none", wm_ok)
        ok = (
            ok
            and photo_ok
            and fetch_ok
            and lazy_ok
            and src_ok
            and srcset_ok
            and title_c >= 7.0
            and desc_c >= 4.5
            and btn_gold_c >= 4.5
            and btn_outline_c >= 4.5
            and eyebrow_c >= 4.5
            and wm_ok
        )

        page.close()
        browser.close()

    return ok


def assert_faz61b_hero_stats_strip() -> bool:
    """Faz 6.1B: sağ kart kaldırıldı, sayaç şeridi sol sütunda."""
    ok = True
    tr_content = load_content()
    services_count = len(tr_content["services"]["items"])
    team_count = len(tr_content["team"]["members"])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(800)

        layout = page.evaluate(
            f"""() => {{
              function parseRgb(c) {{
                const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
              }}
              function lum(rgb) {{
                const a = rgb.map(v => {{ v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); }});
                return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
              }}
              function contrast(fg, bg) {{
                const l1 = lum(parseRgb(fg));
                const l2 = lum(parseRgb(bg));
                return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
              }}
              const hero = document.querySelector('.hero');
              const heroBg = hero ? getComputedStyle(hero).backgroundColor : '';
              const strip = document.querySelector('.hero-stats-strip');
              const stripStyle = strip ? getComputedStyle(strip) : null;
              const values = Array.from(document.querySelectorAll('.hero-stat-value'));
              const labels = Array.from(document.querySelectorAll('.hero-stat-label'));
              const divider = document.querySelector('.hero-stat-divider');
              const wmEl = document.querySelector('.hero-watermark');
              const heroRect = hero.getBoundingClientRect();
              const midX = heroRect.left + heroRect.width / 2;
              let opaqueRightBlocks = 0;
              hero.querySelectorAll('*').forEach(el => {{
                if (el.classList.contains('hero-photo') || el.classList.contains('hero-overlay') || el.classList.contains('hero-watermark')) return;
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (rect.width < 48 || rect.height < 48) return;
                if (rect.left + rect.width * 0.5 < midX) return;
                const bg = style.backgroundColor;
                const m = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
                if (!m) return;
                const alpha = m[4] !== undefined ? parseFloat(m[4]) : 1;
                const opacity = parseFloat(style.opacity || '1');
                if (alpha * opacity > 0.12) opaqueRightBlocks++;
              }});
              return {{
                visualCardCount: document.querySelectorAll('.hero-visual-card').length,
                medallionCount: document.querySelectorAll('.hero-medallion').length,
                stripExists: !!strip,
                stripInContent: !!document.querySelector('.hero-content .hero-stats-strip'),
                stripBg: stripStyle ? stripStyle.backgroundColor : '',
                stripFlexWrap: stripStyle ? stripStyle.flexWrap : '',
                dividerWidth: divider ? getComputedStyle(divider).width : '',
                valueTexts: values.map(v => v.textContent.trim()),
                labelTexts: labels.map(v => v.textContent.trim()),
                valueContrasts: values.map(v => contrast(getComputedStyle(v).color, heroBg)),
                labelContrasts: labels.map(v => contrast(getComputedStyle(v).color, heroBg)),
                opaqueRightBlocks,
                watermarkExists: !!wmEl,
                watermarkDisplay: wmEl ? getComputedStyle(wmEl).display : '',
              }};
            }}"""
        )

        card_gone = layout["visualCardCount"] == 0 and layout["medallionCount"] == 0
        strip_ok = layout["stripExists"] and layout["stripInContent"]
        strip_transparent = layout["stripBg"] in ("rgba(0, 0, 0, 0)", "transparent")
        nowrap_ok = layout["stripFlexWrap"] == "nowrap"
        divider_ok = layout["dividerWidth"] == "1px"
        values_ok = layout["valueTexts"] == [str(services_count), str(team_count)]
        right_clear = layout["opaqueRightBlocks"] == 0
        value_min = min(layout["valueContrasts"]) if layout["valueContrasts"] else 0
        label_min = min(layout["labelContrasts"]) if layout["labelContrasts"] else 0
        wm_ok = layout["watermarkExists"] and layout.get("watermarkDisplay") == "none"

        assert_metric("faz61b_hero_visual_card_removed", layout["visualCardCount"], "0", layout["visualCardCount"] == 0)
        assert_metric("faz61b_hero_medallion_removed", layout["medallionCount"], "0", layout["medallionCount"] == 0)
        assert_metric("faz61b_hero_stats_strip_present", 1 if strip_ok else 0, "in hero-content", strip_ok)
        assert_metric("faz61b_hero_stats_strip_transparent", 1 if strip_transparent else 0, "transparent", strip_transparent)
        assert_metric("faz61b_hero_stats_strip_nowrap", layout["stripFlexWrap"], "nowrap", nowrap_ok)
        assert_metric("faz61b_hero_stat_divider_width", layout["dividerWidth"], "1px", divider_ok)
        assert_metric("faz61b_hero_stat_values_content", 1 if values_ok else 0, "count from content", values_ok)
        assert_metric("faz61b_hero_right_half_opaque_blocks", layout["opaqueRightBlocks"], "0", right_clear)
        assert_metric("faz61b_hero_stat_value_contrast_min", round(value_min, 2), ">= 4.5", value_min >= 4.5)
        assert_metric("faz61b_hero_stat_label_contrast_min", round(label_min, 2), ">= 4.5", label_min >= 4.5)
        assert_metric("faz61b_hero_watermark_dom_hidden", 1 if wm_ok else 0, "present+display:none", wm_ok)
        ok = (
            ok
            and card_gone
            and strip_ok
            and strip_transparent
            and nowrap_ok
            and divider_ok
            and values_ok
            and right_clear
            and value_min >= 4.5
            and label_min >= 4.5
            and wm_ok
        )
        page.close()

        mobile = browser.new_page(viewport={"width": 360, "height": 740})
        mobile.goto(BASE + "/", wait_until="networkidle")
        mobile.wait_for_timeout(500)
        mobile_layout = mobile.evaluate(
            """() => {
              const strip = document.querySelector('.hero-stats-strip');
              const style = strip ? getComputedStyle(strip) : null;
              const stats = Array.from(document.querySelectorAll('.hero-stat'));
              let singleRow = true;
              if (stats.length >= 2) {
                const tops = stats.map(s => s.getBoundingClientRect().top);
                singleRow = Math.abs(tops[0] - tops[1]) <= 4;
              }
              const overflow = document.documentElement.scrollWidth <= window.innerWidth;
              return {
                flexWrap: style ? style.flexWrap : '',
                singleRow,
                overflow,
              };
            }"""
        )
        mobile_ok = mobile_layout["flexWrap"] == "nowrap" and mobile_layout["singleRow"] and mobile_layout["overflow"]
        assert_metric("faz61b_hero_stats_mobile_nowrap", mobile_layout["flexWrap"], "nowrap", mobile_layout["flexWrap"] == "nowrap")
        assert_metric("faz61b_hero_stats_mobile_single_row", 1 if mobile_layout["singleRow"] else 0, "single row", mobile_layout["singleRow"])
        assert_metric("faz61b_hero_stats_mobile_overflow", 1 if mobile_layout["overflow"] else 0, "no overflow", mobile_layout["overflow"])
        ok = ok and mobile_ok
        mobile.close()

        fa_page = browser.new_page(viewport={"width": 768, "height": 1024})
        fa_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
        fa_page.wait_for_timeout(500)
        fa_layout = fa_page.evaluate(
            """() => {
              const strip = document.querySelector('.hero-stats-strip');
              const style = strip ? getComputedStyle(strip) : null;
              const divider = document.querySelector('.hero-stat-divider');
              const stats = Array.from(document.querySelectorAll('.hero-stat'));
              const dir = document.documentElement.getAttribute('dir') || '';
              let mirrored = false;
              if (stats.length >= 2 && strip) {
                const s0 = stats[0].getBoundingClientRect();
                const s1 = stats[1].getBoundingClientRect();
                mirrored = s0.left > s1.left;
              }
              const overflow = document.documentElement.scrollWidth <= window.innerWidth;
              return {
                dir,
                flexDirection: style ? style.flexDirection : '',
                mirrored,
                dividerWidth: divider ? getComputedStyle(divider).width : '',
                overflow,
              };
            }"""
        )
        fa_ok = (
            fa_layout["dir"] == "rtl"
            and fa_layout["flexDirection"] == "row"
            and fa_layout["mirrored"]
            and fa_layout["dividerWidth"] == "1px"
            and fa_layout["overflow"]
        )
        assert_metric("faz61b_hero_stats_fa_dir", fa_layout["dir"], "rtl", fa_layout["dir"] == "rtl")
        assert_metric("faz61b_hero_stats_fa_flex_direction", fa_layout["flexDirection"], "row", fa_layout["flexDirection"] == "row")
        assert_metric("faz61b_hero_stats_fa_mirrored", 1 if fa_layout["mirrored"] else 0, "mirrored", fa_layout["mirrored"])
        assert_metric("faz61b_hero_stats_fa_overflow", 1 if fa_layout["overflow"] else 0, "no overflow", fa_layout["overflow"])
        ok = ok and fa_ok
        fa_page.close()

        browser.close()

    return ok


def measure_hero_watermark_texture(page) -> dict | None:
    return page.evaluate(
        """() => {
          const hero = document.querySelector('.hero');
          const wm = document.querySelector('.hero-watermark');
          if (!hero || !wm) return null;
          const hr = hero.getBoundingClientRect();
          const wr = wm.getBoundingClientRect();
          const style = getComputedStyle(wm);
          const opacity = parseFloat(style.opacity);
          const visibleLeft = Math.max(wr.left, hr.left);
          const visibleRight = Math.min(wr.right, hr.right);
          const visibleTop = Math.max(wr.top, hr.top);
          const visibleBottom = Math.min(wr.bottom, hr.bottom);
          const visibleWidth = Math.max(0, visibleRight - visibleLeft);
          const visibleHeight = Math.max(0, visibleBottom - visibleTop);
          const visibleArea = visibleWidth * visibleHeight;
          const heroArea = hr.width * hr.height;
          const visiblePct = heroArea > 0 ? (visibleArea / heroArea) * 100 : 0;
          const topPct = hr.height > 0 ? ((wr.top - hr.top) / hr.height) * 100 : 0;
          const overflowRight = Math.max(0, wr.right - hr.right);
          const overflowLeft = Math.max(0, hr.left - wr.left);
          const overflowRightPct = wr.width > 0 ? (overflowRight / wr.width) * 100 : 0;
          const overflowLeftPct = wr.width > 0 ? (overflowLeft / wr.width) * 100 : 0;
          return {
            opacity,
            visiblePct,
            topPct,
            overflowRightPct,
            overflowLeftPct,
            heroWidth: hr.width,
            heroHeight: hr.height,
            wmWidth: wr.width,
            wmHeight: wr.height,
          };
        }"""
    )


def measure_hero_watermark_blend(page) -> dict | None:
    return page.evaluate(
        """() => {
          const hero = document.querySelector('.hero');
          const wm = document.querySelector('.hero-watermark');
          const content = document.querySelector('.hero-content');
          const photo = document.querySelector('.hero-photo');
          const overlay = document.querySelector('.hero-overlay');
          const grid = document.querySelector('.hero-grid');
          const title = document.querySelector('.hero-title');
          const desc = document.querySelector('.hero-description');
          if (!hero || !wm || !content) return null;
          const wr = wm.getBoundingClientRect();
          const cr = content.getBoundingClientRect();
          const intersects = !(
            wr.right <= cr.left || wr.left >= cr.right || wr.bottom <= cr.top || wr.top >= cr.bottom
          );
          const wmStyle = getComputedStyle(wm);
          const z = (el) => {
            if (!el) return 0;
            const raw = getComputedStyle(el).zIndex;
            return raw === 'auto' ? 0 : parseInt(raw, 10);
          };
          function parseRgb(c) {
            const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
            return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
          }
          function lum(rgb) {
            const a = rgb.map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
            return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
          }
          function contrast(fg, bg) {
            const l1 = lum(parseRgb(fg));
            const l2 = lum(parseRgb(bg));
            return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
          }
          const heroBg = getComputedStyle(hero).backgroundColor;
          return {
            opacity: parseFloat(wmStyle.opacity),
            blendMode: wmStyle.mixBlendMode,
            intersects,
            wmLeft: wr.left,
            wmTop: wr.top,
            wmRight: wr.right,
            wmBottom: wr.bottom,
            contentLeft: cr.left,
            contentTop: cr.top,
            contentRight: cr.right,
            contentBottom: cr.bottom,
            wmZ: z(wm),
            photoZ: z(photo),
            overlayZ: z(overlay),
            gridZ: z(grid),
            titleContrast: title ? contrast(getComputedStyle(title).color, heroBg) : 0,
            descContrast: desc ? contrast(getComputedStyle(desc).color, heroBg) : 0,
          };
        }"""
    )


def assert_faz61d_hero_watermark_blend() -> bool:
    """Faz 6.1D: büyük blend filigran — foto ile kaynaşır, metinle kesişmez."""
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(800)
        metrics = measure_hero_watermark_blend(page)
        if not metrics:
            assert_metric("faz61d_hero_watermark_present", 0, "1", False)
            return False

        opacity = round(float(metrics["opacity"]), 4)
        blend = metrics["blendMode"]
        opacity_ok = 0.08 <= opacity <= 0.14
        blend_ok = blend in ("soft-light", "screen")
        no_intersect = not metrics["intersects"]
        title_c = round(float(metrics["titleContrast"]), 2)
        desc_c = round(float(metrics["descContrast"]), 2)
        contrast_ok = title_c >= 7.0 and desc_c >= 4.5
        layer_ok = (
            metrics["photoZ"] < metrics["wmZ"] < metrics["overlayZ"] <= metrics["gridZ"]
        )

        assert_metric("faz61d_hero_watermark_opacity", opacity, "0.08-0.14", opacity_ok)
        assert_metric("faz61d_hero_watermark_blend_mode", blend, "soft-light|screen", blend_ok)
        assert_metric("faz61d_hero_watermark_no_text_intersect", 1 if no_intersect else 0, "no overlap", no_intersect)
        assert_metric("faz61d_hero_watermark_title_contrast", title_c, ">= 7.0", title_c >= 7.0)
        assert_metric("faz61d_hero_watermark_desc_contrast", desc_c, ">= 4.5", desc_c >= 4.5)
        assert_metric("faz61d_hero_watermark_layer_order", 1 if layer_ok else 0, "photo<wm<overlay<=grid", layer_ok)
        assert_metric("faz61d_hero_watermark_bbox_left", round(metrics["wmLeft"], 1), "report", True)
        assert_metric("faz61d_hero_watermark_bbox_top", round(metrics["wmTop"], 1), "report", True)
        ok = ok and opacity_ok and blend_ok and no_intersect and contrast_ok and layer_ok
        page.close()

        for label, width, height in VIEWPORTS:
            fa_page = browser.new_page(viewport={"width": width, "height": height})
            fa_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
            fa_page.wait_for_timeout(500)
            fa_metrics = measure_hero_watermark_blend(fa_page)
            fa_overflow = fa_page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth"
            )
            if fa_metrics:
                fa_no_intersect = not fa_metrics["intersects"]
                assert_metric(
                    f"faz61d_hero_watermark_fa_no_intersect_{label}",
                    1 if fa_no_intersect else 0,
                    "no overlap",
                    fa_no_intersect,
                )
                ok = ok and fa_no_intersect
            assert_metric(
                f"faz61d_hero_watermark_fa_overflow_x_{label}",
                1 if fa_overflow else 0,
                "no horizontal overflow",
                fa_overflow,
            )
            ok = ok and fa_overflow
            fa_page.close()

        mobile = browser.new_page(viewport={"width": 360, "height": 740})
        mobile.goto(BASE + "/", wait_until="networkidle")
        mobile.wait_for_timeout(500)
        mobile_metrics = measure_hero_watermark_blend(mobile)
        mobile_overflow = mobile.evaluate(
            "() => document.documentElement.scrollWidth <= window.innerWidth"
        )
        if mobile_metrics:
            mobile_no_intersect = not mobile_metrics["intersects"]
            assert_metric(
                "faz61d_hero_watermark_mobile_no_intersect",
                1 if mobile_no_intersect else 0,
                "no overlap",
                mobile_no_intersect,
            )
            ok = ok and mobile_no_intersect
        assert_metric(
            "faz61d_hero_watermark_mobile_overflow",
            1 if mobile_overflow else 0,
            "no overflow",
            mobile_overflow,
        )
        ok = ok and mobile_overflow
        mobile.close()

        browser.close()

    return ok


def assert_faz61e_hero_embedded_watermark() -> bool:
    """Faz 6.1E: filigran fotoğrafta gömülü; CSS watermark gizli."""
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(800)

        data = page.evaluate(
            """() => {
              const wm = document.querySelector('.hero-watermark');
              const title = document.querySelector('.hero-title');
              const desc = document.querySelector('.hero-description');
              const hero = document.querySelector('.hero');
              function parseRgb(c) {
                const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
              }
              function lum(rgb) {
                const a = rgb.map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
                return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
              }
              function contrast(fg, bg) {
                const l1 = lum(parseRgb(fg));
                const l2 = lum(parseRgb(bg));
                return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
              }
              const heroBg = hero ? getComputedStyle(hero).backgroundColor : '';
              const wmStyle = wm ? getComputedStyle(wm) : null;
              return {
                watermarkExists: !!wm,
                watermarkDisplay: wmStyle ? wmStyle.display : '',
                titleContrast: title ? contrast(getComputedStyle(title).color, heroBg) : 0,
                descContrast: desc ? contrast(getComputedStyle(desc).color, heroBg) : 0,
              };
            }"""
        )

        hidden_ok = data.get("watermarkExists") and data.get("watermarkDisplay") == "none"
        title_c = round(float(data.get("titleContrast", 0)), 2)
        desc_c = round(float(data.get("descContrast", 0)), 2)

        assert_metric("faz61e_hero_watermark_dom_present", 1 if data.get("watermarkExists") else 0, "1", data.get("watermarkExists"))
        assert_metric("faz61e_hero_watermark_display_none", data.get("watermarkDisplay", ""), "none", hidden_ok)
        assert_metric("faz61e_hero_title_contrast", title_c, ">= 7.0", title_c >= 7.0)
        assert_metric("faz61e_hero_desc_contrast", desc_c, ">= 4.5", desc_c >= 4.5)
        ok = ok and hidden_ok and title_c >= 7.0 and desc_c >= 4.5
        page.close()
        browser.close()

    return ok


def assert_faz61c_hero_watermark_texture() -> bool:
    """Faz 6.1C: küçük soluk sağ-alt watermark dokusu."""
    ok = True

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(800)
        metrics = measure_hero_watermark_texture(page)
        if not metrics:
            assert_metric("faz61c_hero_watermark_present", 0, "1", False)
            return False

        opacity = round(float(metrics["opacity"]), 4)
        visible_pct = round(float(metrics["visiblePct"]), 2)
        top_pct = round(float(metrics["topPct"]), 2)
        overflow_right_pct = round(float(metrics["overflowRightPct"]), 2)

        opacity_ok = 0 < opacity <= 0.03
        visible_ok = visible_pct <= 12.0
        top_ok = top_pct >= 45.0
        overflow_ok = overflow_right_pct >= 25.0

        assert_metric("faz61c_hero_watermark_opacity", opacity, "<= 0.03", opacity_ok)
        assert_metric("faz61c_hero_watermark_visible_area_pct", visible_pct, "<= 12", visible_ok)
        assert_metric("faz61c_hero_watermark_top_pct", top_pct, ">= 45", top_ok)
        assert_metric("faz61c_hero_watermark_overflow_right_pct", overflow_right_pct, ">= 25", overflow_ok)
        ok = ok and opacity_ok and visible_ok and top_ok and overflow_ok
        page.close()

        for label, width, height in VIEWPORTS:
            fa_page = browser.new_page(viewport={"width": width, "height": height})
            fa_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
            fa_page.wait_for_timeout(500)
            fa_metrics = measure_hero_watermark_texture(fa_page)
            fa_overflow = fa_page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth"
            )
            if fa_metrics:
                fa_overflow_left = round(float(fa_metrics["overflowLeftPct"]), 2)
                fa_top = round(float(fa_metrics["topPct"]), 2)
                fa_visible = round(float(fa_metrics["visiblePct"]), 2)
                fa_mirror_ok = fa_overflow_left >= 25.0
                assert_metric(
                    f"faz61c_hero_watermark_fa_overflow_left_pct_{label}",
                    fa_overflow_left,
                    ">= 25",
                    fa_mirror_ok,
                )
                assert_metric(
                    f"faz61c_hero_watermark_fa_top_pct_{label}",
                    fa_top,
                    ">= 45",
                    fa_top >= 45.0,
                )
                assert_metric(
                    f"faz61c_hero_watermark_fa_visible_pct_{label}",
                    fa_visible,
                    "<= 12",
                    fa_visible <= 12.0,
                )
                ok = ok and fa_mirror_ok and fa_top >= 45.0 and fa_visible <= 12.0
            assert_metric(
                f"faz61c_hero_watermark_fa_overflow_x_{label}",
                1 if fa_overflow else 0,
                "no horizontal overflow",
                fa_overflow,
            )
            ok = ok and fa_overflow
            fa_page.close()

        browser.close()

    return ok


def capture_faz6_hero_screenshots() -> list[str]:
    """Faz 6.1: hero kanıt ekran görüntüleri (5 dil × 3 viewport)."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.wait_for_timeout(800)
                hero = page.locator("#hero")
                shot_name = f"faz6-hero-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                hero.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def capture_faz6_hero_rev_screenshots() -> list[str]:
    """Faz 6.1B: hero revizyon kanıt ekran görüntüleri."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.wait_for_timeout(800)
                hero = page.locator("#hero")
                shot_name = f"faz6-hero-rev-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                hero.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def capture_faz6_hero_wm_screenshots() -> list[str]:
    """Faz 6.1C: watermark rötuş kanıt ekran görüntüleri."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.wait_for_timeout(800)
                hero = page.locator("#hero")
                shot_name = f"faz6-hero-wm-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                hero.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def capture_faz6_hero_wm2_screenshots() -> list[str]:
    """Faz 6.1D: blend watermark kanıt ekran görüntüleri."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.wait_for_timeout(800)
                hero = page.locator("#hero")
                shot_name = f"faz6-hero-wm2-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                hero.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def capture_faz6_hero_final_screenshots() -> list[str]:
    """Faz 6.1E: gömülü filigranlı final hero ekran görüntüleri."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.wait_for_timeout(800)
                hero = page.locator("#hero")
                shot_name = f"faz6-hero-final-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                hero.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


SEKTOR_SLUGS = ("enerji", "gayrimenkul", "ticaret", "insaat", "yatirim")
SEKTOR_ICON_SLUGS = {
    "energy": "enerji",
    "realestate": "gayrimenkul",
    "trade": "ticaret",
    "construction": "insaat",
    "investment": "yatirim",
}


def assert_faz62_sektor_band() -> bool:
    """Faz 6.2: Kısa Tanıtım sektör foto kart bandı — boyut, kontrast, animasyon, LCP."""
    ok = True
    sektor_dir = ROOT / "public_html/assets/img/sektor"
    expected_files: list[Path] = []
    for slug in SEKTOR_SLUGS:
        expected_files.extend(
            [
                sektor_dir / f"sektor-{slug}-400.webp",
                sektor_dir / f"sektor-{slug}-800.webp",
                sektor_dir / f"sektor-{slug}-800.jpg",
            ]
        )
    total_bytes = 0
    for path in expected_files:
        exists = path.is_file() and path.stat().st_size > 0
        size = path.stat().st_size if exists else 0
        total_bytes += size
        single_ok = exists and size <= 60_000
        assert_metric(f"faz62_asset_{path.name}_bytes", size, "<= 60000", single_ok)
        ok = ok and single_ok
    total_ok = total_bytes <= 400_000
    assert_metric("faz62_assets_total_bytes", total_bytes, "<= 400000", total_ok)
    ok = ok and total_ok

    for src_name in (
        "sektor-enerji.png",
        "sektor-gayrimenkul.png",
        "sektor-ticaret.png",
        "sektor-insaat.png",
        "sektor-yatirim.png",
        "hero-source.png",
    ):
        in_web = (ROOT / "public_html" / src_name).exists()
        assert_metric(f"faz62_raw_not_in_web_{src_name}", 0 if in_web else 1, "absent", not in_web)
        ok = ok and not in_web

    tr_badges = load_content()["intro"]["badges"]
    badge_ok = len(tr_badges) == 5 and all(
        SEKTOR_ICON_SLUGS.get(b.get("icon", "")) in SEKTOR_SLUGS for b in tr_badges
    )
    assert_metric("faz62_badge_keys_from_content", len(tr_badges), "5", badge_ok)
    ok = ok and badge_ok

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(800)

        band_data = page.evaluate(
            """() => {
              function parseRgb(c) {
                const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
              }
              function lum(rgb) {
                const a = rgb.map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
                return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
              }
              function contrast(fg, bg) {
                const l1 = lum(parseRgb(fg));
                const l2 = lum(parseRgb(bg));
                return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
              }
              const band = document.querySelector('.sektor-band');
              const track = document.querySelector('.sektor-band-track');
              const cards = Array.from(document.querySelectorAll('.sektor-card:not([aria-hidden="true"])'));
              const imgs = Array.from(document.querySelectorAll('.sektor-band img'));
              const heroImg = document.querySelector('.hero-photo img');
              const labels = Array.from(document.querySelectorAll('.sektor-card:not([aria-hidden="true"]) .sektor-card-label'));
              const labelContrasts = labels.map(el => contrast(getComputedStyle(el).color, 'rgb(16, 24, 44)'));
              const trackStyle = track ? getComputedStyle(track) : null;
              const bandRect = band ? band.getBoundingClientRect() : { height: 999 };
              const photoRect = document.querySelector('.sektor-card-photo');
              return {
                bandExists: !!band,
                cardCount: cards.length,
                duplicateHidden: document.querySelectorAll('.sektor-card[aria-hidden="true"]').length === cards.length,
                bandHeight: bandRect.height,
                cardHeight: photoRect ? photoRect.getBoundingClientRect().height : 0,
                imgsLazy: imgs.every(img => img.getAttribute('loading') === 'lazy'),
                imgsHaveDimensions: imgs.every(img => img.width > 0 && img.height > 0),
                webpSrcset: imgs.every(img => {
                  const source = img.closest('picture')?.querySelector('source[type="image/webp"]');
                  const srcset = source ? source.getAttribute('srcset') || '' : '';
                  return srcset.includes('-400.webp') && srcset.includes('-800.webp');
                }),
                labelMinContrast: labelContrasts.length ? Math.min(...labelContrasts) : 0,
                animationName: trackStyle ? trackStyle.animationName : '',
                animationDurationSec: trackStyle ? parseFloat(trackStyle.animationDuration) : 0,
                heroFetchPriority: heroImg ? (heroImg.getAttribute('fetchpriority') || '') : '',
                heroNotLazy: heroImg ? heroImg.getAttribute('loading') !== 'lazy' : false,
                overflow: document.documentElement.scrollWidth <= window.innerWidth,
              };
            }"""
        )

        band_h = round(float(band_data.get("bandHeight", 999)), 1)
        card_h = round(float(band_data.get("cardHeight", 0)), 1)
        label_min = round(float(band_data.get("labelMinContrast", 0)), 2)
        anim_dur = float(band_data.get("animationDurationSec", 0))

        height_ok = band_data.get("bandExists") and band_h <= 240
        card_h_ok = 150 <= card_h <= 180
        label_ok = label_min >= 4.5
        anim_ok = anim_dur >= 40 and anim_dur <= 60
        lazy_ok = band_data.get("imgsLazy") and band_data.get("heroNotLazy")
        lcp_ok = band_data.get("heroFetchPriority") == "high"

        assert_metric("faz62_band_present", 1 if band_data.get("bandExists") else 0, "1", band_data.get("bandExists"))
        assert_metric("faz62_band_height_px", band_h, "<= 240", height_ok)
        assert_metric("faz62_card_height_px", card_h, "150-180", card_h_ok)
        assert_metric("faz62_label_contrast_min", label_min, ">= 4.5", label_ok)
        assert_metric("faz62_cards_from_content", band_data.get("cardCount", 0), "5", band_data.get("cardCount") == 5)
        assert_metric("faz62_duplicate_aria_hidden", 1 if band_data.get("duplicateHidden") else 0, "5 hidden", band_data.get("duplicateHidden"))
        assert_metric("faz62_imgs_lazy", 1 if band_data.get("imgsLazy") else 0, "lazy", band_data.get("imgsLazy"))
        assert_metric("faz62_imgs_srcset_webp", 1 if band_data.get("webpSrcset") else 0, "400+800 webp", band_data.get("webpSrcset"))
        assert_metric("faz62_animation_duration_sec", round(anim_dur, 1), "40-60", anim_ok)
        assert_metric("faz62_hero_lcp_fetchpriority", band_data.get("heroFetchPriority", ""), "high", lcp_ok)
        assert_metric("faz62_desktop_overflow", 1 if band_data.get("overflow") else 0, "0", band_data.get("overflow"))
        ok = (
            ok
            and height_ok
            and card_h_ok
            and label_ok
            and band_data.get("cardCount") == 5
            and band_data.get("duplicateHidden")
            and band_data.get("imgsLazy")
            and band_data.get("webpSrcset")
            and anim_ok
            and lazy_ok
            and lcp_ok
            and band_data.get("overflow")
        )

        transform_check = page.evaluate(
            """() => new Promise(resolve => {
              const track = document.querySelector('.sektor-band-track');
              if (!track) return resolve(false);
              const anim = getComputedStyle(track).animationName;
              const before = getComputedStyle(track).transform;
              setTimeout(() => {
                const after = getComputedStyle(track).transform;
                resolve(anim !== 'none' && before !== after);
              }, 600);
            })"""
        )
        assert_metric("faz62_animation_uses_transform", 1 if transform_check else 0, "moving", transform_check)
        ok = ok and transform_check

        page.hover(".sektor-band")
        page.wait_for_timeout(200)
        pause_state = page.evaluate(
            """() => {
              const track = document.querySelector('.sektor-band-track');
              return track ? getComputedStyle(track).animationPlayState : '';
            }"""
        )
        pause_ok = pause_state == "paused"
        assert_metric("faz62_hover_animation_paused", pause_state, "paused", pause_ok)
        ok = ok and pause_ok

        cls_score = page.evaluate(
            """() => new Promise(resolve => {
              let cls = 0;
              const obs = new PerformanceObserver(list => {
                for (const entry of list.getEntries()) {
                  if (!entry.hadRecentInput) cls += entry.value;
                }
              });
              obs.observe({ type: 'layout-shift', buffered: true });
              setTimeout(() => { obs.disconnect(); resolve(cls); }, 1200);
            })"""
        )
        cls_ok = float(cls_score) < 0.05
        assert_metric("faz62_cls_score", round(float(cls_score), 4), "< 0.05", cls_ok)
        ok = ok and cls_ok

        for label, width, height in VIEWPORTS:
            vp = browser.new_page(viewport={"width": width, "height": height})
            vp.goto(BASE + "/", wait_until="networkidle")
            vp.wait_for_timeout(400)
            overflow = vp.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            assert_metric(f"faz62_overflow_{label}_{width}", 1 if overflow else 0, "0", overflow)
            ok = ok and overflow
            if width >= 1024:
                anim_name = vp.evaluate(
                    "() => { const t = document.querySelector('.sektor-band-track'); return t ? getComputedStyle(t).animationName : 'none'; }"
                )
                anim_on = anim_name not in ("none", "")
                assert_metric(f"faz62_anim_desktop_{width}", anim_name, "sektor-band-scroll", anim_on)
                ok = ok and anim_on
            else:
                anim_name = vp.evaluate(
                    "() => { const t = document.querySelector('.sektor-band-track'); return t ? getComputedStyle(t).animationName : 'none'; }"
                )
                anim_off = anim_name in ("none", "")
                assert_metric(f"faz62_anim_mobile_{width}", anim_name, "none", anim_off)
                ok = ok and anim_off
            vp.close()

        fa_page = browser.new_page(viewport={"width": 1440, "height": 900})
        fa_page.emulate_media(reduced_motion="no-preference")
        fa_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
        fa_page.wait_for_timeout(500)
        fa_data = fa_page.evaluate(
            """() => ({
              dir: document.documentElement.getAttribute('dir') || '',
              animDirection: (() => {
                const t = document.querySelector('.sektor-band-track');
                return t ? getComputedStyle(t).animationDirection : '';
              })(),
              overflow: document.documentElement.scrollWidth <= window.innerWidth,
            })"""
        )
        fa_ok = fa_data["dir"] == "rtl" and fa_data["animDirection"] == "reverse" and fa_data["overflow"]
        assert_metric("faz62_fa_rtl_anim_reverse", fa_data["animDirection"], "reverse", fa_data["animDirection"] == "reverse")
        assert_metric("faz62_fa_overflow", 1 if fa_data["overflow"] else 0, "0", fa_data["overflow"])
        ok = ok and fa_ok
        fa_page.close()

        rm_page = browser.new_page(viewport={"width": 1440, "height": 900})
        rm_page.emulate_media(reduced_motion="reduce")
        rm_page.goto(BASE + "/", wait_until="networkidle")
        rm_page.wait_for_timeout(400)
        rm_anim = rm_page.evaluate(
            "() => { const t = document.querySelector('.sektor-band-track'); return t ? getComputedStyle(t).animationName : 'none'; }"
        )
        rm_ok = rm_anim in ("none", "")
        assert_metric("faz62_reduced_motion_no_anim", rm_anim, "none", rm_ok)
        ok = ok and rm_ok
        rm_page.close()

        page.close()
        browser.close()

    return ok


def capture_faz62_sektor_screenshots() -> list[str]:
    """Faz 6.2: sektör foto bandı kanıt ekran görüntüleri (5 dil × 3 viewport)."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.wait_for_timeout(800)
                intro = page.locator("#intro")
                shot_name = f"faz6-sektor-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                intro.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def assert_faz63_sektor_network_audit() -> bool:
    """Faz 6.3 devir: sektör bandında gerçek indirilen varyantları ölç."""
    ok = True
    records: list[tuple[str, int]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        def on_response(response) -> None:
            if "/assets/img/sektor/" not in response.url or response.status != 200:
                return
            name = response.url.split("/")[-1]
            try:
                size = len(response.body())
            except Exception:
                size = 0
            records.append((name, size))

        page.on("response", on_response)
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(400)
        page.locator(".sektor-band").scroll_into_view_if_needed()
        page.wait_for_timeout(2000)
        dpr = float(page.evaluate("window.devicePixelRatio"))
        browser.close()

    by_name: dict[str, int] = {}
    for name, size in records:
        by_name[name] = by_name.get(name, 0) + size

    total = sum(by_name.values())
    count_ok = len(by_name) == 5
    webp_ok = all(n.endswith("-400.webp") for n in by_name)
    no_jpeg = not any(n.endswith(".jpg") for n in by_name)
    no_800 = not any("-800." in n for n in by_name)

    assert_metric("faz63_sektor_download_count", len(by_name), "5", count_ok)
    assert_metric("faz63_sektor_download_400webp_only", 1 if webp_ok else 0, "400webp", webp_ok)
    assert_metric("faz63_sektor_no_jpeg_fallback", 1 if no_jpeg else 0, "no jpg", no_jpeg)
    assert_metric("faz63_sektor_no_800_variant", 1 if no_800 else 0, "no 800", no_800)
    assert_metric("faz63_sektor_download_total_bytes", total, "> 0", total > 0)
    assert_metric("faz63_sektor_device_pixel_ratio", round(dpr, 2), "1.0", dpr == 1.0)
    for name, size in sorted(by_name.items()):
        assert_metric(f"faz63_sektor_downloaded_{name}_bytes", size, "> 0", size > 0)

    ok = ok and count_ok and webp_ok and no_jpeg and no_800 and total > 0
    return ok


def assert_faz63_hizmetler() -> bool:
    """Faz 6.3: Hizmetlerimiz 7 kart — grid, hover, stagger reveal, CLS."""
    ok = True
    tr_services = load_content()["services"]["items"]
    items_ok = len(tr_services) == 7
    assert_metric("faz63_service_items_from_content", len(tr_services), "7", items_ok)
    ok = ok and items_ok

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(BASE + "/", wait_until="networkidle")
        page.locator("#services").scroll_into_view_if_needed()
        page.wait_for_timeout(1500)

        layout = page.evaluate(
            """() => {
              const cards = Array.from(document.querySelectorAll('.service-card'));
              const row1 = cards.slice(0, 4).map(c => c.getBoundingClientRect().height);
              const row2 = cards.slice(4, 7).map(c => c.getBoundingClientRect().height);
              const row1Equal = row1.length === 4 && Math.max(...row1) - Math.min(...row1) <= 2;
              const row2Equal = row2.length === 3 && Math.max(...row2) - Math.min(...row2) <= 2;
              const accent = document.querySelector('.service-accent');
              const accentStyle = accent ? getComputedStyle(accent) : null;
              const cardWidth = cards[0] ? cards[0].getBoundingClientRect().width : 0;
              const accentWidth = accent ? accent.getBoundingClientRect().width : 0;
              const delays = cards.map(c => getComputedStyle(c).getPropertyValue('--stagger-delay').trim());
              const visibleCount = cards.filter(c => c.classList.contains('is-visible')).length;
              return {
                cardCount: cards.length,
                visibleCount,
                row1Equal,
                row2Equal,
                accentWidthPct: cardWidth > 0 ? (accentWidth / cardWidth) * 100 : 0,
                accentLeft: accentStyle ? accentStyle.left : '',
                accentRight: accentStyle ? accentStyle.right : '',
                delay0: delays[0] || '',
                delay1: delays[1] || '',
                gridCols: getComputedStyle(document.querySelector('.services-grid')).gridTemplateColumns,
              };
            }"""
        )

        cards_ok = layout["cardCount"] == 7 and layout["visibleCount"] == 7
        accent_pct = round(float(layout["accentWidthPct"]), 1)
        accent_ok = 35 <= accent_pct <= 45
        delay_step = 0
        if layout["delay0"].endswith("ms") and layout["delay1"].endswith("ms"):
            delay_step = int(layout["delay1"].replace("ms", "")) - int(layout["delay0"].replace("ms", ""))
        delay_ok = 60 <= delay_step <= 80

        assert_metric("faz63_service_card_count", layout["cardCount"], "7", layout["cardCount"] == 7)
        assert_metric("faz63_service_cards_revealed", layout["visibleCount"], "7", layout["visibleCount"] == 7)
        assert_metric("faz63_service_row1_equal_heights", 1 if layout["row1Equal"] else 0, "equal", layout["row1Equal"])
        assert_metric("faz63_service_row2_equal_heights", 1 if layout["row2Equal"] else 0, "equal", layout["row2Equal"])
        assert_metric("faz63_service_accent_width_pct", accent_pct, "~40", accent_ok)
        assert_metric("faz63_service_stagger_delay_step_ms", delay_step, "60-80", delay_ok)
        ok = ok and cards_ok and layout["row1Equal"] and layout["row2Equal"] and accent_ok and delay_ok

        page.emulate_media(reduced_motion="no-preference")
        card = page.locator(".service-card").first
        card.hover()
        page.wait_for_timeout(250)
        hover = card.evaluate(
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
              const accent = el.querySelector('.service-accent');
              const accentW = accent ? accent.getBoundingClientRect().width : 0;
              const cardW = el.getBoundingClientRect().width;
              return {
                translateY,
                accentHoverPct: cardW > 0 ? (accentW / cardW) * 100 : 0,
              };
            }"""
        )
        hover_y = round(float(hover["translateY"]), 1)
        hover_y_ok = hover_y <= -3.5 and hover_y >= -4.5
        accent_hover_ok = hover["accentHoverPct"] >= 95
        assert_metric("faz63_service_hover_translate_y", hover_y, "-4px", hover_y_ok)
        assert_metric("faz63_service_accent_hover_full", round(hover["accentHoverPct"], 1), "~100", accent_hover_ok)
        ok = ok and hover_y_ok and accent_hover_ok

        cls_score = page.evaluate(
            """() => new Promise(resolve => {
              let cls = 0;
              const obs = new PerformanceObserver(list => {
                for (const entry of list.getEntries()) {
                  if (!entry.hadRecentInput) cls += entry.value;
                }
              });
              obs.observe({ type: 'layout-shift', buffered: true });
              setTimeout(() => { obs.disconnect(); resolve(cls); }, 1200);
            })"""
        )
        cls_ok = float(cls_score) < 0.05
        assert_metric("faz63_service_cls_score", round(float(cls_score), 4), "< 0.05", cls_ok)
        ok = ok and cls_ok

        for label, width, height in VIEWPORTS:
            vp = browser.new_page(viewport={"width": width, "height": height})
            vp.goto(BASE + "/", wait_until="networkidle")
            vp.locator("#services").scroll_into_view_if_needed()
            vp.wait_for_timeout(1200)
            overflow = vp.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            assert_metric(f"faz63_overflow_{label}_{width}", 1 if overflow else 0, "0", overflow)
            ok = ok and overflow
            vp.close()

        fa_page = browser.new_page(viewport={"width": 1440, "height": 900})
        fa_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
        fa_page.locator("#services").scroll_into_view_if_needed()
        fa_page.wait_for_timeout(1200)
        fa_data = fa_page.evaluate(
            """() => {
              const accent = document.querySelector('.service-accent');
              const style = accent ? getComputedStyle(accent) : null;
              return {
                dir: document.documentElement.getAttribute('dir') || '',
                accentRight: style ? style.right : '',
                accentLeft: style ? style.left : '',
                overflow: document.documentElement.scrollWidth <= window.innerWidth,
              };
            }"""
        )
        fa_ok = fa_data["dir"] == "rtl" and fa_data["accentRight"] == "0px" and fa_data["overflow"]
        assert_metric("faz63_fa_rtl_accent_mirrored", fa_data["accentRight"], "0px", fa_data["accentRight"] == "0px")
        assert_metric("faz63_fa_overflow", 1 if fa_data["overflow"] else 0, "0", fa_data["overflow"])
        ok = ok and fa_ok
        fa_page.close()

        rm_page = browser.new_page(viewport={"width": 1440, "height": 900})
        rm_page.emulate_media(reduced_motion="reduce")
        rm_page.goto(BASE + "/", wait_until="networkidle")
        rm_page.locator("#services").scroll_into_view_if_needed()
        rm_page.wait_for_timeout(800)
        rm_visible = rm_page.evaluate(
            "() => document.querySelectorAll('.service-card.is-visible').length"
        )
        rm_ok = rm_visible == 7
        assert_metric("faz63_reduced_motion_all_visible", rm_visible, "7", rm_ok)
        ok = ok and rm_ok
        rm_page.close()

        nojs_context = browser.new_context(java_script_enabled=False, viewport={"width": 1440, "height": 900})
        nojs_page = nojs_context.new_page()
        nojs_page.goto(BASE + "/", wait_until="networkidle")
        nojs_visible = nojs_page.evaluate(
            """() => {
              const cards = document.querySelectorAll('.service-card');
              return cards.length === 7 && Array.from(cards).every(c => getComputedStyle(c).opacity === '1');
            }"""
        )
        assert_metric("faz63_nojs_cards_not_hidden", 1 if nojs_visible else 0, "visible", nojs_visible)
        ok = ok and nojs_visible
        nojs_page.close()
        nojs_context.close()

        page.close()
        browser.close()

    return ok


def capture_faz63_hizmetler_screenshots() -> list[str]:
    """Faz 6.3: Hizmetlerimiz bölümü kanıt ekran görüntüleri (reveal sonrası)."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.locator("#services").scroll_into_view_if_needed()
                for i in range(7):
                    page.locator(f'.service-card[data-stagger-index="{i}"]').scroll_into_view_if_needed()
                    page.wait_for_timeout(350)
                page.wait_for_timeout(800)
                visible_count = page.evaluate(
                    "() => document.querySelectorAll('.service-card.is-visible').length"
                )
                if visible_count < 7:
                    page.evaluate(
                        """() => {
                          document.querySelectorAll('.service-card[data-stagger-index]').forEach((card) => {
                            const index = parseInt(card.getAttribute('data-stagger-index') || '0', 10);
                            card.style.setProperty('--stagger-delay', `${index * 70}ms`);
                            card.classList.add('is-visible');
                          });
                        }"""
                    )
                    page.wait_for_timeout(600)
                services = page.locator("#services")
                shot_name = f"faz6-hizmetler-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                services.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def assert_faz64_hakkimizda() -> bool:
    """Faz 6.4: Hakkımızda editorial yerleşim — görsel, iki sütun, Vizyon/Misyon reveal."""
    ok = True
    hakkimizda_dir = ROOT / "public_html/assets/img/hakkimizda"
    asset_specs = [
        ("hakkimizda-600.webp", 150_000),
        ("hakkimizda-1200.webp", 150_000),
        ("hakkimizda-1200.jpg", 150_000),
    ]
    total_bytes = 0
    for name, max_single in asset_specs:
        path = hakkimizda_dir / name
        exists = path.is_file() and path.stat().st_size > 0
        size = path.stat().st_size if exists else 0
        total_bytes += size
        single_ok = exists and size <= max_single
        assert_metric(f"faz64_asset_{name}_bytes", size, f"<= {max_single}", single_ok)
        ok = ok and single_ok
    total_ok = total_bytes <= 300_000
    assert_metric("faz64_assets_total_bytes", total_bytes, "<= 300000", total_ok)
    ok = ok and total_ok

    raw_in_web = (ROOT / "public_html/about-source.png").exists()
    assert_metric("faz64_raw_not_in_web_about_source", 0 if raw_in_web else 1, "absent", not raw_in_web)
    ok = ok and not raw_in_web

    gitignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    gi_ok = "about-source.png" in gitignore_text
    assert_metric("faz64_about_source_gitignored", 1 if gi_ok else 0, "listed", gi_ok)
    ok = ok and gi_ok

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        errors: list[str] = []
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(BASE + "/", wait_until="networkidle")
        page.locator("#about").scroll_into_view_if_needed()
        page.wait_for_timeout(1500)

        layout = page.evaluate(
            """() => {
              function parseRgb(c) {
                const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                return m ? [+m[1], +m[2], +m[3]] : [0, 0, 0];
              }
              function lum(rgb) {
                const a = rgb.map(v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
                return a[0]*0.2126 + a[1]*0.7152 + a[2]*0.0722;
              }
              function contrast(fg, bg) {
                const l1 = lum(parseRgb(fg));
                const l2 = lum(parseRgb(bg));
                return (Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
              }
              const editorial = document.querySelector('.about-editorial');
              const text = document.querySelector('.about-text');
              const photo = document.querySelector('.about-photo');
              const frame = document.querySelector('.about-photo-frame');
              const img = document.querySelector('.about-photo img');
              const cards = Array.from(document.querySelectorAll('.vision-mission-card'));
              if (!editorial || !text || !photo || !frame || !img || cards.length < 2) {
                return { ok: false };
              }
              const tr = text.getBoundingClientRect();
              const pr = photo.getBoundingClientRect();
              const cols = getComputedStyle(editorial).gridTemplateColumns;
              const twoCol = cols.split(' ').filter(Boolean).length >= 2;
              const sideBySide = twoCol && tr.right <= pr.left + 4;
              const frameStyle = getComputedStyle(frame);
              const frameBefore = frame ? getComputedStyle(frame, '::before').borderTopColor : '';
              const title = document.querySelector('#about-heading');
              const body = document.querySelector('.about-text p');
              const titleC = title ? contrast(getComputedStyle(title).color, getComputedStyle(document.querySelector('#about')).backgroundColor) : 0;
              const bodyC = body ? contrast(getComputedStyle(body).color, getComputedStyle(document.querySelector('#about')).backgroundColor) : 0;
              const delays = cards.map(c => getComputedStyle(c).getPropertyValue('--reveal-delay').trim());
              const visibleCards = cards.filter(c => c.classList.contains('is-visible')).length;
              const revealStyles = cards.map(c => {
                const s = getComputedStyle(c);
                return { opacity: s.opacity, transform: s.transform };
              });
              return {
                ok: true,
                twoCol,
                sideBySide,
                textLeft: tr.left,
                photoLeft: pr.left,
                frameBorder: frameStyle.borderTopColor,
                frameBorderWidth: frameStyle.borderTopWidth,
                imgLoading: img.getAttribute('loading') || '',
                imgDecoding: img.getAttribute('decoding') || '',
                imgWidth: img.getAttribute('width') || '',
                imgHeight: img.getAttribute('height') || '',
                imgAlt: img.getAttribute('alt'),
                imgAriaHidden: img.getAttribute('aria-hidden'),
                imgSrc: img.getAttribute('src') || '',
                srcset: document.querySelector('.about-photo source')?.getAttribute('srcset') || '',
                heroPreload: !!document.querySelector('link[rel="preload"][href*="hakkimizda"]'),
                titleContrast: titleC,
                bodyContrast: bodyC,
                delay0: delays[0] || '',
                delay1: delays[1] || '',
                visibleCards,
                revealStyles,
                cardCount: cards.length,
              };
            }"""
        )

        if not layout.get("ok"):
            assert_metric("faz64_about_layout_present", 0, "1", False)
            ok = False
        else:
            layout_ok = layout["twoCol"] and layout["sideBySide"]
            border_ok = layout["frameBorder"] == "rgb(184, 148, 80)" and layout["frameBorderWidth"] == "1px"
            img_ok = (
                layout["imgLoading"] == "lazy"
                and layout["imgDecoding"] == "async"
                and layout["imgWidth"] == "1200"
                and layout["imgHeight"] == "800"
                and layout["imgAlt"] == ""
                and layout["imgAriaHidden"] == "true"
                and "hakkimizda-1200.jpg" in layout["imgSrc"]
                and "hakkimizda-600.webp" in layout["srcset"]
                and "hakkimizda-1200.webp" in layout["srcset"]
            )
            delay_step = 0
            if layout["delay0"].endswith("ms") and layout["delay1"].endswith("ms"):
                delay_step = int(layout["delay1"].replace("ms", "")) - int(layout["delay0"].replace("ms", ""))
            delay_ok = 60 <= delay_step <= 80
            title_c = round(float(layout["titleContrast"]), 2)
            body_c = round(float(layout["bodyContrast"]), 2)
            contrast_ok = title_c >= 4.5 and body_c >= 4.5
            cards_ok = layout["visibleCards"] == 2 and layout["cardCount"] == 2
            anim_ok = all(
                s["opacity"] == "1" and (s["transform"] == "none" or "matrix" in s["transform"])
                for s in layout["revealStyles"]
            )

            assert_metric("faz64_about_two_column_desktop", 1 if layout_ok else 0, "text|photo", layout_ok)
            assert_metric("faz64_about_photo_frame_gold_border", layout["frameBorder"], "rgb(184, 148, 80)", border_ok)
            assert_metric("faz64_about_img_lazy_async_dims", 1 if img_ok else 0, "lazy+async+1200x800", img_ok)
            assert_metric("faz64_about_no_preload", 1 if not layout["heroPreload"] else 0, "no preload", not layout["heroPreload"])
            assert_metric("faz64_about_title_contrast", title_c, ">= 4.5", title_c >= 4.5)
            assert_metric("faz64_about_body_contrast", body_c, ">= 4.5", body_c >= 4.5)
            assert_metric("faz64_vm_stagger_delay_step_ms", delay_step, "60-80", delay_ok)
            assert_metric("faz64_vm_cards_revealed", layout["visibleCards"], "2", cards_ok)
            assert_metric("faz64_vm_reveal_transform_opacity_only", 1 if anim_ok else 0, "visible", anim_ok)
            assert_metric("faz64_about_console_errors", len(errors), "0", len(errors) == 0)
            ok = (
                ok
                and layout_ok
                and border_ok
                and img_ok
                and delay_ok
                and contrast_ok
                and cards_ok
                and anim_ok
                and len(errors) == 0
            )

        cls_score = page.evaluate(
            """() => new Promise(resolve => {
              let cls = 0;
              const obs = new PerformanceObserver(list => {
                for (const entry of list.getEntries()) {
                  if (!entry.hadRecentInput) cls += entry.value;
                }
              });
              obs.observe({ type: 'layout-shift', buffered: true });
              setTimeout(() => { obs.disconnect(); resolve(cls); }, 1200);
            })"""
        )
        cls_ok = float(cls_score) < 0.05
        assert_metric("faz64_about_cls_score", round(float(cls_score), 4), "< 0.05", cls_ok)
        ok = ok and cls_ok

        mobile_page = browser.new_page(viewport={"width": 360, "height": 740})
        mobile_page.goto(BASE + "/", wait_until="networkidle")
        mobile_page.locator("#about").scroll_into_view_if_needed()
        mobile_page.wait_for_timeout(1000)
        mobile_order = mobile_page.evaluate(
            """() => {
              const text = document.querySelector('.about-text');
              const photo = document.querySelector('.about-photo');
              if (!text || !photo) return { ok: false };
              const tr = text.getBoundingClientRect();
              const pr = photo.getBoundingClientRect();
              return { ok: true, photoAfterText: pr.top >= tr.bottom - 4 };
            }"""
        )
        mobile_ok = mobile_order.get("ok") and mobile_order.get("photoAfterText")
        assert_metric("faz64_mobile_photo_after_text", 1 if mobile_ok else 0, "stacked", mobile_ok)
        ok = ok and mobile_ok
        mobile_page.close()

        for label, width, height in VIEWPORTS:
            vp = browser.new_page(viewport={"width": width, "height": height})
            vp.goto(BASE + "/", wait_until="networkidle")
            vp.locator("#about").scroll_into_view_if_needed()
            vp.wait_for_timeout(800)
            overflow = vp.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth")
            assert_metric(f"faz64_overflow_{label}_{width}", 1 if overflow else 0, "0", overflow)
            ok = ok and overflow
            vp.close()

        fa_page = browser.new_page(viewport={"width": 1440, "height": 900})
        fa_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
        fa_page.locator("#about").scroll_into_view_if_needed()
        fa_page.wait_for_timeout(1200)
        fa_data = fa_page.evaluate(
            """() => {
              const editorial = document.querySelector('.about-editorial');
              const text = document.querySelector('.about-text');
              const photo = document.querySelector('.about-photo');
              const frame = document.querySelector('.about-photo-frame');
              const tr = text?.getBoundingClientRect();
              const pr = photo?.getBoundingClientRect();
              const before = frame ? getComputedStyle(frame, '::before') : null;
              return {
                dir: document.documentElement.getAttribute('dir') || '',
                mirrored: tr && pr ? tr.left > pr.left : false,
                beforeLeft: before ? before.left : '',
                beforeRight: before ? before.right : '',
                overflow: document.documentElement.scrollWidth <= window.innerWidth,
                twoCol: editorial ? getComputedStyle(editorial).gridTemplateColumns.split(' ').length >= 2 : false,
              };
            }"""
        )
        fa_ok = (
            fa_data["dir"] == "rtl"
            and fa_data["mirrored"]
            and fa_data["twoCol"]
            and fa_data["overflow"]
        )
        assert_metric("faz64_fa_rtl_two_column", 1 if fa_data["twoCol"] else 0, "2 cols", fa_data["twoCol"])
        assert_metric("faz64_fa_rtl_mirrored", 1 if fa_data["mirrored"] else 0, "text right", fa_data["mirrored"])
        assert_metric("faz64_fa_overflow", 1 if fa_data["overflow"] else 0, "0", fa_data["overflow"])
        ok = ok and fa_ok
        fa_page.close()

        rm_page = browser.new_page(viewport={"width": 1440, "height": 900})
        rm_page.emulate_media(reduced_motion="reduce")
        rm_page.goto(BASE + "/", wait_until="networkidle")
        rm_page.locator("#about").scroll_into_view_if_needed()
        rm_page.wait_for_timeout(800)
        rm_visible = rm_page.evaluate(
            """() => {
              const cards = document.querySelectorAll('.vision-mission-card.is-visible');
              const reveals = document.querySelectorAll('#about .reveal');
              const allVisible = Array.from(reveals).every(el => parseFloat(getComputedStyle(el).opacity) > 0.5);
              return { cards: cards.length, allVisible };
            }"""
        )
        rm_ok = rm_visible["cards"] == 2 and rm_visible["allVisible"]
        assert_metric("faz64_reduced_motion_all_visible", 1 if rm_ok else 0, "2 cards + reveals", rm_ok)
        ok = ok and rm_ok
        rm_page.close()

        nojs_context = browser.new_context(java_script_enabled=False, viewport={"width": 1440, "height": 900})
        nojs_page = nojs_context.new_page()
        nojs_page.goto(BASE + "/", wait_until="networkidle")
        nojs_visible = nojs_page.evaluate(
            """() => {
              const reveals = document.querySelectorAll('#about .reveal');
              const cards = document.querySelectorAll('.vision-mission-card');
              const img = document.querySelector('.about-photo img');
              return reveals.length >= 3
                && Array.from(reveals).every(el => parseFloat(getComputedStyle(el).opacity) === 1)
                && cards.length === 2
                && !!img
                && img.getBoundingClientRect().width > 0;
            }"""
        )
        assert_metric("faz64_nojs_about_fully_visible", 1 if nojs_visible else 0, "visible", nojs_visible)
        ok = ok and nojs_visible
        nojs_page.close()
        nojs_context.close()

        page.close()
        browser.close()

    return ok


def capture_faz64_hakkimizda_screenshots() -> list[str]:
    """Faz 6.4: Hakkımızda + Vizyon/Misyon reveal sonrası kanıt ekran görüntüleri."""
    shots: list[str] = []
    out_dir = ROOT / "docs/faz6"
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for label, width, height in VIEWPORTS:
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(BASE + "/" + suffix, wait_until="networkidle")
                page.locator("#about").scroll_into_view_if_needed()
                page.wait_for_timeout(1500)
                visible_cards = page.evaluate(
                    "() => document.querySelectorAll('.vision-mission-card.is-visible').length"
                )
                if visible_cards < 2:
                    page.evaluate(
                        """() => {
                          document.querySelectorAll('#about .reveal').forEach((el) => {
                            el.classList.add('is-visible');
                          });
                        }"""
                    )
                    page.wait_for_timeout(600)
                about = page.locator("#about")
                shot_name = f"faz6-hakkimizda-{lang}-{label}-{width}x{height}.png"
                shot_path = out_dir / shot_name
                about.screenshot(path=str(shot_path))
                shots.append(f"docs/faz6/{shot_name}")
                page.close()
        browser.close()

    return shots


def assert_faz55_multilang_frontend() -> bool:
    ok = True
    en_content = load_lang_content(CONTENT_EN_PATH)
    de_content = load_lang_content(CONTENT_DE_PATH)
    ru_content = load_lang_content(CONTENT_RU_PATH)
    fa_content = load_lang_content(CONTENT_FA_PATH)
    tr_content = load_content()
    hero_expected = {
        "tr": tr_content["hero"]["tagline"],
        "en": en_content["hero"]["tagline"],
        "de": de_content["hero"]["tagline"],
        "ru": ru_content["hero"]["tagline"],
        "fa": fa_content["hero"]["tagline"],
    }
    kvkk_en_title = en_content["kvkk"]["title"]
    kvkk_ru_title = ru_content["kvkk"]["title"]
    kvkk_fa_title = fa_content["kvkk"]["title"]
    en_title_expected = en_content["site"]["title"]
    locale_map = {"tr": "tr_TR", "en": "en_US", "de": "de_DE"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(500)
        header_baseline = page.evaluate(
            """() => Math.round(document.querySelector('.site-header').getBoundingClientRect().height)"""
        )
        assert_metric("lang_header_height_baseline_px", header_baseline, "baseline", True)

        # Desktop real click EN
        page.click('.lang-switcher a[href*="lang=en"]')
        page.wait_for_load_state("networkidle")
        en_hero = page.locator(".hero-title-accent").inner_text().strip()
        en_lang_attr = page.locator("html").get_attribute("lang") or ""
        en_og_locale = page.locator('meta[property="og:locale"]').get_attribute("content") or ""
        en_title = page.locator("title").inner_text().strip()
        assert_metric("lang_en_hero_exact", 1 if en_hero == hero_expected["en"] else 0, "exact", en_hero == hero_expected["en"])
        assert_metric("lang_en_html_lang", en_lang_attr, "en", en_lang_attr == "en")
        assert_metric("lang_en_og_locale", en_og_locale, "en_US", en_og_locale == "en_US")
        assert_metric("lang_en_title_exact", 1 if en_title == en_title_expected else 0, "exact", en_title == en_title_expected)
        ok = ok and en_hero == hero_expected["en"] and en_lang_attr == "en" and en_og_locale == "en_US" and en_title == en_title_expected

        hreflang_count = page.locator('link[rel="alternate"][hreflang]').count()
        assert_metric("lang_hreflang_total", hreflang_count, "6", hreflang_count == 6)
        ok = ok and hreflang_count == 6

        # Cookie persistence
        page.goto(BASE + "/", wait_until="networkidle")
        persisted_lang = page.locator("html").get_attribute("lang") or ""
        assert_metric("lang_cookie_persist_en", persisted_lang, "en", persisted_lang == "en")
        ok = ok and persisted_lang == "en"

        # Invalid language falls back to TR without console errors
        errors.clear()
        page.goto(BASE + "/?lang=xx", wait_until="networkidle")
        bad_lang_attr = page.locator("html").get_attribute("lang") or ""
        bad_hero = page.locator(".hero-title-accent").inner_text().strip()
        bad_console = len(errors)
        assert_metric("lang_invalid_fallback_tr", bad_lang_attr, "tr", bad_lang_attr == "tr")
        assert_metric("lang_invalid_tr_hero", 1 if bad_hero == hero_expected["tr"] else 0, "exact", bad_hero == hero_expected["tr"])
        assert_metric("lang_invalid_console_errors", bad_console, "0", bad_console == 0)
        ok = ok and bad_lang_attr == "tr" and bad_hero == hero_expected["tr"] and bad_console == 0

        # Desktop real click DE then TR
        page.click('.lang-switcher a[href*="lang=de"]')
        page.wait_for_load_state("networkidle")
        de_hero = page.locator(".hero-title-accent").inner_text().strip()
        de_lang_attr = page.locator("html").get_attribute("lang") or ""
        de_og_locale = page.locator('meta[property="og:locale"]').get_attribute("content") or ""
        assert_metric("lang_de_hero_exact", 1 if de_hero == hero_expected["de"] else 0, "exact", de_hero == hero_expected["de"])
        assert_metric("lang_de_html_lang", de_lang_attr, "de", de_lang_attr == "de")
        assert_metric("lang_de_og_locale", de_og_locale, "de_DE", de_og_locale == "de_DE")
        ok = ok and de_hero == hero_expected["de"] and de_lang_attr == "de" and de_og_locale == "de_DE"

        page.click('.lang-switcher a[href*="lang=ru"]')
        page.wait_for_load_state("networkidle")
        ru_hero = page.locator(".hero-title-accent").inner_text().strip()
        ru_lang_attr = page.locator("html").get_attribute("lang") or ""
        ru_dir_attr = page.locator("html").get_attribute("dir") or ""
        ru_og_locale = page.locator('meta[property="og:locale"]').get_attribute("content") or ""
        assert_metric("lang_ru_hero_exact", 1 if ru_hero == hero_expected["ru"] else 0, "exact", ru_hero == hero_expected["ru"])
        assert_metric("lang_ru_html_lang", ru_lang_attr, "ru", ru_lang_attr == "ru")
        assert_metric("lang_ru_html_dir", ru_dir_attr, "ltr", ru_dir_attr == "ltr")
        assert_metric("lang_ru_og_locale", ru_og_locale, "ru_RU", ru_og_locale == "ru_RU")
        ok = ok and ru_hero == hero_expected["ru"] and ru_lang_attr == "ru" and ru_dir_attr == "ltr" and ru_og_locale == "ru_RU"

        page.click('.lang-switcher a[href*="lang=fa"]')
        page.wait_for_load_state("networkidle")
        fa_hero = page.locator(".hero-title-accent").inner_text().strip()
        fa_lang_attr = page.locator("html").get_attribute("lang") or ""
        fa_dir_attr = page.locator("html").get_attribute("dir") or ""
        fa_og_locale = page.locator('meta[property="og:locale"]').get_attribute("content") or ""
        fa_hero_align = page.evaluate(
            """() => {
              const el = document.querySelector('.hero-content');
              return el ? getComputedStyle(el).textAlign : '';
            }"""
        )
        assert_metric("lang_fa_hero_exact", 1 if fa_hero == hero_expected["fa"] else 0, "exact", fa_hero == hero_expected["fa"])
        assert_metric("lang_fa_html_lang", fa_lang_attr, "fa", fa_lang_attr == "fa")
        assert_metric("lang_fa_html_dir", fa_dir_attr, "rtl", fa_dir_attr == "rtl")
        assert_metric("lang_fa_og_locale", fa_og_locale, "fa_IR", fa_og_locale == "fa_IR")
        assert_metric("lang_fa_hero_text_align", fa_hero_align, "right", fa_hero_align == "right")
        ok = (
            ok
            and fa_hero == hero_expected["fa"]
            and fa_lang_attr == "fa"
            and fa_dir_attr == "rtl"
            and fa_og_locale == "fa_IR"
            and fa_hero_align == "right"
        )

        for vp_name, vp_w, vp_h in VIEWPORTS:
            vp_page = browser.new_page(viewport={"width": vp_w, "height": vp_h})
            vp_page.goto(BASE + "/?lang=fa", wait_until="networkidle")
            fa_overflow = vp_page.evaluate(
                "() => document.documentElement.scrollWidth <= window.innerWidth"
            )
            assert_metric(
                f"lang_fa_overflow_{vp_name}",
                1 if fa_overflow else 0,
                "no horizontal overflow",
                fa_overflow,
            )
            ok = ok and fa_overflow
            vp_page.close()

        page.click('.lang-switcher a[href*="lang=tr"]')
        page.wait_for_load_state("networkidle")
        tr_hero = page.locator(".hero-title-accent").inner_text().strip()
        tr_lang_attr = page.locator("html").get_attribute("lang") or ""
        assert_metric("lang_tr_return_hero_exact", 1 if tr_hero == hero_expected["tr"] else 0, "exact", tr_hero == hero_expected["tr"])
        assert_metric("lang_tr_return_html_lang", tr_lang_attr, "tr", tr_lang_attr == "tr")
        ok = ok and tr_hero == hero_expected["tr"] and tr_lang_attr == "tr"

        # Header height guard
        for lang in SITE_LANGS:
            page.goto(BASE + f"/?lang={lang}", wait_until="networkidle")
            header_h = page.evaluate(
                """() => Math.round(document.querySelector('.site-header').getBoundingClientRect().height)"""
            )
            growth = header_h - header_baseline
            assert_metric(f"lang_{lang}_header_height_px", header_h, "<= 96", header_h <= 96)
            assert_metric(f"lang_{lang}_header_growth_px", growth, "<= 8", growth <= 8)
            ok = ok and header_h <= 96 and growth <= 8

        # KVKK EN render
        page.goto(BASE + "/kvkk.php?lang=en", wait_until="networkidle")
        kvkk_h1 = page.locator("#kvkk-heading").inner_text().strip()
        assert_metric("lang_kvkk_en_heading", 1 if kvkk_h1 == kvkk_en_title else 0, "exact", kvkk_h1 == kvkk_en_title)
        ok = ok and kvkk_h1 == kvkk_en_title

        page.goto(BASE + "/kvkk.php?lang=ru", wait_until="networkidle")
        kvkk_ru_h1 = page.locator("#kvkk-heading").inner_text().strip()
        assert_metric("lang_kvkk_ru_heading", 1 if kvkk_ru_h1 == kvkk_ru_title else 0, "exact", kvkk_ru_h1 == kvkk_ru_title)
        ok = ok and kvkk_ru_h1 == kvkk_ru_title

        page.goto(BASE + "/kvkk.php?lang=fa", wait_until="networkidle")
        kvkk_fa_h1 = page.locator("#kvkk-heading").inner_text().strip()
        kvkk_fa_dir = page.locator("html").get_attribute("dir") or ""
        assert_metric("lang_kvkk_fa_heading", 1 if kvkk_fa_h1 == kvkk_fa_title else 0, "exact", kvkk_fa_h1 == kvkk_fa_title)
        assert_metric("lang_kvkk_fa_dir", kvkk_fa_dir, "rtl", kvkk_fa_dir == "rtl")
        ok = ok and kvkk_fa_h1 == kvkk_fa_title and kvkk_fa_dir == "rtl"

        # Mobile selector real click
        mobile = browser.new_page(viewport={"width": 360, "height": 740})
        mobile.goto(BASE + "/", wait_until="networkidle")
        mobile.click("[data-nav-toggle]")
        mobile.click('.lang-switcher a[href*="lang=en"]')
        mobile.wait_for_load_state("networkidle")
        mobile_lang = mobile.locator("html").get_attribute("lang") or ""
        mobile_hero = mobile.locator(".hero-title-accent").inner_text().strip()
        assert_metric("lang_mobile_switch_en_html_lang", mobile_lang, "en", mobile_lang == "en")
        assert_metric("lang_mobile_switch_en_hero", 1 if mobile_hero == hero_expected["en"] else 0, "exact", mobile_hero == hero_expected["en"])
        ok = ok and mobile_lang == "en" and mobile_hero == hero_expected["en"]
        mobile.close()
        browser.close()

    # Per-language resource byte budgets
    for lang in SITE_LANGS:
        total = measure_homepage_total_bytes_for_lang(lang)
        assert_metric(f"homepage_total_resource_bytes_{lang}", total, "<= 1200000", total <= 1_200_000)
        ok = ok and total <= 1_200_000

    # Contact form messages in EN (log + 422)
    session = requests.Session()
    status_en, body_en = contact_post(
        session,
        {
            "lang": "en",
            "name": "Lang QA",
            "email": "lang.qa@example.com",
            "subject": "Language",
            "message": "English response test",
        },
    )
    status_en_422, body_en_422 = contact_post(
        requests.Session(),
        {"lang": "en", "email": "invalid", "message": "missing name"},
    )
    en_success = body_en.get("message", "") == en_content["contact"]["form"]["success"]
    en_error = body_en_422.get("message", "") == en_content["contact"]["form"]["error"]
    assert_metric("lang_contact_en_success_status", status_en, "200", status_en == 200)
    assert_metric("lang_contact_en_success_message", 1 if en_success else 0, "exact", en_success)
    assert_metric("lang_contact_en_422_status", status_en_422, "422", status_en_422 == 422)
    assert_metric("lang_contact_en_422_message", 1 if en_error else 0, "exact", en_error)
    ok = ok and status_en == 200 and en_success and status_en_422 == 422 and en_error

    return ok


def assert_faz58_hours_frontend() -> bool:
    ok = True
    hours_closed = {
        "tr": "Kapalı",
        "en": "Closed",
        "de": "Geschlossen",
        "ru": "Закрыто",
        "fa": "تعطیل",
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        errors: list[str] = []
        for lang, expected in hours_closed.items():
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            url = BASE + "/" if lang == "tr" else f"{BASE}/?lang={lang}"
            page.goto(url + "#contact", wait_until="networkidle")
            closed = page.locator(".contact-hours-row").nth(1).locator("dd").inner_text().strip()
            assert_metric(f"faz58_hours_frontend_{lang}", 1 if closed == expected else 0, expected, closed == expected)
            ok = ok and closed == expected
            page.close()
        console_ok = len(errors) == 0
        assert_metric("faz58_hours_frontend_console_errors", len(errors), "0", console_ok)
        ok = ok and console_ok
        browser.close()
    return ok


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


def pick_free_port(host: str = SMTP_DEBUG_HOST) -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def write_smtp_test_config(stub_dir: Path, smtp_port: int) -> None:
    if not CONFIG_PATH.is_file() or "admin_password_hash" not in CONFIG_PATH.read_text(encoding="utf-8"):
        setup_admin_config()
    text = CONFIG_PATH.read_text(encoding="utf-8")
    replacements = [
        (r"'mail_mode'\s*=>\s*'[^']*'", "'mail_mode' => 'smtp'"),
        (r"'smtp_host'\s*=>\s*'[^']*'", f"'smtp_host' => '{SMTP_DEBUG_HOST}'"),
        (r"'smtp_port'\s*=>\s*\d+", f"'smtp_port' => {smtp_port}"),
        (r"'smtp_secure'\s*=>\s*'[^']*'", "'smtp_secure' => ''"),
    ]
    for pattern, repl in replacements:
        text, count = re.subn(pattern, repl, text, count=1)
        if count == 0 and pattern.startswith("'smtp_host'"):
            text = text.replace(
                "'smtp_user' => 'info@emirgandanismanlik.com',",
                "'smtp_host' => '127.0.0.1',\n    'smtp_port' => "
                + str(smtp_port)
                + ",\n    'smtp_secure' => '',\n    'smtp_user' => 'info@emirgandanismanlik.com',",
                1,
            )
    if re.search(r"'smtp_pass'\s*=>", text):
        text = re.sub(r"'smtp_pass'\s*=>\s*'[^']*'", "'smtp_pass' => ''", text, count=1)
    else:
        text = text.replace(
            "'smtp_user' => 'info@emirgandanismanlik.com',",
            "'smtp_user' => 'info@emirgandanismanlik.com',\n    'smtp_pass' => '',",
            1,
        )
    CONFIG_PATH.write_text(text, encoding="utf-8")
    (stub_dir / "config.php").write_bytes(CONFIG_PATH.read_bytes())


def start_smtp_debug_server(stub_dir: Path, smtp_port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            str(SMTP_DEBUG_SCRIPT),
            "--host",
            SMTP_DEBUG_HOST,
            "--port",
            str(smtp_port),
            "--out-dir",
            str(stub_dir / "captured"),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_smtp_ready(port: int, timeout: float = 8.0) -> bool:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((SMTP_DEBUG_HOST, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def assert_faz53_contact_smtp() -> bool:
    ok = True
    config_before = snapshot_config()
    server: subprocess.Popen | None = None
    php_server: subprocess.Popen | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="smtp-stub-") as tmp:
            stub_dir = Path(tmp)
            smtp_port = pick_free_port()
            write_smtp_test_config(stub_dir, smtp_port)
            config_text = CONFIG_PATH.read_text(encoding="utf-8")
            smtp_mode_ok = bool(re.search(r"'mail_mode'\s*=>\s*'smtp'", config_text)) and bool(
                re.search(rf"'smtp_port'\s*=>\s*{smtp_port}\b", config_text)
            )
            assert_metric("smtp_test_config_mail_mode", 1 if smtp_mode_ok else 0, "smtp + debug port", smtp_mode_ok)
            ok = ok and smtp_mode_ok
            if not smtp_mode_ok:
                return ok

            server = start_smtp_debug_server(stub_dir, smtp_port)
            smtp_ready = wait_smtp_ready(smtp_port)
            time.sleep(0.5)
            assert_metric("smtp_debug_server_ready", 1 if smtp_ready else 0, "port open", smtp_ready)
            ok = ok and smtp_ready
            if not smtp_ready:
                return ok

            php_server = start_mail_test_server(stub_dir, fail=False)
            ready = wait_http_ready(MAIL_TEST_BASE)
            assert_metric("smtp_php_server_ready", 1 if ready else 0, "HTTP 200", ready)
            ok = ok and ready
            if not ready:
                return ok

            payload = {
                "name": "SMTP Stub QA",
                "email": "stub.sender@example.com",
                "phone": "5550001122",
                "subject": "UTF-8 konu: SMTP testi",
                "message": "SMTP stub gövde doğrulama metni.",
            }
            session = requests.Session()
            resp = session.post(
                MAIL_TEST_BASE + "/api/contact.php",
                data=payload,
                headers={"Accept": "application/json"},
                timeout=30,
            )
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            captured = sorted((stub_dir / "captured").glob("mail-*.eml"))
            count_ok = len(captured) == 1
            assert_metric("smtp_mode_valid_post_status", resp.status_code, "200", resp.status_code == 200)
            assert_metric("smtp_mode_debug_file_count", len(captured), "1", count_ok)
            assert_metric("smtp_mode_valid_post_ok", 1 if body.get("ok") else 0, "true", bool(body.get("ok")))
            ok = ok and resp.status_code == 200 and count_ok and bool(body.get("ok"))

            if captured:
                mail = parse_mail_file(captured[0])
                to_ok = "info@emirgandanismanlik.com" in mail["to"]
                reply_ok = mail["reply_to"] == payload["email"]
                subject_ok = mail["subject"] == payload["subject"]
                body_ok = payload["name"] in mail["body"] and payload["message"] in mail["body"]
                assert_metric("smtp_mode_captured_to", mail["to"], "info@emirgandanismanlik.com", to_ok)
                assert_metric("smtp_mode_captured_reply_to", mail["reply_to"], payload["email"], reply_ok)
                assert_metric("smtp_mode_captured_subject", mail["subject"], payload["subject"], subject_ok)
                assert_metric("smtp_mode_captured_body", 1 if body_ok else 0, "name+message present", body_ok)
                ok = ok and to_ok and reply_ok and subject_ok and body_ok

            stop_server(php_server)
            php_server = None
            stop_server(server)
            server = None
            time.sleep(0.5)

            closed_port = pick_free_port()
            write_smtp_test_config(stub_dir, closed_port)
            CONFIG_PATH.write_bytes((stub_dir / "config.php").read_bytes())
            php_server = start_mail_test_server(stub_dir, fail=False)
            fail_ready = wait_http_ready(MAIL_TEST_BASE)
            assert_metric("smtp_fail_php_server_ready", 1 if fail_ready else 0, "HTTP 200", fail_ready)
            ok = ok and fail_ready
            if fail_ready:
                logs_before = snapshot_mail_log()
                fail_session = requests.Session()
                fail_resp = fail_session.post(
                    MAIL_TEST_BASE + "/api/contact.php",
                    data={
                        "name": "Fail SMTP",
                        "email": "fail.smtp@example.com",
                        "subject": "Fail",
                        "message": "SMTP fail senaryosu.",
                    },
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                logs_after = snapshot_mail_log()
                fail_text = fail_resp.text.lower()
                status_ok = fail_resp.status_code == 500
                no_log_ok = logs_after == logs_before
                no_leak_ok = "exception" not in fail_text and "stack" not in fail_text and "phpmailer" not in fail_text
                assert_metric("smtp_mode_debug_off_status", fail_resp.status_code, "500", status_ok)
                assert_metric("smtp_mode_debug_off_no_log", 1 if no_log_ok else 0, "no new mail-log", no_log_ok)
                assert_metric("smtp_mode_debug_off_no_leak", 1 if no_leak_ok else 0, "no exception/stack", no_leak_ok)
                ok = ok and status_ok and no_log_ok and no_leak_ok
    finally:
        stop_server(php_server)
        stop_server(server)
        restore_config(config_before)

    return ok


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
        rel_posix = rel.replace("\\", "/")
        if rel_posix == "scripts/verify_qa.py":
            continue
        if "api/lib/phpmailer/" in rel_posix.lower():
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in CREDENTIAL_VALUE_RE.finditer(text):
            if match.group(1).strip():
                credential_hits += 1
                break
    cred_ok = credential_hits == 0
    assert_metric("security_no_credential_values_in_repo", credential_hits, "0", cred_ok)
    ok = ok and cred_ok
    return ok


def assert_faz51_scope_css() -> bool:
    ok = True
    for name in ("tokens.css",):
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

    main_path = CSS_DIR / "main.css"
    main_rel = main_path.relative_to(ROOT).as_posix()
    main_head = subprocess.run(["git", "show", f"HEAD:{main_rel}"], cwd=ROOT, capture_output=True)
    if main_head.returncode != 0:
        assert_metric("scope_main_css_changed_faz54", 0, "changed from HEAD", False)
        ok = False
    else:
        main_changed = hashlib.sha256(main_head.stdout).hexdigest() != hashlib.sha256(main_path.read_bytes()).hexdigest()
        assert_metric("scope_main_css_changed_faz54", 1 if main_changed else 0, "changed from HEAD", main_changed)
        ok = ok and main_changed
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

    hreflang_tags = re.findall(r'rel="alternate"\s+hreflang="([^"]+)"', home)
    hreflang_ok = set(hreflang_tags) == {"tr", "en", "de", "ru", "fa", "x-default"}
    assert_metric("homepage_hreflang_count", len(hreflang_tags), "6", len(hreflang_tags) == 6)
    assert_metric("homepage_hreflang_set", 1 if hreflang_ok else 0, "tr,en,de,ru,fa,x-default", hreflang_ok)
    ok = ok and hreflang_ok

    home_en = requests.get(BASE + "/?lang=en", timeout=30).text
    og_locale_en = 'property="og:locale" content="en_US"' in home_en
    en_title = load_lang_content(CONTENT_EN_PATH)["site"]["title"]
    title_match = f"<title>{en_title}</title>" in home_en
    assert_metric("homepage_en_og_locale", 1 if og_locale_en else 0, "en_US", og_locale_en)
    assert_metric("homepage_en_title_exact", 1 if title_match else 0, "match content.en.json", title_match)
    ok = ok and og_locale_en and title_match

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


def measure_homepage_total_bytes_for_lang(lang: str = "tr") -> int:
    session = requests.Session()
    total = 0
    path = "/" if lang == "tr" else f"/?lang={lang}"
    html_resp = session.get(BASE + path, timeout=30)
    total += len(html_resp.content)
    allowed_ext = (".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".woff", ".woff2")
    for path in collect_page_asset_paths(html_resp.text):
        if (
            path.startswith("/#")
            or "?lang=" in path.lower()
            or path.lower().endswith(".php")
        ):
            continue
        if not path.lower().endswith(allowed_ext):
            continue
        try:
            resp = session.get(BASE + path, timeout=30)
            if resp.status_code == 200:
                total += len(resp.content)
        except requests.RequestException:
            pass
    return total


def measure_homepage_total_bytes() -> int:
    total = measure_homepage_total_bytes_for_lang("tr")
    limit_ok = total <= 1_200_000
    assert_metric("homepage_total_resource_bytes", total, "<= 1200000", limit_ok)
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
        page.locator("#services").scroll_into_view_if_needed()
        page.wait_for_timeout(800)

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
              if (!el) return { exists: false, display: '', pointerEvents: '' };
              const s = getComputedStyle(el);
              return {
                exists: true,
                display: s.display,
                pointerEvents: s.pointerEvents,
              };
            }"""
        )
        wm_ok = (
            watermark.get("exists")
            and watermark.get("display") == "none"
            and watermark.get("pointerEvents") == "none"
        )
        assert_metric("hero_watermark_display_none", watermark.get("display", ""), "none", wm_ok)
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
              const serviceVisible = document.querySelectorAll('.service-card.is-visible').length;
              return { total: els.length, visible: v, serviceVisible };
            }"""
        )
        reveal_ok = (
            reveal["visible"] == reveal["total"]
            and reveal["total"] >= 15
            and reveal["serviceVisible"] == 7
        )
        assert_metric(
            "homepage_reveal_visible",
            f"{reveal['visible']}/{reveal['total']}+svc{reveal['serviceVisible']}",
            "all visible",
            reveal_ok,
        )
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


def assert_faz54_contact_hours() -> bool:
    """Faz 5.4: çalışma saatleri kartı ve sütun alt hizası."""
    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(BASE + "/#contact", wait_until="networkidle")
        page.wait_for_timeout(600)

        layout = page.evaluate(
            """() => {
              const leftCol = document.querySelector('.contact-form-col');
              const info = document.querySelector('.contact-info');
              const form = document.querySelector('.contact-form');
              const hours = document.querySelector('.contact-hours-card');
              const section = document.getElementById('contact');
              if (!leftCol || !info || !section) return null;
              const lr = leftCol.getBoundingClientRect();
              const ir = info.getBoundingClientRect();
              const fr = form.getBoundingClientRect();
              const hr = hours ? hours.getBoundingClientRect() : null;
              return {
                columnDelta: Math.round(Math.abs(lr.bottom - ir.bottom)),
                sectionHeight: Math.round(section.getBoundingClientRect().height),
                hoursVisible: !!hours,
                hoursTitle: hours ? (hours.querySelector('h3')?.textContent || '').trim() : '',
                rowCount: hours ? hours.querySelectorAll('.contact-hours-row').length : 0,
                cardLeftDelta: hr ? Math.abs(hr.left - fr.left) : 999,
                cardRightDelta: hr ? Math.abs(hr.right - fr.right) : 999,
              };
            }"""
        )
        if layout is None:
            assert_metric("contact_hours_layout_present", 0, "1", False)
            return False

        delta_ok = layout["columnDelta"] <= CONTACT_HOURS_COLUMN_ALIGN_MAX_PX
        height_ok = layout["sectionHeight"] <= CONTACT_SECTION_PRE_HOURS_HEIGHT_PX + 8
        visible_ok = layout["hoursVisible"] and layout["hoursTitle"] == "Çalışma Saatleri" and layout["rowCount"] == 2
        left_ok = layout["cardLeftDelta"] <= CONTACT_HOURS_CARD_EDGE_MAX_PX
        right_ok = layout["cardRightDelta"] <= CONTACT_HOURS_CARD_EDGE_MAX_PX
        assert_metric("contact_hours_column_bottom_delta_px", layout["columnDelta"], f"<= {CONTACT_HOURS_COLUMN_ALIGN_MAX_PX}", delta_ok)
        assert_metric(
            "contact_hours_section_height_px",
            layout["sectionHeight"],
            f"<= {CONTACT_SECTION_PRE_HOURS_HEIGHT_PX + 8}",
            height_ok,
        )
        assert_metric("contact_hours_card_visible", 1 if visible_ok else 0, "title + 2 rows", visible_ok)
        assert_metric("contact_hours_card_left_align_px", round(layout["cardLeftDelta"], 2), f"<= {CONTACT_HOURS_CARD_EDGE_MAX_PX}", left_ok)
        assert_metric("contact_hours_card_right_align_px", round(layout["cardRightDelta"], 2), f"<= {CONTACT_HOURS_CARD_EDGE_MAX_PX}", right_ok)
        ok = ok and delta_ok and height_ok and visible_ok and left_ok and right_ok

        console_ok = len(errors) == 0
        assert_metric("contact_hours_desktop_console_errors", len(errors), "0", console_ok)
        ok = ok and console_ok
        page.close()

        mobile = browser.new_page(viewport={"width": 360, "height": 740})
        mobile.goto(BASE + "/#contact", wait_until="networkidle")
        mobile.wait_for_timeout(400)
        mobile_layout = mobile.evaluate(
            """() => {
              const hours = document.querySelector('.contact-hours-card');
              const formCol = document.querySelector('.contact-form-col');
              const form = document.querySelector('.contact-form');
              const hr = hours ? hours.getBoundingClientRect() : null;
              const fr = form.getBoundingClientRect();
              const below = hr ? hr.top >= fr.bottom - 4 : false;
              const full = hr ? Math.abs(hr.width - formCol.getBoundingClientRect().width) <= 8 : false;
              const overflow = document.documentElement.scrollWidth <= window.innerWidth;
              return { below, full, overflow, hasHours: !!hours };
            }"""
        )
        mobile_ok = mobile_layout["hasHours"] and mobile_layout["below"] and mobile_layout["full"] and mobile_layout["overflow"]
        assert_metric("contact_hours_mobile_below_form", 1 if mobile_layout["below"] else 0, "below form", mobile_layout["below"])
        assert_metric("contact_hours_mobile_full_width", 1 if mobile_layout["full"] else 0, "full width", mobile_layout["full"])
        assert_metric("contact_hours_mobile_no_overflow", 1 if mobile_layout["overflow"] else 0, "no overflow", mobile_layout["overflow"])
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
            for lang in SITE_LANGS:
                suffix = "" if lang == "tr" else f"?lang={lang}"
                path = "/" + suffix
                page_name = f"home-{lang}"
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
        ok = assert_faz53_contact_smtp() and ok
        ok = assert_mail_security() and ok
        ok = assert_lang_content_parity() and ok
        ok = assert_faz55_multilang_frontend() and ok
        ok = assert_faz58_hours_frontend() and ok
        ok = assert_seo_files() and ok
        ok = assert_page_health() and ok
        ok = assert_htaccess() and ok
        total_bytes = measure_homepage_total_bytes()
        results["homepage_total_resource_bytes"] = total_bytes
        ok = total_bytes <= 1_200_000 and ok
        ok = assert_faz61_hero_photo() and ok
        ok = assert_faz61b_hero_stats_strip() and ok
        ok = assert_faz61e_hero_embedded_watermark() and ok
        ok = assert_faz62_sektor_band() and ok
        ok = assert_faz63_sektor_network_audit() and ok
        ok = assert_faz63_hizmetler() and ok
        ok = assert_faz64_hakkimizda() and ok
        ok = assert_team_reorder_delete_guard() and ok
        ok = assert_visual_enrichment() and ok
        ok = assert_faz47_contact_layout() and ok
        ok = assert_faz54_contact_hours() and ok
        viewport_ok, shots = assert_viewport_qa()
        ok = viewport_ok and ok
        faz6_shots = capture_faz6_hero_screenshots()
        faz6_rev_shots = capture_faz6_hero_rev_screenshots()
        faz6_wm_shots = capture_faz6_hero_wm_screenshots()
        faz6_wm2_shots = capture_faz6_hero_wm2_screenshots()
        faz6_final_shots = capture_faz6_hero_final_screenshots()
        faz62_shots = capture_faz62_sektor_screenshots()
        faz63_shots = capture_faz63_hizmetler_screenshots()
        faz64_shots = capture_faz64_hakkimizda_screenshots()
        results["screenshots"] = shots + faz6_shots + faz6_rev_shots + faz6_wm_shots + faz6_wm2_shots + faz6_final_shots + faz62_shots + faz63_shots + faz64_shots
        results["faz6_hero_screenshots"] = faz6_shots
        results["faz6_hero_rev_screenshots"] = faz6_rev_shots
        results["faz6_hero_wm_screenshots"] = faz6_wm_shots
        results["faz6_hero_wm2_screenshots"] = faz6_wm2_shots
        results["faz6_hero_final_screenshots"] = faz6_final_shots
        results["faz62_sektor_screenshots"] = faz62_shots
        results["faz63_hizmetler_screenshots"] = faz63_shots
        results["faz64_hakkimizda_screenshots"] = faz64_shots
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
