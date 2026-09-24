import { Component, DestroyRef, TemplateRef, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { ApiError } from '../../core/api/api-error';
import { CourtControlService } from '../../core/api/court-control.service';
import { CourtByTokenResponse } from '../../core/api/court-link.models';
import { CourtStateResponse } from '../../core/api/court-live-state.models';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { waitingReasonKey } from '../../core/waiting-reason-label';
import { CourtScoringShellComponent, ScorePadContext } from './court-scoring-shell.component';
import { courtLinkActions } from './scoring-actions';

/**
 * 043: the `/scoreboard/:courtToken` and `/control/:courtToken` pages of a
 * non-net-rally sport type — the link check, live updates and waiting
 * states every court page has, around `app-court-scoring-shell` and the
 * sport type's `pad`. The net rally pages keep their own components.
 */
@Component({
  selector: 'app-court-link-page',
  imports: [TranslatePipe, CourtScoringShellComponent],
  template: `
    @if (linkInvalidated()) {
      <p role="alert">{{ 'courtManagement.linkInvalidatedNotice' | translate }}</p>
    } @else if (loading()) {
      <p>{{ 'common.loading' | translate }}</p>
    } @else if (errorKey(); as key) {
      <p role="alert">{{ key | translate }}</p>
    } @else if (courtInfo(); as info) {
      @if (info.deleted) {
        <p role="alert">{{ 'courtManagement.courtDeletedNotice' | translate }}</p>
      } @else if (info.group_disbanded) {
        <p role="alert">{{ 'courtManagement.groupDisbandedNotice' | translate }}</p>
      } @else {
        @if (connectionState() !== 'connected') {
          <p role="status" class="status-badge status-badge--danger offline-banner">
            {{ 'common.offlineBanner' | translate }}
          </p>
        }
        <h1>{{ info.name }}</h1>
        @if (state(); as s) {
          <p class="round-label">
            {{ 'scheduleManagement.roundLabel' | translate: { round: s.round_number } }}
          </p>
          @if (s.current_match; as match) {
            <app-court-scoring-shell
              [match]="match"
              [actions]="actions"
              [pad]="pad()"
              [readOnly]="mode() === 'scoreboard'"
              (changed)="loadState()"
            />
          } @else if (s.waiting_reason === 'manual_assignment') {
            <p class="waiting-message">{{ 'scheduleManagement.waitingManualAssignment' | translate }}</p>
          } @else if (!s.next_up) {
            <p class="waiting-message">{{ waitingReasonKey(s.waiting_reason) | translate }}</p>
          }
          @if (s.next_up; as next) {
            <p class="next-up status-badge">
              {{ 'controlPanel.nextUpLabel' | translate: { names: nextUpNames(next.participants) } }}
            </p>
          }
        }
      }
    }
  `,
  styles: `
    :host {
      display: block;
      max-width: 40rem;
      margin: 0 auto;
      padding: var(--space-md);
    }
    .round-label {
      margin: 0 0 var(--space-md);
    }
  `,
})
export class CourtLinkPageComponent {
  readonly waitingReasonKey = waitingReasonKey;
  private readonly route = inject(ActivatedRoute);
  private readonly heartbeat = inject(LinkHeartbeatService);
  private readonly realtime = inject(RealtimeService);
  private readonly courtControl = inject(CourtControlService);
  private readonly destroyRef = inject(DestroyRef);

  readonly mode = input<'control' | 'scoreboard'>('control');
  readonly pad = input<TemplateRef<ScorePadContext> | null>(null);

  private readonly token = this.route.snapshot.paramMap.get('courtToken') ?? '';
  readonly actions = courtLinkActions(this.courtControl, this.token);

  readonly courtInfo = signal<CourtByTokenResponse | null>(null);
  readonly state = signal<CourtStateResponse | null>(null);
  readonly linkInvalidated = signal(false);
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);
  readonly connectionState = this.realtime.connectionState;
  private subscribed = false;
  /** Realtime messages are sent after each request's response, one by one,
   * so two quick actions can arrive in the wrong order and leave an older
   * score on screen. Each push is shown at once, then the page reads the
   * state again shortly after the last one. */
  static readonly SETTLE_MS = 400;
  private settleTimer: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    this.destroyRef.onDestroy(() => clearTimeout(this.settleTimer));
    inject(ReconnectRefetchService)
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadState());
    this.heartbeat
      .watchCourtLink(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (info) => {
          if (this.linkInvalidated()) {
            return;
          }
          this.courtInfo.set(info);
          this.loading.set(false);
          if (!this.subscribed) {
            this.subscribed = true;
            this.subscribeToLiveEvents(info);
            this.loadState();
          }
        },
        error: (error: ApiError) => {
          if (this.linkInvalidated()) {
            return;
          }
          this.loading.set(false);
          this.errorKey.set(error.i18nKey);
        },
      });
  }

  loadState(): void {
    this.courtControl
      .getState(this.token)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((state) => this.state.set(state));
  }

  nextUpNames(participants: readonly { nickname: string }[]): string {
    return participants.map((p) => p.nickname).join(' / ');
  }

  private subscribeToLiveEvents(info: CourtByTokenResponse): void {
    const channel = `court:${info.group_id}:${info.court_id}`;
    const on = (event: string) =>
      this.realtime.subscribe(channel, event).pipe(takeUntilDestroyed(this.destroyRef));

    on('link.regenerated').subscribe((message) => {
      const data = message.data as { link_type: string };
      if (data.link_type === info.link_type) {
        this.linkInvalidated.set(true);
      }
    });
    for (const event of ['match.scoreUpdated', 'match.eventApplied']) {
      on(event).subscribe((message) => {
        const data = message.data as {
          match_id: string;
          score_a: number;
          score_b: number;
          sport_state?: unknown;
        };
        const state = this.state();
        if (state?.current_match?.match_id !== data.match_id) {
          return;
        }
        this.state.set({
          ...state,
          current_match: {
            ...state.current_match,
            score_a: data.score_a,
            score_b: data.score_b,
            ...(data.sport_state !== undefined && data.sport_state !== null
              ? { sport_state: data.sport_state }
              : {}),
          },
        });
        clearTimeout(this.settleTimer);
        this.settleTimer = setTimeout(() => this.loadState(), CourtLinkPageComponent.SETTLE_MS);
      });
    }
    for (const event of ['match.ended', 'rotation.updated', 'match.nextRound']) {
      on(event).subscribe(() => this.loadState());
    }
    // The first state load can race the channel attach: anything scored in
    // between would never arrive, so read the state again once attached.
    this.realtime.whenAttached(channel).then(
      () => this.loadState(),
      () => undefined,
    );
  }
}
