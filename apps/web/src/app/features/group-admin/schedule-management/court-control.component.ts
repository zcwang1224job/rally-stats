import {
  Component,
  DestroyRef,
  OnInit,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import {
  getScoreSwapPreference,
  setScoreSwapPreference,
} from '../../../core/score-swap-preference';
import { ConfirmDialogComponent } from '../shared/confirm-dialog.component';
import { ScheduleService } from './schedule.service';
import { CourtScheduleStatus, MatchSummary, Team } from './schedule.models';

/** 管理頁「場地控制」區塊之單一場地操作元件（007 US4）——與公開控制板
 * 完全相同的比分/提前結束業務規則，唯一差異是走管理員 PIN session 驗證
 * 路徑而非 token（research.md #10）。斷線提示/操作限制/重連強制覆蓋
 * （FR-021~025）比照公開控制板同一套規則。 */
@Component({
  selector: 'app-court-control',
  imports: [TranslatePipe, ConfirmDialogComponent],
  templateUrl: './court-control.component.html',
  styleUrl: './court-control.component.scss',
})
export class CourtControlComponent implements OnInit {
  readonly groupId = input.required<string>();
  readonly court = input.required<CourtScheduleStatus>();
  readonly changed = output<void>();

  private readonly scheduleService = inject(ScheduleService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  readonly connectionState = this.realtime.connectionState;
  readonly endMatchDialog = viewChild<ConfirmDialogComponent>('endMatchDialog');

  // Lets whoever's scoring swap which side each team's block renders on —
  // remembered per court, not globally, since a different physical court
  // may warrant a different left/right arrangement. Read in ngOnInit, not a
  // field initializer — `court` is a required input and only guaranteed set
  // by the time lifecycle hooks run, not necessarily at construction.
  readonly swapped = signal(false);
  readonly leftTeam = computed<Team>(() => (this.swapped() ? 'B' : 'A'));
  readonly rightTeam = computed<Team>(() => (this.swapped() ? 'A' : 'B'));

  // feature/control-panel-scoreboard-style: same pulse-on-genuine-change
  // animation as ScoreboardComponent/ControlPanelComponent. Unlike those,
  // this component has no live-patched local state of its own — every score
  // change (self-inflicted or from another scorer) only ever arrives as a
  // brand-new `court` input once the parent's `changed` output triggers its
  // own refetch — so the comparison happens in the effect below instead of
  // inline at each call site.
  readonly scorePulseA = signal(false);
  readonly scorePulseB = signal(false);
  private readonly pulseTimeouts: Partial<Record<Team, ReturnType<typeof setTimeout>>> = {};
  private lastPulseMatchId: string | null = null;
  private lastPulseScoreA = 0;
  private lastPulseScoreB = 0;

  private subscribedChannel: string | null = null;

  constructor() {
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());

    effect(() => {
      const match = this.court().current_match;
      if (!match) {
        this.lastPulseMatchId = null;
        return;
      }
      if (this.lastPulseMatchId === match.match_id) {
        if (match.score_a !== this.lastPulseScoreA) {
          this.triggerScorePulse('A');
        }
        if (match.score_b !== this.lastPulseScoreB) {
          this.triggerScorePulse('B');
        }
      }
      this.lastPulseMatchId = match.match_id;
      this.lastPulseScoreA = match.score_a;
      this.lastPulseScoreB = match.score_b;
    });

    // 場地 court_id 一旦確定（掛載後恆定不變）即訂閱一次頻道；`schedule`
    // 每次重新整理都會建立新的 CourtScheduleStatus 物件，但同一場地的
    // court_id 不變，故只需訂閱一次，不隨每次 changed 事件重複訂閱。
    effect(() => {
      const channel = `court:${this.groupId()}:${this.court().court_id}`;
      if (this.subscribedChannel === channel) {
        return;
      }
      this.subscribedChannel = channel;
      for (const event of [
        'match.scoreUpdated',
        'match.ended',
        'rotation.updated',
        'match.nextRound',
      ]) {
        this.realtime
          .subscribe(channel, event)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.changed.emit());
      }
    });
  }

  ngOnInit(): void {
    this.swapped.set(getScoreSwapPreference(this.court().court_id));
  }

  toggleSwap(): void {
    const next = !this.swapped();
    this.swapped.set(next);
    setScoreSwapPreference(this.court().court_id, next);
  }

  /** Restarts the CSS pulse animation on `side`'s score even if it's still
   * mid-animation from a previous change — see ScoreboardComponent's
   * identical method for the full rationale. */
  private triggerScorePulse(side: Team): void {
    const pulseSignal = side === 'A' ? this.scorePulseA : this.scorePulseB;
    clearTimeout(this.pulseTimeouts[side]);
    pulseSignal.set(false);
    requestAnimationFrame(() => {
      pulseSignal.set(true);
      this.pulseTimeouts[side] = setTimeout(() => pulseSignal.set(false), 1200);
    });
  }

  /** feature/control-panel-scoreboard-style: resolves one of the four
   * station slots for `team`'s top/bottom pill — mirrors
   * ControlPanelComponent's identical method (see its comment for why
   * `slot` is a fixed screen position, mapped per-team rather than
   * per-screen-half, to correctly mirror each team's own left/right
   * service court across the net). */
  serveRosterId(match: MatchSummary, team: Team, slot: 'top' | 'bottom'): string | null {
    const serve = match.serve;
    if (!serve) {
      return null;
    }
    if (team === 'A') {
      return slot === 'top'
        ? serve.team_a_left_roster_entry_id
        : serve.team_a_right_roster_entry_id;
    }
    return slot === 'top'
      ? serve.team_b_right_roster_entry_id
      : serve.team_b_left_roster_entry_id;
  }

  /** A station pill is a fixed-size chip in a court corner, not a name
   * list — displayName truncates to the first 2 characters so a long
   * nickname never forces the pill (or the court markings around it) to
   * grow or wrap; `nickname` (the untruncated original) is kept alongside
   * it for the pill's aria-label, so screen readers still get the full
   * name even though the visible text doesn't. */
  station(
    match: MatchSummary,
    rosterEntryId: string | null,
  ): { nickname: string; displayName: string; isServer: boolean } | null {
    if (!rosterEntryId) {
      return null;
    }
    const participant = match.participants.find((p) => p.roster_entry_id === rosterEntryId);
    if (!participant) {
      return null;
    }
    return {
      nickname: participant.nickname,
      displayName: participant.nickname.slice(0, 2),
      isServer: match.serve?.server_roster_entry_id === rosterEntryId,
    };
  }

  score(side: Team, delta: 1 | -1): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.court().current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.scheduleService
      .scoreMatch(this.groupId(), this.court().court_id, matchId, side, delta)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
  }

  openEndMatchDialog(): void {
    this.endMatchDialog()?.open();
  }

  confirmEndMatch(): void {
    if (this.connectionState() !== 'connected') {
      return; // FR-023
    }
    const matchId = this.court().current_match?.match_id;
    if (!matchId) {
      return;
    }
    this.scheduleService
      .endMatch(this.groupId(), this.court().court_id, matchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.changed.emit());
  }
}
