"""OPTIONAL real-browser check (needs:  pip install playwright && playwright install chromium).
Run from the project folder:  python tests/browser_check.py
It starts the app on port 5066 with a temporary database, drives the UI like a user and saves screenshots to ./screenshots.
Note: Leaflet/Chart.js load from CDNs, so with no internet the map shows its list view and the chart shows its table.
"""
import os, subprocess, sys, tempfile, time, re
from playwright.sync_api import sync_playwright
tmp = tempfile.mkdtemp()
SHOTS = os.path.join(os.getcwd(), "screenshots"); os.makedirs(SHOTS, exist_ok=True)
env = dict(os.environ, PORT="5066", DATABASE_PATH=f"{tmp}/b.db", ADMIN_PASSWORD="browser-test-pw-1", SECRET_KEY="x"*40)
srv = subprocess.Popen([sys.executable, "app.py"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(3)
B = "http://localhost:5066"
errors, results = [], []
def ok(name, cond): results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)
try:
  with sync_playwright() as p:
    br = p.chromium.launch()
    for label, vp in (("desktop", {"width":1280,"height":900}), ("mobile", {"width":375,"height":780})):
        ctx = br.new_context(viewport=vp); pg = ctx.new_page()
        pg.on("pageerror", lambda e, l=label: errors.append(f"[{l}] pageerror: {e}"))
        pg.on("console", lambda m, l=label: errors.append(f"[{l}] console.{m.type}: {m.text}") if m.type=="error" and "ERR_" not in m.text and "Failed to load resource" not in m.text else None)
        for path in ("/", "/dashboard", "/map", "/report", "/assistant", "/resources", "/about", "/admin/login"):
            pg.goto(B+path, wait_until="domcontentloaded"); pg.wait_for_timeout(700)
            over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            ok(f"{label} {path} no horizontal overflow (over={over})", over <= 1)
            if path in ("/", "/dashboard", "/map", "/assistant") : pg.screenshot(path=f"{SHOTS}/{label}{path.replace('/','_') or '_home'}.png", full_page=(path!="/map"))
        if label == "mobile":
            pg.goto(B+"/"); pg.click(".nav-toggle"); ok("mobile menu opens", pg.is_visible("#site-nav a[href='/map']"))
        if label == "desktop":
            # chat via UI
            pg.goto(B+"/assistant"); pg.click("#suggestions .chip >> nth=0"); pg.wait_for_selector(".msg.bot .tag", timeout=5000)
            txt = pg.inner_text("#chat-log"); ok("chat shows DEMO ANSWER label", "DEMO ANSWER" in txt and "torch" in txt.lower())
            pg.fill("#chat-input", "I am trapped"); pg.click("#chat-send"); pg.wait_for_selector(".msg.urgent", timeout=5000); ok("urgent notice shown", "112" in pg.inner_text(".msg.urgent"))
            # report via UI, with client-side validation first
            pg.goto(B+"/report"); pg.once("dialog", lambda d: d.accept()); pg.click("#report-form button[type=submit]")
            ok("client-side validation blocks empty form", pg.url.endswith("/report"))
            pg.fill("[name=title]", "Browser test blocked road"); pg.select_option("[name=category]", "Road blockage"); pg.select_option("[name=severity]", "Moderate")
            pg.fill("textarea[name=description]", "A fallen branch blocks the lane near the market."); pg.fill("[name=location_name]", "Market Road")
            pg.fill("[name=latitude]", "13.06"); pg.fill("[name=longitude]", "80.25"); pg.fill("[name=reporter_contact]", "browser-private@example.com")
            pg.click("#report-form button[type=submit]"); pg.wait_for_url("**/confirmation")
            body = pg.inner_text("body"); m = re.search(r"RQ-\d{8}-[0-9A-F]{6}", body); ok("confirmation page with incident ID", m)
            pg.screenshot(path=f"{SHOTS}/desktop_confirm.png")
            pg.goto(B+"/report"); pg.fill("[name=incident_id]", m.group(0)); pg.click("text=Find report"); ok("lookup finds report", m.group(0) in pg.inner_text("body"))
            pg.goto(B+"/report"); pg.fill("[name=incident_id]", "RQ-20200101-FFFFFF"); pg.click("text=Find report"); ok("lookup unknown ID shows error", "No report found" in pg.inner_text("body"))
            # dashboard & map list
            pg.goto(B+"/dashboard"); ok("dashboard shows new report", "Browser test blocked road" in pg.inner_text("body"))
            pg.wait_for_function("document.querySelector('#weather').innerText.includes('unavailable') || document.querySelector('#weather').innerText.includes('Source')", timeout=15000)
            ok("weather panel shows labelled unavailable state (no network here)", "unavailable" in pg.inner_text("#weather").lower())
            ok("category table fallback visible", pg.is_visible("#cat-table"))
            pg.goto(B+"/map"); pg.wait_for_timeout(1500)
            ok("map list populated without Leaflet CDN", pg.locator("#map-list li").count() >= 5)
            ok("no-coordinate note shown", "no valid coordinates" in pg.inner_text("#no-coords-note"))
            pg.select_option("#f-category", "Flooding"); pg.wait_for_timeout(800); n = pg.locator("#map-list li").count(); ok(f"map filter works (n={n})", 0 < n < 5)
            # admin
            pg.goto(B+"/admin/login"); pg.fill("[name=username]", "admin"); pg.fill("[name=password]", "nope"); pg.click("button[type=submit]"); ok("bad admin login shows error", "Incorrect" in pg.inner_text("body"))
            pg.fill("[name=username]", "admin"); pg.fill("[name=password]", "browser-test-pw-1"); pg.click("button[type=submit]"); pg.wait_for_url("**/admin")
            pg.click("text=Browser test blocked road"); ok("admin sees private contact", "browser-private@example.com" in pg.inner_text("body"))
            pg.select_option("select[name=status]", "Verified"); pg.click("text=Save status"); ok("status saved", "Status updated to Verified" in pg.inner_text("body"))
            pg.screenshot(path=f"{SHOTS}/desktop_admin.png", full_page=True)
            pg.once("dialog", lambda d: d.accept()); pg.click("text=Delete report"); pg.wait_for_url("**/admin"); ok("delete with confirm works", "Report deleted" in pg.inner_text("body"))
            pg.click("text=Sign out"); ok("sign out works", "signed out" in pg.inner_text("body"))
        ctx.close()
    br.close()
finally:
    srv.terminate()
print("\nJS/console errors:", errors or "none")
print(f"{sum(1 for _,c in results if c)}/{len(results)} browser checks passed")
