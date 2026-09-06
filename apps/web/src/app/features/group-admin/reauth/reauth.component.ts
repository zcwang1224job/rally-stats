import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { GroupAdminService } from '../group-admin.service';

@Component({
  selector: 'app-reauth',
  imports: [ReactiveFormsModule, TranslatePipe],
  templateUrl: './reauth.component.html',
  styleUrl: './reauth.component.scss',
})
export class ReauthComponent {
  private readonly fb = inject(FormBuilder);
  private readonly groupAdmin = inject(GroupAdminService);
  private readonly router = inject(Router);

  readonly submitting = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly retryAfterSeconds = signal<number | null>(null);

  readonly form = this.fb.nonNullable.group({
    group_number: [null as number | null, Validators.required],
    admin_pin: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { group_number, admin_pin } = this.form.getRawValue();
    this.submitting.set(true);
    this.errorKey.set(null);
    this.retryAfterSeconds.set(null);

    this.groupAdmin.reauth(group_number!, admin_pin).subscribe({
      next: (response) => {
        this.submitting.set(false);
        this.groupAdmin.setAdminToken(response.group_id, response.admin_token);
        void this.router.navigate(['/groups', response.group_id, 'admin']);
      },
      error: (error: ApiError) => {
        this.submitting.set(false);
        this.errorKey.set(error.i18nKey);
        const retryAfter = error.detail?.['retry_after_seconds'];
        if (typeof retryAfter === 'number') {
          this.retryAfterSeconds.set(retryAfter);
        }
      },
    });
  }
}
