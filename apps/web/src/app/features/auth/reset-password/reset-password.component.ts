import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../auth.service';
import { passwordStrengthValidator, passwordsMatchValidator } from '../auth-form-validators';

@Component({
  selector: 'app-reset-password',
  imports: [ReactiveFormsModule, TranslatePipe],
  templateUrl: './reset-password.component.html',
  styleUrl: './reset-password.component.scss',
})
export class ResetPasswordComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly submitting = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly reset = signal(false);

  readonly form = this.fb.nonNullable.group(
    {
      new_password: ['', [Validators.required, passwordStrengthValidator]],
      confirm_new_password: ['', Validators.required],
    },
    { validators: [passwordsMatchValidator('new_password', 'confirm_new_password')] },
  );

  submit(): void {
    const token = this.route.snapshot.paramMap.get('token');
    if (this.form.invalid || !token) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    this.submitting.set(true);
    this.errorKey.set(null);

    this.auth.resetPassword(token, raw.new_password, raw.confirm_new_password).subscribe({
      next: () => {
        this.submitting.set(false);
        this.reset.set(true);
      },
      error: (error: ApiError) => {
        this.submitting.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  goToLogin(): void {
    void this.router.navigate(['/auth/login']);
  }
}
