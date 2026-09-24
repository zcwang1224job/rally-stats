import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';

import { LiveMatch, ScoringActions, ScoringResult } from '../../shells/scoring-actions';
import { FRAME_END, FRAME_POINT, FramesPadComponent, framesLiveState } from './frames-pad.component';

const BASE: LiveMatch = {
  match_id: 'm1',
  participants: [
    { roster_entry_id: 'a', nickname: '阿明', team: 'A' },
    { roster_entry_id: 'b', nickname: '小華', team: 'B' },
  ],
  score_a: 1,
  score_b: 0,
  target_score: 5,
};

function scored(a: number, b: number): LiveMatch {
  return {
    ...BASE,
    sport_state: {
      frame_no: 2,
      frame_score_a: a,
      frame_score_b: b,
      frames_to_win: 5,
      frame_scoring_enabled: true,
      frame_target: null,
    },
  };
}

function setup(match: LiveMatch, readOnly = false) {
  TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  const applyEvent = vi.fn(
    (): Observable<ScoringResult> =>
      of({ applied: true, match_id: 'm1', status: 'in_progress', score_a: 1, score_b: 0, winner_team: null }),
  );
  const actions = { applyEvent } as unknown as ScoringActions;
  const sent: Observable<ScoringResult>[] = [];
  const fixture = TestBed.createComponent(FramesPadComponent);
  fixture.componentRef.setInput('match', match);
  fixture.componentRef.setInput('actions', actions);
  fixture.componentRef.setInput('run', (action: Observable<ScoringResult>) => sent.push(action));
  fixture.componentRef.setInput('readOnly', readOnly);
  fixture.detectChanges();
  return { fixture, applyEvent, sent, el: fixture.nativeElement as HTMLElement };
}

function click(el: HTMLElement, action: string): void {
  (el.querySelector(`[data-action="${action}"]`) as HTMLButtonElement).click();
}

describe('FramesPadComponent', () => {
  it('derives the frame on from the score when the state is missing', () => {
    expect(framesLiveState(BASE)).toMatchObject({ frame_no: 2, frames_to_win: 5 });
  });

  it('without in-frame scores it only marks winners', () => {
    const { el, applyEvent } = setup(BASE);
    expect(el.querySelector('[data-testid="frame-score"]')).toBeNull();
    click(el, 'frame-win-B');
    expect(applyEvent).toHaveBeenCalledWith('m1', FRAME_END, { winner_team: 'B' });
  });

  it('in-frame points go out as frame_point events', () => {
    const { el, applyEvent } = setup(scored(3, 1));
    expect(el.querySelector('[data-testid="frame-score"]')?.textContent).toContain('3');
    click(el, 'frame-plus-A');
    click(el, 'frame-minus-B');
    expect(applyEvent).toHaveBeenCalledWith('m1', FRAME_POINT, { side: 'A', delta: 1 });
    expect(applyEvent).toHaveBeenCalledWith('m1', FRAME_POINT, { side: 'B', delta: -1 });
  });

  it('−1 is disabled at zero', () => {
    const { el } = setup(scored(0, 2));
    expect((el.querySelector('[data-action="frame-minus-A"]') as HTMLButtonElement).disabled).toBe(true);
  });

  it('marking the side that is behind asks first', () => {
    const { fixture, el, applyEvent } = setup(scored(1, 4));
    click(el, 'frame-win-A');
    expect(applyEvent).not.toHaveBeenCalled();
    expect(fixture.componentInstance.pendingWinner()).toBe('A');
    fixture.componentInstance.confirmBehindWinner();
    expect(applyEvent).toHaveBeenCalledWith('m1', FRAME_END, { winner_team: 'A' });
  });

  it('the scoreboard shows the frame but no buttons', () => {
    const { el } = setup(scored(2, 2), true);
    expect(el.querySelector('[data-testid="frame-status"]')).not.toBeNull();
    expect(el.querySelector('button')).toBeNull();
  });
});
