from __future__ import annotations

import os
from pathlib import Path

SITE_DEFAULT = "ultrapackv2"
ITEM_TYPE_DEFAULT = "plugin"
ACCOUNT_DEFAULT = "coproducaolancamentos"
SLOT_DEFAULT = "default"

HEADLESS = False
DELAY = 1.4
TIMEOUT = 30000
MAX_PAGINAS_FALLBACK = 200
RETOMAR_DE_ONDE_PAROU = True
DEFAULT_SAVE_EVERY_ITEMS = 5
DEFAULT_SAVE_EVERY_MINUTES = 1

PANEL_HOST = "127.0.0.1"
PANEL_PORT = 8765

TEST_MODE = False
TESTE_MAX_CATEGORIAS = 2
TESTE_MAX_ITENS_POR_CATEGORIA = 15

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
SLOTS_ROOT_DIR = DATA_DIR / "slots"
LOGS_DIR = BASE_DIR / "logs"
SLOTS_META_JSON = DATA_DIR / "slots_meta.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def ensure_base_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SLOTS_ROOT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
