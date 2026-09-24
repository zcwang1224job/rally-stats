import { Component, computed, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { LineChartComponent, LineChartPoint } from '../../../shared/line-chart/line-chart.component';
import { Section, SectionComponent, SectionContext } from '../../sport-type-module';

// 043 contracts/sections-manifest.md §3 `frames`.
interface FrameRow {
  frame_no: number;
  winner_team: 'A' | 'B';
  score_a: number | null;
  score_b: number | null;
  ended_by: 'target' | 'manual';
  elapsed_seconds: number | null;
}

interface TrendPoint {
  frame_no: number;
  frames_a: number;
  frames_b: number;
}

interface SummaryData {
  decider_record: { played: number; won: number };
  longest_match_frames: number;
}

/** `frames.frame_list`: one row per frame — who won, the in-frame score
 * when it was kept, and whether the frame ended at its target or by hand. */
@Component({
  selector: 'app-frames-frame-list-section',
  imports: [TranslatePipe],
  template: `
    <section class="card" data-section-kind="frames.frame_list">
      <h3 class="section-title">{{ (section().title_key ?? 'frames.sections.frameList') | translate }}</h3>
      @if (rows().length === 0) {
        <p class="empty-state">{{ 'sections.empty' | translate }}</p>
      } @else {
        <table class="frame-table">
          <thead>
            <tr>
              <th scope="col">{{ 'frames.sections.frameNo' | translate }}</th>
              <th scope="col">{{ 'frames.sections.winner' | translate }}</th>
              <th scope="col">{{ 'frames.sections.frameScore' | translate }}</th>
              <th scope="col">{{ 'frames.sections.endedBy' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            @for (row of rows(); track row.frame_no) {
              <tr>
                <td>{{ row.frame_no }}</td>
                <td>{{ 'sections.team' | translate: { team: row.winner_team } }}</td>
                <td>{{ row.score_a === null ? '—' : row.score_a + ' : ' + row.score_b }}</td>
                <td>{{ 'frames.sections.ended.' + row.ended_by | translate }}</td>
              </tr>
            }
          </tbody>
        </table>
      }
    </section>
  `,
  styles: `
    .section-title { margin: 0 0 0.75rem; font-size: 1rem; }
    .frame-table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
    .frame-table th, .frame-table td {
      padding: 0.35rem 0.25rem; border-bottom: 1px solid var(--color-border); text-align: left;
    }
  `,
})
export class FrameListSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();
  readonly rows = computed(
    () => ((this.section().data as { frames?: FrameRow[] } | null)?.frames ?? []) as FrameRow[],
  );
}

/** `frames.frame_trend`: team A's frame lead after each frame. */
@Component({
  selector: 'app-frames-frame-trend-section',
  imports: [TranslatePipe, LineChartComponent],
  template: `
    <section class="card" data-section-kind="frames.frame_trend">
      <h3 class="section-title">{{ (section().title_key ?? 'frames.sections.frameTrend') | translate }}</h3>
      @if (points().length === 0) {
        <p class="empty-state">{{ 'sections.empty' | translate }}</p>
      } @else {
        <app-line-chart
          [points]="points()"
          kind="number"
          [ariaLabel]="'frames.sections.frameTrend' | translate"
          [tableViewLabel]="'frames.sections.trendTable' | translate"
          [labelHeader]="'frames.sections.frameNo' | translate"
          [valueHeader]="'frames.sections.lead' | translate"
        />
      }
    </section>
  `,
  styles: `.section-title { margin: 0 0 0.75rem; font-size: 1rem; }`,
})
export class FrameTrendSectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();

  readonly points = computed<LineChartPoint[]>(() => {
    const data = this.section().data as { points?: TrendPoint[] } | null;
    return (data?.points ?? []).map((point) => ({
      label: String(point.frame_no),
      value: point.frames_a - point.frames_b,
      display: `${point.frames_a} : ${point.frames_b}`,
    }));
  });
}

/** `frames.dashboard_summary`: deciding-frame record and longest match. */
@Component({
  selector: 'app-frames-dashboard-summary-section',
  imports: [TranslatePipe],
  template: `
    <section class="card" data-section-kind="frames.dashboard_summary">
      <h3 class="section-title">{{ (section().title_key ?? 'frames.sections.summary') | translate }}</h3>
      @if (data(); as d) {
        <dl class="summary-list">
          <dt>{{ 'frames.sections.deciders' | translate }}</dt>
          <dd>
            {{ 'frames.sections.decidersValue' | translate: { won: d.decider_record.won, played: d.decider_record.played } }}
          </dd>
          <dt>{{ 'frames.sections.longest' | translate }}</dt>
          <dd>{{ 'frames.sections.longestValue' | translate: { n: d.longest_match_frames } }}</dd>
        </dl>
      }
    </section>
  `,
  styles: `
    .section-title { margin: 0 0 0.75rem; font-size: 1rem; }
    .summary-list { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1rem; margin: 0; }
    .summary-list dd { margin: 0; font-weight: 600; }
  `,
})
export class FramesDashboardSummarySectionComponent implements SectionComponent {
  readonly section = input.required<Section>();
  readonly context = input.required<SectionContext>();
  readonly data = computed(() => this.section().data as SummaryData | null);
}
