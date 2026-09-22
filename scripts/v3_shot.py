"""Screenshot helper: scroll to trigger reveals, then full-page desktop + mobile."""
import sys
from playwright.sync_api import sync_playwright

def shoot(pg, path):
    pg.evaluate("""async () => {
        const h = document.body.scrollHeight;
        for (let y = 0; y <= h; y += 500) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 90)); }
        window.scrollTo(0, 0);
        await new Promise(r => setTimeout(r, 500));
    }""")
    pg.wait_for_timeout(600)
    pg.screenshot(path=path, full_page=True)

def main():
    url, tag = sys.argv[1], sys.argv[2]
    console_msgs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("console", lambda m: console_msgs.append(f"{m.type}: {m.text}"))
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(1200)
        shoot(pg, f"/tmp/v3_shots/{tag}-desktop.png")
        pg2 = b.new_page(viewport={"width": 390, "height": 844})
        pg2.on("console", lambda m: console_msgs.append(f"m-{m.type}: {m.text}"))
        pg2.goto(url, wait_until="networkidle")
        pg2.wait_for_timeout(1200)
        shoot(pg2, f"/tmp/v3_shots/{tag}-mobile.png")
        b.close()
    errs = [m for m in console_msgs if m.startswith(("error", "m-error"))]
    print("console errors:", len(errs))
    for e in errs[:10]:
        print(" ", e)

if __name__ == "__main__":
    main()
