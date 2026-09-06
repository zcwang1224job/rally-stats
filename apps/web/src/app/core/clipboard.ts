/** `navigator.clipboard` requires a secure context (HTTPS, or the
 * `localhost` exception) — it's `undefined` on a plain `http://` origin,
 * which is exactly how this app gets tested from a phone over the LAN
 * (docs/local-development.md §10's `http://<LAN IP>:4200`). Calling
 * `.writeText` on `undefined` there throws, silently failing the "copy
 * link" buttons with no visible error. Falls back to the older
 * `execCommand('copy')` trick via a hidden textarea, which has no such
 * secure-context restriction, so copy still works there. */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied or similar — fall through to the legacy path.
    }
  }
  return legacyCopyTextToClipboard(text);
}

function legacyCopyTextToClipboard(text: string): boolean {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  let succeeded = false;
  try {
    succeeded = document.execCommand('copy');
  } catch {
    succeeded = false;
  }
  document.body.removeChild(textarea);
  return succeeded;
}
