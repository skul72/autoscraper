import os

ACCOUNTS = {
    "coproducaolancamentos": {
        "email": os.getenv("AUTOSCRAPER_EMAIL", ""),
        "password": os.getenv("AUTOSCRAPER_PASSWORD", ""),
    }
}
