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
]


def run_form_tests(page, name: str, results: dict) -> None:
    form = page.locator("#contact-form")
    feedback = page.locator("#form-feedback")

    results[f"form_exists_{name}"] = form.count() > 0

    # Boş gönderim
    form.evaluate("el => el.reset()")
    feedback.evaluate("el => { el.hidden = true; el.textContent = ''; }")
    form.locator('button[type="submit"]').click()
    page.wait_for_timeout(200)
    results[f"form_empty_error_{name}"] = page.evaluate(
        """() => {
          const fb = document.getElementById('form-feedback');
          return fb && !fb.hidden && fb.classList.contains('is-error') && fb.textContent.trim().length > 0;
        }"""
    )

    # Geçersiz e-posta
    form.evaluate("el => el.reset()")
    feedback.evaluate("el => { el.hidden = true; el.textContent = ''; }")
    page.fill("#contact-name", "Test Kullanıcı")
    page.fill("#contact-email", "gecersiz-eposta")
    page.fill("#contact-subject", "Test")
    page.fill("#contact-message", "Test mesajı")
    form.locator('button[type="submit"]').click()
    page.wait_for_timeout(200)
    results[f"form_invalid_email_{name}"] = page.evaluate(
        """() => {
          const fb = document.getElementById('form-feedback');
          const email = document.getElementById('contact-email');
          return fb && !fb.hidden && fb.classList.contains('is-error')
            && email && email.classList.contains('is-invalid');
        }"""
    )


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    results: dict = {"console_errors": [], "checks": {}, "screenshots": [], "form_tests": {}}

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

            # Form id — DOM üzerinden doğrula (HTML string tırnak farklarından etkilenmez)
            form_id_ok = page.evaluate("() => document.getElementById('contact-form') !== null")
            results["checks"][f"{name}:contact-form-id"] = form_id_ok

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

            js_class = page.evaluate("() => document.documentElement.classList.contains('js')")
            results[f"js_class_{name}"] = js_class

            # Form doğrulama testleri (yalnızca masaüstü — mobilde de çalıştır)
            page.locator("#contact").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            run_form_tests(page, name, results["form_tests"])

            path = SHOT_DIR / f"home-{name}.png"
            page.screenshot(path=str(path), full_page=True)
            results["screenshots"].append(str(path.relative_to(ROOT)))

            # Footer logo halo kontrolü ekran görüntüsü
            footer_path = SHOT_DIR / f"footer-logo-{name}.png"
            footer = page.locator(".footer-brand")
            if footer.count():
                footer.screenshot(path=str(footer_path))
                results["screenshots"].append(str(footer_path.relative_to(ROOT)))

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
    for key, val in results.get("form_tests", {}).items():
        if not val:
            print(f"FAILED FORM TEST: {key}", file=sys.stderr)
            return 1
    for key, val in results.items():
        if key.startswith("js_class_") and not val:
            print(f"JS CLASS MISSING: {key}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
