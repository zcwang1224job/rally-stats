import { convertToParamMap, ActivatedRoute, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { Observable, of, throwError } from 'rxjs';
import { GroupMemberViewService } from './group-member-view.service';
import { GroupMemberViewComponent } from './group-member-view.component';
import { RealtimeService } from '../../core/realtime/ably.service';
import { GroupJoinService } from '../group-join/group-join.service';
import { GuestBindingCtaComponent } from '../group-join/guest-binding-cta/guest-binding-cta.component';
import { GroupPublic } from '../group-admin/group-admin.models';
import { AuthService } from '../auth/auth.service';
import { FriendsService } from '../friends/friends.service';
import { Component, input, signal } from '@angular/core';

/** The real GuestBindingCtaComponent injects AuthService (-> HttpClient,
 * unprovided here) — 028-guest-stats-binding: only used for the
 * guestSessionToken !== null test case below, its own behavior is covered
 * in guest-binding-cta.component.spec.ts. */
@Component({ selector: 'app-guest-binding-cta', template: '' })
class StubGuestBindingCtaComponent {
  readonly guestSessionToken = input.required<string>();
}

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
  created_by_member: false,
};

function realtimeStub() {
  return { connectionState: signal('connected'), subscribe: () => of() };
}

function setup(
  options: {
    getGroupPublic?: () => Observable<GroupPublic>;
    guestSessionToken?: string | null;
    /** Server-truth response for getGuestBindingStatus() — only consulted
     * when guestSessionToken is non-null. Defaults to "not yet bound" so
     * existing "CTA renders" tests keep their prior meaning. */
    bindingStatus?: () => Observable<{ already_bound: boolean; group_id: string }>;
  } = {},
) {
  const clearGuestSessionTokenCalls: unknown[] = [];
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
          // 028-guest-stats-binding: null means "not a Guest in this
          // group" — the binding CTA stays hidden, same as a logged-in
          // Member.
          getGuestSessionToken: () => options.guestSessionToken ?? null,
          getGuestBindingStatus:
            options.bindingStatus ?? (() => of({ already_bound: false, group_id: 'g1' })),
          clearGuestSessionToken: (...args: unknown[]) => {
            clearGuestSessionTokenCalls.push(args);
          },
        },
      },
      // 026-match-record-friend-invite: MemberScheduleComponent (this
      // shell's default child) now injects these too.
      { provide: AuthService, useValue: { getCachedMemberId: () => null } },
      { provide: FriendsService, useValue: { getInviteCandidatesStatus: () => of({ candidates: [] }) } },
    ],
  });
  TestBed.overrideComponent(GroupMemberViewComponent, {
    remove: { imports: [GuestBindingCtaComponent] },
    add: { imports: [StubGuestBindingCtaComponent] },
  });
  const fixture = TestBed.createComponent(GroupMemberViewComponent);
  fixture.detectChanges();
  return { fixture, clearGuestSessionTokenCalls };
}

/** SC-001: a general member's nav MUST show exactly 賽程/戰績/退出組團/
 * 對戰紀錄 (FR-001), and MUST NOT expose any admin-only entry point (場地
 * 設定/賽程設定/輪替名單管理/解散). Renders the full shell, including an
 * in-progress match, to make sure no branch is simply un-rendered. */
describe('GroupMemberViewComponent nav (SC-001)', () => {
  it('shows exactly the four member-view nav items and no admin items', () => {
    const { fixture } = setup();

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
    const { fixture } = setup();

    expect(fixture.nativeElement.querySelector('h1')?.textContent).toContain('週三夜羽球團');
    expect(fixture.nativeElement.textContent).toContain('1001');
  });

  it('shows a disbanded notice, without hiding the nav, when the group has disbanded', () => {
    // 005-member-view: a disbanded group's member view stays fully
    // readable/leavable (edge case) — unlike admin-page's read-only mode,
    // this MUST NOT hide the tabs/leave action.
    const { fixture } = setup({ getGroupPublic: () => of({ ...groupPublic, status: 'disbanded' }) });

    expect(fixture.nativeElement.textContent).toContain('adminPage.disbandedNotice');
    expect(fixture.nativeElement.querySelector('.member-nav')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.member-nav button').length).toBeGreaterThan(0);
  });

  it('shows an error instead of the shell when the group lookup fails', () => {
    const { fixture } = setup({
      getGroupPublic: () =>
        throwError(() => ({ i18nKey: 'errors.LINK_NOT_FOUND', errorCode: 'LINK_NOT_FOUND' })),
    });

    expect(fixture.nativeElement.textContent).toContain('errors.LINK_NOT_FOUND');
    expect(fixture.nativeElement.querySelector('.member-nav')).toBeNull();
  });
});

// --- 028-guest-stats-binding: inline binding CTA for a現役 Guest ---------

describe('GroupMemberViewComponent guest binding CTA', () => {
  it('renders the CTA when this browser holds a guest_session_token for this group', () => {
    const { fixture } = setup({ guestSessionToken: 'tok-123' });

    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).not.toBeNull();
  });

  it('does not render the CTA for a logged-in Member (no stored guest_session_token)', () => {
    const { fixture } = setup({ guestSessionToken: null });

    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).toBeNull();
  });

  it('hides the CTA once bound() fires, shows the "已完成綁定" badge instead, and clears the now-stale stored guest_session_token', () => {
    const { fixture, clearGuestSessionTokenCalls } = setup({ guestSessionToken: 'tok-123' });
    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).not.toBeNull();
    expect(fixture.nativeElement.textContent).not.toContain('guestBinding.boundBadge');

    fixture.componentInstance.onBound();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('guestBinding.boundBadge');
    expect(clearGuestSessionTokenCalls).toEqual([['g1']]);
  });

  // --- Bug fix: a stale token from an already-bound roster entry ----------
  // (most reliably reproduced by OAuth binding, whose redirect-back always
  // lands on a *fresh* instance of this component — onBound()'s local
  // showBindingCta.set(false) from a previous instance never gets a chance
  // to run, and the stored token alone can't tell "unbound" from "bound".)

  it('a stored token whose roster entry the server reports as already_bound does NOT render the CTA, and shows the "已完成綁定" badge instead', () => {
    const { fixture } = setup({
      guestSessionToken: 'tok-123',
      bindingStatus: () => of({ already_bound: true, group_id: 'g1' }),
    });

    expect(fixture.nativeElement.querySelector('app-guest-binding-cta')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('guestBinding.boundBadge');
  });

  it('an already-bound stored token gets cleared, so it cannot cause a second, doomed-to-fail bind attempt', () => {
    const { clearGuestSessionTokenCalls } = setup({
      guestSessionToken: 'tok-123',
      bindingStatus: () => of({ already_bound: true, group_id: 'g1' }),
    });

    expect(clearGuestSessionTokenCalls).toEqual([['g1']]);
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
    const { fixture } = setup();

    const nav = (fixture.nativeElement as HTMLElement).querySelector('nav');
    expect(nav?.classList.contains('member-nav')).toBe(true);
  });
});
