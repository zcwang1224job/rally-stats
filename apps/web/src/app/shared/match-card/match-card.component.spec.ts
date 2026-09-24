import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import { MatchRecordSummary } from '../../core/api/group-member-view.models';
import { MatchCardComponent, MatchCardResult } from './match-card.component';

const MATCH: MatchRecordSummary = {
  match_id: 'm1',
  round_number: 1,
  team_a: [{ roster_entry_id: 'a', nickname: '阿明', team: 'A' }],
  team_b: [{ roster_entry_id: 'b', nickname: '小華', team: 'B' }],
  score_a: 3,
  score_b: 3,
  winner_team: 'D',
  started_at: '2026-09-24T10:00:00Z',
  ended_at: '2026-09-24T10:20:00Z',
};

@Component({
  imports: [MatchCardComponent],
  template: `<ul><li app-match-card [match]="match()" [result]="result()"></li></ul>`,
})
class HostComponent {
  readonly match = signal(MATCH);
  readonly result = signal<MatchCardResult>(null);
}

function render(result: MatchCardResult, match: MatchRecordSummary = MATCH): HTMLElement {
  TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  const fixture = TestBed.createComponent(HostComponent);
  fixture.componentInstance.result.set(result);
  fixture.componentInstance.match.set(match);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('MatchCardComponent (043 draws)', () => {
  it('a draw reads as a draw in words, whoever reads the card', () => {
    for (const result of ['loss', 'win', null] as const) {
      TestBed.resetTestingModule();
      const el = render(result);
      const badge = el.querySelector('[data-result="draw"]');
      expect(badge?.textContent).toContain('common.draw');
      expect(el.querySelector('li')?.classList.contains('match-card--loss')).toBe(false);
      expect(el.querySelector('li')?.classList.contains('match-card--win')).toBe(false);
    }
  });

  it('a decided match keeps its win / loss badge', () => {
    const el = render('loss', { ...MATCH, score_a: 3, score_b: 1, winner_team: 'A' });
    expect(el.querySelector('[data-result="draw"]')).toBeNull();
    expect(el.querySelector('li')?.classList.contains('match-card--loss')).toBe(true);
  });
});
