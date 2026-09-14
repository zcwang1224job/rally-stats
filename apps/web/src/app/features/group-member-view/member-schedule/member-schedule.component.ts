import { Component, DestroyRef, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import { InviteCandidateStatus } from '../../../core/api/friend.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../../core/realtime/reconnect-refetch.service';
import { AddFriendButtonComponent } from '../../../shared/add-friend-button/add-friend-button.component';
import { AuthService } from '../../auth/auth.service';
import { FriendsService } from '../../friends/friends.service';
import {
  RosterScheduleStatus,
  RoundMatchesResponse,
  RoundMatchSummary,
  ScheduleResponse,
} from '../../group-admin/schedule-management/schedule.models';
import { GroupMemberViewService } from '../group-member-view.service';

const COURT_EVENTS = ['match.scoreUpdated', 'match.ended', 'rotation.updated', 'match.nextRound'];
const GROUP_EVENTS = ['member.joined', 'member.left'];

/** US1 (FR-003/004): one-way唯讀 read model reusing the admin schedule
 * snapshot shape — no score/round/roster-management controls of any kind.
 * Real-time sync reuses 007's existing Ably channels/events verbatim. */
@Component({
  selector: 'app-member-schedule',
  imports: [TranslatePipe, AddFriendButtonComponent],
  templateUrl: './member-schedule.component.html',
  styleUrl: './member-schedule.component.scss',
})
export class MemberScheduleComponent {
  readonly groupId = input.required<string>();

  private readonly memberView = inject(GroupMemberViewService);
  private readonly realtime = inject(RealtimeService);
  private readonly reconnectRefetch = inject(ReconnectRefetchService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly friends = inject(FriendsService);

  readonly connectionState = this.realtime.connectionState;
  readonly schedule = signal<ScheduleResponse | null>(null);
  readonly roundMatches = signal<RoundMatchesResponse | null>(null);
  readonly errorKey = signal<string | null>(null);

  /** 026-match-record-friend-invite (roster-list redesign): batched
   * relationship + eligibility status for every roster member, re-batched
   * on every `load()` (which already fires on every relevant Ably event,
   * so this naturally updates as members join/leave). */
  readonly inviteCandidates = signal<Map<string, InviteCandidateStatus>>(new Map());

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
        this.loadInviteCandidates(response.roster);
      },
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
    // Same load()-on-every-relevant-event refresh as the per-court view
    // above — no separate polling loop for this list.
    this.memberView.getRoundMatches(this.groupId()).subscribe({
      next: (response) => this.roundMatches.set(response),
      error: (error: ApiError) => this.errorKey.set(error.i18nKey),
    });
  }

  private loadInviteCandidates(roster: RosterScheduleStatus[]): void {
    const selfMemberId = this.auth.getCachedMemberId();
    if (!selfMemberId) {
      this.inviteCandidates.set(new Map());
      return;
    }
    const memberIds = [
      ...new Set(
        roster
          .map((r) => r.member_id)
          .filter((id): id is string => !!id && id !== selfMemberId),
      ),
    ];
    if (memberIds.length === 0) {
      this.inviteCandidates.set(new Map());
      return;
    }
    this.friends.getInviteCandidatesStatus(memberIds).subscribe({
      next: (result) => {
        this.inviteCandidates.set(new Map(result.candidates.map((c) => [c.member_id, c])));
      },
      error: () => this.inviteCandidates.set(new Map()),
    });
  }

  inviteCandidateFor(memberId: string): InviteCandidateStatus | undefined {
    return this.inviteCandidates().get(memberId);
  }

  vsLabel(match: RoundMatchSummary): string {
    const teamA = match.participants.filter((p) => p.team === 'A').map((p) => p.nickname);
    const teamB = match.participants.filter((p) => p.team === 'B').map((p) => p.nickname);
    return `${teamA.join(' / ')} vs ${teamB.join(' / ')}`;
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
