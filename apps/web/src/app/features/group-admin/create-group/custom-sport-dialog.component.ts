import {
  Component,
  DestroyRef,
  ElementRef,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { TranslatePipe } from '@ngx-translate/core';

import { ApiError } from '../../../core/api/api-error';
import {
  CustomSport,
  EndMode,
  MemberNoun,
  ScoreNoun,
  SportTypeKey,
  VenueNoun,
} from '../../../core/api/sport.models';
import { CustomSportCreate, SportsService } from '../../../core/api/sports.service';
import { SportSurfaceComponent } from '../../../sports/hosts/sport-surface.component';
import { parseScoreSteps } from '../shared/group-form-validators';

const TYPES: readonly SportTypeKey[] = ['generic', 'frames', 'net_rally'];
const VENUES: readonly VenueNoun[] = ['court', 'table', 'board', 'arena', 'station', 'venue'];
const SCORES: readonly ScoreNoun[] = ['point', 'frame', 'score'];
const MEMBERS: readonly MemberNoun[] = ['player', 'member', 'competitor'];

/**
 * 043 US4 (FR-004): a verified member saves an activity of their own — a
 * name, the sport type it plays by, the team sizes it allows and the
 * defaults a new group starts from. No editing afterwards this release
 * (clarify Q3): a mistake is deleted and made again.
 */
@Component({
  selector: 'app-custom-sport-dialog',
  imports: [ReactiveFormsModule, TranslatePipe, SportSurfaceComponent],
  template: `
    <dialog #dialog class="dialog dialog--lg custom-sport-dialog" (close)="closed.emit()">
      <h2>{{ 'createGroup.customSport.title' | translate }}</h2>
      <form class="form" [formGroup]="form" (ngSubmit)="save()">
        <label>
          {{ 'createGroup.customSport.name' | translate }}
          <input type="text" formControlName="name" maxlength="20" />
        </label>
        @if (form.controls.name.touched && form.controls.name.invalid) {
          <p role="alert">{{ 'createGroup.customSport.nameRequired' | translate }}</p>
        }

        <label>
          {{ 'createGroup.customSport.type' | translate }}
          <select formControlName="type_key" (change)="typeChanged()">
            @for (type of types; track type) {
              <option [value]="type">{{ 'createGroup.customSport.types.' + type | translate }}</option>
            }
          </select>
        </label>

        <fieldset class="team-sizes">
          <legend>{{ 'createGroup.customSport.teamSizes' | translate }}</legend>
          <label class="checkbox-label">
            <input type="checkbox" formControlName="singles" />
            {{ 'createGroup.matchModeSingles' | translate }}
          </label>
          <label class="checkbox-label">
            <input type="checkbox" formControlName="doubles" />
            {{ 'createGroup.matchModeDoubles' | translate }}
          </label>
        </fieldset>

        <label>
          {{ 'createGroup.generic.endMode' | translate }}
          <select formControlName="end_mode">
            <option value="target">{{ 'createGroup.generic.endModeTarget' | translate }}</option>
            <option value="manual">{{ 'createGroup.generic.endModeManual' | translate }}</option>
          </select>
        </label>
        <label>
          {{ 'createGroup.generic.targetScore' | translate: { noun: ('sports.nouns.' + form.controls.score_noun.value | translate) } }}
          <input type="number" formControlName="target_score" min="1" inputmode="numeric" />
        </label>
        @if (endMode() === 'target') {
          <label>
            {{ 'createGroup.generic.winBy' | translate }}
            <input type="number" formControlName="win_by" min="1" inputmode="numeric" />
          </label>
          <label>
            {{ 'createGroup.generic.capScore' | translate }}
            <input type="number" formControlName="cap_score" min="1" inputmode="numeric" />
          </label>
        } @else {
          <label class="checkbox-label">
            <input type="checkbox" formControlName="allow_draw" />
            {{ 'createGroup.generic.allowDraw' | translate }}
          </label>
        }
        <label>
          {{ 'createGroup.generic.scoreSteps' | translate }}
          <input type="text" formControlName="score_steps" inputmode="numeric" />
        </label>
        <p class="form-hint">{{ 'createGroup.generic.scoreStepsHint' | translate }}</p>

        <fieldset class="nouns">
          <legend>{{ 'createGroup.customSport.nouns' | translate }}</legend>
          <label>
            {{ 'createGroup.customSport.venueNoun' | translate }}
            <select formControlName="venue_noun">
              @for (noun of venues; track noun) {
                <option [value]="noun">{{ 'sports.nouns.' + noun | translate }}</option>
              }
            </select>
          </label>
          <label>
            {{ 'createGroup.customSport.scoreNoun' | translate }}
            <select formControlName="score_noun">
              @for (noun of scores; track noun) {
                <option [value]="noun">{{ 'sports.nouns.' + noun | translate }}</option>
              }
            </select>
          </label>
          <label>
            {{ 'createGroup.customSport.memberNoun' | translate }}
            <select formControlName="member_noun">
              @for (noun of members; track noun) {
                <option [value]="noun">{{ 'sports.nouns.' + noun | translate }}</option>
              }
            </select>
          </label>
        </fieldset>

        <app-sport-surface
          [typeKey]="typeKey()"
          surface="createFormFields"
          [inputs]="{ form: typeParams, defaults: null }"
        />

        @if (errorKey(); as key) {
          <p role="alert" data-testid="custom-sport-error">{{ key | translate }}</p>
        }
        <div class="dialog__actions">
          <button type="button" class="btn btn--secondary" (click)="close()">
            {{ 'common.cancel' | translate }}
          </button>
          <button type="submit" class="btn" data-action="save-custom-sport" [disabled]="saving()">
            {{ 'createGroup.customSport.save' | translate }}
          </button>
        </div>
      </form>
    </dialog>
  `,
  styles: `
    .checkbox-label {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: var(--space-sm);
      min-height: 44px;
    }
    .checkbox-label input[type='checkbox'] {
      width: 1.25rem;
      height: 1.25rem;
      min-height: 0;
      flex: none;
      margin: 0;
    }
    .team-sizes,
    .nouns {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      border: 1px solid var(--color-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
    }
    .dialog__actions {
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
    }
    .dialog__actions .btn {
      min-height: 44px;
    }
  `,
})
export class CustomSportDialogComponent {
  private readonly fb = inject(FormBuilder);
  private readonly sports = inject(SportsService);
  private readonly destroyRef = inject(DestroyRef);

  /** The member's `Authorization` header. */
  readonly headers = input.required<Record<string, string>>();
  readonly created = output<CustomSport>();
  readonly closed = output<void>();

  readonly types = TYPES;
  readonly venues = VENUES;
  readonly scores = SCORES;
  readonly members = MEMBERS;

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  readonly saving = signal(false);
  readonly errorKey = signal<string | null>(null);

  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(20)]],
    type_key: ['generic' as SportTypeKey],
    singles: [true],
    doubles: [true],
    end_mode: ['manual' as EndMode],
    target_score: [1, [Validators.required, Validators.min(1)]],
    win_by: [1, [Validators.required, Validators.min(1)]],
    cap_score: [null as number | null, [Validators.min(1)]],
    allow_draw: [true],
    score_steps: ['1'],
    venue_noun: ['venue' as VenueNoun],
    score_noun: ['point' as ScoreNoun],
    member_noun: ['player' as MemberNoun],
  });
  /** The sport type's own `type_params`, filled by its form fields. */
  readonly typeParams: FormGroup = this.fb.group({});

  readonly typeKey = toSignal(this.form.controls.type_key.valueChanges, {
    initialValue: this.form.controls.type_key.value,
  });
  readonly endMode = toSignal(this.form.controls.end_mode.valueChanges, {
    initialValue: this.form.controls.end_mode.value,
  });

  open(): void {
    this.errorKey.set(null);
    const native = this.dialog().nativeElement;
    if (typeof native.showModal === 'function') {
      native.showModal();
    }
  }

  close(): void {
    const native = this.dialog().nativeElement;
    if (typeof native.close === 'function') {
      native.close();
    }
  }

  typeChanged(): void {
    for (const name of Object.keys(this.typeParams.controls)) {
      this.typeParams.removeControl(name);
    }
  }

  /** The request body, or an i18n key naming what is wrong. */
  body(): CustomSportCreate | string {
    const raw = this.form.getRawValue();
    const sizes = [raw.singles ? 1 : null, raw.doubles ? 2 : null].filter(
      (size): size is number => size !== null,
    );
    if (sizes.length === 0) {
      return 'createGroup.customSport.teamSizesRequired';
    }
    const steps = parseScoreSteps(raw.score_steps);
    if (!steps) {
      return 'createGroup.generic.invalid.score_steps';
    }
    const target = raw.end_mode === 'target';
    return {
      name: raw.name.trim(),
      type_key: raw.type_key,
      team_size_options: sizes,
      defaults: {
        team_size: sizes[0],
        end_mode: raw.end_mode,
        target_score: Number(raw.target_score),
        win_by: target ? Number(raw.win_by) : 1,
        cap_score: target && raw.cap_score ? Number(raw.cap_score) : null,
        allow_draw: !target && raw.allow_draw,
        score_steps: steps,
        type_params: this.typeParams.getRawValue() as Record<string, unknown>,
        nouns: { venue: raw.venue_noun, score: raw.score_noun, member: raw.member_noun },
      },
    };
  }

  save(): void {
    this.form.markAllAsTouched();
    if (this.form.controls.name.invalid || !this.form.controls.name.value.trim()) {
      this.errorKey.set('createGroup.customSport.nameRequired');
      return;
    }
    if (this.form.invalid) {
      this.errorKey.set('createGroup.customSport.numbersInvalid');
      return;
    }
    const body = this.body();
    if (typeof body === 'string') {
      this.errorKey.set(body);
      return;
    }
    this.saving.set(true);
    this.errorKey.set(null);
    this.sports
      .createCustomSport(body, this.headers())
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (sport) => {
          this.saving.set(false);
          this.created.emit(sport);
          this.close();
        },
        error: (error: ApiError) => {
          this.saving.set(false);
          this.errorKey.set(error?.i18nKey ?? 'errors.UNKNOWN_ERROR');
        },
      });
  }
}
