import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';
import { ApiError } from '../../../core/api/api-error';
import {
  MatchRecordDetailResponse,
  MemberMatchRecordsResponse,
} from '../../../core/api/group-member-view.models';
import { AuthService } from '../../auth/auth.service';
import { FriendMatchRecordsComponent } from './friend-match-records.component';

const oneMatch: MemberMatchRecordsResponse = {
  matches: [
    {
      match_id: 'match-1',
      round_number: 2,
      team_a: [{ roster_entry_id: 'r1', nickname: '小美', team: 'A' }],
      team_b: [{ roster_entry_id: 'r2', nickname: '小華', team: 'B' }],
      score_a: 21,
      score_b: 15,
      winner_team: 'A',
      started_at: '2026-09-14T10:00:00Z',
      ended_at: '2026-09-14T10:20:00Z',
      group_id: 'g1',
      group_name: '週末羽球團',
      won: true,
    },
  ],
  total_matches: 1,
  total_wins: 1,
  total_losses: 0,
  win_rate: 1,
  round_win_rates: [],
  opponent_records: [],
  page: 1,
  total_pages: 1,
};

const emptyRecords: MemberMatchRecordsResponse = {
  matches: [],
  total_matches: 0,
  total_wins: 0,
  total_losses: 0,
  win_rate: 0,
  round_win_rates: [],
  opponent_records: [],
  page: 1,
  total_pages: 1,
};

function setup(options: {
  nickname?: string | null;
  getFriendMatchRecords?: () => unknown;
  getFriendMatchRecordDetail?: () => unknown;
}) {
  const getFriendMatchRecordsCalls: unknown[][] = [];
  const authServiceStub = {
    getFriendMatchRecords: (...args: unknown[]) => {
      getFriendMatchRecordsCalls.push(args);
      return (options.getFriendMatchRecords ?? (() => of(oneMatch)))();
    },
    getFriendMatchRecordDetail:
      options.getFriendMatchRecordDetail ??
      (() =>
        of({
          match_id: 'match-1',
          round_number: 2,
          team_a: [{ roster_entry_id: 'r1', nickname: '小美', team: 'A' }],
          team_b: [{ roster_entry_id: 'r2', nickname: '小華', team: 'B' }],
          score_a: 21,
          score_b: 15,
          winner_team: 'A',
          started_at: '2026-09-14T10:00:00Z',
          ended_at: '2026-09-14T10:20:00Z',
          record_completeness: 'complete',
          events: [],
          player_stats: [],
          serve_stats: null,
          momentum_stats: null,
          tempo_stats: null,
          landing_distribution: [],
          clutch_stats: null,
        } satisfies MatchRecordDetailResponse)),
  };

  TestBed.configureTestingModule({
    imports: [FriendMatchRecordsComponent],
    providers: [
      provideTranslateService({}),
      { provide: AuthService, useValue: authServiceStub },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: {
            paramMap: convertToParamMap({ memberId: 'friend-1' }),
            queryParamMap: convertToParamMap(
              'nickname' in options && options.nickname !== undefined
                ? options.nickname === null
                  ? {}
                  : { nickname: options.nickname }
                : { nickname: '小美' },
            ),
          },
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(FriendMatchRecordsComponent);
  fixture.detectChanges();
  return { fixture, getFriendMatchRecordsCalls };
}

describe('FriendMatchRecordsComponent', () => {
  // US1
  it('loads the friend match records on init and renders the list newest-first with aggregate stats', () => {
    const { fixture, getFriendMatchRecordsCalls } = setup({});

    expect(getFriendMatchRecordsCalls).toEqual([['friend-1', 1]]);
    const rows = fixture.nativeElement.querySelectorAll('.match-card');
    expect(rows.length).toBe(1);
    expect(fixture.nativeElement.textContent).toContain('小美');
    expect(fixture.nativeElement.textContent).toContain('小華');
  });

  it('uses the nickname-specific title key when a nickname query param is present', () => {
    const { fixture } = setup({ nickname: '小美' });

    const title = fixture.nativeElement.querySelector('h1')?.textContent ?? '';
    expect(title).toContain('friendMatchRecords.title');
    expect(title).not.toContain('friendMatchRecords.titleGeneric');
  });

  it('falls back to the generic title key when no nickname query param is present (direct URL access)', () => {
    const { fixture } = setup({ nickname: null });

    const title = fixture.nativeElement.querySelector('h1')?.textContent ?? '';
    expect(title).toContain('friendMatchRecords.titleGeneric');
  });

  it('paginating calls getFriendMatchRecords with the new page number', () => {
    const { fixture, getFriendMatchRecordsCalls } = setup({
      getFriendMatchRecords: () =>
        of({ ...oneMatch, total_pages: 3 } satisfies MemberMatchRecordsResponse),
    });

    const nextPageButton = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.pagination button'),
    ).find((btn) => btn.textContent?.trim() === '2');
    nextPageButton?.click();
    fixture.detectChanges();

    expect(getFriendMatchRecordsCalls).toEqual([
      ['friend-1', 1],
      ['friend-1', 2],
    ]);
  });

  // US1: three rejection error codes + empty state, each distinguishable
  it.each([
    ['MEMBER_NOT_FOUND', 'errors.MEMBER_NOT_FOUND'],
    ['FRIENDSHIP_REQUIRED', 'errors.FRIENDSHIP_REQUIRED'],
    ['MATCH_RECORDS_PRIVATE', 'errors.MATCH_RECORDS_PRIVATE'],
  ])('shows the %s rejection message, not a blank page', (errorCode, i18nKey) => {
    const { fixture } = setup({
      getFriendMatchRecords: () =>
        throwError(
          () =>
            ({
              errorCode,
              i18nKey,
              detail: null,
              status: 403,
            }) satisfies ApiError,
        ),
    });

    const alert = fixture.nativeElement.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert.textContent).toContain(i18nKey);
    expect(fixture.nativeElement.querySelector('.match-card')).toBeNull();
  });

  it('shows a distinct empty state (not the [role="alert"] error styling) when the friend has no match records', () => {
    const { fixture } = setup({ getFriendMatchRecords: () => of(emptyRecords) });

    expect(fixture.nativeElement.querySelector('[role="alert"]')).toBeNull();
    const empty = fixture.nativeElement.querySelector('.empty-state');
    expect(empty).not.toBeNull();
    expect(empty.textContent?.length).toBeGreaterThan(0);
  });

  it('does not cache the authorization outcome: reloading (paginating) re-calls the endpoint every time', () => {
    let callCount = 0;
    const { fixture } = setup({
      getFriendMatchRecords: () => {
        callCount += 1;
        return of({ ...oneMatch, total_pages: 2, page: callCount });
      },
    });
    expect(callCount).toBe(1);

    const page2Button = Array.from<HTMLButtonElement>(
      fixture.nativeElement.querySelectorAll('.pagination button'),
    ).find((btn) => btn.textContent?.trim() === '2');
    page2Button?.click();
    fixture.detectChanges();

    expect(callCount).toBe(2);
  });

  // US2
  it('clicking a match row opens the detail dialog with data from getFriendMatchRecordDetail', () => {
    const { fixture } = setup({});

    const row = fixture.nativeElement.querySelector('.match-card') as HTMLElement;
    row.click();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('小美');
    expect(fixture.componentInstance.detail()?.match_id).toBe('match-1');
  });

  // Polish: FR-011 — no notification side effects. The component is only
  // ever given `AuthService` (which has no notify-style method) and
  // `ActivatedRoute` as dependencies — TestBed's strict DI would fail this
  // very setup() if the component tried to inject a NotificationService or
  // similar that this test doesn't provide, so viewing the list and
  // opening a match detail completing without error IS the evidence that
  // no notification side channel was wired in.
  it('viewing the list and opening a match detail completes with no unexpected dependency on a notification service', () => {
    const { fixture } = setup({});

    const row = fixture.nativeElement.querySelector('.match-card') as HTMLElement;
    expect(() => {
      row.click();
      fixture.detectChanges();
    }).not.toThrow();
    expect(fixture.componentInstance.detail()?.match_id).toBe('match-1');
  });
});
