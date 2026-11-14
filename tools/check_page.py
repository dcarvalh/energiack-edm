"""Headless check of the prototype: every view, FR and EN, desktop and phone.

Reports JS errors, FR/EN dictionary mismatches, horizontal overflow, and saves screenshots.
Usage: .venv/bin/python tools/check_page.py [URL] [OUTDIR]
On the server stack (compose.yaml with DEMO_LOGIN=1), CHECK_ROLE=technique (or admin) logs in first, since Manage
and Data quality need a role; tools/check_roles.py checks what each role sees.
"""
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://dcarvalh.github.io/energiack-edm/"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "shots")
OUT.mkdir(parents=True, exist_ok=True)
problems = []
ROLE = os.environ.get("CHECK_ROLE")

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for dev, vp in (("desk", {"width": 1366, "height": 900}), ("phone", {"width": 390, "height": 844})):
        for scheme in ("light", "dark"):
            ctx = b.new_context(viewport=vp, color_scheme=scheme)
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("console", lambda m: m.type == "error" and errs.append(m.text))
            if ROLE:                                  # server stack with DEMO_LOGIN=1: run the whole check as this role
                r = page.request.post(URL.rstrip("/") + "/api/demo-login", data={"role": ROLE})
                assert r.ok, f"demo login as {ROLE} failed: {r.status}"
            for lang in ("fr", "en"):
                for view in ("accueil", "gestion", "qualite", "citoyens", "carte", "apropos", "site/S01"):
                    if scheme == "dark" and (dev == "phone" or view not in ("gestion", "accueil", "qualite")):
                        continue
                    page.goto(f"{URL}?lang={lang}#{view}")
                    page.wait_for_timeout(700)
                    if view == "carte":
                        page.wait_for_selector("#m3 canvas", timeout=60000); page.wait_for_timeout(2000)
                    if view == "site/S01":
                        page.wait_for_selector("#drawer.open")
                    ow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                    if ow > 1:
                        problems.append(f"{dev} {lang} {view}: horizontal overflow {ow}px")
                    if page.evaluate("document.documentElement.lang") != lang:
                        problems.append(f"{lang} {view}: <html lang> wrong")
                    name = f"{dev}-{scheme}-{lang}-{view.replace('/', '_')}.png"
                    page.screenshot(path=str(OUT / name), full_page=(view not in ("site/S01", "carte")))
            if dev == "desk" and scheme == "light":
                miss = page.evaluate("""() => { const a = Object.keys(T.fr), b = Object.keys(T.en);
                    return [a.filter(k => !b.includes(k)), b.filter(k => !a.includes(k))]; }""")
                if miss[0] or miss[1]:
                    problems.append(f"i18n keys only in fr: {miss[0]}, only in en: {miss[1]}")
                # Interactions: year switch, filter, sort, search, language toggle
                page.goto(URL + "?lang=fr#gestion"); page.wait_for_timeout(500)
                page.click("[data-y='2023']"); page.click("[data-f='fossil']"); page.click("th[data-k='int']")
                page.fill("#q", "école"); page.wait_for_timeout(200)
                n = page.locator("#sites tbody tr").count()
                print("fossil schools 2023 rows:", n)
                page.click("[data-y='2021']"); page.wait_for_timeout(200)
                page.click("nav a[data-view='citoyens']"); page.wait_for_timeout(500)
                if "2025" not in page.inner_text("#c-hero"):
                    problems.append("citizen hero is not on the latest year")
                page.goto(URL + "?lang=fr#gestion"); page.wait_for_timeout(500)
                page.click("[data-lang='en']"); page.wait_for_timeout(300)
                if "Manage" not in page.inner_text("nav"):
                    problems.append("language toggle did not switch nav to EN")
                # 3D map: Rive-Claire by default, switch to Geneva and back (one WebGL canvas at a time)
                page.goto(URL + "?lang=en#carte"); page.wait_for_selector("#m3 canvas", timeout=60000)
                page.wait_for_function("window.__m3 && window.__m3.n < 100", timeout=60000)
                page.click("[data-map='ge']"); page.wait_for_function("window.__m3 && window.__m3.n > 1000", timeout=90000)
                page.wait_for_timeout(1500); page.screenshot(path=str(OUT / "desk-light-en-carte-geneva.png"))
                page.click("[data-map='rc']"); page.wait_for_function("window.__m3 && window.__m3.n < 100", timeout=60000)
                if page.locator("canvas").count() != 1:
                    problems.append(f"map switch left {page.locator('canvas').count()} canvases")
                page.evaluate("localStorage.removeItem('energiack-map')")
            if errs:
                problems.append(f"{dev} {scheme} JS errors: {errs[:5]}")
            ctx.close()
    b.close()

print("\n".join(problems) if problems else "OK: no problems found")
print("screenshots in", OUT.resolve())
