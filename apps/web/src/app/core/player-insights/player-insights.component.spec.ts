import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import en from '../../../assets/i18n/en.json';
import zhTW from '../../../assets/i18n/zh-TW.json';
import { DashboardInsights, INSIGHT_RULES } from '../api/player-dashboard.models';
import { insightFixture, insightsFixture, NO_INSIGHTS } from '../player-dashboard/dashboard-fixtures';
import { INSIGHT_VARIANTS, insightSentenceKey, percent, plain, points } from './insight-format';
import { PlayerInsightsComponent } from './player-insights.component';

// No translations are loaded, so every string renders as its own i18n key.

function setup(
  insights: DashboardInsights | null,
  inputs: Record<string, unknown> = {},
): ComponentFixture<PlayerInsightsComponent> {
  TestBed.configureTestingModule({
    imports: [PlayerInsightsComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(PlayerInsightsComponent);
  fixture.componentRef.setInput('insights', insights);
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

function texts(root: HTMLElement, selector: string): string[] {
  return Array.from(root.querySelectorAll(selector)).map(
    (node) => node.textContent?.replace(/\s+/g, ' ').trim() ?? '',
  );
}

function lookup(bundle: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) =>
        node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined,
      bundle,
    );
}

describe('PlayerInsightsComponent — lists (US1)', () => {
  it('renders nothing at all before there is anything to show', () => {
    expect(setup(null).nativeElement.querySelector('.insights')).toBeNull();
  });

  it('says it is working while the dashboard loads', () => {
    const root: HTMLElement = setup(null, { loading: true }).nativeElement;
    expect(texts(root, '[data-loading]')).toEqual(['playerInsights.loading']);
  });

  it('shows each list under its own heading, in the order it was given', () => {
    const root: HTMLElement = setup(
      insightsFixture({
        strengths: [
          insightFixture({ metric_key: 'own_serve', level: 'strong' }),
          insightFixture({ metric_key: 'endgame' }),
        ],
        weaknesses: [insightFixture({ list: 'weakness', metric_key: 'team_receive' })],
        recent: [
          insightFixture({
            list: 'recent',
            rule: 'recent_change',
            source: 'trend',
            metric_key: 'avg_loss_margin',
            params: { direction: 'improved', all_value: 6, recent_value: 2, kind: 'average' },
          }),
        ],
      }),
    ).nativeElement;

    expect(texts(root, '.insights__list-title')).toEqual([
      'playerInsights.list.strength',
      'playerInsights.list.weakness',
      'playerInsights.list.recent',
    ]);
    const strengths = root.querySelectorAll('[data-list="strength"] .insight');
    expect(Array.from(strengths).map((node) => node.getAttribute('data-level'))).toEqual([
      'strong',
      'mild',
    ]);
    expect(texts(root, '[data-list="weakness"] [data-sentence]')).toEqual([
      'playerInsights.rule.rate_vs_overall.weakness',
    ]);
    expect(texts(root, '[data-list="recent"] [data-evidence]')).toEqual([
      'playerInsights.evidence.recent',
    ]);
  });

  it('explains an empty list instead of hiding it (FR-018)', () => {
    const root: HTMLElement = setup(
      insightsFixture({ strengths: [insightFixture()] }),
    ).nativeElement;

    expect(texts(root, '[data-list="weakness"] [data-list-empty]')).toEqual([
      'playerInsights.listEmpty.weakness',
    ]);
    expect(texts(root, '[data-list="recent"] [data-list-empty]')).toEqual([
      'playerInsights.listEmpty.recent',
    ]);
  });

  it('only shows the matchup list once there is something in it', () => {
    const without: HTMLElement = setup(
      insightsFixture({ strengths: [insightFixture()] }),
    ).nativeElement;
    expect(without.querySelector('[data-list="matchup"]')).toBeNull();

    TestBed.resetTestingModule();
    const withOne: HTMLElement = setup(
      insightsFixture({
        matchups: [
          insightFixture({
            list: 'matchup',
            rule: 'partner_above_overall',
            source: 'matchup',
            metric_key: null,
            player: { key: 'm:1', nickname: '阿哲', member_id: '1' },
            params: { win_rate: 0.75, matches: 12, wins: 9, losses: 3, baseline: 0.5, diff: 0.25 },
          }),
        ],
      }),
    ).nativeElement;
    expect(texts(withOne, '[data-list="matchup"] [data-sentence]')).toEqual([
      'playerInsights.rule.partner_above_overall.matchup',
    ]);
  });

  it('replaces the lists with one explanation when there is nothing to say', () => {
    const insufficient: HTMLElement = setup(NO_INSIGHTS).nativeElement;
    expect(texts(insufficient, '[data-status-note]')).toEqual([
      'playerInsights.status.insufficientData',
    ]);
    expect(insufficient.querySelector('.insights__lists')).toBeNull();

    TestBed.resetTestingModule();
    const balanced: HTMLElement = setup({ ...NO_INSIGHTS, status: 'balanced' }).nativeElement;
    expect(texts(balanced, '[data-status-note]')).toEqual(['playerInsights.status.balanced']);
  });
});

describe('PlayerInsightsComponent — meaning never rides on colour alone (FR-006)', () => {
  it('gives every insight an icon and a word for its tone', () => {
    const root: HTMLElement = setup(
      insightsFixture({
        strengths: [insightFixture()],
        weaknesses: [insightFixture({ list: 'weakness' })],
        recent: [
          insightFixture({
            list: 'recent',
            rule: 'recent_change',
            params: { direction: 'declined', kind: 'rate' },
          }),
        ],
      }),
    ).nativeElement;

    expect(texts(root, '.insight__tone')).toEqual([
      '▲ playerInsights.tone.strength',
      '▼ playerInsights.tone.weakness',
      '▼ playerDashboard.verdict.declined',
    ]);
    expect(
      Array.from(root.querySelectorAll('.insight')).map((node) => node.getAttribute('data-tone')),
    ).toEqual(['strength', 'weakness', 'declined']);
  });
});

describe('PlayerInsightsComponent — every sentence leads somewhere (FR-010)', () => {
  it('emits the metric an insight is about', () => {
    const fixture = setup(insightsFixture({ strengths: [insightFixture({ metric_key: 'endgame' })] }));
    const picked: string[] = [];
    fixture.componentInstance.metricPicked.subscribe((key) => picked.push(key));

    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.insight')!.click();

    expect(picked).toEqual(['endgame']);
  });

  it('emits the player a matchup insight is about', () => {
    const fixture = setup(
      insightsFixture({
        matchups: [
          insightFixture({
            list: 'matchup',
            rule: 'opponent_below_overall',
            metric_key: null,
            player: { key: 'r:9', nickname: '阿強', member_id: null },
            params: { win_rate: 0.2, matches: 10, wins: 2, losses: 8, baseline: 0.5, diff: -0.3 },
          }),
        ],
      }),
    );
    const players: string[] = [];
    const metrics: string[] = [];
    fixture.componentInstance.playerPicked.subscribe((key) => players.push(key));
    fixture.componentInstance.metricPicked.subscribe((key) => metrics.push(key));

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[data-list="matchup"] .insight')!
      .click();

    expect(players).toEqual(['r:9']);
    expect(metrics).toEqual([]);
  });

  it('uses real buttons, so the keyboard can reach every sentence', () => {
    const root: HTMLElement = setup(insightsFixture({ strengths: [insightFixture()] })).nativeElement;
    const button = root.querySelector('.insight')!;
    expect(button.tagName).toBe('BUTTON');
    expect(button.getAttribute('type')).toBe('button');
  });
});

describe('PlayerInsightsComponent — the in-group source (US3)', () => {
  it('says so while the benchmark is still on its way', () => {
    const root: HTMLElement = setup(insightsFixture(), { pendingBenchmark: true }).nativeElement;
    expect(texts(root, '[data-benchmark-pending]')).toEqual(['playerInsights.benchmarkPending']);
  });

  it('says why the in-group sentences are missing under a filter (FR-034)', () => {
    const root: HTMLElement = setup(insightsFixture(), {
      benchmarkOmittedByFilters: true,
    }).nativeElement;
    expect(texts(root, '[data-benchmark-omitted]')).toEqual([
      'playerInsights.benchmarkOmittedByFilters',
    ]);
  });

  it('names the group whose comparison is included', () => {
    const root: HTMLElement = setup(
      insightsFixture({ benchmark_group_name: '週三羽球' }),
    ).nativeElement;
    expect(texts(root, '[data-benchmark-group]')).toEqual(['playerInsights.benchmarkIncluded']);
  });
});

describe('insight wording', () => {
  it('knows exactly the eight documented rules (data-model.md 規則表; backend: T009)', () => {
    expect([...INSIGHT_RULES]).toEqual([
      'rate_vs_overall',
      'deuce_vs_even',
      'error_share_high',
      'winner_share_high',
      'recent_change',
      'partner_above_overall',
      'opponent_below_overall',
      'benchmark_quartile',
    ]);
  });

  it('has a sentence for every variant of every rule, in both languages (FR-005)', () => {
    for (const rule of INSIGHT_RULES) {
      for (const variant of INSIGHT_VARIANTS[rule]) {
        const key = `playerInsights.rule.${rule}.${variant}`;
        expect(typeof lookup(zhTW, key), `zh-TW ${key}`).toBe('string');
        expect(typeof lookup(en, key), `en ${key}`).toBe('string');
      }
    }
  });

  it('picks the variant from what the backend sent, never from a comparison', () => {
    expect(insightSentenceKey(insightFixture({ list: 'weakness' }))).toBe(
      'playerInsights.rule.rate_vs_overall.weakness',
    );
    expect(
      insightSentenceKey(
        insightFixture({
          list: 'weakness',
          rule: 'error_share_high',
          params: { dominant_error: 'out', dominant_share: 0.6 },
        }),
      ),
    ).toBe('playerInsights.rule.error_share_high.weaknessDominant');
    expect(
      insightSentenceKey(
        insightFixture({
          list: 'weakness',
          rule: 'error_share_high',
          params: { dominant_error: null, dominant_share: null },
        }),
      ),
    ).toBe('playerInsights.rule.error_share_high.weakness');
    expect(
      insightSentenceKey(
        insightFixture({ list: 'recent', rule: 'recent_change', params: { direction: 'declined' } }),
      ),
    ).toBe('playerInsights.rule.recent_change.declined');
  });

  it('writes numbers the way the metric cards do', () => {
    expect(percent(0.5118)).toBe('51%');
    expect(percent(null)).toBe('—');
    expect(plain(6.3913)).toBe('6.4');
    expect(points(-0.1328)).toBe('13');
  });
});
