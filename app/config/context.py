from __future__ import annotations

from dataclasses import dataclass

from app.config.accounts import ACCOUNTS
from app.config.item_types import ITEM_TYPES
from app.config.settings import ACCOUNT_DEFAULT, ITEM_TYPE_DEFAULT, SITE_DEFAULT, SLOT_DEFAULT
from app.config.sites import SITES


@dataclass(frozen=True)
class RuntimeContext:
    site: str = SITE_DEFAULT
    item_type: str = ITEM_TYPE_DEFAULT
    account: str = ACCOUNT_DEFAULT
    slot: str = SLOT_DEFAULT

    @property
    def site_cfg(self) -> dict:
        return SITES[self.site]

    @property
    def item_type_cfg(self) -> dict:
        return ITEM_TYPES[self.item_type]

    @property
    def account_cfg(self) -> dict:
        return ACCOUNTS[self.account]
