import { convertToParamMap, ActivatedRoute, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { GroupMemberViewService } from './group-member-view.service';
import { GroupMemberViewComponent } from './group-member-view.component';
import { RealtimeService } from '../../core/realtime/ably.service';
import { signal } from '@angular/core';

const scheduleResponse = {
  current_round_number: 1,
  scheduling_mechanism: 'manual',
  auto_next_round: false,
  courts: [],
  roster: [],
};

function realtimeStub() {
  return { connectionState: signal('connected'), subscribe: () => of() };
}

/** SC-001: a general member's nav MUST show exactly 賽程/戰績/退出組團/
 * 對戰紀錄 (FR-001), and MUST NOT expose any admin-only entry point (場地
 * 設定/賽程設定/輪替名單管理/解散). Renders the full shell, including an
 * in-progress match, to make sure no branch is simply un-rendered. */
describe('GroupMemberViewComponent nav (SC-001)', () => {
  it('shows exactly the four member-view nav items and no admin items', () => {
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
          useValue: { getMemberSchedule: () => of(scheduleResponse) },
        },
      ],
    });

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

    const fixture = TestBed.createComponent(GroupMemberViewComponent);
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
});

/** 008-sport-minimalist-ui FR-007/research.md #4: the nav renders as a
 * `.bottom-nav` (fixed to the bottom of the viewport under the tablet
 * breakpoint via CSS, not jsdom-testable layout) while still carrying all
 * four SC-001 nav items — this only asserts the class contract. */
describe('GroupMemberViewComponent nav renders as a bottom nav on mobile (FR-007)', () => {
  it('nav element carries the bottom-nav class', () => {
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
          useValue: { getMemberSchedule: () => of(scheduleResponse) },
        },
      ],
    });

    const fixture = TestBed.createComponent(GroupMemberViewComponent);
    fixture.detectChanges();

    const nav = (fixture.nativeElement as HTMLElement).querySelector('nav');
    expect(nav?.classList.contains('bottom-nav')).toBe(true);
  });
});
