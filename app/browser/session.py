from __future__ import annotations

from app.config.settings import HEADLESS, USER_AGENT


async def open_browser_session():
    from playwright.async_api import async_playwright

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=HEADLESS, args=["--disable-blink-features=AutomationControlled"])
    context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1440, "height": 900})
    page = await context.new_page()
    detail_page = await context.new_page()
    return p, browser, context, page, detail_page


async def close_browser_session(p=None, browser=None, page=None, detail_page=None):
    for obj in [detail_page, page, browser]:
        try:
            if obj is not None:
                await obj.close()
        except Exception:
            pass
    try:
        if p is not None:
            await p.stop()
    except Exception:
        pass
