import { Component, DestroyRef, OnInit, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslatePipe } from '@ngx-translate/core';

interface FramesDefaults {
  frame_scoring_enabled?: boolean;
  frame_target?: number | null;
  frame_win_by?: number;
}

/**
 * 043 US3: the frames `type_params` on the create-group form — whether to
 * keep an in-frame score, and optionally the in-frame points (with a lead)
 * that end a frame on their own. "First to N frames" is the common target
 * score above. Adds its controls to the host's `form` group.
 */
@Component({
  selector: 'app-frames-create-form-fields',
  imports: [ReactiveFormsModule, TranslatePipe],
  template: `
    <div class="frames-fields" [formGroup]="form()">
      <p class="form-hint">{{ 'frames.form.targetHint' | translate }}</p>
      <label class="checkbox-label">
        <input type="checkbox" formControlName="frame_scoring_enabled" />
        {{ 'frames.form.frameScoring' | translate }}
      </label>
      @if (scoringEnabled()) {
        <label>
          {{ 'frames.form.frameTarget' | translate }}
          <input type="number" formControlName="frame_target" min="1" inputmode="numeric" />
        </label>
        <p class="form-hint">{{ 'frames.form.frameTargetHint' | translate }}</p>
        <label>
          {{ 'frames.form.frameWinBy' | translate }}
          <input type="number" formControlName="frame_win_by" min="1" inputmode="numeric" />
        </label>
      }
    </div>
  `,
})
export class FramesCreateFormFieldsComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);

  readonly form = input.required<FormGroup>();
  readonly defaults = input<FramesDefaults | null>(null);
  readonly scoringEnabled = signal(false);

  ngOnInit(): void {
    const defaults = this.defaults() ?? {};
    const enabled = new FormControl(defaults.frame_scoring_enabled ?? false, { nonNullable: true });
    const group = this.form();
    group.addControl('frame_scoring_enabled', enabled);
    group.addControl(
      'frame_target',
      new FormControl<number | null>(defaults.frame_target ?? null, [Validators.min(1)]),
    );
    group.addControl(
      'frame_win_by',
      new FormControl(defaults.frame_win_by ?? 1, {
        nonNullable: true,
        validators: [Validators.required, Validators.min(1)],
      }),
    );
    this.scoringEnabled.set(enabled.value);
    enabled.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => this.scoringEnabled.set(value));
  }
}
