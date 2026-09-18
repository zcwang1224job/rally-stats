import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import {
  BenchmarkGroupOption,
  GroupBenchmarkMetric,
  GroupBenchmarkResponse,
} from '../../../../core/api/group-benchmark.models';
import { NO_INSIGHTS } from '../../../../core/player-dashboard/dashboard-fixtures';
import { GroupBenchmarkComponent } from './group-benchmark.component';

// No translations are loaded, so every string renders as its own i18n key.

const GROUPS: BenchmarkGroupOption[] = [
  { group_id: 'g1', group_number: 1, name: '週三羽球', status: 'active', member_status: 'active', my_completed_matches: 86 },
  { group_id: 'g2', group_number: 2, name: '老球友', status: 'disbanded', member_status: 'left', my_completed_matches: 12 },
];

function metric(overrides: Partial<GroupBenchmarkMetric>): GroupBenchmarkMetric {
  return {
    key: 'team_serve',
    kind: 'rate',
    better_when: 'higher',
    mine: { value: 0.531, numerator: 412, denominator: 776, matches_used: 61 },
    status: 'ok',
    group_average: 0.487,
    pool_size: 12,
    rank: 3,
    ...overrides,
  };
}

function benchmark(metrics: GroupBenchmarkMetric[]): GroupBenchmarkResponse {
  return {
    group: { group_id: 'g1', name: '週三羽球' },
    total_matches: 1000,
    my_matches: 86,
    metrics,
    insights: NO_INSIGHTS,
  };
}

function setup(inputs: Record<string, unknown>): ComponentFixture<GroupBenchmarkComponent> {
  TestBed.configureTestingModule({
    imports: [GroupBenchmarkComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(GroupBenchmarkComponent);
  for (const [name, value] of Object.entries({ groups: GROUPS, selectedGroupId: 'g1', ...inputs })) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

function text(node: Element | null | undefined): string {
  return node?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('GroupBenchmarkComponent — asks for nothing until it is opened', () => {
  it('is collapsed by default and announces the first opening', () => {
    const fixture = setup({ groups: null });
    const details = (fixture.nativeElement as HTMLElement).querySelector('details')!;
    let opened = 0;
    fixture.componentInstance.opened.subscribe(() => opened++);
    expect(details.open).toBe(false);

    details.open = true;
    details.dispatchEvent(new Event('toggle'));
    expect(opened).toBe(1);

    details.open = false;
    details.dispatchEvent(new Event('toggle'));
    expect(opened).toBe(1); // closing is not a request
  });

  it('says it is working while the groups, then the benchmark, load', () => {
    expect(text(setup({ groups: null }).nativeElement.querySelector('[data-loading]'))).toBe(
      'groupBenchmark.loading',
    );
    TestBed.resetTestingModule();
    expect(text(setup({ loading: true }).nativeElement.querySelector('[data-loading]'))).toBe(
      'groupBenchmark.loading',
    );
  });

  it('explains when there is no group to compare within (US3-10)', () => {
    const root: HTMLElement = setup({ groups: [] }).nativeElement;
    expect(text(root.querySelector('[data-no-groups]'))).toBe('groupBenchmark.noGroups');
    expect(root.querySelector('select')).toBeNull();
  });
});

describe('GroupBenchmarkComponent — choosing a group', () => {
  it('lists my groups with their state and emits the one chosen', () => {
    const fixture = setup({ benchmark: benchmark([metric({})]) });
    const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>('select')!;
    const chosen: string[] = [];
    fixture.componentInstance.groupChanged.subscribe((id) => chosen.push(id));

    expect(Array.from(select.options).map((option) => option.value)).toEqual(['g1', 'g2']);
    expect(text(select.options[1])).toContain('groupBenchmark.groupStatus.disbanded');
    expect(select.options[0].selected).toBe(true);

    select.value = 'g2';
    select.dispatchEvent(new Event('change'));
    expect(chosen).toEqual(['g2']);
  });
});

describe('GroupBenchmarkComponent — the four statuses', () => {
  it('ok: my value, the average with its pool, and my rank', () => {
    const root: HTMLElement = setup({ benchmark: benchmark([metric({})]) }).nativeElement;
    const row = root.querySelector('[data-metric="team_serve"]')!;
    expect(text(row.querySelector('.benchmark__label'))).toBe('playerDashboard.metric.team_serve.label');
    expect(text(row.querySelector('[data-mine]'))).toContain('53%');
    expect(text(row.querySelector('[data-average]'))).toContain('49%');
    expect(text(row.querySelector('[data-rank]'))).toBe('groupBenchmark.rank');
    expect(row.querySelector('[data-status-note]')).toBeNull();
  });

  it('pool_too_small: one explanation, no average and no rank', () => {
    const root: HTMLElement = setup({
      benchmark: benchmark([
        metric({ status: 'pool_too_small', group_average: null, rank: null, pool_size: 2 }),
      ]),
    }).nativeElement;
    const row = root.querySelector('[data-metric="team_serve"]')!;
    expect(text(row.querySelector('[data-status-note]'))).toBe('groupBenchmark.status.poolTooSmall');
    expect(row.querySelector('[data-average]')).toBeNull();
    expect(row.querySelector('[data-rank]')).toBeNull();
    expect(text(row.querySelector('[data-mine]'))).toContain('53%'); // my own number is still mine
  });

  it('self_below_minimum: the average, and why I am not ranked', () => {
    const root: HTMLElement = setup({
      benchmark: benchmark([metric({ status: 'self_below_minimum', rank: null })]),
    }).nativeElement;
    const row = root.querySelector('[data-metric="team_serve"]')!;
    expect(text(row.querySelector('[data-average]'))).toContain('49%');
    expect(text(row.querySelector('[data-status-note]'))).toBe('groupBenchmark.status.selfBelowMinimum');
  });

  it('no_direction: an average but never a rank', () => {
    const root: HTMLElement = setup({
      benchmark: benchmark([
        metric({
          key: 'match_points_saved',
          kind: 'average',
          better_when: null,
          status: 'no_direction',
          group_average: 0.41,
          rank: null,
          mine: { value: 0.6, numerator: 6, denominator: 10, matches_used: 10 },
        }),
      ]),
    }).nativeElement;
    const row = root.querySelector('[data-metric="match_points_saved"]')!;
    expect(text(row.querySelector('[data-average]'))).toContain('0.4');
    expect(text(row.querySelector('[data-status-note]'))).toBe('groupBenchmark.status.noDirection');
    expect(row.querySelector('[data-rank]')).toBeNull();
  });

  it('shows a dash for a metric I have no data for in this group', () => {
    const root: HTMLElement = setup({
      benchmark: benchmark([metric({ mine: null, status: 'self_below_minimum', rank: null })]),
    }).nativeElement;
    expect(text(root.querySelector('[data-mine]'))).toContain('—');
  });
});

describe('GroupBenchmarkComponent — scope and failure', () => {
  it('says in words that it ignores the page filters (FR-032)', () => {
    const root: HTMLElement = setup({ benchmark: benchmark([metric({})]) }).nativeElement;
    expect(text(root.querySelector('[data-scope]'))).toBe('groupBenchmark.scopeNote');
  });

  it('keeps a failure to itself', () => {
    const root: HTMLElement = setup({ failed: true }).nativeElement;
    expect(text(root.querySelector('[data-failed]'))).toBe('groupBenchmark.failed');
    expect(root.querySelector('select')).not.toBeNull(); // another group can still be tried
  });

  it('labels every cell for assistive technology, since the column heads are decorative', () => {
    const root: HTMLElement = setup({ benchmark: benchmark([metric({})]) }).nativeElement;
    expect(root.querySelector('.benchmark__row--head')!.getAttribute('aria-hidden')).toBe('true');
    expect(text(root.querySelector('[data-mine] .benchmark__cell-label'))).toBe(
      'groupBenchmark.columns.mine',
    );
    expect(text(root.querySelector('[data-average] .benchmark__cell-label'))).toBe(
      'groupBenchmark.columns.average',
    );
  });
});
