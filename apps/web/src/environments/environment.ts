export const environment = {
  production: false,
  apiBaseUrl: 'http://localhost:8000',
  // Cloudflare's documented "always visible, always passes" test site key —
  // swap for the real key via a build-time environment substitution in prod.
  turnstileSiteKey: '1x00000000000000000000AA',
};
