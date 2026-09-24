// 043 contracts/sections-manifest.md §2: data shapes of the generic section
// kinds, which every sport type may emit and no sport type module renders.

export type MetricKind = 'rate' | 'average' | 'ratio' | 'count';

export interface MetricGridItem {
  key: string;
  label_key: string;
  kind: MetricKind;
  value: number | null;
  numerator?: number | null;
  denominator?: number | null;
  better_when?: 'higher' | 'lower' | null;
  /** FR-027: the group's average for the same metric, and the gap to it. */
  group_average?: number | null;
  delta?: number | null;
}

export interface MetricGridData {
  metrics: MetricGridItem[];
}

export interface StatTableData {
  columns: { key: string; label_key: string }[];
  rows: Record<string, string | number | null>[];
}

export interface ScoreTimelineEvent {
  side: 'A' | 'B';
  delta: number;
  score_a: number;
  score_b: number;
  elapsed_seconds: number;
  kind?: string;
}

export interface ScoreTimelineData {
  target_score: number;
  cap_score: number | null;
  events: ScoreTimelineEvent[];
}

export interface TextNoteData {
  text_key: string;
  params?: Record<string, unknown>;
}

export function formatMetricValue(kind: MetricKind, value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (kind === 'rate') {
    return `${Math.round(value * 100)}%`;
  }
  if (kind === 'count') {
    return String(Math.round(value));
  }
  return (Math.round(value * 10) / 10).toString();
}
