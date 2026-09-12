const KEY = 'rally-stats:remembered-login-email';

export function getRememberedLoginEmail(): string | null {
  return localStorage.getItem(KEY);
}

export function setRememberedLoginEmail(email: string | null): void {
  if (email) {
    localStorage.setItem(KEY, email);
  } else {
    localStorage.removeItem(KEY);
  }
}
