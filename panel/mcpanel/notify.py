"""Discord webhook notifications. Fire-and-forget, never raises."""
from __future__ import annotations

import threading

import httpx


def send(webhook_url: str, text: str) -> None:
    if not webhook_url:
        return

    def _post() -> None:
        try:
            httpx.post(webhook_url, json={"content": text[:1900]}, timeout=10.0)
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()
