"""Browser check of the target workflows (Playwright + Chromium). Start the app, then:

  uv run python tools/browser_workflows.py http://127.0.0.1:8000 /tmp/shots/

Writes screenshots to the second argument and prints ok / FAIL per workflow. It records a review in the database it
runs against: use a copy, never production.
"""

import asyncio
import os
import re
import sys

from playwright.async_api import async_playwright, expect

S = sys.argv[2] if len(sys.argv) > 2 else "./"
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
results = []


async def step(name, coro):
    try:
        await coro
        results.append((name, "ok", ""))
    except Exception as e:
        results.append((name, "FAIL", str(e)[:200]))


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        pg = await b.new_page(viewport={"width": 1300, "height": 950})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))

        # 1 competitor replacement
        async def w1():
            await pg.goto(B + "/")
            await pg.fill("#finder-search", "ISO7741DBQR")
            await pg.keyboard.press("Enter")
            await pg.wait_for_url(re.compile(r"/parts/\d+"))
            await expect(pg.locator(".ref-summary")).to_be_visible()
            boxes = pg.locator('input[name="pick"][type="checkbox"]')
            await boxes.nth(0).check()
            await boxes.nth(1).check()
            await expect(pg.locator("#compare-tray")).to_be_visible()
            await expect(pg.locator("[data-tray-count]")).to_have_text("2")
            await pg.screenshot(path=S + "wf1_part.png")
            await pg.locator("#compare-tray button[type=submit]").click()
            await pg.wait_for_url(re.compile(r"/compare"))
            await expect(pg.locator("table").first).to_be_visible()
            await pg.screenshot(path=S + "wf1_compare.png")
            r = await pg.request.get(B + "/parts/1198/replacements.xlsx")
            assert r.status == 200 and len(await r.body()) > 1000
            r = await pg.request.get(B + "/overlay/1198/" + "1199")
            assert r.status in (200, 404)

        await step("1 competitor replacement: search → reference → select → tray → compare → export", w1())

        # 2 system exploration
        async def w2():
            await pg.goto(B + "/blocks?market=Automotive")
            await pg.locator(".tpl-card").first.click()
            await pg.wait_for_url(re.compile(r"/blocks/new"))
            await pg.wait_for_timeout(1500)
            blk = pg.locator("[data-block]").first
            await blk.click()
            await pg.wait_for_timeout(1500)
            await expect(pg.locator("#bk-below")).to_be_visible()
            await pg.screenshot(path=S + "wf2_workspace.png")

        await step("2 system exploration: library (automotive) → architecture → block → candidates", w2())

        # 3 cross-sell
        async def w3():
            await pg.goto(B + "/business/attach?fn=digital_isolator")
            await expect(pg.locator("text=Modeled, not observed")).to_be_visible()
            await pg.goto(B + "/business/markets")
            await pg.locator("text=customers →").first.click()
            await pg.wait_for_url(re.compile(r"/business/customers\?.*fn="))
            await expect(pg.locator("h2").first).to_be_visible()

        await step("3 cross-sell: product → co-occurring functions → markets → system designers", w3())

        # 4 product opportunity
        async def w4():
            await pg.goto(B + "/business/explorer?view=feasibility")
            await pg.screenshot(path=S + "wf4_explorer.png")
            await pg.locator("table.explorer tbody a").first.click()
            await pg.wait_for_url(re.compile(r"/business/evidence/"))
            await expect(pg.get_by_role("heading", name="How it is scored")).to_be_visible()
            fn = pg.url.split("/business/evidence/")[1].split("?")[0]
            await pg.goto(B + f"/business/data?focus=asp:{fn}")
            await expect(pg.locator(".ci-focus")).to_have_count(1)
            await pg.goto(B + f"/business/cases/new?fn={fn}")
            await expect(pg.locator("text=What Cross List knows")).to_be_visible()

        await step("4 product opportunity: explorer → evidence → commercial input in context → business case", w4())

        # 5 data correction
        async def w5():
            pg.once("dialog", lambda d: asyncio.ensure_future(d.accept("Value looks wrong, see datasheet")))
            await pg.goto(B + "/business/evidence/pol_ldo")
            await pg.evaluate("localStorage.setItem('bo-reviewer', 'workflow test')")
            await pg.locator(".rv-b[data-v=wrong]").first.click()
            await pg.wait_for_timeout(800)
            await expect(pg.locator(".rv-st.rv-disputed").first).to_be_visible()
            await pg.goto(B + "/manage/reviews?type=mapping")
            await expect(pg.locator("text=the vote changes no result").first).to_be_visible()
            t = await (await pg.request.get(B + "/business/quality/todo.txt")).text()
            assert "Value looks wrong" in t

        await step("5 data correction: flag in context → queue → to-do, with resolution path", w5())
        # keyboard + mobile
        m = await b.new_page(viewport={"width": 390, "height": 844})

        async def w6():
            await m.goto(B + "/business")
            # navigation is two rows at the top that wrap on a phone: no drawer, no separate scrolling menu
            await expect(m.locator("nav.main-nav")).to_be_in_viewport()
            await expect(m.locator("nav.sub-nav a.on")).to_be_in_viewport()
            await m.screenshot(path=S + "wf6_nav.png")
            w = await m.evaluate("document.documentElement.scrollWidth")
            assert w <= 400, w
            await m.goto(B + "/parts?cat=isolation")
            await m.screenshot(path=S + "wf6_parts.png")

        await step("6 phone: navigation rows at the top, no horizontal page scroll", w6())

        async def w7():
            await pg.goto(B + "/business")
            await pg.keyboard.press("Tab")
            await expect(pg.locator(".skip-link")).to_be_focused()
            await pg.keyboard.press("Enter")
            assert await pg.evaluate("document.activeElement.id") in ("main", "finder-search")
            await pg.goto(B + "/business")
            await pg.locator(".bo-about summary").focus()
            await pg.keyboard.press("Enter")
            assert await pg.evaluate("document.querySelector('.bo-about').open")

        await step("7 keyboard: skip link, disclosure controls", w7())
        print("page errors:", errs)
        await b.close()
    for r in results:
        print(*r, sep=" | ")


asyncio.run(main())
