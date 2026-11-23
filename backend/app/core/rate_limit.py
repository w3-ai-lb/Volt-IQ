"""
Limits on repeated attempts at the endpoints that guard an account.

WHY THESE FIVE
--------------
Each of them can be tried over and over by somebody who is not the owner:

  sign-in           guessing a password
  registration      guessing the one-time registration code for a known
                    Customer ID (the ID is printed on every bill)
  forgot password   flooding an account with reset tokens, which also
                    invalidates the owner's own outstanding link each time
  reset password    trying tokens until one works
  change password   guessing the current password with a stolen session

Nothing stopped any of them. A password guesser could try as fast as the
server answered.

WHAT IS COUNTED
---------------
Failures, not requests, wherever a success exists: a person who types the right
password is never slowed down by the wrong ones they typed before it, and a
successful sign-in clears the count for that address. Forgot-password has no
failure (it answers the same way for every address, so it cannot be used to
find accounts), so there every request counts.

Each count has a target and, where a client address means something, a second
count per client address, so spreading guesses over many accounts from one
machine does not get through either:

  sign-in           per address and client together, and per client. The
                    per-account count includes the client so that a stranger
                    typing wrong passwords cannot lock the owner out of their
                    own account; the price is that guesses spread over many
                    machines are limited per machine only.
  registration      per Customer ID, from any client, and per client
  forgot password   per address, from any client, and per client
  reset password    per client (the token is the only thing typed)
  change password   per signed-in account

Every window is 15 minutes, which is what the refusal tells the user ("wait a
few minutes").

WHAT IT IS NOT
--------------
The counts live in this process's memory. They are lost on a restart and not
shared between server processes, which is enough for the single-process
deployment this project runs as (render.yaml starts one uvicorn worker). A
deployment with several workers or machines needs a shared store such as
Redis behind the same interface.

Behind a reverse proxy the client address is the proxy's unless uvicorn trusts
the proxy's X-Forwarded-For header (--forwarded-allow-ips). render.yaml starts
uvicorn that way, because on Render every request arrives through its proxy.
The per-target limits do not depend on the address and apply either way.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Hashable

from fastapi import HTTPException, Request, status

TOO_MANY_ATTEMPTS = "Too many attempts. Please wait a few minutes and try again."


class AttemptLimiter:
    """At most `max_attempts` recorded attempts per key in any `window_seconds`."""

    # Above this many keys, expired ones are swept out; if that is not enough,
    # the least recently used are dropped. Bounds memory under a flood of
    # distinct keys, at the cost of forgetting the oldest counts first.
    MAX_KEYS = 10_000

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = float(window_seconds)
        self._hits: dict[Hashable, deque[float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: Hashable, now: float) -> deque[float] | None:
        hits = self._hits.get(key)
        if hits is None:
            return None
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if not hits:
            del self._hits[key]
            return None
        return hits

    def retry_after(self, key: Hashable) -> int | None:
        """Seconds until another attempt is allowed, or None if one is allowed now."""
        now = time.monotonic()
        with self._lock:
            hits = self._live(key, now)
            if hits is None or len(hits) < self.max_attempts:
                return None
            return max(1, math.ceil(self.window - (now - hits[0])))

    def record(self, key: Hashable) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._live(key, now)
            if hits is None:
                if len(self._hits) >= self.MAX_KEYS:
                    self._shrink(now)
                hits = self._hits[key] = deque()
            hits.append(now)

    def clear(self, key: Hashable) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _shrink(self, now: float) -> None:
        for key in list(self._hits):
            self._live(key, now)
        overflow = len(self._hits) - self.MAX_KEYS + 1
        if overflow > 0:
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:overflow]
            for key in oldest:
                del self._hits[key]


MINUTE = 60

# Sign-in: failed passwords.
LOGIN_PER_ACCOUNT = AttemptLimiter(5, 15 * MINUTE)       # per (client, email)
# Per-client limits are higher than per-account ones: several people can share
# one address (an office, a mobile network), and the per-account limit is what
# actually stops a password being guessed.
LOGIN_PER_CLIENT = AttemptLimiter(50, 15 * MINUTE)       # per client, any email
# Registration: refused claims. Fifteen minutes like the others, so the refusal
# ("wait a few minutes") is true here too; that still allows only 20 guesses an
# hour at a code drawn from 31^8 (about 8.5 x 10^11) values.
REGISTER_PER_ACCOUNT = AttemptLimiter(5, 15 * MINUTE)    # per Customer ID
REGISTER_PER_CLIENT = AttemptLimiter(30, 15 * MINUTE)
# Forgot password: every request.
FORGOT_PER_EMAIL = AttemptLimiter(5, 15 * MINUTE)
FORGOT_PER_CLIENT = AttemptLimiter(30, 15 * MINUTE)
# Reset password: tokens that do not work.
RESET_PER_CLIENT = AttemptLimiter(30, 15 * MINUTE)
# Change password: wrong current password, per signed-in account.
CHANGE_PER_ACCOUNT = AttemptLimiter(5, 15 * MINUTE)

ALL = (
    LOGIN_PER_ACCOUNT, LOGIN_PER_CLIENT, REGISTER_PER_ACCOUNT, REGISTER_PER_CLIENT,
    FORGOT_PER_EMAIL, FORGOT_PER_CLIENT, RESET_PER_CLIENT, CHANGE_PER_ACCOUNT,
)


def client_of(request: Request) -> str:
    """The client's address as the server sees it (see the note on proxies above)."""
    return request.client.host if request.client else "unknown"


def guard(*checks: tuple[AttemptLimiter, Hashable]) -> None:
    """Refuse with 429 if any of the (limiter, key) pairs has no attempt left."""
    waits = [w for limiter, key in checks if (w := limiter.retry_after(key)) is not None]
    if waits:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=TOO_MANY_ATTEMPTS,
            headers={"Retry-After": str(max(waits))},
        )


def record(*checks: tuple[AttemptLimiter, Hashable]) -> None:
    for limiter, key in checks:
        limiter.record(key)


def reset_all() -> None:
    """Forget every count. For tests."""
    for limiter in ALL:
        limiter.reset()
