from __future__ import annotations

import asyncio

from app.config.settings import DELAY, TIMEOUT
from app.core.exceptions import StopScraper


async def aguardar(segundos: float = DELAY):
    await asyncio.sleep(segundos)


async def checar_pause_stop(control, app):
    if control.should_stop():
        raise StopScraper()
    while control.is_paused():
        app.state.update(status="Pausado")
        await asyncio.sleep(0.4)
        if control.should_stop():
            raise StopScraper()
    if control.is_running():
        app.state.update(status="Rodando")


async def safe_goto(page, url: str, control, app, timeout: int = TIMEOUT):
    await checar_pause_stop(control, app)
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    await aguardar()
