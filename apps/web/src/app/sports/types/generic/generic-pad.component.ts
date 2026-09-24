import { Component, computed, input, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { Observable } from 'rxjs';

import { Team } from '../../../core/api/court-live-state.models';
import { ConfirmDialogComponent } from '../../../features/group-admin/shared/confirm-dialog.component';
import { LiveMatch, ScoringActions, ScoringResult } from '../../shells/scoring-actions';

/**
 * 043 FR-017 / FR-017a: the generic score pad — `+N` per side for every
 * step the group allows, and for a manual-end match "end and record the
 * result", which is named, marked and confirmed differently from the
 * shell's "abandon the match" (constitution V). A mistake is taken back
 * with the shell's undo.
 */
@Component({
  selector: 'app-generic-pad',
  imports: [TranslatePipe, ConfirmDialogComponent],
  template: `
    @if (!readOnly()) {
      <div class="step-grid">
        @for (team of teams; track team) {
          <div class="step-side">
            @for (step of steps(); track step) {
              <button
                type="button"
                class="btn"
                [attr.data-action]="'plus-' + step + '-' + team"
                [attr.aria-label]="'genericSport.addPoints' | translate: { n: step, team: teamLabel(team) }"
                [disabled]="!enabled()"
                (click)="score(team, step)"
              >+{{ step }}</button>
            }
          </div>
        }
      </div>
      @if (manual()) {
        <button
          type="button"
          class="btn btn--primary finish-button"
          data-action="finish"
          [disabled]="!enabled()"
          (click)="finishDialog.open()"
        >
          ✓ {{ 'genericSport.finish' | translate }}
        </button>
        <app-confirm-dialog
          #finishDialog
          variant="primary"
          [title]="'genericSport.finishTitle' | translate"
          [body]="finishText().key | translate: finishText().params"
          [confirmLabel]="'genericSport.finish' | translate"
          (confirmed)="finish()"
        />
      }
    } @else if (manual() && match().score_a === match().score_b && match().allow_draw) {
      <p class="level-note">{{ 'genericSport.levelNow' | translate }}</p>
    }
  `,
  styles: `
    .step-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 0.75rem;
      margin-top: 0.75rem;
    }
    .step-side {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: center;
    }
    .btn {
      min-height: 44px;
      min-width: 44px;
    }
    .finish-button {
      display: block;
      width: 100%;
      margin-top: 1rem;
    }
    .level-note {
      text-align: center;
    }
  `,
})
export class GenericPadComponent {
  readonly match = input.required<LiveMatch>();
  readonly actions = input.required<ScoringActions>();
  readonly run = input.required<(action: Observable<ScoringResult>) => void>();
  readonly busy = input(false);
  readonly connected = input(true);
  readonly readOnly = input(false);
  readonly teams: readonly Team[] = ['A', 'B'];
  readonly enabled = computed(() => this.connected() && !this.busy());
  readonly steps = computed(() => {
    const steps = this.match().score_steps;
    return steps && steps.length > 0 ? steps : [1];
  });
  readonly manual = computed(() => this.match().end_mode === 'manual');
  readonly finishDialog = viewChild<ConfirmDialogComponent>('finishDialog');

  /** What "end and record the result" will record: the leader wins, a
   * level score is a draw where allowed, otherwise it is refused. */
  readonly finishText = computed(() => {
    const m = this.match();
    const score = `${m.score_a} : ${m.score_b}`;
    if (m.score_a !== m.score_b) {
      const leader: Team = m.score_a > m.score_b ? 'A' : 'B';
      return { key: 'genericSport.finishBodyWin', params: { score, team: this.teamLabel(leader) } };
    }
    return {
      key: m.allow_draw ? 'genericSport.finishBodyDraw' : 'genericSport.finishBodyNoDraw',
      params: { score },
    };
  });

  teamLabel(team: Team): string {
    return this.match()
      .participants.filter((p) => p.team === team)
      .map((p) => p.nickname)
      .join(' / ');
  }

  score(side: Team, step: number): void {
    this.run()(this.actions().score(this.match().match_id, side, step));
  }

  finish(): void {
    this.run()(this.actions().finish(this.match().match_id));
  }
}
