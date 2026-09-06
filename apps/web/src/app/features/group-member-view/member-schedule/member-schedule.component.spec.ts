import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { RoundMatchesResponse } from '../../group-admin/schedule-management/schedule.models';
import { GroupMemberViewService } from '../group-member-view.service';
import { MemberScheduleComponent } from './member-schedule.component';

const scheduleResponse = {
  current_round_number: 1,
  scheduling_mechanism: 'manual' as const,
  auto_next_round: false,
  courts: [],
  roster: [],
};

const roundMatchesResponse: RoundMatchesResponse = {
  round_number: 1,
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

function setup(options: { getRoundMatches?: () => Observable<RoundMatchesResponse> } = {}) {
  TestBed.configureTestingModule({
    imports: [MemberScheduleComponent],
    providers: [
      provideTranslateService({}),
      { provide: RealtimeService, useValue: { connectionState: signal('connected'), subscribe: () => of() } },
      {
        provide: GroupMemberViewService,
        useValue: {
          getMemberSchedule: () => of(scheduleResponse),
          getRoundMatches: options.getRoundMatches ?? (() => of(roundMatchesResponse)),
        },
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
    const fixture = setup({ getRoundMatches: () => of({ round_number: 1, matches: [] }) });

    expect(fixture.nativeElement.textContent).toContain('scheduleManagement.noRoundMatchesYet');
  });
});
