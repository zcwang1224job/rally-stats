#!/bin/sh
# The production build (environment.prod.ts) bakes in the literal string
# __TURNSTILE_SITE_KEY__ instead of a real Turnstile site key, since that
# value is an environment concern, not a build-time one. Substitute it here,
# at container start, from the TURNSTILE_SITE_KEY env var — this runs before
# nginx starts serving traffic, so every response already has the real value.
set -e

: "${TURNSTILE_SITE_KEY:=1x00000000000000000000AA}"

files=$(grep -rl '__TURNSTILE_SITE_KEY__' /usr/share/nginx/html 2>/dev/null || true)
if [ -n "$files" ]; then
  echo "$files" | xargs sed -i "s|__TURNSTILE_SITE_KEY__|${TURNSTILE_SITE_KEY}|g"
fi

exec "$@"
