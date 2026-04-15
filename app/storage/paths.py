from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.config.settings import SLOTS_META_JSON, SLOTS_ROOT_DIR
from app.config.settings import SLOT_DEFAULT

DEFAULT_SLOT_FALLBACK = SLOT_DEFAULT

OUTPUT_CSV_NAME = "ultrapack_plugins.csv"
OUTPUT_JSON_NAME = "ultrapack_plugins.json"
PROGRESS_JSON_NAME = "ultrapack_plugins_progress.json"
CATEGORIES_CACHE_JSON_NAME = "ultrapack_plugins_categories.json"
QUEUE_CACHE_JSON_NAME = "ultrapack_plugins_queue.json"
CONFIG_JSON_NAME = "ultrapack_plugins_config.json"
LAST_LOGS_TXT_NAME = "last_logs.txt"
STATUS_TXT_NAME = "status.txt"


def sanitizar_nome_slot(nome: str) -> str:
    nome = re.sub(r"\s+", " ", str(nome or "")).strip().lower()
    nome = nome.replace("\\", " ").replace("/", " ").replace(":", " ")
    nome = re.sub(r"[^a-z0-9._ -]+", "", nome)
    nome = re.sub(r"\s+", "-", nome)
    nome = re.sub(r"-{2,}", "-", nome).strip("-._ ")
    return nome or DEFAULT_SLOT_FALLBACK


def slot_dir(slot_name: str) -> Path:
    return SLOTS_ROOT_DIR / sanitizar_nome_slot(slot_name)


def ensure_slot_dir(slot_name: str) -> Path:
    p = slot_dir(slot_name)
    p.mkdir(parents=True, exist_ok=True)
    return p


def slot_file(slot_name: str, filename: str) -> Path:
    return ensure_slot_dir(slot_name) / filename


def slots_meta_path() -> Path:
    return SLOTS_META_JSON


def remove_slot_dir(slot_name: str) -> None:
    p = slot_dir(slot_name)
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)


def output_csv_path(slot_name: str) -> Path:
    return slot_file(slot_name, OUTPUT_CSV_NAME)


def output_json_path(slot_name: str) -> Path:
    return slot_file(slot_name, OUTPUT_JSON_NAME)


def progress_json_path(slot_name: str) -> Path:
    return slot_file(slot_name, PROGRESS_JSON_NAME)


def categories_cache_path(slot_name: str) -> Path:
    return slot_file(slot_name, CATEGORIES_CACHE_JSON_NAME)


def queue_cache_path(slot_name: str) -> Path:
    return slot_file(slot_name, QUEUE_CACHE_JSON_NAME)


def config_json_path(slot_name: str) -> Path:
    return slot_file(slot_name, CONFIG_JSON_NAME)


def status_txt_path(slot_name: str) -> Path:
    return slot_file(slot_name, STATUS_TXT_NAME)


def logs_txt_path(slot_name: str) -> Path:
    return slot_file(slot_name, LAST_LOGS_TXT_NAME)
