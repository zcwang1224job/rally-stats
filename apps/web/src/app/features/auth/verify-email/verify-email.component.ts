import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../auth.service';

type Status = 'verifying' | 'verified' | 'error';

/** Handles the verification link itself (GET /auth/verify-email/:token) —
 * the pre-verification "請驗證你的信箱" prompt (FR-009's locked state) is
 * shown inline wherever a signed-in-but-unverified member lands, not as a
 * separate route, since it's a state rather than a navigation destination. */
@Component({
  selector: 'app-verify-email',
  imports: [TranslatePipe],
  templateUrl: './verify-email.component.html',
  styleUrl: './verify-email.component.scss',
})
export class VerifyEmailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly status = signal<Status>('verifying');
  readonly errorKey = signal<string | null>(null);

  constructor() {
    const token = this.route.snapshot.paramMap.get('token');
    if (!token) {
      this.status.set('error');
      return;
    }
    this.auth.verifyEmail(token).subscribe({
      next: () => this.status.set('verified'),
      error: (error: ApiError) => {
        this.status.set('error');
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  goToLogin(): void {
    void this.router.navigate(['/auth/login']);
  }
}
