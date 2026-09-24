import { Component, computed, input, signal, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { Observable } from 'rxjs';

import { Team } from '../../../core/api/court-live-state.models';
import { ConfirmDialogComponent } from '../../../features/group-admin/shared/confirm-dialog.component';
import { LiveMatch, ScoringActions, ScoringResult } from '../../shells/scoring-actions';

/** The frames plugin's `sport_state` (backend `frames/events.py::_state`). */
export interface FramesLiveState {
  readonly frame_no: number;
  readonly frame_score_a: number;
  readonly frame_score_b: number;
  readonly frames_to_win: number;
  readonly frame_scoring_enabled: boolean;
  readonly frame_target: number | null;
}

export function framesLiveState(match: LiveMatch): FramesLiveState {
  const raw = (match.sport_state ?? {}) as Partial<FramesLiveState>;
  return {
    frame_no: raw.frame_no ?? match.score_a + match.score_b + 1,
    frame_score_a: raw.frame_score_a ?? 0,
    frame_score_b: raw.frame_score_b ?? 0,
    frames_to_win: raw.frames_to_win ?? match.target_score ?? 1,
    frame_scoring_enabled: raw.frame_scoring_enabled ?? false,
    frame_target: raw.frame_target ?? null,
  };
}

export const FRAME_POINT = 'frames.frame_point';
export const FRAME_END = 'frames.frame_end';

/**
 * 043 FR-018: the frames score pad — which frame is on, "first to N", the
 * in-frame score (when the group keeps it) with +1/−1 per side, and "mark
 * this frame's winner". Marking the side that is behind in the frame asks
 * twice. Undo and abandon come from the shell around it.
 */
@Component({
  selector: 'app-frames-pad',
  imports: [TranslatePipe, ConfirmDialogComponent],
  template: `
    @let s = state();
    <p class="frame-status" data-testid="frame-status">
      {{ 'frames.pad.frameNo' | translate: { n: s.frame_no } }}
      ·
      {{ 'frames.pad.firstTo' | translate: { n: s.frames_to_win } }}
    </p>
    @if (s.frame_scoring_enabled) {
      <div class="frame-score" data-testid="frame-score">
        @for (team of teams; track team) {
          <div class="frame-side">
            <span class="frame-points">{{ team === 'A' ? s.frame_score_a : s.frame_score_b }}</span>
            @if (!readOnly()) {
              <div class="frame-buttons">
                <button
                  type="button"
                  class="btn"
                  [attr.data-action]="'frame-plus-' + team"
                  [attr.aria-label]="'frames.pad.addPoint' | translate: { team: teamLabel(team) }"
                  [disabled]="!enabled()"
                  (click)="point(team, 1)"
                >+1</button>
                <button
                  type="button"
                  class="btn btn--secondary"
                  [attr.data-action]="'frame-minus-' + team"
                  [attr.aria-label]="'frames.pad.removePoint' | translate: { team: teamLabel(team) }"
                  [disabled]="!enabled() || (team === 'A' ? s.frame_score_a : s.frame_score_b) === 0"
                  (click)="point(team, -1)"
                >−1</button>
              </div>
            }
          </div>
        }
      </div>
    }
    @if (!readOnly()) {
      <p class="mark-label">{{ 'frames.pad.markWinner' | translate }}</p>
      <div class="mark-buttons">
        @for (team of teams; track team) {
          <button
            type="button"
            class="btn"
            [attr.data-action]="'frame-win-' + team"
            [disabled]="!enabled()"
            (click)="markWinner(team)"
          >
            {{ 'frames.pad.teamWins' | translate: { team: teamLabel(team) } }}
          </button>
        }
      </div>
      <app-confirm-dialog
        #behindDialog
        variant="primary"
        [title]="'frames.pad.behindTitle' | translate"
        [body]="'frames.pad.behindBody' | translate: { team: teamLabel(pendingWinner() ?? 'A') }"
        (confirmed)="confirmBehindWinner()"
        (closed)="pendingWinner.set(null)"
      />
    }
  `,
  styles: `
    .frame-status {
      text-align: center;
      font-weight: 600;
      margin: 0.75rem 0;
    }
    .frame-score {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 0.75rem;
    }
    .frame-side {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.5rem;
    }
    .frame-points {
      font-size: 2rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .frame-buttons,
    .mark-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: center;
    }
    .mark-label {
      text-align: center;
      margin: 1rem 0 0.5rem;
    }
    .btn {
      min-height: 44px;
      min-width: 44px;
    }
  `,
})
export class FramesPadComponent {
  readonly match = input.required<LiveMatch>();
  readonly actions = input.required<ScoringActions>();
  readonly run = input.required<(action: Observable<ScoringResult>) => void>();
  readonly busy = input(false);
  readonly connected = input(true);
  readonly readOnly = input(false);

  readonly teams: readonly Team[] = ['A', 'B'];
  readonly state = computed(() => framesLiveState(this.match()));
  readonly enabled = computed(() => this.connected() && !this.busy());
  readonly pendingWinner = signal<Team | null>(null);
  readonly behindDialog = viewChild<ConfirmDialogComponent>('behindDialog');

  teamLabel(team: Team): string {
    return this.match()
      .participants.filter((p) => p.team === team)
      .map((p) => p.nickname)
      .join(' / ');
  }

  point(side: Team, delta: 1 | -1): void {
    const match = this.match();
    this.run()(this.actions().applyEvent(match.match_id, FRAME_POINT, { side, delta }));
  }

  markWinner(team: Team): void {
    const s = this.state();
    const mine = team === 'A' ? s.frame_score_a : s.frame_score_b;
    const theirs = team === 'A' ? s.frame_score_b : s.frame_score_a;
    if (s.frame_scoring_enabled && mine < theirs) {
      this.pendingWinner.set(team);
      this.behindDialog()?.open();
      return;
    }
    this.endFrame(team);
  }

  confirmBehindWinner(): void {
    const team = this.pendingWinner();
    if (team) {
      this.endFrame(team);
    }
  }

  private endFrame(team: Team): void {
    const match = this.match();
    this.run()(this.actions().applyEvent(match.match_id, FRAME_END, { winner_team: team }));
  }
}
