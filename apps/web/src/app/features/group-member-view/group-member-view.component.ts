import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { LeaveGroupComponent } from './leave-group/leave-group.component';
import { MatchRecordsComponent } from './match-records/match-records.component';
import { MemberScheduleComponent } from './member-schedule/member-schedule.component';
import { StandingsComponent } from './standings/standings.component';

type Tab = 'schedule' | 'standings' | 'match-records';

/** US1 (FR-001/002): the non-admin entry point for a group — nav shows
 * exactly 賽程/戰績/退出組團/對戰紀錄, never any admin-only action (場地
 * 設定/賽程設定/輪替名單管理/解散). Each nav item is either a read-only
 * tab (schedule/standings/match-records) or the leave-group action —
 * never a control that mutates schedule/score state. */
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

  readonly groupId = this.route.snapshot.paramMap.get('groupId')!;
  readonly activeTab = signal<Tab>('schedule');

  setTab(tab: Tab): void {
    this.activeTab.set(tab);
  }
}
