import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import { RoundMatchesListComponent } from './round-matches-list.component';
import { RoundMatchesResponse, RoundMatchSummary } from './schedule.models';
import { ScheduleService } from './schedule.service';

function match(id: string, status: string): RoundMatchSummary {
  return {
    match_id: id,
    status,
    court_name: null,
    participants: [
      { roster_entry_id: `${id}-a`, nickname: `${id}A`, team: 'A' },
      { roster_entry_id: `${id}-b`, nickname: `${id}B`, team: 'B' },
    ],
    score_a: 0,
    score_b: 0,
    winner_team: null,
  };
}

function response(remaining: number, matches: RoundMatchSummary[]): RoundMatchesResponse {
  return {
    round_number: 1,
    matches,
    remaining_count: remaining,
    estimated_remaining_minutes: remaining > 0 ? remaining * 12 : null,
    sitting_out: [],
  };
}

describe('RoundMatchesListComponent', () => {
  function setup(responses: RoundMatchesResponse[]) {
    let calls = 0;
    TestBed.configureTestingModule({
      imports: [RoundMatchesListComponent],
      providers: [
        provideTranslateService({}),
        {
          provide: ScheduleService,
          useValue: {
            getRoundMatches: () => of(responses[Math.min(calls++, responses.length - 1)]),
          },
        },
      ],
    });
    const fixture = TestBed.createComponent(RoundMatchesListComponent);
    fixture.componentRef.setInput('groupId', 'g1');
    fixture.componentRef.setInput('roundPhase', 'in_progress');
    fixture.detectChanges();
    return { fixture, calls: () => calls };
  }

  it('reloads quietly when the parent refetches the schedule', () => {
    const { fixture, calls } = setup([
      response(2, [match('m1', 'in_progress'), match('m2', 'queued')]),
      response(1, [match('m1', 'completed'), match('m2', 'in_progress')]),
    ]);
    expect(calls()).toBe(1); // auto-expanded on becoming editable
    expect(fixture.componentInstance.remainingCount()).toBe(2);

    fixture.componentRef.setInput('refreshKey', 1);
    fixture.detectChanges();

    expect(calls()).toBe(2);
    expect(fixture.componentInstance.remainingCount()).toBe(1);
    expect(fixture.componentInstance.matches()[0].status).toBe('completed');
  });

  it('does not reload under the admin while they are picking a swap', () => {
    const { fixture, calls } = setup([
      response(2, [match('m1', 'queued'), match('m2', 'queued')]),
    ]);
    fixture.componentInstance.pick('m1', 'm1-a');

    fixture.componentRef.setInput('refreshKey', 1);
    fixture.detectChanges();

    expect(calls()).toBe(1);
    expect(fixture.componentInstance.firstPick()).toEqual({ matchId: 'm1', rosterEntryId: 'm1-a' });
  });

  it('does not fetch while collapsed', () => {
    const { fixture, calls } = setup([response(2, [match('m1', 'queued')])]);
    fixture.componentInstance.toggle(); // collapse

    fixture.componentRef.setInput('refreshKey', 1);
    fixture.detectChanges();

    expect(calls()).toBe(1);
  });
});
