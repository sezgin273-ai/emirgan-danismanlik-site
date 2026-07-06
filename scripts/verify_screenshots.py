"""Kabul kriterli site doğrulama ve ekran görüntüsü üretici."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# process_logo metrikleri
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_logo import (  # noqa: E402
    SRC,
    content_bbox_alpha,
    crop_emblem_deterministic,
    emblem_metrics,
    make_transparent,
    to_rgba_array,
)
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "docs" / "screenshots"
BRAND_SHEET = ROOT / "docs" / "brand" / "contact-sheet.html"
BASE = "http://localhost:8080"

ACCEPTANCE: dict[str, dict] = {}


def record(name: str, measured: float, limit: str, passed: bool) -> None:
    ACCEPTANCE[name] = {"measured": measured, "limit": limit, "passed": passed}


def assert_metric(name: str, measured: float, limit: str, passed: bool) -> None:
    record(name, measured, limit, passed)
    if not passed:
        print(f"FAIL {name}: measured={measured}, limit={limit}", file=sys.stderr)


def measure_hero_emblem(page) -> dict:
    page.locator("#hero").scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    return page.evaluate(
        """() => {
          const img = document.querySelector('.hero-emblem');
          const medallion = document.querySelector('.hero-medallion');
          const vp = { w: window.innerWidth, h: window.innerHeight };
          if (!img) return null;
          const r = img.getBoundingClientRect();
          const mr = medallion ? medallion.getBoundingClientRect() : r;
          const parentClip = r.left < mr.left - 1 || r.right > mr.right + 1
            || r.top < mr.top - 1 || r.bottom > mr.bottom + 1;
          const viewportClip = r.top < 0 || r.left < 0 || r.bottom > vp.h || r.right > vp.w;
          const rot = getComputedStyle(img).transform;
          const hasRotation = rot && rot !== 'none' && !/^matrix\\(1, 0, 0, 1/.test(rot);
          return {
            top: r.top, left: r.left, bottom: r.bottom, right: r.right,
            width: r.width, height: r.height,
            clipped: parentClip || viewportClip || r.width < 20 || r.height < 20,
            hasRotation,
            aspect: r.width / (r.height || 1)
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
          const formRow = document.querySelector('#contact-form .form-row');
          const card = document.querySelector('.address-card');
          if (!formRow || !card) return null;
          const fr = formRow.getBoundingClientRect();
          const cr = card.getBoundingClientRect();
          return { top_delta: Math.abs(fr.top - cr.top) };
        }"""
    )


def screenshot_section(page, selector: str, path: Path) -> None:
    loc = page.locator(selector)
    if loc.count():
        loc.screenshot(path=str(path))


def run_viewport(page, width: int, name: str, results: dict) -> bool:
    ok = True
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(BASE, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1200)

    hero = measure_hero_emblem(page)
    if not hero:
        ok = False
        assert_metric(f"hero_emblem_exists_{name}", 0, "present", False)
    else:
        clipped = hero["clipped"]
        assert_metric(
            f"hero_emblem_in_viewport_{name}",
            0 if clipped else 1,
            "not clipped",
            not clipped,
        )
        assert_metric(
            f"hero_no_rotation_{name}",
            1 if hero.get("hasRotation") else 0,
            "no rotation",
            not hero.get("hasRotation"),
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

    page.screenshot(path=str(SHOT_DIR / f"home-{name}.png"), full_page=True)
    results["screenshots"].append(f"docs/screenshots/home-{name}.png")

    for section_id, slug in [
        ("#hero", "hero"),
        ("#about", "about"),
        ("#services", "services"),
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


def emblem_source_metrics() -> dict:
    raw = to_rgba_array(Image.open(SRC))
    transparent = make_transparent(raw)
    x0, y0, x1, y1 = content_bbox_alpha(transparent)
    logo_full = transparent[y0:y1, x0:x1]
    emblem = crop_emblem_deterministic(logo_full)
    return emblem_metrics(emblem, logo_full.shape[0])


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"screenshots": [], "acceptance": {}}

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

        page.close()
        browser.close()

    results["acceptance"] = ACCEPTANCE
    results["emblem_source_metrics"] = emblem_source_metrics()
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
