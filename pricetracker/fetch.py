"""Polite HTTP fetching: honest user-agent, robots.txt compliance, rate limiting.

All outbound requests in the project go through PoliteFetcher so the
politeness rules cannot be bypassed by accident.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

USER_AGENT = (
    "part-price-tracker/0.1 (personal price tracker; "
    "+https://github.com/lukedinsdale; contact lukedinsdale43@gmail.com)"
)

DEFAULT_TIMEOUT = 25
# Minimum seconds between any two requests to the same host.
PER_HOST_DELAY = 6.0
# Minimum seconds between any two requests at all.
GLOBAL_DELAY = 2.0


class RobotsDisallowedError(Exception):
    """robots.txt forbids fetching this URL for our user-agent."""


class FetchError(Exception):
    """The request failed (network error or non-200 status)."""


class PoliteFetcher:
    def __init__(self, user_agent: str = USER_AGENT):
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-GB,en;q=0.9",
            }
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_request_per_host: dict[str, float] = {}
        self._last_request: float = 0.0

    def _robots_for(self, host: str) -> urllib.robotparser.RobotFileParser | None:
        """Fetch and cache robots.txt for a host. None means 'could not read,
        assume allowed' (the conventional interpretation of an unreachable
        robots.txt for well-behaved crawlers is allow, per RFC 9309 5xx aside)."""
        if host in self._robots:
            return self._robots[host]
        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"https://{host}/robots.txt"
        try:
            self._throttle(host)
            resp = self.session.get(robots_url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                self._robots[host] = rp
            elif 400 <= resp.status_code < 500:
                # No robots.txt (or blocked): treat as allow-all per RFC 9309.
                self._robots[host] = None
            else:
                # 5xx: be conservative, treat as disallow-all this run.
                rp.disallow_all = True
                self._robots[host] = rp
        except requests.RequestException as exc:
            log.warning("robots.txt unreachable for %s (%s); assuming allowed", host, exc)
            self._robots[host] = None
        return self._robots[host]

    def _throttle(self, host: str) -> None:
        now = time.monotonic()
        wait = max(
            self._last_request + GLOBAL_DELAY - now,
            self._last_request_per_host.get(host, 0.0) + PER_HOST_DELAY - now,
            0.0,
        )
        if wait > 0:
            time.sleep(wait)
        now = time.monotonic()
        self._last_request = now
        self._last_request_per_host[host] = now

    def get(self, url: str) -> str:
        """Fetch a URL politely; return the response body as text."""
        host = urlparse(url).netloc
        rp = self._robots_for(host)
        if rp is not None and not rp.can_fetch(self.user_agent, url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")
        self._throttle(host)
        try:
            resp = self.session.get(url, timeout=DEFAULT_TIMEOUT, allow_redirects=True)
        except requests.RequestException as exc:
            raise FetchError(f"request failed for {url}: {exc}") from exc
        if resp.status_code != 200:
            raise FetchError(f"HTTP {resp.status_code} for {url}")
        return resp.text
