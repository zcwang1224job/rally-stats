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

/** 010-app-wide-ui-redesign FR-005: score centered, each team's +1/-1
 * flanking it on the outside (team A's buttons before its score-block in DOM
 * order, team B's buttons after its score-block) — this is what makes both
 * scores land adjacent in the middle under a plain flex row. `.score-block`
 * groups the score with its own team's nickname(s) (added so the color
 * block can be matched to a player at a glance) — it's the unit that
 * flanks, in place of the bare `.score` this test originally checked. */
describe('ControlPanelComponent score-board button placement (US2 FR-005)', () => {
  it('team A renders buttons before the score-block; team B renders the score-block before its buttons', () => {
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
      ],
    });

    const fixture = TestBed.createComponent(ControlPanelComponent);
    fixture.detectChanges();

    const teamA = fixture.nativeElement.querySelector('.team--a');
    const teamB = fixture.nativeElement.querySelector('.team--b');
    expect(teamA.children[0].classList.contains('buttons')).toBe(true);
    expect(teamA.children[1].classList.contains('score-block')).toBe(true);
    expect(teamA.querySelector('.score-block .score')).not.toBeNull();
    expect(teamB.children[0].classList.contains('score-block')).toBe(true);
    expect(teamB.children[1].classList.contains('buttons')).toBe(true);
    expect(teamB.querySelector('.score-block .score')).not.toBeNull();
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
