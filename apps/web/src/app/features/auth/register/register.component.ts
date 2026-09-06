import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { RegisterResponse } from '../../../core/api/member-auth.models';
import { TurnstileWidgetComponent } from '../../group-admin/shared/turnstile-widget.component';
import { AuthService } from '../auth.service';
import { passwordStrengthValidator, passwordsMatchValidator } from '../auth-form-validators';

@Component({
  selector: 'app-register',
  imports: [ReactiveFormsModule, TranslatePipe, TurnstileWidgetComponent],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
})
export class RegisterComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);

  readonly submitting = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly result = signal<RegisterResponse | null>(null);
  readonly turnstileToken = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group(
    {
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, passwordStrengthValidator]],
      confirm_password: ['', Validators.required],
    },
    { validators: [passwordsMatchValidator('password', 'confirm_password')] },
  );

  onTurnstileVerified(token: string): void {
    this.turnstileToken.set(token);
  }

  onTurnstileExpired(): void {
    this.turnstileToken.set(null);
  }

  submit(): void {
    if (this.form.invalid || !this.turnstileToken()) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    this.submitting.set(true);
    this.errorKey.set(null);

    this.auth
      .register({
        email: raw.email,
        password: raw.password,
        confirm_password: raw.confirm_password,
        turnstile_token: this.turnstileToken()!,
      })
      .subscribe({
        next: (response) => {
          this.submitting.set(false);
          this.result.set(response);
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

  get turnstileLanguage(): string {
    return this.translate.currentLang() === 'zh-TW' ? 'zh-tw' : 'auto';
  }
}
