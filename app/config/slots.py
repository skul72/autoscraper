from __future__ import annotations

from app.config.settings import SLOT_DEFAULT
from app.storage.files import read_json, write_json_atomic
from app.storage.paths import ensure_slot_dir, remove_slot_dir, sanitizar_nome_slot, slots_meta_path

DEFAULT_SLOT_FALLBACK = SLOT_DEFAULT


def load_slots_meta() -> dict:
    meta = read_json(slots_meta_path(), {})
    if not isinstance(meta, dict):
        meta = {}
    slots = meta.get("slots", [])
    if not isinstance(slots, list):
        slots = []
    clean = sorted({sanitizar_nome_slot(s) for s in slots if sanitizar_nome_slot(s)})
    if DEFAULT_SLOT_FALLBACK not in clean:
        clean.insert(0, DEFAULT_SLOT_FALLBACK)
    default_slot = sanitizar_nome_slot(meta.get("default_slot", DEFAULT_SLOT_FALLBACK))
    if default_slot not in clean:
        clean.insert(0, default_slot)
    active_slot = sanitizar_nome_slot(meta.get("active_slot", default_slot))
    if active_slot not in clean:
        clean.insert(0, active_slot)
    result = {"slots": sorted(set(clean)), "default_slot": default_slot, "active_slot": active_slot}
    for s in result["slots"]:
        ensure_slot_dir(s)
    return result


def save_slots_meta(meta: dict) -> None:
    slots = meta.get("slots", []) if isinstance(meta.get("slots", []), list) else []
    slots = sorted({sanitizar_nome_slot(x) for x in slots if sanitizar_nome_slot(x)})
    if DEFAULT_SLOT_FALLBACK not in slots:
        slots.insert(0, DEFAULT_SLOT_FALLBACK)
    default_slot = sanitizar_nome_slot(meta.get("default_slot", DEFAULT_SLOT_FALLBACK))
    if default_slot not in slots:
        slots.insert(0, default_slot)
    active_slot = sanitizar_nome_slot(meta.get("active_slot", default_slot))
    if active_slot not in slots:
        slots.insert(0, active_slot)
    payload = {"slots": slots, "default_slot": default_slot, "active_slot": active_slot}
    write_json_atomic(slots_meta_path(), payload)
    for s in slots:
        ensure_slot_dir(s)


def list_slots() -> list[dict]:
    meta = load_slots_meta()
    return [
        {
            "name": s,
            "path": str(ensure_slot_dir(s)),
            "is_default": s == meta["default_slot"],
            "is_active": s == meta["active_slot"],
        }
        for s in meta["slots"]
    ]


def get_active_slot() -> str:
    meta = load_slots_meta()
    return sanitizar_nome_slot(meta.get("active_slot", meta.get("default_slot", DEFAULT_SLOT_FALLBACK)))


def set_active_slot(slot_name: str) -> str:
    meta = load_slots_meta()
    slot = sanitizar_nome_slot(slot_name)
    if slot not in meta["slots"]:
        meta["slots"].append(slot)
    meta["active_slot"] = slot
    save_slots_meta(meta)
    ensure_slot_dir(slot)
    return slot


def set_default_slot(slot_name: str) -> str:
    meta = load_slots_meta()
    slot = sanitizar_nome_slot(slot_name)
    if slot not in meta["slots"]:
        meta["slots"].append(slot)
    meta["default_slot"] = slot
    save_slots_meta(meta)
    ensure_slot_dir(slot)
    return slot


def create_slot(slot_name: str) -> str:
    return set_active_slot(slot_name)


def delete_slot(slot_name: str) -> tuple[bool, str]:
    meta = load_slots_meta()
    slot = sanitizar_nome_slot(slot_name)
    if slot == DEFAULT_SLOT_FALLBACK:
        return False, "O slot default não pode ser apagado."
    if slot == meta.get("default_slot"):
        return False, "Remova o slot como default antes de apagar."
    remove_slot_dir(slot)
    meta["slots"] = [s for s in meta["slots"] if s != slot]
    if not meta["slots"]:
        meta["slots"] = [DEFAULT_SLOT_FALLBACK]
    if meta.get("active_slot") == slot:
        meta["active_slot"] = meta.get("default_slot", DEFAULT_SLOT_FALLBACK)
    save_slots_meta(meta)
    return True, "Slot apagado."
