"""Push notifications via ntfy.sh.

ntfy.sh: free, no account, no API key. Your phone subscribes to a topic in
the ntfy app; anyone who can POST to the topic can notify it, so the topic
name is effectively the password — use something unguessable and keep it in
a secret (NTFY_TOPIC env var), not in the repo.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")


def send(title: str, message: str, click_url: str | None = None, priority: str = "default") -> bool:
    """Send a push notification. Returns False (and logs) when NTFY_TOPIC is
    unset or the POST fails — notification failure must never kill a run."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log.warning("NTFY_TOPIC not set; would have sent: %s — %s", title, message)
        return False
    headers = {"Title": title, "Priority": priority, "Tags": "moneybag"}
    if click_url:
        headers["Click"] = click_url
    try:
        resp = requests.post(
            f"{NTFY_SERVER}/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("ntfy notification failed: %s", exc)
        return False
