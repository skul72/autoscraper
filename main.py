#!/usr/bin/env python3
from app.config.settings import ensure_base_dirs
from app.config.slots import get_active_slot, load_slots_meta
from app.storage.paths import ensure_slot_dir
from app.core.app import ScraperApp
from app.web.server import start_server


def main():
    ensure_base_dirs()
    load_slots_meta()
    ensure_slot_dir(get_active_slot())
    app = ScraperApp()
    app.refresh_slots_state()
    app.load_initial_summary()
    start_server(app)


if __name__ == "__main__":
    main()
