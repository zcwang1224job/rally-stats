import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import {
  ComparisonMetric,
  MatchComparisonResponse,
} from '../../../../core/api/match-comparison.models';
import { FriendComparisonComponent } from './friend-comparison.component';

// No translations are loaded, so every string renders as its own i18n key.

function metric(overrides: Partial<ComparisonMetric>): ComparisonMetric {
  return {
    key: 'team_serve',
    kind: 'rate',
    better_when: 'higher',
    friend: { value: 0.512, numerator: 640, denominator: 1250, matches_used: 88 },
    me: { value: 0.487, numerator: 380, denominator: 780, matches_used: 52 },
    better: 'friend',
    ...overrides,
  };
}

function comparison(
  metrics: ComparisonMetric[],
  headToHead: MatchComparisonResponse['head_to_head'] = { as_opponents: null, as_partners: null },
): MatchComparisonResponse {
  return { friend_total_matches: 142, my_total_matches: 97, metrics, head_to_head: headToHead };
}

function setup(inputs: Record<string, unknown>): ComponentFixture<FriendComparisonComponent> {
  TestBed.configureTestingModule({
    imports: [FriendComparisonComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(FriendComparisonComponent);
  for (const [name, value] of Object.entries({ comparison: null, ...inputs })) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

function text(node: Element | null | undefined): string {
  return node?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('FriendComparisonComponent — side by side (US4)', () => {
  it('shows both values with the matches behind each', () => {
    const root: HTMLElement = setup({
      comparison: comparison([metric({})]),
      friendNickname: '小美',
    }).nativeElement;
    const row = root.querySelector('[data-metric="team_serve"]')!;

    expect(text(row.querySelector('.comparison__label'))).toBe('playerDashboard.metric.team_serve.label');
    expect(text(row.querySelector('[data-side="friend"] .comparison__value'))).toBe('51%');
    expect(text(row.querySelector('[data-side="me"] .comparison__value'))).toBe('49%');
    expect(text(row.querySelector('[data-side="friend"] .comparison__basis'))).toBe(
      'friendComparison.basedOn',
    );
    expect(text(root.querySelector('.comparison__row--head'))).toContain('小美');
  });

  it('marks the better side with a symbol and a word, on that side only (FR-006)', () => {
    const root: HTMLElement = setup({ comparison: comparison([metric({ better: 'me' })]) }).nativeElement;
    expect(text(root.querySelector('[data-side="me"] [data-better-mark]'))).toBe(
      '▲ friendComparison.better',
    );
    expect(root.querySelector('[data-side="friend"] [data-better-mark]')).toBeNull();
  });

  it('says level for a tie, and nothing at all when no verdict was given', () => {
    const tie: HTMLElement = setup({ comparison: comparison([metric({ better: 'tie' })]) }).nativeElement;
    expect(text(tie.querySelector('[data-tie-mark]'))).toBe('＝ friendComparison.tie');
    expect(tie.querySelector('[data-better-mark]')).toBeNull();

    TestBed.resetTestingModule();
    const none: HTMLElement = setup({ comparison: comparison([metric({ better: null })]) }).nativeElement;
    expect(none.querySelector('[data-better-mark]')).toBeNull();
    expect(none.querySelector('[data-tie-mark]')).toBeNull();
  });

  it('shows a dash for the side without data, and only the other side\'s basis', () => {
    const root: HTMLElement = setup({
      comparison: comparison([metric({ me: null, better: null })]),
    }).nativeElement;
    expect(text(root.querySelector('[data-side="me"] .comparison__value'))).toBe('—');
    expect(root.querySelector('[data-side="me"] .comparison__basis')).toBeNull();
    expect(root.querySelector('[data-side="friend"] .comparison__basis')).not.toBeNull();
  });

  it('writes an average with one decimal, like the metric cards', () => {
    const root: HTMLElement = setup({
      comparison: comparison([
        metric({
          key: 'avg_points_for',
          kind: 'average',
          friend: { value: 17.4, numerator: 87, denominator: 5, matches_used: 5 },
          me: { value: 21, numerator: 63, denominator: 3, matches_used: 3 },
          better: 'me',
        }),
      ]),
    }).nativeElement;
    expect(text(root.querySelector('[data-side="friend"] .comparison__value'))).toBe('17.4');
    expect(text(root.querySelector('[data-side="me"] .comparison__value'))).toBe('21.0');
  });
});

describe('FriendComparisonComponent — head to head', () => {
  it('shows both tallies from my side', () => {
    const root: HTMLElement = setup({
      comparison: comparison([], {
        as_opponents: { matches: 9, wins: 4, losses: 5, win_rate: 0.4444, avg_margin: -1.2 },
        as_partners: { matches: 3, wins: 3, losses: 0, win_rate: 1, avg_margin: 5 },
      }),
    }).nativeElement;
    expect(text(root.querySelector('[data-as-opponents]'))).toBe('friendComparison.headToHead.tally');
    expect(text(root.querySelector('[data-as-partners]'))).toBe('friendComparison.headToHead.tally');
  });

  it('says so in words where we never met (US4-3)', () => {
    const root: HTMLElement = setup({ comparison: comparison([]) }).nativeElement;
    expect(text(root.querySelector('[data-as-opponents]'))).toBe(
      'friendComparison.headToHead.neverOpponents',
    );
    expect(text(root.querySelector('[data-as-partners]'))).toBe(
      'friendComparison.headToHead.neverPartners',
    );
  });

  it('signs the margin with a real minus', () => {
    const component = setup({ comparison: comparison([]) }).componentInstance;
    expect(component.margin({ matches: 1, wins: 0, losses: 1, win_rate: 0, avg_margin: -6 })).toBe('−6.0');
    expect(component.margin({ matches: 1, wins: 1, losses: 0, win_rate: 1, avg_margin: 3.5 })).toBe('+3.5');
  });
});

describe('FriendComparisonComponent — loading and failure', () => {
  it('says it is working', () => {
    expect(text(setup({ loading: true }).nativeElement.querySelector('[data-loading]'))).toBe(
      'friendComparison.loading',
    );
  });

  it('keeps a failure to itself', () => {
    const root: HTMLElement = setup({ failed: true }).nativeElement;
    expect(text(root.querySelector('[data-failed]'))).toBe('friendComparison.failed');
    expect(root.querySelector('.comparison__rows')).toBeNull();
  });
});
