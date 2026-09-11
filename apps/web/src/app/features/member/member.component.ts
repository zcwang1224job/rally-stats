import { Component, DestroyRef, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { MemberPublic } from '../../core/api/member-auth.models';
import { AuthService } from '../auth/auth.service';

/** Member home page (006). Real implementation replacing the pre-006
 * placeholder: fetches the signed-in member and, per FR-012/019, redirects
 * to /member/settings when `nickname === null` (first-login setup) before
 * showing anything else — but only once the member is verified. A freshly
 * registered member always has `nickname === null` AND `verification_status
 * === 'unverified'` at the same time (register() never sets a nickname),
 * and `PATCH /members/me/nickname` requires a verified member
 * (`require_verified_member`, router.py) — so redirecting unconditionally
 * on `nickname === null` would trap an unverified member on the settings
 * page forever (every save attempt 403s), never reaching the resend-
 * verification button below. Showing this page instead (with `user_number`
 * standing in for the missing nickname) lets them resend/verify first; the
 * settings redirect resumes once they're verified.
 *
 * 020-resend-verification-email adds "重新寄送驗證信" (FR-001~FR-009):
 * an unverified member sees a button next to the existing "請驗證你的
 * 信箱" notice. `resendAvailableAt`/`resendCoolingDown` mirror the
 * server-computed cooldown timestamp (`MemberPublic.resend_verification_
 * available_at` on load, `available_at` from a successful resend) — this
 * component only renders it and schedules a one-shot expiry timer against
 * it, never recomputes the cooldown window itself client-side
 * (constitution X, research.md #3/#4). No live mm:ss countdown — just a
 * binary cooling-down/available state (research.md #4), per FR-008. */
@Component({
  selector: 'app-member',
  imports: [TranslatePipe, RouterLink],
  templateUrl: './member.component.html',
  styleUrl: './member.component.scss',
})
export class MemberComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly loading = signal(true);
  readonly member = signal<MemberPublic | null>(null);

  readonly resendSubmitting = signal(false);
  readonly resendSent = signal(false);
  readonly resendErrorKey = signal<string | null>(null);
  readonly resendAvailableAt = signal<string | null>(null);
  readonly resendCoolingDown = signal(false);

  private cooldownTimeoutId: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    this.destroyRef.onDestroy(() => this.clearCooldownTimeout());

    if (!this.auth.isLoggedIn()) {
      void this.router.navigate(['/auth/login']);
      return;
    }
    this.auth.getMe().subscribe({
      next: (member) => {
        this.loading.set(false);
        if (member.nickname === null && member.verification_status === 'verified') {
          void this.router.navigate(['/member/settings']);
          return;
        }
        this.member.set(member);
        this.applyResendAvailableAt(member.resend_verification_available_at);
      },
      error: () => {
        this.auth.clearTokens();
        void this.router.navigate(['/auth/login']);
      },
    });
  }

  logout(): void {
    this.auth.logout();
    void this.router.navigateByUrl('/');
  }

  resendVerification(): void {
    this.resendSubmitting.set(true);
    this.resendSent.set(false);
    this.resendErrorKey.set(null);
    this.auth.resendVerification().subscribe({
      next: (response) => {
        this.resendSubmitting.set(false);
        this.resendSent.set(true);
        this.applyResendAvailableAt(response.available_at);
      },
      // ALREADY_VERIFIED, RESEND_RATE_LIMITED, and any other failure all
      // resolve to the same i18n-keyed message (constitution VIII) —
      // resendSent MUST NOT be set on any error path (US2 FR-005/FR-006).
      error: (error: ApiError) => {
        this.resendSubmitting.set(false);
        this.resendErrorKey.set(error.i18nKey);
      },
    });
  }

  /** research.md #3/#4: `availableAt` is always server-computed (either
   * from `GET /members/me` on load, or a resend response). Schedules
   * exactly one `setTimeout` for the precise expiry moment — no polling,
   * no client-side "+5 minutes" guessing (FR-009). */
  private applyResendAvailableAt(availableAt: string | null): void {
    this.resendAvailableAt.set(availableAt);
    this.clearCooldownTimeout();

    if (availableAt === null) {
      this.resendCoolingDown.set(false);
      return;
    }
    const remainingMs = new Date(availableAt).getTime() - Date.now();
    if (remainingMs <= 0) {
      this.resendCoolingDown.set(false);
      return;
    }
    this.resendCoolingDown.set(true);
    this.cooldownTimeoutId = setTimeout(() => this.resendCoolingDown.set(false), remainingMs);
  }

  private clearCooldownTimeout(): void {
    if (this.cooldownTimeoutId !== undefined) {
      clearTimeout(this.cooldownTimeoutId);
      this.cooldownTimeoutId = undefined;
    }
  }
}
