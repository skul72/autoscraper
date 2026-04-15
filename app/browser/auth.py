from __future__ import annotations

import asyncio

from app.config.accounts import ACCOUNTS
from app.config.settings import ACCOUNT_DEFAULT
from app.scraper.flow_helpers import safe_goto


async def tentar_login(page, site_url: str, control, app) -> bool:
    conta = ACCOUNTS.get(ACCOUNT_DEFAULT, {})
    email = conta.get("email", "")
    senha = conta.get("password", "")
    if not email or not senha:
        app.log("⚠️ Credenciais não configuradas em AUTOSCRAPER_EMAIL/AUTOSCRAPER_PASSWORD.")
        return False
    login_urls = [f"{site_url}/login", f"{site_url}/minha-conta", f"{site_url}/my-account", f"{site_url}/wp-login.php", f"{site_url}/entrar", f"{site_url}/account"]
    for login_url in login_urls:
        try:
            await safe_goto(page, login_url, control, app, timeout=20000)
            email_sel = await page.query_selector("input[type='email'], input[name='email'], input[name='log'], input[name='username'], input[name='user_login'], #user_login, #email")
            if not email_sel:
                continue
            await email_sel.fill(email)
            senha_sel = await page.query_selector("input[type='password'], input[name='password'], input[name='pwd'], #user_pass, #password")
            if senha_sel:
                await senha_sel.fill(senha)
            btn = await page.query_selector("button[type='submit'], input[type='submit'], .login-button, .woocommerce-Button, button.button, input.button")
            if btn:
                await btn.click()
                await asyncio.sleep(3)
                return True
        except Exception as e:
            app.log(f"↳ Falhou em {login_url}: {str(e)[:80]}")
    return False
