import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { NEVER, Observable, Subject, of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import { InviteCandidatesResponse } from '../../../core/api/friend.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { AuthService } from '../../auth/auth.service';
import { FriendsService } from '../../friends/friends.service';
import {
  RestStateResponse,
  RoundMatchesResponse,
  ScheduleResponse,
} from '../../group-admin/schedule-management/schedule.models';
import { GroupMemberViewService } from '../group-member-view.service';
import { MemberScheduleComponent } from './member-schedule.component';

const scheduleResponse: ScheduleResponse = {
  current_round_number: 1,
  scheduling_mechanism: 'manual',
  match_mode: 'singles',
  auto_next_round: false,
  continuous_rotation: false,
  round_phase: null,
  courts: [
    {
      court_id: 'c1',
      name: '1號場',
      waiting_reason: null,
      next_up: null,
      current_match: {
        match_id: 'cm1',
        status: 'in_progress',
        score_a: 0,
        score_b: 0,
        participants: [
          { roster_entry_id: 'cp1', nickname: '會員自己', team: 'A' },
          { roster_entry_id: 'cp2', nickname: '對手', team: 'B' },
        ],
        serve: null,
      },
    },
  ],
  roster: [
    {
      roster_entry_id: 'cp1',
      nickname: '會員自己',
      status: 'active',
      wait_count: null,
      currently_playing: true,
      is_creator: true,
      is_guest: false,
      member_id: 'self-id',
    },
    {
      roster_entry_id: 'cp2',
      nickname: '對手',
      status: 'active',
      wait_count: null,
      currently_playing: true,
      is_creator: false,
      is_guest: false,
      member_id: 'm2',
    },
    {
      roster_entry_id: 'cp3',
      nickname: '訪客',
      status: 'active',
      wait_count: 0,
      currently_playing: false,
      is_creator: false,
      is_guest: true,
    },
  ],
};

const defaultCandidates: InviteCandidatesResponse = {
  candidates: [{ member_id: 'm2', friendship_status: 'none', invite_eligible: true }],
};

const roundMatchesResponse: RoundMatchesResponse = {
  round_number: 1,
  remaining_count: 0,
  estimated_remaining_minutes: null,
  sitting_out: [],
  matches: [
    {
      match_id: 'm1',
      status: 'completed',
      court_name: '1號場',
      participants: [
        { roster_entry_id: 'p1', nickname: '小明', team: 'A' },
        { roster_entry_id: 'p2', nickname: '小美', team: 'B' },
      ],
      score_a: 21,
      score_b: 10,
      winner_team: 'A',
    },
    {
      match_id: 'm2',
      status: 'queued',
      court_name: null,
      participants: [
        { roster_entry_id: 'p3', nickname: '小華', team: 'A' },
        { roster_entry_id: 'p4', nickname: '小強', team: 'B' },
      ],
      score_a: 0,
      score_b: 0,
      winner_team: null,
    },
  ],
};

function setup(
  options: {
    getRoundMatches?: () => Observable<RoundMatchesResponse>;
    schedule?: ScheduleResponse;
    candidates?: InviteCandidatesResponse;
    selfMemberId?: string | null;
    getMemberSchedule?: () => Observable<ScheduleResponse>;
    selfRosterEntryId?: string;
    setOwnRestState?: (groupId: string, id: string, resting: boolean) => Observable<RestStateResponse>;
    subscribe?: (channel: string, event: string) => Observable<unknown>;
  } = {},
) {
  TestBed.configureTestingModule({
    imports: [MemberScheduleComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: RealtimeService,
        useValue: { connectionState: signal('connected'), subscribe: options.subscribe ?? (() => of()) },
      },
      {
        provide: GroupMemberViewService,
        useValue: {
          getMemberSchedule: options.getMemberSchedule ?? (() => of(options.schedule ?? scheduleResponse)),
          getRoundMatches: options.getRoundMatches ?? (() => of(roundMatchesResponse)),
          resolveRosterEntryId: () => of(options.selfRosterEntryId ?? 'cp1'),
          setOwnRestState: options.setOwnRestState ?? (() => NEVER),
        },
      },
      {
        provide: AuthService,
        useValue: {
          getCachedMemberId: () => (options.selfMemberId === undefined ? 'self-id' : options.selfMemberId),
        },
      },
      {
        provide: FriendsService,
        useValue: { getInviteCandidatesStatus: () => of(options.candidates ?? defaultCandidates) },
      },
    ],
  });
  const fixture = TestBed.createComponent(MemberScheduleComponent);
  fixture.componentRef.setInput('groupId', 'g1');
  fixture.detectChanges();
  return fixture;
}

describe('MemberScheduleComponent full round-matches list', () => {
  it('shows every match of the current round, not just what is on court', () => {
    const fixture = setup();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('小明');
    expect(text).toContain('小美');
    expect(text).toContain('小華');
    expect(text).toContain('小強');
    expect(fixture.nativeElement.querySelectorAll('.round-matches-list li').length).toBe(2);
  });

  it('vsLabel joins each side\'s nicknames with " vs "', () => {
    const fixture = setup();

    expect(fixture.componentInstance.vsLabel(roundMatchesResponse.matches[0])).toBe('小明 vs 小美');
  });

  it('shows a placeholder message when the round has no matches yet', () => {
    const fixture = setup({ getRoundMatches: () => of({ round_number: 1, matches: [], remaining_count: 0, estimated_remaining_minutes: null, sitting_out: [] }) });

    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.noRoundMatchesYet');
  });
});

// 026-match-record-friend-invite (roster-list redesign)
describe('MemberScheduleComponent roster-list add-friend entries', () => {
  it('renders an add-friend entry for another member, not self or a Guest', () => {
    const fixture = setup();

    const buttons = fixture.nativeElement.querySelectorAll('.roster-list app-add-friend-button');
    expect(buttons.length).toBe(1);
  });

  it('renders every roster member (not just current-match participants)', () => {
    const fixture = setup();

    expect(fixture.nativeElement.querySelectorAll('.roster-list .friend-row').length).toBe(3);
  });

  it('renders nothing when the viewer has no member login (Guest/PIN-only)', () => {
    const fixture = setup({ selfMemberId: null });

    expect(fixture.nativeElement.querySelectorAll('.roster-list app-add-friend-button').length).toBe(0);
  });

  it('re-batches when the roster changes (e.g. a member joins)', () => {
    let requestedIds: string[] = [];
    const rosterChanged$ = new Subject<void>();

    const nextRosterSchedule: ScheduleResponse = {
      ...scheduleResponse,
      roster: [
        ...scheduleResponse.roster,
        {
          roster_entry_id: 'cp4',
          nickname: '新成員',
          status: 'active',
          wait_count: null,
          currently_playing: false,
          is_creator: false,
          is_guest: false,
          member_id: 'm3',
        },
      ],
    };
    let call = 0;
    const scheduleResponses = [scheduleResponse, nextRosterSchedule];

    TestBed.configureTestingModule({
      imports: [MemberScheduleComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: RealtimeService,
          useValue: {
            connectionState: signal('connected'),
            subscribe: (_channel: string, event: string) =>
              event === 'member.joined' ? rosterChanged$.asObservable() : of(),
          },
        },
        {
          provide: GroupMemberViewService,
          useValue: {
            getMemberSchedule: () => of(scheduleResponses[Math.min(call++, 1)]),
            getRoundMatches: () => of(roundMatchesResponse),
            resolveRosterEntryId: () => of('cp1'),
          },
        },
        { provide: AuthService, useValue: { getCachedMemberId: () => 'self-id' } },
        {
          provide: FriendsService,
          useValue: {
            getInviteCandidatesStatus: (ids: string[]) => {
              requestedIds = ids;
              return of({
                candidates: ids.map((id) => ({
                  member_id: id,
                  friendship_status: 'none' as const,
                  invite_eligible: true,
                })),
              });
            },
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(MemberScheduleComponent);
    fixture.componentRef.setInput('groupId', 'g1');
    fixture.detectChanges();
    expect(requestedIds).toEqual(['m2']);
    expect(fixture.nativeElement.textContent).not.toContain('新成員');

    rosterChanged$.next();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('新成員');
    expect(requestedIds.sort()).toEqual(['m2', 'm3']);
  });
});

// 037-rest-ready-toggle US1
describe('MemberScheduleComponent rest/ready', () => {
  function withRoster(overrides: Partial<ScheduleResponse['roster'][number]>[]): ScheduleResponse {
    return {
      ...scheduleResponse,
      roster: scheduleResponse.roster.map((row, i) => ({ ...row, ...(overrides[i] ?? {}) })),
    };
  }

  const restOk: RestStateResponse = {
    roster_entry_id: 'cp3',
    resting: true,
    resting_since: '2026-09-19T12:00:00Z',
    currently_playing: false,
    changed: true,
  };

  it('marks resting players on the roster, with text not just colour', () => {
    const fixture = setup({ schedule: withRoster([{}, {}, { resting: true }]) });

    const rows = fixture.nativeElement.querySelectorAll('.roster-list .friend-row');
    expect(rows[2].textContent).toContain('scheduleManagement.restingBadge');
    expect(rows[0].textContent).not.toContain('scheduleManagement.restingBadge');
  });

  it('shows one rest button, for the viewer themself', () => {
    const fixture = setup({ selfRosterEntryId: 'cp3' });

    const buttons = fixture.nativeElement.querySelectorAll('app-rest-toggle-button');
    expect(buttons.length).toBe(1);
    expect(buttons[0].textContent).toContain('restToggle.rest');
  });

  it('shows no rest button until it knows who the viewer is', () => {
    const fixture = setup({ selfRosterEntryId: 'not-on-the-roster' });

    expect(fixture.nativeElement.querySelector('app-rest-toggle-button')).toBeNull();
  });

  it('offers "ready" to a resting viewer, and tells a playing one when the break starts', () => {
    const fixture = setup({
      schedule: withRoster([{ resting: true }]),
      selfRosterEntryId: 'cp1',
    });

    const text = fixture.nativeElement.querySelector('app-rest-toggle-button').textContent;
    expect(text).toContain('restToggle.ready');
    expect(text).toContain('restToggle.afterThisMatch');
  });

  it('sends the target state and reloads from the server on success', () => {
    const sent: [string, string, boolean][] = [];
    let loads = 0;
    const fixture = setup({
      selfRosterEntryId: 'cp3',
      getMemberSchedule: () => {
        loads += 1;
        return of(scheduleResponse);
      },
      setOwnRestState: (groupId, id, resting) => {
        sent.push([groupId, id, resting]);
        return of(restOk);
      },
    });
    const before = loads;

    fixture.nativeElement.querySelector('app-rest-toggle-button button').click();

    expect(sent).toEqual([['g1', 'cp3', true]]);
    expect(loads).toBe(before + 1);
    expect(fixture.componentInstance.restPending()).toBe(false);
  });

  it('keeps the old state and shows the error when the request fails', () => {
    const error: ApiError = {
      errorCode: 'ROSTER_ENTRY_NOT_FOUND',
      i18nKey: 'errors.ROSTER_ENTRY_NOT_FOUND',
      detail: null,
      status: 404,
    };
    const fixture = setup({
      selfRosterEntryId: 'cp3',
      setOwnRestState: () => throwError(() => error),
    });

    fixture.nativeElement.querySelector('app-rest-toggle-button button').click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.self-rest [role="alert"]').textContent).toContain(
      'errors.ROSTER_ENTRY_NOT_FOUND',
    );
    expect(fixture.nativeElement.querySelector('app-rest-toggle-button').textContent).toContain(
      'restToggle.rest',
    );
    expect(fixture.componentInstance.restPending()).toBe(false);
  });

  it('refetches when someone rests or comes back', () => {
    const restChanged$ = new Subject<void>();
    let loads = 0;
    setup({
      getMemberSchedule: () => {
        loads += 1;
        return of(scheduleResponse);
      },
      subscribe: (_channel, event) => (event === 'roster.restChanged' ? restChanged$ : of()),
    });
    const before = loads;

    restChanged$.next();

    expect(loads).toBe(before + 1);
  });
});
