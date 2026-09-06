import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../core/api/api-error';
import { GroupPublic } from '../group-admin/group-admin.models';
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
  }

  setTab(tab: Tab): void {
    this.activeTab.set(tab);
  }
}
