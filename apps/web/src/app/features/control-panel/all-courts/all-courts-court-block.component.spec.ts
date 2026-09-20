import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { signal } from '@angular/core';
import { of, EMPTY } from 'rxjs';
import { CourtControlService } from '../../../core/api/court-control.service';
import { CourtLiveState } from '../../../core/api/court-live-state.models';
import { RealtimeService } from '../../../core/realtime/ably.service';
import { AllCourtsCourtBlockComponent } from './all-courts-court-block.component';

/** 039-match-point-confirm: this component had no spec file at all — nothing
 * in the all-courts folder did — so this covers the match-point branch it
 * gained, not the block's whole surface. */

const doublesServe = {
  server_roster_entry_id: 'p1',
  server_team: 'A' as const,
  team_a_right_roster_entry_id: 'p1',
  team_a_left_roster_entry_id: 'p2',
  team_b_right_roster_entry_id: 'p3',
  team_b_left_roster_entry_id: 'p4',
};

function stateAt(scoreA: number, scoreB: number, detailed = false): CourtLiveState {
  return {
    court_id: 'c1',
    round_number: 1,
    waiting_reason: null,
    next_up: null,
    current_match: {
      match_id: 'm1',
      status: 'in_progress',
      score_a: scoreA,
      score_b: scoreB,
      participants: [
        { roster_entry_id: 'p1', nickname: '陳甲', team: 'A' },
        { roster_entry_id: 'p2', nickname: '劉乙', team: 'A' },
        { roster_entry_id: 'p3', nickname: '徐丙', team: 'B' },
        { roster_entry_id: 'p4', nickname: '李丁', team: 'B' },
      ],
      serve: doublesServe,
      detailed_scoring_enabled: detailed,
      target_score: 21,
      cap_score: 30,
    },
  };
}

function setup(state: CourtLiveState, services: Record<string, unknown> = {}) {
  TestBed.configureTestingModule({
    imports: [AllCourtsCourtBlockComponent],
    providers: [
      provideTranslateService({}),
      {
        provide: RealtimeService,
        useValue: { connectionState: signal('connected'), subscribe: () => EMPTY },
      },
      {
        provide: CourtControlService,
        useValue: {
          scoreAllCourts: () =>
            of({
              applied: true,
              match_id: 'm1',
              status: 'in_progress',
              score_a: state.current_match!.score_a + 1,
              score_b: state.current_match!.score_b,
              winner_team: null,
              score_event_id: 'ev1',
              serve: doublesServe,
            }),
          endMatchAllCourts: () => of({}),
          recordShotPlacementAllCourts: () => of({ recorded: true }),
          undoMatchCompletionAllCourts: () => of({}),
          ...services,
        },
      },
    ],
  });
  const fixture = TestBed.createComponent(AllCourtsCourtBlockComponent);
  fixture.componentRef.setInput('token', 'tok');
  fixture.componentRef.setInput('courtId', 'c1');
  fixture.componentRef.setInput('name', '1號場');
  fixture.componentRef.setInput('state', state);
  fixture.detectChanges();
  return fixture;
}

describe('AllCourtsCourtBlockComponent match-point confirmation', () => {
  it('asks before the point that would end the match', () => {
    const scoreSpy = vi.fn().mockReturnValue(of({ applied: true, match_id: 'm1' }));
    const fixture = setup(stateAt(20, 15), { scoreAllCourts: scoreSpy });
    const openSpy = vi.spyOn(fixture.componentInstance.matchPointDialog()!, 'open');

    fixture.componentInstance.plusPressed('A');

    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(scoreSpy).not.toHaveBeenCalled();
  });

  it('scores once the scorer confirms', () => {
    const scoreSpy = vi.fn().mockReturnValue(of({ applied: true, match_id: 'm1' }));
    const fixture = setup(stateAt(20, 15), { scoreAllCourts: scoreSpy });

    fixture.componentInstance.plusPressed('A');
    fixture.componentInstance.onMatchPointConfirmed();

    expect(scoreSpy).toHaveBeenCalledWith('tok', 'c1', 'm1', 'A', 1);
  });

  it('DEUCE: 20-20 does not ask — 21-20 leads by one', () => {
    const scoreSpy = vi.fn().mockReturnValue(of({ applied: true, match_id: 'm1' }));
    const fixture = setup(stateAt(20, 20), { scoreAllCourts: scoreSpy });
    const openSpy = vi.spyOn(fixture.componentInstance.matchPointDialog()!, 'open');

    fixture.componentInstance.plusPressed('A');

    expect(openSpy).not.toHaveBeenCalled();
    expect(scoreSpy).toHaveBeenCalledWith('tok', 'c1', 'm1', 'A', 1);
  });
});
