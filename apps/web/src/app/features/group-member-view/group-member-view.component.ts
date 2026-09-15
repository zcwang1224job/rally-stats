import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { GroupPublic } from '../group-admin/group-admin.models';
import { GuestBindingCtaComponent } from '../group-join/guest-binding-cta/guest-binding-cta.component';
import { GroupJoinService } from '../group-join/group-join.service';
import { LeaveGroupComponent } from './leave-group/leave-group.component';
import { MatchRecordsComponent } from './match-records/match-records.component';
import { MemberScheduleComponent } from './member-schedule/member-schedule.component';
import { StandingsComponent } from './standings/standings.component';

type Tab = 'schedule' | 'standings' | 'match-records';

/** US1 (FR-001/002): the non-admin entry point for a group — nav shows
 * exactly 賽程/戰績/退出組團/對戰紀錄, never any admin-only action (場地
 * 設定/賽程設定/輪替名單管理/解散). Each nav item is either a read-only
 * tab (schedule/standings/match-records) or the leave-group action —
 * never a control that mutates schedule/score state.
 *
 * Shell mirrors admin-page's layout (010-app-wide-ui-redesign) for a
 * consistent look across the two group-scoped pages a Member/Guest can
 * land on — same horizontally-scrollable-strip-turned-sidebar nav
 * (`.member-nav`), same header structure (group name + number). Renders
 * behind the global nav-shell topbar too, unlike admin-page and the join
 * flow (those stay `navShell: false`) — this page has no group-admin
 * powers to keep separate from ordinary site navigation. */
@Component({
  selector: 'app-group-member-view',
  imports: [
    TranslatePipe,
    MemberScheduleComponent,
    StandingsComponent,
    MatchRecordsComponent,
    LeaveGroupComponent,
    GuestBindingCtaComponent,
  ],
  templateUrl: './group-member-view.component.html',
  styleUrl: './group-member-view.component.scss',
})
export class GroupMemberViewComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly groupJoin = inject(GroupJoinService);

  readonly groupId = this.route.snapshot.paramMap.get('groupId')!;
  readonly activeTab = signal<Tab>('schedule');
  readonly loading = signal(true);
  readonly errorKey = signal<string | null>(null);
  readonly group = signal<GroupPublic | null>(null);

  // 028-guest-stats-binding FR-001/FR-007: only a Guest holds a stored
  // guest_session_token for this exact group — a logged-in Member never
  // does, so the CTA never renders for them.
  //
  // Bug fix: presence of the stored token alone is NOT enough to decide
  // whether to show the CTA — binding never clears it (it's also used to
  // restore a Guest's session, and clearing it is a separate concern from
  // "am I bound"), so a stale token from an *already-bound* roster entry
  // would otherwise make the CTA reappear on the very next page load — most
  // reliably right after a successful OAuth bind, which always lands back
  // here via a fresh navigation/component instance, so `onBound()`'s local
  // `showBindingCta.set(false)` never gets a chance to run. Ask the server
  // for the actual status instead (same check GuestAccessComponent already
  // uses), and clear the stale token once we learn it's no longer needed.
  readonly guestSessionToken = this.groupJoin.getGuestSessionToken(this.groupId);
  readonly showBindingCta = signal(false);
  // Shown in place of the CTA once we know this browser's guest identity
  // here is bound — either detected on load (a stale stored token whose
  // entry the server reports as already_bound, e.g. right after an OAuth
  // redirect) or just now via onBound(). Replaces silently hiding the CTA
  // with an explicit "done" confirmation.
  readonly showBoundNotice = signal(false);

  constructor() {
    this.groupJoin.getGroupPublic(this.groupId).subscribe({
      next: (group) => {
        this.loading.set(false);
        this.group.set(group);
      },
      error: (error: ApiError) => {
        this.loading.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });

    const token = this.guestSessionToken;
    if (token !== null) {
      this.groupJoin.getGuestBindingStatus(token).subscribe({
        next: (status) => {
          if (status.already_bound) {
            this.groupJoin.clearGuestSessionToken(this.groupId);
            this.showBoundNotice.set(true);
          } else {
            this.showBindingCta.set(true);
          }
        },
        // An invalid/regenerated token isn't this component's problem to
        // surface — it just means there's no Guest identity to offer
        // binding for here.
        error: () => undefined,
      });
    }
  }

  setTab(tab: Tab): void {
    this.activeTab.set(tab);
  }

  onBound(): void {
    this.showBindingCta.set(false);
    this.showBoundNotice.set(true);
    this.groupJoin.clearGuestSessionToken(this.groupId);
  }
}
