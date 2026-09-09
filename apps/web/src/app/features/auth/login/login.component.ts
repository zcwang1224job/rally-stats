import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../auth.service';

/** Not part of any tasks.md-listed frontend task — login/refresh were
 * scoped as Foundational (shared infra with no dedicated FR/story of their
 * own), but a login *page* is still required for the auth flow to be
 * usable at all, so it's built here alongside register/verify-email. */
@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, TranslatePipe, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly submitting = signal(false);
  readonly errorKey = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    this.submitting.set(true);
    this.errorKey.set(null);

    this.auth.login({ email: raw.email, password: raw.password }).subscribe({
      next: () => {
        this.submitting.set(false);
        void this.router.navigate(['/member']);
      },
      error: (error: ApiError) => {
        this.submitting.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }
}
