import { convertToParamMap } from '@angular/router';
import { ActivatedRoute } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, EMPTY } from 'rxjs';
import { signal } from '@angular/core';
import { ApiClient } from '../../core/api/api-client';
import { CourtControlService } from '../../core/api/court-control.service';
import { LinkHeartbeatService } from '../../core/api/link-heartbeat.service';
import { RealtimeService } from '../../core/realtime/ably.service';
import { ReconnectRefetchService } from '../../core/realtime/reconnect-refetch.service';
import { AuthService } from '../auth/auth.service';
import { ControlPanelComponent } from './control-panel.component';
import { AllCourtsControlPanelComponent } from './all-courts/all-courts-control-panel.component';
import { AllCourtsCourtBlockComponent } from './all-courts/all-courts-court-block.component';

const currentMatch = {
  match_id: 'm1',
  status: 'in_progress' as const,
  score_a: 3,
  score_b: 2,
  participants: [
    { roster_entry_id: 'p1', nickname: '小明', team: 'A' as const },
    { roster_entry_id: 'p2', nickname: '小美', team: 'B' as const },
  ],
};

const courtStateResponse = {
  court_id: 'c1',
  group_id: 'g1',
  name: '1號場',
  link_type: 'control_panel' as const,
  link_version: 0,
  deleted: false,
  group_disbanded: false,
  round_number: 3,
  current_match: currentMatch,
  waiting_reason: null,
  next_up: null,
};

function realtimeStub() {
  return { connectionState: signal('connected'), subscribe: () => EMPTY };
}

function reconnectStub() {
  return { onReconnect: () => EMPTY };
}

/** feature/control-panel-scoreboard-style: supersedes the old US2 FR-005
 * contract (each team's +1/-1 flanking its score inside `.team`) — the panel
 * now mirrors scoreboard.component's layout instead: the score sits centered
 * in each `.team-center` and the scoring buttons render in a single
 * `.scoring-controls` section below `.board-main` (the court), never inside
 * `.team` itself, so they can never draw on top of the court markings. */
describe('ControlPanelComponent score-board layout (scoreboard-style)', () => {
  it('renders the score centered in each team and the scoring buttons below the court', () => {
    TestBed.configureTestingModule({
      imports: [ControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
        },
        {
          provide: LinkHeartbeatService,
          useValue: {
            watchCourtLink: () =>
              of({
                court_id: 'c1',
                group_id: 'g1',
                name: '1號場',
                link_type: 'control_panel',
                link_version: 0,
                deleted: false,
                group_disbanded: false,
              }),
          },
        },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: CourtControlService,
          useValue: { getState: () => of(courtStateResponse) },
        },
        { provide: ApiClient, useValue: {} },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.querySelector('.buttons')).toBeNull();
    expect(teamB.querySelector('.buttons')).toBeNull();
    expect(teamA.querySelector('.team-center .score')).not.toBeNull();
    expect(teamB.querySelector('.team-center .score')).not.toBeNull();

    const scoringControls = fixture.nativeElement.querySelector('.scoring-controls');
    expect(scoringControls).not.toBeNull();
    expect(scoringControls.querySelectorAll('.buttons').length).toBe(2);

    const boardMain = fixture.nativeElement.querySelector('.board-main');
    // .scoring-controls must be a later sibling of .board-main (the court),
    // never nested inside it — DOCUMENT_POSITION_FOLLOWING (4) confirms it
    // comes after, not that it is contained within.
    expect(
      boardMain.compareDocumentPosition(scoringControls) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});

/** Teams face each other across the net, so each team's own right/left
 * service court sits on OPPOSITE physical sidelines (see
 * ScoreboardComponent.html's comment) — team A: left→top, right→bottom;
 * team B: right→top, left→bottom. This mapping must follow team IDENTITY,
 * not which screen half currently renders that team, since toggleSwap()
 * only moves a team sideways and never changes which direction it faces. */
describe('ControlPanelComponent mirrors each team\'s own left/right service court (station top/bottom)', () => {
  // toggleSwap() persists the preference per court (localStorage); start
  // every test here unswapped so no test depends on the order they run in.
  beforeEach(() => localStorage.clear());

  const doublesServe = {
    server_roster_entry_id: 'p1',
    server_team: 'A' as const,
    team_a_right_roster_entry_id: 'p1',
    team_a_left_roster_entry_id: 'p2',
    team_b_right_roster_entry_id: 'p3',
    team_b_left_roster_entry_id: 'p4',
  };

  function setupWithServe(p1Nickname = '陳甲', scoreSpy = vi.fn()) {
    TestBed.configureTestingModule({
      imports: [ControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
        },
        {
          provide: LinkHeartbeatService,
          useValue: {
            watchCourtLink: () =>
              of({
                court_id: 'c1',
                group_id: 'g1',
                name: '1號場',
                link_type: 'control_panel',
                link_version: 0,
                deleted: false,
                group_disbanded: false,
              }),
          },
        },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: CourtControlService,
          useValue: {
            getState: () =>
              of({
                ...courtStateResponse,
                current_match: {
                  match_id: 'm1',
                  status: 'in_progress' as const,
                  score_a: 5,
                  score_b: 7,
                  participants: [
                    { roster_entry_id: 'p1', nickname: p1Nickname, team: 'A' as const },
                    { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' as const },
                    { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' as const },
                    { roster_entry_id: 'p4', nickname: '李丁', team: 'B' as const },
                  ],
                  serve: doublesServe,
                },
              }),
            score: scoreSpy,
          },
        },
        { provide: ApiClient, useValue: {} },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('unswapped: team A top=left-court player, bottom=right-court player; team B mirrored', () => {
    const fixture = setupWithServe();

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.querySelector('.station--top').textContent).toContain('劉乙'); // team_a_left
    expect(teamA.querySelector('.station--bottom').textContent).toContain('陳甲'); // team_a_right
    expect(teamB.querySelector('.station--top').textContent).toContain('徐丙'); // team_b_right
    expect(teamB.querySelector('.station--bottom').textContent).toContain('李丁'); // team_b_left
  });

  it('swapped: the whole court turns around, so each team\'s right court changes slot', () => {
    const fixture = setupWithServe();
    fixture.componentInstance.toggleSwap();
    fixture.detectChanges();

    // Team B now plays from the left (right court at the bottom), team A
    // from the right (right court at the top).
    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamB.querySelector('.station--top').textContent).toContain('李丁'); // team_b_left
    expect(teamB.querySelector('.station--bottom').textContent).toContain('徐丙'); // team_b_right
    expect(teamA.querySelector('.station--top').textContent).toContain('陳甲'); // team_a_right
    expect(teamA.querySelector('.station--bottom').textContent).toContain('劉乙'); // team_a_left
  });

  it('truncates a long nickname to its first 2 characters, keeping the full name as the pill\'s aria-label', () => {
    const fixture = setupWithServe('陳大文豪');

    const station = fixture.nativeElement.querySelector('.team--a .station--bottom'); // team_a_right = p1
    expect(station.textContent).toContain('陳大');
    expect(station.textContent).not.toContain('陳大文豪');
    expect(station.getAttribute('aria-label')).toBe('陳大文豪');
  });

  it('updates the station display from the score response itself, without waiting on a realtime echo', () => {
    const scoreSpy = vi.fn().mockReturnValue(
      of({
        applied: true,
        match_id: 'm1',
        status: 'in_progress',
        score_a: 6,
        score_b: 7,
        winner_team: null,
        score_event_id: null,
        serve: {
          server_roster_entry_id: 'p2',
          server_team: 'A' as const,
          team_a_right_roster_entry_id: null,
          team_a_left_roster_entry_id: 'p2',
          team_b_right_roster_entry_id: 'p3',
          team_b_left_roster_entry_id: 'p4',
        },
      }),
    );
    const fixture = setupWithServe('陳甲', scoreSpy);

    // Before: team A's bottom station (team_a_right) shows 陳甲 (p1), per
    // the original doublesServe fixture.
    expect(fixture.nativeElement.querySelector('.team--a .station--bottom')).not.toBeNull();

    fixture.nativeElement.querySelector('.scoring-controls .buttons--left .btn:not(.btn--secondary)').click();
    fixture.detectChanges();

    // After: the response's new serve payload moves the server to 劉乙
    // (p2, now team_a_left) and drops team_a_right entirely (null) — this
    // must be visible immediately from the score() response, not only
    // after some later match.scoreUpdated realtime message.
    const teamA = fixture.nativeElement.querySelector('.team--a');
    expect(teamA.querySelector('.station--bottom')).toBeNull();
    expect(teamA.querySelector('.station--top').textContent).toContain('劉乙');
    expect(teamA.querySelector('.station--server').textContent).toContain('劉乙');
  });
});

/** SC-004: 僅持有控制板連結的使用者 0% 能在畫面上找到或觸發 Next Round
 * 相關操作（FR-014）——實際渲染單一場地/全部場地控制板（含比賽進行中
 * 的完整比分畫面，確保不是因為分支未渲染而漏檢），確認畫面文字中不
 * 含任何 Next Round 相關字樣。控制板元件本身仍會**被動訂閱** Ably 的
 * `match.nextRound` 事件以同步顯示新賽程表（FR-015）——這是合法的
 * 接收端行為，`RealtimeService.subscribe` 在此測試中被 stub 掉，不影響
 * 本測試的判斷範圍（畫面文字，而非訂閱行為本身）。 */
describe('Control panels never expose a Next Round entry point (SC-004)', () => {
  const forbidden = /next.?round/i;

  it('ControlPanelComponent renders no Next Round text', () => {
    TestBed.configureTestingModule({
      imports: [ControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
        },
        {
          provide: LinkHeartbeatService,
          useValue: {
            watchCourtLink: () =>
              of({
                court_id: 'c1',
                group_id: 'g1',
                name: '1號場',
                link_type: 'control_panel',
                link_version: 0,
                deleted: false,
                group_disbanded: false,
              }),
          },
        },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: CourtControlService,
          useValue: { getState: () => of(courtStateResponse) },
        },
        { provide: ApiClient, useValue: {} },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toMatch(forbidden);
  });

  it('AllCourtsCourtBlockComponent renders no Next Round text', () => {
    TestBed.configureTestingModule({
      imports: [AllCourtsCourtBlockComponent],
      providers: [
        provideTranslateService({}),
        { provide: RealtimeService, useFactory: realtimeStub },
        {
          provide: CourtControlService,
          useValue: { scoreAllCourts: () => of({}), endMatchAllCourts: () => of({}) },
        },
      ],
    });

    const fixture = TestBed.createComponent(AllCourtsCourtBlockComponent);
    fixture.componentRef.setInput('token', 'tok');
    fixture.componentRef.setInput('courtId', 'c1');
    fixture.componentRef.setInput('name', '1號場');
    fixture.componentRef.setInput('state', {
      court_id: 'c1',
      round_number: 3,
      current_match: currentMatch,
      waiting_reason: null,
      next_up: null,
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toMatch(forbidden);
  });

  it('AllCourtsControlPanelComponent renders no Next Round text', () => {
    TestBed.configureTestingModule({
      imports: [AllCourtsControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ allCourtsToken: 'tok' }) } },
        },
        {
          provide: LinkHeartbeatService,
          useValue: {
            watchAllCourtsLink: () =>
              of({
                group_id: 'g1',
                all_courts_link_version: 0,
                group_disbanded: false,
                courts: [{ court_id: 'c1', name: '1號場' }],
              }),
          },
        },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: CourtControlService,
          useValue: {
            getAllCourtsState: () =>
              of({
                group_id: 'g1',
                round_number: 3,
                courts: [
                  {
                    court_id: 'c1',
                    round_number: 3,
                    current_match: currentMatch,
                    waiting_reason: null,
                    next_up: null,
                  },
                ],
              }),
          },
        },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(AllCourtsControlPanelComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).not.toMatch(forbidden);
  });
});

/** 008-sport-minimalist-ui FR-002/SC-002: every interactive control on the
 * control panel MUST carry the shared `.btn` class, which guarantees a
 * touch target of at least `--touch-target-min` (44px, WCAG 2.5.5) — see
 * apps/web/src/styles/_base.scss. This asserts the class contract rather
 * than measuring pixels (jsdom doesn't run real layout). */
describe('ControlPanelComponent buttons carry the shared touch-target class (FR-002)', () => {
  it('every button in the score board and end-match action has class btn', () => {
    TestBed.configureTestingModule({
      imports: [ControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
        },
        {
          provide: LinkHeartbeatService,
          useValue: {
            watchCourtLink: () =>
              of({
                court_id: 'c1',
                group_id: 'g1',
                name: '1號場',
                link_type: 'control_panel',
                link_version: 0,
                deleted: false,
                group_disbanded: false,
              }),
          },
        },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: CourtControlService,
          useValue: { getState: () => of(courtStateResponse) },
        },
        { provide: ApiClient, useValue: {} },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();

    // Scoped to this component's own template — app-confirm-dialog's
    // internal confirm/cancel buttons are that component's own concern
    // (see T020, confirm-dialog.component.scss).
    const buttons: HTMLButtonElement[] = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('button'),
    ).filter((button) => !button.closest('app-confirm-dialog'));
    expect(buttons.length).toBeGreaterThan(0);
    for (const button of buttons) {
      expect(button.classList.contains('btn')).toBe(true);
    }
  });
});

/** feature/control-panel-scoreboard-style: ControlPanelComponent deliberately
 * opts out of 024-add-english-language FR-003a — the operator-facing single-
 * court panel dropped its language switcher (whatever language is already
 * active elsewhere on the origin, e.g. localStorage from another page,
 * still applies here; there's just no on-screen switcher to change it from
 * this route). AllCourtsControlPanelComponent still follows FR-003a
 * unchanged, since it wasn't part of this restyle. */
describe('ControlPanelComponent has no language switcher of its own', () => {
  it('does not render app-language-switcher even while still loading', () => {
    TestBed.configureTestingModule({
      imports: [ControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
        },
        { provide: LinkHeartbeatService, useValue: { watchCourtLink: () => EMPTY } },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        { provide: CourtControlService, useValue: { getState: () => EMPTY } },
        { provide: ApiClient, useValue: {} },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-language-switcher')).toBeNull();
  });
});

/** 024-add-english-language FR-003a: this route has no shared nav shell, so
 * it MUST carry its own switcher. */
describe('Nav-shell-less all-courts control panel carries its own language switcher (FR-003a)', () => {
  it('AllCourtsControlPanelComponent shows the language switcher even while still loading', () => {
    TestBed.configureTestingModule({
      imports: [AllCourtsControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ allCourtsToken: 'tok' }) } },
        },
        { provide: LinkHeartbeatService, useValue: { watchAllCourtsLink: () => EMPTY } },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        { provide: CourtControlService, useValue: { getAllCourtsState: () => EMPTY } },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });

    const fixture = TestBed.createComponent(AllCourtsControlPanelComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-language-switcher')).not.toBeNull();
  });
});

/** 035-point-ending-type: the picker's fourth optional detail rides the same
 * call as the other three — pinned here for the control panel (the
 * scoreboard has its own copy of this test; the all-courts block shares
 * the same shape via recordShotPlacementAllCourts). */
describe('ControlPanelComponent passes the ending type through (035)', () => {
  it('sends the picker\'s endingType as recordShotPlacement\'s last argument', () => {
    const scoreSpy = vi.fn().mockReturnValue(
      of({
        applied: true, match_id: 'm1', status: 'in_progress', score_a: 4, score_b: 2,
        winner_team: null, score_event_id: 'ev1',
      }),
    );
    const recordSpy = vi.fn().mockReturnValue(of({ recorded: true }));
    TestBed.configureTestingModule({
      imports: [ControlPanelComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ courtToken: 'tok' }) } },
        },
        {
          provide: LinkHeartbeatService,
          useValue: {
            watchCourtLink: () =>
              of({
                court_id: 'c1',
                group_id: 'g1',
                name: '1號場',
                link_type: 'control_panel',
                link_version: 0,
                deleted: false,
                group_disbanded: false,
              }),
          },
        },
        { provide: RealtimeService, useFactory: realtimeStub },
        { provide: ReconnectRefetchService, useFactory: reconnectStub },
        {
          provide: CourtControlService,
          useValue: {
            getState: () =>
              of({
                ...courtStateResponse,
                current_match: { ...currentMatch, detailed_scoring_enabled: true },
              }),
            score: scoreSpy,
            recordShotPlacement: recordSpy,
          },
        },
        { provide: ApiClient, useValue: {} },
        {
          provide: AuthService,
          useValue: {
            isLoggedIn: () => false,
            getSupportedLanguages: () => of({ languages: ['zh-TW', 'en'] }),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();

    fixture.nativeElement.querySelector('.buttons--left button').click();
    fixture.componentInstance.onShotPlacementConfirmed({
      rosterEntryId: null,
      losingRosterEntryId: null,
      landingX: null,
      landingY: null,
      endingType: 'net',
    });

    expect(scoreSpy).toHaveBeenCalledTimes(1);
    expect(recordSpy).toHaveBeenCalledWith('tok', 'm1', 'ev1', null, null, null, null, 'net');
  });
});
