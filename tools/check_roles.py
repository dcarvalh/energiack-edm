"""Headless check of logins and roles (issue #15) on the server stack (compose.yaml with DEMO_LOGIN=1).

For a visitor and each demo role: which menu items show, which pages open, whether the site page shows raw readings,
the Users page (admin), logout; the login dialog in FR and EN at desktop and phone width. Screenshots in OUTDIR.
Usage: .venv/bin/python tools/check_roles.py http://127.0.0.1:18088/ [OUTDIR]
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/") + "/"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "shots")
OUT.mkdir(parents=True, exist_ok=True)
SEES = {  # role -> menu items that must show (others must not)
    None: {"accueil", "carte", "citoyens", "apropos"},
    "public": {"accueil", "carte", "citoyens", "apropos"},
    "elu": {"accueil", "gestion", "carte", "citoyens", "apropos"},
    "technique": {"accueil", "gestion", "donnees", "qualite", "carte", "citoyens", "apropos"},
    "admin": {"accueil", "gestion", "donnees", "qualite", "carte", "localites", "utilisateurs", "citoyens", "apropos"},
}
problems = []

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for dev, vp in (("desk", {"width": 1366, "height": 900}), ("phone", {"width": 390, "height": 844})):
        for lang in ("fr", "en"):
            ctx = b.new_context(viewport=vp)
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("console", lambda m: m.type == "error" and errs.append(m.text))
            for role in SEES:
                tag = f"{dev} {lang} {role or 'visitor'}"
                page.goto(f"{URL}?lang={lang}#accueil"); page.wait_for_timeout(600)
                if role:                                       # log in through the dialog, as a person would
                    page.click("#login-btn"); page.click(f"[data-demo='{role}']"); page.wait_for_timeout(800)
                    if page.locator("#login.open").count():
                        problems.append(f"{tag}: login dialog still open"); continue
                shown = set(page.eval_on_selector_all("nav a:not(.hide)", "els => els.map(e => e.dataset.view)"))
                if shown != SEES[role]:
                    problems.append(f"{tag}: menu {sorted(shown)} expected {sorted(SEES[role])}")
                page.goto(f"{URL}?lang={lang}#qualite"); page.wait_for_timeout(600)
                gated = "qualite" not in SEES[role]
                if gated != bool(page.locator("#login.open").count()):
                    problems.append(f"{tag}: #qualite gate wrong")
                if gated and dev == "phone" and role is None:
                    page.screenshot(path=str(OUT / f"roles-{dev}-{lang}-login.png"))
                if gated:
                    page.keyboard.press("Escape")
                page.goto(f"{URL}?lang={lang}#site/S01"); page.wait_for_selector("#drawer.open")
                raw = page.locator("#dcsv").count() == 1
                if raw != (role in ("technique", "admin")):
                    problems.append(f"{tag}: raw readings shown={raw}")
                if role == "admin":
                    page.goto(f"{URL}?lang={lang}#utilisateurs"); page.wait_for_selector("#u-table select")
                    page.screenshot(path=str(OUT / f"roles-{dev}-{lang}-users.png"), full_page=True)
                    page.select_option("select[data-u='l.favre']", "elu"); page.wait_for_timeout(500)
                    if not page.inner_text("#u-msg").strip() or page.locator("select[data-u='demo-elu']").count():
                        problems.append(f"{tag}: users page role change")
                    page.select_option("select[data-u='l.favre']", "public"); page.wait_for_timeout(300)
                ow = page.evaluate("document.documentElement.scrollWidth - innerWidth")
                if ow > 1:
                    problems.append(f"{tag}: horizontal overflow {ow}px")
                if role:
                    page.goto(f"{URL}?lang={lang}#accueil"); page.wait_for_timeout(500)
                    if dev == "phone" and role == "elu":
                        page.screenshot(path=str(OUT / f"roles-{dev}-{lang}-elu.png"))
                    page.click("#logout-btn"); page.wait_for_timeout(600)
                    if not page.locator("#login-btn").count():
                        problems.append(f"{tag}: logout did not return to visitor")
            if errs:
                problems.append(f"{dev} {lang} JS errors: {errs[:5]}")
            ctx.close()
    b.close()

print("\n".join(problems) if problems else "OK: roles check passed")
print("screenshots in", OUT.resolve())
