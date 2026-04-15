from __future__ import annotations

import re

from app.adapters.ultrapackv2_plugin import BASE_URL, is_grouped_category, remover_count_do_nome
from app.core.utils import ensure_trailing_slash, normalizar_espacos
from app.scraper.flow_helpers import safe_goto


async def extrair_dev_links_da_pagina(page):
    categorias = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a.dev-link')).map(a => ({ texto: (a.innerText || a.textContent || '').trim(), href: a.href || '' }))
        """
    )
    resultado = []
    vistos = set()
    for cat in categorias:
        href = normalizar_espacos(cat.get("href", ""))
        texto = normalizar_espacos(cat.get("texto", ""))
        if not href or href in vistos or "/plugins/" not in href or "/item/" in href:
            continue
        m = re.search(r"\((\d+)\)\s*$", texto)
        total = int(m.group(1)) if m else 0
        resultado.append({"categoria_nome": remover_count_do_nome(texto), "categoria_url": ensure_trailing_slash(href), "total_esperado": total, "tipo": "plugin"})
        vistos.add(href)
    return resultado


async def coletar_categorias_plugins(page, control, app):
    url = f"{BASE_URL}/plugins/"
    app.log(f"📚 Abrindo catálogo de plugins: {url}")
    await safe_goto(page, url, control, app)
    await page.wait_for_selector("a.dev-link", timeout=20000)
    categorias_raiz = await extrair_dev_links_da_pagina(page)
    finais, vistos = [], set()
    for categoria in categorias_raiz:
        cat_url = ensure_trailing_slash(categoria["categoria_url"])
        if is_grouped_category(cat_url):
            try:
                await safe_goto(page, cat_url, control, app)
                subcategorias = await extrair_dev_links_da_pagina(page)
                validas = [s for s in subcategorias if ensure_trailing_slash(s["categoria_url"]) != cat_url and "/plugins/" in s["categoria_url"] and "/item/" not in s["categoria_url"]]
                if validas:
                    for sub in validas:
                        sub_url = ensure_trailing_slash(sub["categoria_url"])
                        if sub_url not in vistos:
                            vistos.add(sub_url)
                            finais.append(sub)
                    continue
            except Exception as e:
                app.log(f"   ↳ erro ao expandir {categoria['categoria_nome']}: {str(e)[:80]}")
        if cat_url not in vistos:
            vistos.add(cat_url)
            finais.append(categoria)
    return finais
