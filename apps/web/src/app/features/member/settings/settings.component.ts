import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { AuthService } from '../../auth/auth.service';
import {
  passwordStrengthValidator,
  passwordsMatchValidator,
} from '../../auth/auth-form-validators';

/** FR-012/019 (006): the "首次登入設定暱稱" redirect lands here whenever
 * GET /members/me returns nickname === null (see member.component.ts, and
 * 004's join-flow — a member joining without a nickname yet is sent here
 * with `?returnTo=` so a successful save sends them straight back to
 * finish joining instead of the generic member home). */
@Component({
  selector: 'app-member-settings',
  imports: [ReactiveFormsModule, TranslatePipe],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.scss',
})
export class SettingsComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly nicknameSubmitting = signal(false);
  readonly nicknameErrorKey = signal<string | null>(null);
  readonly nicknameSaved = signal(false);

  readonly passwordSubmitting = signal(false);
  readonly passwordErrorKey = signal<string | null>(null);
  readonly passwordSaved = signal(false);

  readonly nicknameForm = this.fb.nonNullable.group({
    nickname: ['', [Validators.required, Validators.maxLength(20)]],
  });

  readonly passwordForm = this.fb.nonNullable.group(
    {
      current_password: ['', Validators.required],
      new_password: ['', [Validators.required, passwordStrengthValidator]],
      confirm_new_password: ['', Validators.required],
    },
    { validators: [passwordsMatchValidator('new_password', 'confirm_new_password')] },
  );

  submitNickname(): void {
    if (this.nicknameForm.invalid) {
      this.nicknameForm.markAllAsTouched();
      return;
    }
    this.nicknameSubmitting.set(true);
    this.nicknameErrorKey.set(null);
    this.auth.setNickname(this.nicknameForm.getRawValue().nickname).subscribe({
      next: () => {
        this.nicknameSubmitting.set(false);
        this.nicknameSaved.set(true);
        const returnTo = this.route.snapshot.queryParamMap.get('returnTo');
        void this.router.navigateByUrl(returnTo ?? '/member');
      },
      error: (error: ApiError) => {
        this.nicknameSubmitting.set(false);
        this.nicknameErrorKey.set(error.i18nKey);
      },
    });
  }

  submitPassword(): void {
    if (this.passwordForm.invalid) {
      this.passwordForm.markAllAsTouched();
      return;
    }
    const raw = this.passwordForm.getRawValue();
    this.passwordSubmitting.set(true);
    this.passwordErrorKey.set(null);
    this.auth
      .changePassword(raw.current_password, raw.new_password, raw.confirm_new_password)
      .subscribe({
        next: () => {
          this.passwordSubmitting.set(false);
          this.passwordSaved.set(true);
          this.passwordForm.reset();
        },
        error: (error: ApiError) => {
          this.passwordSubmitting.set(false);
          this.passwordErrorKey.set(error.i18nKey);
        },
      });
  }
}
