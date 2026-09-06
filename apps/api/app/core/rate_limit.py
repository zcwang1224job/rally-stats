"""slowapi rate limiter — used by the PIN reauth endpoint (per-IP) and, in later
specs, by the search/resend-verification endpoints (see specs/architecture.md)."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
