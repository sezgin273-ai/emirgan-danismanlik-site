"""Kabul kriterli site doğrulama ve ekran görüntüsü üretici."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_emblem import (  # noqa: E402
    SRC,
    clean_transparency,
    cleaning_metrics,
    content_bbox_alpha,
    crop_to_square_emblem,
    dark_navy_band_count,
    emblem_metrics,
    to_rgba_array,
)
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "docs" / "screenshots"
BRAND_SHEET = ROOT / "docs" / "brand" / "contact-sheet.html"
BASE = "http://localhost:8080"
PROTECTED_ASSETS = [
    ROOT / "public_html/assets/img/logo-full.png",
    ROOT / "public_html/assets/img/logo-full-dark.png",
    ROOT / "public_html/assets/img/favicon.png",
    ROOT / "public_html/assets/img/apple-touch-icon.png",
]

ACCEPTANCE: dict[str, dict] = {}


def record(name: str, measured: float, limit: str, passed: bool) -> None:
    ACCEPTANCE[name] = {"measured": measured, "limit": limit, "passed": passed}


def assert_metric(name: str, measured: float, limit: str, passed: bool) -> None:
    record(name, measured, limit, passed)
    if not passed:
        print(f"FAIL {name}: measured={measured}, limit={limit}", file=sys.stderr)


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


def emblem_pipeline_metrics() -> dict:
    raw = to_rgba_array(Image.open(SRC))
    cleaned = clean_transparency(raw)
    clean_m = cleaning_metrics(cleaned)
    x0, y0, x1, y1 = content_bbox_alpha(cleaned)
    content_height = y1 - y0
    emblem = crop_to_square_emblem(cleaned)
    emblem_m = emblem_metrics(emblem, content_height)
    emblem_dark = np.array(Image.open(ROOT / "public_html/assets/img/emblem-dark.png").convert("RGBA"))
    navy_remaining = dark_navy_band_count(emblem_dark)
    return {
        "cleaning": clean_m,
        "emblem": emblem_m,
        "emblem_dark_navy_band_pixels": navy_remaining,
    }


def emblem_pipeline_assertions(metrics: dict) -> bool:
    ok = True
    clean = metrics["cleaning"]
    corners_ok = all(a == 0 for a in clean["corner_alphas"])
    assert_metric("emblem_corner_alphas_zero", 1 if corners_ok else 0, "all 0", corners_ok)
    oo = clean["opaque_outside_bbox"]
    assert_metric("emblem_opaque_outside_bbox", oo, "= 0", oo == 0)
    ok = ok and corners_ok and oo == 0

    em = metrics["emblem"]
    ar = em["aspect_ratio"]
    assert_metric("emblem_aspect_ratio", ar, "0.95–1.05", 0.95 <= ar <= 1.05)
    lr = em["left_right_fill_ratio"]
    assert_metric("emblem_left_right_fill_ratio", lr, "0.85–1.15", 0.85 <= lr <= 1.15)
    ok = ok and 0.95 <= ar <= 1.05 and 0.85 <= lr <= 1.15

    navy = metrics["emblem_dark_navy_band_pixels"]
    assert_metric("emblem_dark_navy_band_pixels", navy, "= 0", navy == 0)
    ok = ok and navy == 0
    return ok


def measure_hero_stats_strip(page) -> dict:
    page.locator("#hero").scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    return page.evaluate(
        """() => {
          const strip = document.querySelector('.hero-stats-strip');
          const stats = [...document.querySelectorAll('.hero-stat')];
          const divider = document.querySelector('.hero-stat-divider');
          const vp = { w: window.innerWidth, h: window.innerHeight };
          if (!strip || stats.length < 2) return null;
          const sr = strip.getBoundingClientRect();
          const viewportClip = sr.top < -3 || sr.left < -3
            || sr.bottom > vp.h + 3 || sr.right > vp.w + 3;
          const style = getComputedStyle(strip);
          const bg = style.backgroundColor;
          const bgMatch = bg.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
          const bgAlpha = bgMatch && bgMatch[4] !== undefined ? parseFloat(bgMatch[4]) : (bgMatch ? 1 : 0);
          const transparent = bg === 'transparent' || bgAlpha === 0;
          return {
            top: sr.top, left: sr.left, bottom: sr.bottom, right: sr.right,
            width: sr.width, height: sr.height,
            clipped: viewportClip || sr.width < 20 || sr.height < 10,
            statCount: stats.length,
            dividerWidth: divider ? getComputedStyle(divider).width : '',
            nowrap: style.flexWrap === 'nowrap',
            transparent,
          };
        }"""
    )


def measure_about(page) -> dict | None:
    return page.evaluate(
        """() => {
          const left = document.querySelector('.about-text');
          const right = document.querySelector('.about-cards');
          const cards = [...document.querySelectorAll('.vision-mission-card')];
          if (!left || !right || cards.length < 2) return null;
          const lr = left.getBoundingClientRect();
          const rr = right.getBoundingClientRect();
          const c0 = cards[0].getBoundingClientRect();
          const c1 = cards[1].getBoundingClientRect();
          const leftCenter = lr.top + lr.height / 2;
          const rightCenter = rr.top + rr.height / 2;
          const cols = getComputedStyle(document.querySelector('.about-grid')).gridTemplateColumns.split(' ');
          const colRatio = cols.length >= 2 ? parseFloat(cols[0]) / parseFloat(cols[1]) : 0;
          return {
            vertical_center_delta: Math.abs(leftCenter - rightCenter),
            card_height_delta: Math.abs(c0.height - c1.height),
            column_ratio: colRatio,
            alignItems: getComputedStyle(document.querySelector('.about-grid')).alignItems
          };
        }"""
    )


def measure_contact(page) -> dict | None:
    return page.evaluate(
        """() => {
          const formRow = document.querySelector('#contact-form .form-row:not(.visually-hidden)');
          const card = document.querySelector('.contact-info-grid .address-card');
          if (!formRow || !card) return null;
          const fr = formRow.getBoundingClientRect();
          const cr = card.getBoundingClientRect();
          return { top_delta: Math.abs(fr.top - cr.top) };
        }"""
    )


def measure_team(page) -> dict | None:
    return page.evaluate(
        """() => {
          const header = document.querySelector('#team .section-header');
          const grid = document.querySelector('#team .team-grid');
          const subtitle = document.querySelector('#team .section-subtitle');
          const intro = document.querySelector('.intro-text');
          const cards = [...document.querySelectorAll('#team .team-card')];
          if (!header || !grid || !subtitle || !intro || cards.length < 5) return null;
          const hr = header.getBoundingClientRect();
          const gr = grid.getBoundingClientRect();
          const subFs = getComputedStyle(subtitle).fontSize;
          const introFs = getComputedStyle(intro).fontSize;
          return {
            header_grid_right_delta_px: Math.abs(hr.right - gr.right),
            subtitle_font_size: subFs,
            intro_font_size: introFs,
            font_size_match: subFs === introFs,
            cards: cards.map((c, i) => {
              const r = c.getBoundingClientRect();
              return { index: i + 1, left: r.left, top: r.top, right: r.right, bottom: r.bottom };
            }),
          };
        }"""
    )


def assert_team_card_positions(cards: list[dict], baseline: list[dict], prefix: str = "team_card") -> bool:
    ok = True
    for card, ref in zip(cards, baseline, strict=True):
        for key in ("left", "top"):
            delta = abs(card[key] - ref[key])
            passed = delta <= 1
            name = f"{prefix}{card['index']}_{key}_delta_px"
            assert_metric(name, delta, "<= 1", passed)
            ok = ok and passed
    return ok


def test_js_resilience(browser, results: dict) -> bool:
    page = browser.new_page()
    page.route("**/assets/js/main.js", lambda route: route.abort())
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(BASE + "/?lang=tr", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(400)

    state = page.evaluate(
        """() => {
          const els = document.querySelectorAll('.reveal');
          let visible = 0;
          els.forEach(el => { if (parseFloat(getComputedStyle(el).opacity) > 0.5) visible++; });
          const serviceCards = document.querySelectorAll('.service-card');
          const serviceVisible = Array.from(serviceCards).every(
            c => parseFloat(getComputedStyle(c).opacity) > 0.5
          );
          return {
            total: els.length,
            visible,
            serviceCount: serviceCards.length,
            serviceVisible,
            hasJsClass: document.documentElement.classList.contains('js'),
          };
        }"""
    )
    results["js_resilience"] = state
    all_visible = (
        state["visible"] == state["total"]
        and state["total"] >= 15
        and state["serviceCount"] == 7
        and state["serviceVisible"]
    )
    assert_metric(
        "js_blocked_reveal_visible_count",
        f"{state['visible']}/{state['total']}+svc{state['serviceCount']}",
        "all visible",
        all_visible,
    )
    assert_metric("js_blocked_reveal_total", state["total"], ">= 15", state["total"] >= 15)
    page.close()
    return all_visible


def screenshot_section(page, selector: str, path: Path) -> None:
    loc = page.locator(selector)
    if loc.count():
        loc.screenshot(path=str(path))


def run_viewport(page, width: int, name: str, results: dict) -> bool:
    ok = True
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(BASE + "/?lang=tr", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1200)

    hero = measure_hero_stats_strip(page)
    if not hero:
        ok = False
        assert_metric(f"hero_stats_strip_exists_{name}", 0, "present", False)
    else:
        clipped = hero["clipped"]
        assert_metric(
            f"hero_stats_strip_in_viewport_{name}",
            0 if clipped else 1,
            "not clipped",
            not clipped,
        )
        assert_metric(
            f"hero_stats_strip_nowrap_{name}",
            1 if hero.get("nowrap") else 0,
            "nowrap",
            hero.get("nowrap"),
        )
        assert_metric(
            f"hero_stats_strip_transparent_{name}",
            1 if hero.get("transparent") else 0,
            "transparent",
            hero.get("transparent"),
        )
        results[f"hero_{name}"] = hero

    if width >= 900:
        page.locator("#about").scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        about = measure_about(page)
        if not about:
            ok = False
        else:
            vcd = about["vertical_center_delta"]
            chd = about["card_height_delta"]
            assert_metric("about_vertical_center_delta_px", vcd, "<= 8", vcd <= 8)
            assert_metric("about_card_height_delta_px", chd, "<= 4", chd <= 4)
            assert_metric(
                "about_column_ratio",
                about["column_ratio"],
                "~1.618 (±0.08)",
                abs(about["column_ratio"] - 1.618) < 0.08,
            )
            results["about_desktop"] = about
            ok = ok and vcd <= 8 and chd <= 4 and abs(about["column_ratio"] - 1.618) < 0.08

        page.locator("#contact").scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        contact = measure_contact(page)
        if contact:
            td = contact["top_delta"]
            assert_metric("contact_top_delta_px", td, "<= 8", td <= 8)
            results["contact_desktop"] = contact
            ok = ok and td <= 8

        if width == 1440:
            page.locator("#team").scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            team = measure_team(page)
            if not team:
                ok = False
                assert_metric("team_metrics_present", 0, "present", False)
            else:
                hgrd = team["header_grid_right_delta_px"]
                assert_metric("team_header_grid_right_delta_px", hgrd, "<= 2", hgrd <= 2)
                fs_ok = team["font_size_match"]
                assert_metric(
                    "team_subtitle_intro_font_size_match",
                    1 if fs_ok else 0,
                    "equal computed font-size",
                    fs_ok,
                )
                results["team_desktop"] = team
                ok = ok and hgrd <= 2 and fs_ok

                baseline_path = SHOT_DIR / "team-card-baseline-1440.json"
                if baseline_path.exists():
                    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
                    ok = assert_team_card_positions(team["cards"], baseline) and ok
                else:
                    baseline_path.write_text(
                        json.dumps(team["cards"], indent=2),
                        encoding="utf-8",
                    )
                    results["team_card_baseline_created"] = str(baseline_path)

    page.screenshot(path=str(SHOT_DIR / f"home-{name}.png"), full_page=True)
    results["screenshots"].append(f"docs/screenshots/home-{name}.png")

    for section_id, slug in [
        ("#hero", "hero"),
        ("#about", "about"),
        ("#services", "services"),
        ("#team", "team"),
        ("#contact", "contact"),
    ]:
        shot = SHOT_DIR / f"section-{slug}-{name}.png"
        page.locator(section_id).scroll_into_view_if_needed()
        page.wait_for_timeout(200)
        screenshot_section(page, section_id, shot)
        results["screenshots"].append(f"docs/screenshots/section-{slug}-{name}.png")

    form_ok = page.evaluate("() => document.getElementById('contact-form') !== null")
    assert_metric(f"contact_form_id_{name}", 1 if form_ok else 0, "present", form_ok)
    ok = ok and form_ok

    reveal = page.evaluate(
        """() => {
          const els = document.querySelectorAll('.reveal');
          let v = 0;
          els.forEach(el => { if (parseFloat(getComputedStyle(el).opacity) > 0.5) v++; });
          return { total: els.length, visible: v };
        }"""
    )
    results[f"reveal_{name}"] = reveal
    if reveal["visible"] < reveal["total"]:
        ok = False

    return ok


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"screenshots": [], "acceptance": {}}

    ok = assert_scope_unchanged()
    pipeline = emblem_pipeline_metrics()
    results["emblem_pipeline"] = pipeline
    ok = emblem_pipeline_assertions(pipeline) and ok

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Marka kontrol sayfası
        brand_page = browser.new_page(viewport={"width": 1100, "height": 800})
        brand_uri = BRAND_SHEET.resolve().as_uri()
        brand_page.goto(brand_uri, wait_until="networkidle")
        brand_page.screenshot(path=str(SHOT_DIR / "brand-contact-sheet.png"), full_page=True)
        results["screenshots"].append("docs/screenshots/brand-contact-sheet.png")
        brand_page.close()

        page = browser.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        ok = True
        ok = run_viewport(page, 1440, "desktop-1440", results) and ok
        ok = run_viewport(page, 390, "mobile-390", results) and ok
        ok = test_js_resilience(browser, results) and ok

        page.close()
        browser.close()

    results["acceptance"] = ACCEPTANCE
    results["all_passed"] = ok and all(v["passed"] for v in ACCEPTANCE.values())

    out = SHOT_DIR / "verify-report.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))

    if not results["all_passed"]:
        failed = [k for k, v in ACCEPTANCE.items() if not v["passed"]]
        print("FAILED ACCEPTANCE:", failed, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
