import { NgTemplateOutlet } from '@angular/common';
import {
  Component,
  DestroyRef,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { Observable } from 'rxjs';

import { ApiError } from '../../core/api/api-error';
import { Team } from '../../core/api/court-live-state.models';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ConfirmDialogComponent } from '../../features/group-admin/shared/confirm-dialog.component';
import { LiveMatch, ScoringActions, ScoringResult } from './scoring-actions';

/** What a sport type's score pad template receives. */
export interface ScorePadContext {
  /** The match as the pad should show it (this client's own last result
   * applied on top of the page's state). */
  readonly $implicit: LiveMatch;
  readonly actions: ScoringActions;
  /** Sends one action; the shell applies the result, shows its error and
   * blocks other actions until it returns. */
  readonly run: (action: Observable<ScoringResult>) => void;
  readonly busy: boolean;
  readonly connected: boolean;
  readonly readOnly: boolean;
}

/**
 * 043: the parts of a court's scoring screen every non-net-rally sport type
 * shares — both teams' names and match score, "undo" and "abandon the
 * match" — around the sport type's own score pad (`pad`). Used on all three
 * scorer faces: the court link page, the all-courts page and the admin
 * page's court control, each passing its own `actions`.
 *
 * `changed` fires when the court moves on (the match ended or was
 * abandoned) so the page reloads its state.
 */
@Component({
  selector: 'app-court-scoring-shell',
  imports: [NgTemplateOutlet, TranslatePipe, ConfirmDialogComponent],
  template: `
    @let m = shown();
    <div class="scoring-shell">
      <div class="teams">
        @for (team of teams; track team) {
          <div class="team" [class.team--a]="team === 'A'" [class.team--b]="team === 'B'">
            <div class="names">
              @for (p of m.participants; track p.roster_entry_id) {
                @if (p.team === team) {
                  <span>{{ p.nickname }}</span>
                }
              }
            </div>
            <span class="score" data-testid="match-score">{{ team === 'A' ? m.score_a : m.score_b }}</span>
          </div>
        }
      </div>

      @if (errorKey(); as key) {
        <p role="alert" class="shell-error">{{ key | translate }}</p>
      }

      @if (pad(); as padTemplate) {
        <ng-container
          [ngTemplateOutlet]="padTemplate"
          [ngTemplateOutletContext]="padContext()"
        />
      }

      @if (!readOnly()) {
        <div class="shell-actions">
          @if (showUndo()) {
            <button
              type="button"
              class="btn btn--secondary"
              data-action="undo"
              [disabled]="!connected() || busy()"
              (click)="undo()"
            >
              {{ 'sports.shell.undo' | translate }}
            </button>
          }
          <button
            type="button"
            class="btn btn--danger"
            data-action="abandon"
            [disabled]="!connected() || busy()"
            (click)="abandonDialog.open()"
          >
            {{ 'sports.shell.abandon' | translate }}
          </button>
        </div>
        <app-confirm-dialog
          #abandonDialog
          [title]="'sports.shell.abandonTitle' | translate"
          [body]="'sports.shell.abandonBody' | translate"
          [confirmLabel]="'sports.shell.abandon' | translate"
          (confirmed)="abandon()"
        />
      }
    </div>
  `,
  styles: `
    .teams {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 0.75rem;
    }
    .team {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.25rem;
      padding: 0.75rem;
      border-radius: 0.75rem;
      border: 2px solid transparent;
      color: #fff;
    }
    /* The same team colours every score display uses (_tokens.scss). */
    .team--a {
      background: var(--color-team-a-bg);
      border-color: var(--color-team-a-border);
    }
    .team--b {
      background: var(--color-team-b-bg);
      border-color: var(--color-team-b-border);
    }
    .names {
      display: flex;
      flex-direction: column;
      align-items: center;
      font-weight: 600;
      overflow-wrap: anywhere;
      text-align: center;
    }
    .score {
      font-size: clamp(2.5rem, 12vw, 4.5rem);
      font-weight: 700;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }
    .shell-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 1rem;
    }
    .shell-actions .btn {
      min-height: 44px;
    }
  `,
})
export class CourtScoringShellComponent {
  private readonly destroyRef = inject(DestroyRef);
  private readonly realtime = inject(RealtimeService);

  readonly match = input.required<LiveMatch>();
  readonly actions = input.required<ScoringActions>();
  readonly pad = input<TemplateRef<ScorePadContext> | null>(null);
  /** A scoreboard shows the pad's read-only view and no buttons. */
  readonly readOnly = input(false);
  readonly showUndo = input(true);
  readonly changed = output<void>();

  readonly teams: readonly Team[] = ['A', 'B'];
  readonly busy = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly abandonDialog = viewChild<ConfirmDialogComponent>('abandonDialog');
  readonly connected = computed(() => this.realtime.connectionState() === 'connected');

  /** This client's own last result. Realtime echoes of this client's
   * EARLIER actions can arrive after a later action's response and would
   * briefly show an older score, so the page's state only takes over again
   * once the echoes have had time to arrive (they come in order). */
  private readonly own = signal<Partial<LiveMatch> & { match_id: string } | null>(null);
  private ownTimer: ReturnType<typeof setTimeout> | undefined;
  static readonly OWN_RESULT_GRACE_MS = 2500;

  readonly shown = computed<LiveMatch>(() => {
    const match = this.match();
    const own = this.own();
    return own && own.match_id === match.match_id ? { ...match, ...own } : match;
  });

  readonly padContext = computed<ScorePadContext>(() => ({
    $implicit: this.shown(),
    actions: this.actions(),
    run: (action) => this.run(action),
    busy: this.busy(),
    connected: this.connected(),
    readOnly: this.readOnly(),
  }));

  constructor() {
    this.destroyRef.onDestroy(() => clearTimeout(this.ownTimer));
    // Another match on the court: nothing of the old one applies.
    effect(() => {
      const matchId = this.match().match_id;
      untracked(() => {
        if (this.own() && this.own()!.match_id !== matchId) {
          this.own.set(null);
        }
      });
    });
  }

  private holdOwn(own: Partial<LiveMatch> & { match_id: string }): void {
    this.own.set(own);
    clearTimeout(this.ownTimer);
    this.ownTimer = setTimeout(
      () => this.own.set(null),
      CourtScoringShellComponent.OWN_RESULT_GRACE_MS,
    );
  }

  run(action: Observable<ScoringResult>): void {
    if (this.busy() || !this.connected()) {
      return;
    }
    this.busy.set(true);
    this.errorKey.set(null);
    action.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => {
        this.busy.set(false);
        if (result.status !== 'in_progress') {
          this.changed.emit();
          return;
        }
        this.holdOwn({
          match_id: result.match_id,
          score_a: result.score_a,
          score_b: result.score_b,
          ...(result.sport_state !== undefined && result.sport_state !== null
            ? { sport_state: result.sport_state }
            : {}),
        });
      },
      error: (error: ApiError) => {
        this.busy.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  undo(): void {
    if (this.canAct()) {
      this.run(this.actions().undo(this.match().match_id));
    }
  }

  abandon(): void {
    if (this.canAct()) {
      this.run(this.actions().abandon(this.match().match_id));
    }
  }

  private canAct(): boolean {
    return this.connected() && !this.busy();
  }
}
