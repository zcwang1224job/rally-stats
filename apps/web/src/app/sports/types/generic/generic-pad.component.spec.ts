import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { Observable, of } from 'rxjs';

import { LiveMatch, ScoringActions, ScoringResult } from '../../shells/scoring-actions';
import { GenericPadComponent } from './generic-pad.component';

const MATCH: LiveMatch = {
  match_id: 'm1',
  participants: [
    { roster_entry_id: 'a', nickname: '阿明', team: 'A' },
    { roster_entry_id: 'b', nickname: '小華', team: 'B' },
  ],
  score_a: 2,
  score_b: 2,
  end_mode: 'manual',
  allow_draw: true,
  score_steps: [1, 2, 3],
};

function setup(match: LiveMatch) {
  TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  const ok = (): Observable<ScoringResult> =>
    of({ applied: true, match_id: 'm1', status: 'in_progress', score_a: 0, score_b: 0, winner_team: null });
  const score = vi.fn(ok);
  const finish = vi.fn(ok);
  const actions = { score, finish } as unknown as ScoringActions;
  const fixture = TestBed.createComponent(GenericPadComponent);
  fixture.componentRef.setInput('match', match);
  fixture.componentRef.setInput('actions', actions);
  fixture.componentRef.setInput('run', (action: Observable<ScoringResult>) => action.subscribe());
  fixture.detectChanges();
  return { fixture, score, finish, el: fixture.nativeElement as HTMLElement };
}

describe('GenericPadComponent', () => {
  it('offers +N for every allowed step on both sides', () => {
    const { el, score } = setup(MATCH);
    const labels = [...el.querySelectorAll('[data-action^="plus-"]')].map((b) => b.textContent?.trim());
    expect(labels).toEqual(['+1', '+2', '+3', '+1', '+2', '+3']);
    (el.querySelector('[data-action="plus-3-B"]') as HTMLButtonElement).click();
    expect(score).toHaveBeenCalledWith('m1', 'B', 3);
  });

  it('manual end: "end and record" says what will be recorded', () => {
    const { fixture, finish } = setup(MATCH);
    expect(fixture.componentInstance.finishText().key).toBe('genericSport.finishBodyDraw');
    fixture.componentRef.setInput('match', { ...MATCH, score_a: 3 });
    expect(fixture.componentInstance.finishText()).toEqual({
      key: 'genericSport.finishBodyWin',
      params: { score: '3 : 2', team: '阿明' },
    });
    fixture.componentRef.setInput('match', { ...MATCH, allow_draw: false });
    fixture.detectChanges();
    expect(fixture.componentInstance.finishText().key).toBe('genericSport.finishBodyNoDraw');
    // Level with no draws: the button says why instead of offering a refusal.
    expect((fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-action="finish"]')?.disabled).toBe(true);
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-testid="no-draw-note"]')).not.toBeNull();
    fixture.componentRef.setInput('match', { ...MATCH, allow_draw: false, score_a: 3 });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-action="finish"]')?.disabled).toBe(false);
    fixture.componentInstance.finish();
    expect(finish).toHaveBeenCalledWith('m1');
  });

  it('target mode has no finish button', () => {
    const { el } = setup({ ...MATCH, end_mode: 'target', target_score: 10 });
    expect(el.querySelector('[data-action="finish"]')).toBeNull();
  });

  it('a group with no steps set still scores one at a time', () => {
    const { el } = setup({ ...MATCH, score_steps: undefined });
    expect(el.querySelectorAll('[data-action^="plus-"]').length).toBe(2);
  });
});
