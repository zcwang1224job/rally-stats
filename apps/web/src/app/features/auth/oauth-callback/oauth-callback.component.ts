import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { AuthService } from '../auth.service';
import { LanguageService } from '../../../core/language/language.service';

/** 027-google-line-oauth-login US1/US2 — contracts/oauth-login-api.md's
 * "前端行為對照": the landing page Google/LINE redirect back to after the
 * backend's own callback finishes. The result rides in `location.hash`
 * (`#status=success&access_token=...`), never a query string — a fragment
 * never reaches server access logs or the `Referer` header, unlike a
 * query param. `status=success` hands off to the exact same
 * `AuthService.setTokens()`/`LanguageService.onLoginSuccess()` pair
 * `LoginComponent.submit()` uses, so an OAuth login and a password login
 * converge on identical post-login behavior — including FR-012's
 * nickname-setup redirect, which is `MemberComponent`'s own existing
 * `nickname === null` check, not anything this component re-implements. */
@Component({
  selector: 'app-oauth-callback',
  imports: [TranslatePipe],
  templateUrl: './oauth-callback.component.html',
  styleUrl: './oauth-callback.component.scss',
})
export class OauthCallbackComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly languageService = inject(LanguageService);

  errorKey: string | null = null;

  constructor() {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    this.clearHash();

    const status = params.get('status');
    if (status === 'success') {
      const accessToken = params.get('access_token');
      const refreshToken = params.get('refresh_token');
      // 028-guest-stats-binding research.md #3: present only when this
      // OAuth login also completed a guest roster binding — lets the
      // guest land back on their own live/summary screen instead of the
      // default post-login destination (FR-007).
      const boundGroupId = params.get('bound_group_id');
      const destination = boundGroupId ? ['/groups', boundGroupId, 'member-view'] : ['/member'];
      if (accessToken && refreshToken) {
        this.auth.setTokens(accessToken, refreshToken);
        this.auth.getMe().subscribe({
          next: (member) => {
            this.languageService.onLoginSuccess(member.language_preference);
            void this.router.navigate(destination);
          },
          // Tokens are valid (we just minted them) — a getMe() failure here
          // would be a transient network issue, not an auth problem. Still
          // navigate onward rather than stranding the member on this page.
          error: () => void this.router.navigate(destination),
        });
        return;
      }
    }

    if (status === 'cancelled') {
      void this.router.navigate(['/auth/login']);
      return;
    }

    this.errorKey = `errors.${params.get('code') ?? 'OAUTH_PROVIDER_ERROR'}`;
  }

  goToLogin(): void {
    void this.router.navigate(['/auth/login']);
  }

  /** Never let the token pair linger in browser history. */
  private clearHash(): void {
    history.replaceState(null, '', window.location.pathname + window.location.search);
  }
}
