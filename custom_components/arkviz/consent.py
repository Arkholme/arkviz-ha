"""Who has agreed to what, and the random IDs that go with it. Nothing here touches Home Assistant or the network, so the rules can be tested alone."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

# Raise this when what a setting covers changes, along with CONSENT_TEXT_VERSION in src/telemetry/telemetry.ts. Settings
# answered under an older text go off, and admins are asked again.
CONSENT_TEXT_VERSION = 1

ERRORS = "errors"
USAGE = "usage"
SETTINGS = (ERRORS, USAGE)


def _new_id() -> str:
    return uuid4().hex


class Consent:
    """The home's two settings, each account's opt-outs, and the IDs they allow. `data` is what's saved."""

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        new_id: Callable[[], str] = _new_id,
        text_version: int = CONSENT_TEXT_VERSION,
    ) -> None:
        self.data: dict[str, Any] = data or {"settings": {}, "home_ids": {}, "accounts": {}, "snapshot_day": None}
        self._new_id = new_id
        self.text_version = text_version
        for setting in SETTINGS:
            record = self.data["settings"].get(setting)
            if record and record["on"] and record["text_version"] != text_version:
                record["on"] = False
                self._forget_ids(setting)

    def is_on(self, setting: str) -> bool:
        record = self.data["settings"].get(setting)
        return bool(record and record["on"] and record["text_version"] == self.text_version)

    def answered(self, setting: str) -> bool:
        record = self.data["settings"].get(setting)
        return bool(record and record["text_version"] == self.text_version)

    def needs_answer(self, available: dict[str, bool]) -> bool:
        """Whether an admin has a question to answer. A setting this build can't send has none."""
        return any(available.get(setting) and not self.answered(setting) for setting in SETTINGS)

    def record(self, setting: str) -> dict[str, Any] | None:
        return self.data["settings"].get(setting)

    def set_home(self, setting: str, on: bool, by: str, at: str) -> None:
        """An admin's answer. Off forgets the setting's IDs, so on again starts with new ones."""
        was_on = self.is_on(setting)
        self.data["settings"][setting] = {"on": on, "by": by, "at": at, "text_version": self.text_version}
        if not on:
            self._forget_ids(setting)
        elif not was_on:
            self.data["home_ids"][setting] = self._new_id()

    def _forget_ids(self, setting: str) -> None:
        self.data["home_ids"].pop(setting, None)
        if setting == USAGE:
            self.data["snapshot_day"] = None
            for account in self.data["accounts"].values():
                account.pop("usage_id", None)
                account.pop("active_day", None)

    def home_id(self, setting: str) -> str | None:
        return self.data["home_ids"].get(setting) if self.is_on(setting) else None

    def opted_out(self, user_id: str, setting: str) -> bool:
        return setting in self.data["accounts"].get(user_id, {}).get("opted_out", [])

    def set_opt_out(self, user_id: str, setting: str, out: bool) -> None:
        """An account leaving or rejoining a setting. Leaving usage forgets its ID, so rejoining starts with a new one."""
        account = self.data["accounts"].setdefault(user_id, {})
        opted_out = set(account.get("opted_out", []))
        opted_out.add(setting) if out else opted_out.discard(setting)
        account["opted_out"] = sorted(opted_out)
        if out and setting == USAGE:
            account.pop("usage_id", None)
            account.pop("active_day", None)

    def allowed(self, user_id: str, setting: str) -> bool:
        return self.is_on(setting) and not self.opted_out(user_id, setting)

    def active_today(self, user_id: str, day: str) -> str | None:
        """The account's ID the first time it opens ArkViz on `day`, and None after that or when it may not be counted."""
        if not self.allowed(user_id, USAGE):
            return None
        account = self.data["accounts"].setdefault(user_id, {})
        if account.get("active_day") == day:
            return None
        account["active_day"] = day
        return account.setdefault("usage_id", self._new_id())

    def snapshot_due(self, day: str) -> str | None:
        """The home's ID when `day`'s snapshot hasn't been sent, and None otherwise."""
        return None if self.data.get("snapshot_day") == day else self.home_id(USAGE)

    def snapshot_sent(self, day: str) -> None:
        if self.is_on(USAGE):
            self.data["snapshot_day"] = day
