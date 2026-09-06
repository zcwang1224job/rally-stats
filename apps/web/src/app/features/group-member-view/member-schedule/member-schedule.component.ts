import { Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import { ScheduleResponse } from '../../group-admin/schedule-management/schedule.models';
import { GroupMemberViewService } from '../group-member-view.service';

const COURT_EVENTS = ['match.scoreUpdated', 'match.ended', 'rotation.updated', 'match.nextRound'];
const GROUP_EVENTS = ['member.joined', 'member.left'];

/** US1 (FR-003/004): one-way唯讀 read model reusing the admin schedule
 * snapshot shape — no score/round/roster-management controls of any kind.
 * Real-time sync reuses 007's existing Ably channels/events verbatim. */
@Component({
  selector: 'app-member-schedule',
  imports: [TranslatePipe],
  templateUrl: './member-schedule.component.html',
  styleUrl: './member-schedule.component.scss',
})
export class MemberScheduleComponent {
  readonly groupId = input.required<string>();

  private readonly memberView = inject(GroupMemberViewService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);

  readonly connectionState = this.realtime.connectionState;
  readonly schedule = signal<ScheduleResponse | null>(null);
  readonly errorKey = signal<string | null>(null);

  private readonly subscribedCourtChannels = new Set<string>();
  private groupChannelSubscribed = false;

  constructor() {
    effect(() => {
      // groupId is a route param, stable for the component's lifetime —
      // this effect really just defers `load()` until the input is bound.
      if (this.groupId()) {
        this.load();
      }
    });
    effect(() => {
      const current = this.schedule();
      if (current) {
        this.subscribeToCourtChannels(current);
      }
    });
    // Constitution III: a reconnect MUST force-refetch and overwrite the
    // screen with server state, never trust what accumulated while offline.
    this.reconnectRefetch
      .onReconnect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.load());
  }

  private load(): void {
    this.memberView.getMemberSchedule(this.groupId()).subscribe({
      next: (response) => {
        this.schedule.set(response);
        this.subscribeToGroupChannel();
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  private subscribeToGroupChannel(): void {
    if (this.groupChannelSubscribed) {
      return;
    }
    this.groupChannelSubscribed = true;
    const channel = `group:${this.groupId()}:notifications`;
    for (const event of GROUP_EVENTS) {
      this.realtime
        .subscribe(channel, event)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe(() => this.load());
    }
  }

  private subscribeToCourtChannels(schedule: ScheduleResponse): void {
    for (const court of schedule.courts) {
      const channel = `court:${this.groupId()}:${court.court_id}`;
      if (this.subscribedCourtChannels.has(channel)) {
        continue;
      }
      this.subscribedCourtChannels.add(channel);
      for (const event of COURT_EVENTS) {
        this.realtime
          .subscribe(channel, event)
          .pipe(takeUntilDestroyed(this.destroyRef))
          .subscribe(() => this.load());
      }
    }
  }
}
