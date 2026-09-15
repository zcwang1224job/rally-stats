import { Component, inject, input, output, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../../auth/auth.service';
import { TurnstileWidgetComponent } from '../../group-admin/shared/turnstile-widget.component';
import { GroupJoinService } from '../group-join.service';

type Mode = 'register' | 'login';

/** 028-guest-stats-binding: the shared "建立帳號並綁定戰績" entry point,
 * embedded both inline in the live member-view (現役, research.md #5) and
 * in `GuestAccessComponent`'s standalone "個人戰績摘要" screen (非現役) —
 * kept as a self-contained, page-shell-free component so both callers
 * reuse the exact same UI/logic (constitution VI). Text/behavior switches
 * on `AuthService.loggedIn` per FR-001/FR-012 (Clarifications
 * 2026-09-15). */
@Component({
  selector: 'app-guest-binding-cta',
  imports: [ReactiveFormsModule, TranslatePipe, TurnstileWidgetComponent],
  templateUrl: './guest-binding-cta.component.html',
  styleUrl: './guest-binding-cta.component.scss',
})
export class GuestBindingCtaComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly joinService = inject(GroupJoinService);
  private readonly translate = inject(TranslateService);

  readonly guestSessionToken = input.required<string>();
  /** Emitted once binding succeeds — callers hide/replace this component
   * (FR-005: the entry point MUST NOT reappear once bound). */
  readonly bound = output<void>();

  readonly loggedIn = this.auth.loggedIn;
  readonly mode = signal<Mode>('register');
  readonly submitting = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly turnstileToken = signal<string | null>(null);
  // UI polish: not logged in starts as a compact banner (so a guest who
  // just wants to check the score/schedule isn't greeted by a full sign-up
  // form) and expands into it on demand. The already-logged-in one-click
  // path (FR-012) is a single button either way, so it has no collapsed
  // state to toggle.
  readonly expanded = signal(false);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  expand(): void {
    this.expanded.set(true);
  }

  collapse(): void {
    this.expanded.set(false);
    this.errorKey.set(null);
  }

  switchMode(mode: Mode): void {
    this.mode.set(mode);
    this.errorKey.set(null);
    this.form.patchValue({ password: '' });
  }

  onTurnstileVerified(token: string): void {
    this.turnstileToken.set(token);
  }

  onTurnstileExpired(): void {
    this.turnstileToken.set(null);
  }

  /** FR-012 / Clarifications 2026-09-15: already-logged-in one-click bind
   * — no form fields involved at all. */
  bindWithCurrentSession(): void {
    this.submitting.set(true);
    this.errorKey.set(null);
    this.joinService.bindGuestSession(this.guestSessionToken(), {}, true).subscribe({
      next: () => {
        this.submitting.set(false);
        this.bound.emit();
      },
      error: (error: ApiError) => {
        this.submitting.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  submit(): void {
    if (this.form.invalid || (this.mode() === 'register' && !this.turnstileToken())) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    this.submitting.set(true);
    this.errorKey.set(null);

    this.joinService
      .bindGuestSession(this.guestSessionToken(), {
        mode: this.mode(),
        email: raw.email,
        password: raw.password,
        turnstile_token: this.mode() === 'register' ? this.turnstileToken() : null,
      })
      .subscribe({
        next: (response) => {
          this.submitting.set(false);
          if (response.access_token && response.refresh_token) {
            this.auth.setTokens(response.access_token, response.refresh_token);
          }
          this.bound.emit();
        },
        error: (error: ApiError) => {
          this.submitting.set(false);
          this.errorKey.set(error.i18nKey);
          // FR-009: an Email collision while creating a new account
          // guides the guest to log in instead, carrying the Email they
          // already typed over rather than leaving them at a dead end.
          if (error.errorCode === 'EMAIL_ALREADY_REGISTERED') {
            this.mode.set('login');
            this.form.patchValue({ password: '' });
          }
        },
      });
  }

  continueWithOAuth(provider: 'google' | 'line'): void {
    this.errorKey.set(null);
    this.auth.startOAuthFlow(provider, 'login', this.guestSessionToken()).subscribe({
      next: (response) => this.navigateToAuthorizeUrl(response.authorize_url),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  protected navigateToAuthorizeUrl(url: string): void {
    window.location.href = url;
  }

  get turnstileLanguage(): string {
    return this.translate.currentLang() === 'zh-TW' ? 'zh-tw' : 'auto';
  }
}
