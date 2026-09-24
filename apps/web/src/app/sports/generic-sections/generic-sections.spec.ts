import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';

import { Section, SectionComponent } from '../sport-type-module';
import { MetricGridSectionComponent } from './metric-grid-section.component';
import { ScoreTimelineSectionComponent } from './score-timeline-section.component';
import { StatTableSectionComponent } from './stat-table-section.component';
import { TextNoteSectionComponent } from './text-note-section.component';
import { formatMetricValue } from './section-data';

function render(component: Type<SectionComponent>, section: Section): HTMLElement {
  const fixture = TestBed.createComponent(component);
  fixture.componentRef.setInput('section', section);
  fixture.componentRef.setInput('context', { typeKey: 'generic', source: null });
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('generic sections', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  });

  it('metric_grid shows each value, its fraction and the group average', () => {
    const el = render(MetricGridSectionComponent, {
      kind: 'metric_grid',
      title_key: null,
      data: {
        metrics: [
          { key: 'match_win_rate', label_key: 'l', kind: 'rate', value: 0.6, numerator: 3, denominator: 5, group_average: 0.5 },
          { key: 'draws', label_key: 'l', kind: 'count', value: null },
        ],
      },
    });
    const rate = el.querySelector('[data-metric="match_win_rate"]')?.textContent ?? '';
    expect(rate).toContain('60%');
    expect(rate).toContain('3 / 5');
    expect(rate).toContain('50%');
    expect(el.querySelector('[data-metric="draws"]')?.textContent).toContain('—');
  });

  it('stat_table renders one row per data row and an empty note otherwise', () => {
    const el = render(StatTableSectionComponent, {
      kind: 'stat_table',
      title_key: null,
      data: {
        columns: [{ key: 'name', label_key: 'n' }, { key: 'wins', label_key: 'w' }],
        rows: [{ name: '阿明', wins: 2 }, { name: '小華', wins: null }],
      },
    });
    const rows = el.querySelectorAll('tbody tr');
    expect(rows.length).toBe(2);
    expect(rows[1].textContent).toContain('—');

    const empty = render(StatTableSectionComponent, {
      kind: 'stat_table',
      title_key: null,
      data: { columns: [], rows: [] },
    });
    expect(empty.querySelector('.empty-state')).not.toBeNull();
  });

  it('score_timeline lists only point events, with +N deltas', () => {
    const el = render(ScoreTimelineSectionComponent, {
      kind: 'score_timeline',
      title_key: null,
      data: {
        target_score: 10,
        cap_score: null,
        events: [
          { side: 'A', delta: 2, score_a: 2, score_b: 0, elapsed_seconds: 65, kind: 'point' },
          { side: 'B', delta: 0, score_a: 2, score_b: 0, elapsed_seconds: 70, kind: 'frames.frame_point' },
          { side: 'B', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 90 },
        ],
      },
    });
    const rows = el.querySelectorAll('.score-timeline-section__row');
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('+2');
    expect(rows[0].textContent).toContain('1:05');
    expect(rows[1].textContent).toContain('2 : 1');
  });

  it('text_note shows its key', () => {
    const el = render(TextNoteSectionComponent, {
      kind: 'text_note',
      title_key: null,
      data: { text_key: 'playerDashboard.empty' },
    });
    expect(el.textContent).toContain('playerDashboard.empty');
  });

  it('formatMetricValue formats each kind', () => {
    expect(formatMetricValue('rate', 0.333)).toBe('33%');
    expect(formatMetricValue('average', 7.25)).toBe('7.3');
    expect(formatMetricValue('count', 4)).toBe('4');
    expect(formatMetricValue('ratio', null)).toBe('—');
  });
});
