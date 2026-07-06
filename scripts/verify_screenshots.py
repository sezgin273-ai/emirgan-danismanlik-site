"""Headless tarayıcı ile site doğrulama ve ekran görüntüsü."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOT_DIR = ROOT / "docs" / "screenshots"
BASE = "http://localhost:8080"

CHECKS = [
    "Güvenilir",
    "Kim Can",
    "Stratejik Yönetim",
    "Hakkımızda",
    "Bize Ulaşın",
    "logo-full.png",
    "emblem.png",
    "service-card",
    'id="contact-form"',
]


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    results: dict = {"console_errors": [], "checks": {}, "screenshots": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for width, name in [(1440, "desktop-1440"), (390, "mobile-390")]:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            page.goto(BASE, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1200)

            html = page.content()
            for check in CHECKS:
                key = f"{name}:{check}"
                results["checks"][key] = check in html

            # Görünürlük: .reveal öğelerinin opacity kontrolü
            visible_count = page.evaluate(
                """() => {
                  const els = document.querySelectorAll('.reveal');
                  let visible = 0;
                  els.forEach(el => {
                    const s = getComputedStyle(el);
                    if (parseFloat(s.opacity) > 0.5) visible++;
                  });
                  return { total: els.length, visible };
                }"""
            )
            results[f"reveal_{name}"] = visible_count

            # Tam sayfa ekran görüntüsü
            path = SHOT_DIR / f"home-{name}.png"
            page.screenshot(path=str(path), full_page=True)
            results["screenshots"].append(str(path.relative_to(ROOT)))

            # JS asset 404 kontrolü
            js_status = page.evaluate(
                """async () => {
                  const r = await fetch('/assets/js/main.js');
                  return r.status;
                }"""
            )
            results[f"main_js_status_{name}"] = js_status

            page.close()

        browser.close()

    results["console_errors"] = list(dict.fromkeys(errors))
    out = ROOT / "docs" / "screenshots" / "verify-report.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(results, indent=2, ensure_ascii=False))

    failed = [k for k, v in results["checks"].items() if not v]
    if failed:
        print("FAILED CHECKS:", failed, file=sys.stderr)
        return 1
    if results["console_errors"]:
        print("CONSOLE ERRORS:", results["console_errors"], file=sys.stderr)
        return 1
    for key, val in results.items():
        if key.startswith("reveal_") and val["visible"] < val["total"] * 0.8:
            print(f"LOW VISIBILITY {key}: {val}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
