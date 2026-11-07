"""Offline mode: one switch (Edit > Preferences > Advanced) that stops every internet call - maps, ground
levels, rain and forecasts, the update check and the online AI assistants."""
from __future__ import annotations

OFFLINE = False


class OfflineError(RuntimeError):
    pass


def set_offline(on: bool):
    global OFFLINE
    OFFLINE = bool(on)


def check(what: str = "This"):
    if OFFLINE:
        raise OfflineError(f"{what} needs the internet, and GeoLab is in offline mode "
                           "(Edit > Preferences > Advanced).")
