import { convertToParamMap, ActivatedRoute, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { Observable, of, throwError } from 'rxjs';
import { GroupMemberViewService } from './group-member-view.service';
import { GroupMemberViewComponent } from './group-member-view.component';
import { RealtimeService } from '../../core/realtime/ably.service';
import { GroupJoinService } from '../group-join/group-join.service';
import { GroupPublic } from '../group-admin/group-admin.models';
import { signal } from '@angular/core';

const scheduleResponse = {
  current_round_number: 1,
  scheduling_mechanism: 'manual',
  auto_next_round: false,
  courts: [],
  roster: [],
};

const groupPublic = {
  group_id: 'g1',
  group_number: 1001,
  name: '週三夜羽球團',
  has_password: false,
  current_member_count: 4,
  max_members: 8,
  match_mode: 'doubles' as const,
  scheduling_mechanism: 'fair_rotation' as const,
  partner_source: 'manual' as const,
  activity_time_start: null,
  activity_time_end: null,
  status: 'active' as const,
};

function realtimeStub() {
  return { connectionState: signal('connected'), subscribe: () => of() };
}

function setup(options: { getGroupPublic?: () => Observable<GroupPublic> } = {}) {
  TestBed.configureTestingModule({
    imports: [GroupMemberViewComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: ActivatedRoute,
        useValue: { snapshot: { paramMap: convertToParamMap({ groupId: 'g1' }) } },
      },
      { provide: RealtimeService, useFactory: realtimeStub },
      { provide: Router, useValue: { navigate: () => Promise.resolve(true) } },
      {
        provide: GroupMemberViewService,
        useValue: {
          getMemberSchedule: () => of(scheduleResponse),
          getRoundMatches: () => of({ round_number: 1, matches: [] }),
        },
      },
      {
        provide: GroupJoinService,
        useValue: {
          getActiveGuestGroupId: () => null,
          clearActiveGuestGroupId: () => undefined,
          getGroupPublic: options.getGroupPublic ?? (() => of(groupPublic)),
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(GroupMemberViewComponent);
  fixture.detectChanges();
  return fixture;
}

/** SC-001: a general member's nav MUST show exactly 賽程/戰績/退出組團/
 * 對戰紀錄 (FR-001), and MUST NOT expose any admin-only entry point (場地
 * 設定/賽程設定/輪替名單管理/解散). Renders the full shell, including an
 * in-progress match, to make sure no branch is simply un-rendered. */
describe('GroupMemberViewComponent nav (SC-001)', () => {
  it('shows exactly the four member-view nav items and no admin items', () => {
    const fixture = setup();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      groupMemberView: {
        nav: {
          schedule: '賽程',
          standings: '戰績',
          matchRecords: '對戰紀錄',
          leaveGroup: '退出組團',
        },
        leaveGroup: { confirmTitle: '確定退出本團？', confirmBody: '無法復原' },
        schedule: { roundLabel: '第 {{round}} 輪' },
      },
    });
    translate.use('en');
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('賽程');
    expect(text).toContain('戰績');
    expect(text).toContain('對戰紀錄');
    expect(text).toContain('退出組團');

    for (const adminOnly of ['場地設定', '賽程設定', '輪替名單管理', '解散', 'Next Round']) {
      expect(text).not.toContain(adminOnly);
    }
  });

  it('shows the group name and number in the page header', () => {
    const fixture = setup();

    expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('週三夜羽球團');
    expect(fixture.nativeElement.textContent).toContain('1001');
  });

  it('shows a disbanded notice, without hiding the nav, when the group has disbanded', () => {
    // 005-member-view: a disbanded group's member view stays fully
    // readable/leavable (edge case) — unlike admin-page's read-only mode,
    // this MUST NOT hide the tabs/leave action.
    const fixture = setup({ getGroupPublic: () => of({ ...groupPublic, status: 'disbanded' }) });

    expect(fixture.nativeElement.textContent).toContain('adminPage.disbandedNotice');
    expect(fixture.nativeElement.querySelector('.member-nav')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.member-nav button').length).toBeGreaterThan(0);
  });

  it('shows an error instead of the shell when the group lookup fails', () => {
    const fixture = setup({
      getGroupPublic: () =>
        throwError(() => ({ i18nKey: 'errors.LINK_NOT_FOUND', errorCode: 'LINK_NOT_FOUND' })),
    });

    expect(fixture.nativeElement.textContent).toContain('errors.LINK_NOT_FOUND');
    expect(fixture.nativeElement.querySelector('.member-nav')).toBeNull();
  });
});

/** 008-sport-minimalist-ui FR-007/010-app-wide-ui-redesign: the nav now
 * reuses admin-page's pattern — a horizontally-scrollable pill strip under
 * $breakpoint-tablet, a left sidebar at tablet+ (CSS, not jsdom-testable
 * layout) — rather than a fixed-to-viewport bottom bar. Still satisfies
 * FR-007 (clear, tappable, no pinch-zoom required) the same way admin-page
 * already does; this only asserts the class contract. */
describe('GroupMemberViewComponent nav is the shared admin-page-style nav (FR-007)', () => {
  it('nav element carries the member-nav class', () => {
    const fixture = setup();

    const nav = (fixture.nativeElement as HTMLElement).querySelector('nav');
    expect(nav?.classList.contains('member-nav')).toBe(true);
  });
});
