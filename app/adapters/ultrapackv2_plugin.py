from __future__ import annotations

import re

from app.core.utils import ensure_trailing_slash, normalizar_espacos, set_query_param

BASE_URL = "https://www.ultrapackv2.com"
GROUPED_CATEGORY_HINTS = {"https://www.ultrapackv2.com/plugins/codecanyon/"}


def is_grouped_category(url: str) -> bool:
    target = ensure_trailing_slash(url).lower()
    return any(ensure_trailing_slash(h).lower() == target for h in GROUPED_CATEGORY_HINTS)


def build_page_candidates(categoria_url: str, numero_pagina: int) -> list[str]:
    base = ensure_trailing_slash(categoria_url)
    if numero_pagina == 1:
        return [set_query_param(base, ppg=128)]
    return [
        set_query_param(f"{base}page/{numero_pagina}/", ppg=128),
        set_query_param(base, ppg=128, paged=numero_pagina),
        set_query_param(base, paged=numero_pagina, ppg=128),
    ]


def remover_count_do_nome(texto: str) -> str:
    return normalizar_espacos(re.sub(r"\s*\(\d+\)\s*$", "", texto or ""))
