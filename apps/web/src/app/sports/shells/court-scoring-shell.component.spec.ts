import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { EMPTY, of, throwError } from 'rxjs';

import { RealtimeService } from '../../core/realtime/ably.service';
import { CourtScoringShellComponent } from './court-scoring-shell.component';
import { LiveMatch, ScoringActions, ScoringResult } from './scoring-actions';

const MATCH: LiveMatch = {
  match_id: 'm1',
  participants: [
    { roster_entry_id: 'a', nickname: '阿明', team: 'A' },
    { roster_entry_id: 'b', nickname: '小華', team: 'B' },
  ],
  score_a: 1,
  score_b: 2,
  end_mode: 'manual',
  score_steps: [1],
};

function result(partial: Partial<ScoringResult>): ScoringResult {
  return {
    applied: true,
    match_id: 'm1',
    status: 'in_progress',
    score_a: 1,
    score_b: 2,
    winner_team: null,
    ...partial,
  };
}

function actions(overrides: Partial<ScoringActions> = {}): ScoringActions {
  return {
    score: () => of(result({})),
    applyEvent: () => of(result({})),
    undo: () => of(result({ score_b: 1 })),
    finish: () => of(result({ status: 'completed', winner_team: 'B' })),
    abandon: () => of(result({ status: 'abandoned' })),
    ...overrides,
  };
}

function setup(connected = 'connected', scoring: ScoringActions = actions(), readOnly = false) {
  TestBed.configureTestingModule({
    providers: [
      provideTranslateService({}),
      {
        provide: RealtimeService,
        useValue: { connectionState: signal(connected), subscribe: () => EMPTY },
      },
    ],
  });
  const fixture = TestBed.createComponent(CourtScoringShellComponent);
  fixture.componentRef.setInput('match', MATCH);
  fixture.componentRef.setInput('actions', scoring);
  fixture.componentRef.setInput('readOnly', readOnly);
  fixture.detectChanges();
  return fixture;
}

describe('CourtScoringShellComponent', () => {
  it('shows both teams and their match score', () => {
    const el = setup().nativeElement as HTMLElement;
    const scores = [...el.querySelectorAll('[data-testid="match-score"]')].map((s) => s.textContent);
    expect(scores).toEqual(['1', '2']);
    expect(el.textContent).toContain('阿明');
    expect(el.textContent).toContain('小華');
  });

  it('undo applies the returned score in place', () => {
    const fixture = setup();
    const el = fixture.nativeElement as HTMLElement;
    (el.querySelector('[data-action="undo"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    const scores = [...el.querySelectorAll('[data-testid="match-score"]')].map((s) => s.textContent);
    expect(scores).toEqual(['1', '1']);
  });

  it('a late echo of an earlier action does not override the newer result', () => {
    vi.useFakeTimers();
    try {
      const fixture = setup();
      fixture.componentInstance.undo(); // own result: 1 : 1
      // The echo of an action from before the undo arrives afterwards.
      fixture.componentRef.setInput('match', { ...MATCH, score_a: 1, score_b: 3 });
      fixture.detectChanges();
      const scores = () =>
        [...(fixture.nativeElement as HTMLElement).querySelectorAll('[data-testid="match-score"]')].map(
          (s) => s.textContent,
        );
      expect(scores()).toEqual(['1', '1']);
      // Once the echoes have had time to arrive, the page's state is the truth.
      vi.advanceTimersByTime(CourtScoringShellComponent.OWN_RESULT_GRACE_MS);
      fixture.detectChanges();
      expect(scores()).toEqual(['1', '3']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('a result that ends the match asks the page to reload', () => {
    const fixture = setup();
    let changed = 0;
    fixture.componentInstance.changed.subscribe(() => changed++);
    fixture.componentInstance.abandon();
    expect(changed).toBe(1);
  });

  it('shows the error of a refused action', () => {
    const fixture = setup(
      'connected',
      actions({
        undo: () => throwError(() => ({ i18nKey: 'errors.NOTHING_TO_UNDO' })),
      }),
    );
    fixture.componentInstance.undo();
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).querySelector('[role="alert"]')?.textContent).toContain(
      'errors.NOTHING_TO_UNDO',
    );
  });

  it('offline: buttons are disabled and actions are not sent', () => {
    const undo = vi.fn(() => of(result({})));
    const fixture = setup('disconnected', actions({ undo }));
    const button = (fixture.nativeElement as HTMLElement).querySelector(
      '[data-action="undo"]',
    ) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fixture.componentInstance.undo();
    expect(undo).not.toHaveBeenCalled();
  });

  it('a scoreboard has no action buttons', () => {
    const el = setup('connected', actions(), true).nativeElement as HTMLElement;
    expect(el.querySelector('[data-action="undo"]')).toBeNull();
    expect(el.querySelector('[data-action="abandon"]')).toBeNull();
  });
});
