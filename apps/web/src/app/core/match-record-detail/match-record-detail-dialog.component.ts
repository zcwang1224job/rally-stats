import { Component, ElementRef, computed, effect, input, signal, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchRecordDetailResponse, ShotPlacementDetail } from '../api/group-member-view.models';
import { CourtDiagramComponent } from '../court-diagram/court-diagram.component';
import { NicknameComponent } from '../nickname/nickname.component';
import { ShareCardContext } from '../match-share-card/share-card.models';
import { ShareCardDialogComponent } from '../match-share-card/share-card-dialog/share-card-dialog.component';
import { MatchDerivedStatsComponent } from './match-derived-stats/match-derived-stats.component';
import { ScoreTrendPoint, buildScoreTrendPoints } from './score-trend';

type ChartPoint = ScoreTrendPoint;

interface YAxisTick {
  value: number;
  /** Distance from the chart's TOP edge, as a % of its height — the same
   * orientation `yA`/`yB` use (0 = top = maxScore, 100 = bottom = 0). */
  percent: number;
}

/** dataviz skill, marks-and-anatomy.md: "Y-axis ticks: round to clean
 * numbers." A plain step-size picker (nice-numbers algorithm) — badminton
 * scores are always whole numbers, so the step itself is never fractional
 * (`Math.max(1, ...)` floors it before rounding to a power-of-ten residual).
 * Exported for direct unit testing without any DOM/component setup. */
export function niceAxisStep(maxValue: number, targetTicks = 4): number {
  const rawStep = Math.max(1, maxValue / targetTicks);
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const residual = rawStep / magnitude;
  const niceResidual = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  return niceResidual * magnitude;
}

/** Ticks from 0 up to (and stopping at or just before) `maxValue` — the
 * top of the actual data range never gets a forced, non-round tick of its
 * own; the final score is already shown above the chart (`basic-info`). */
export function computeYTicks(maxValue: number): YAxisTick[] {
  const step = niceAxisStep(maxValue);
  const ticks: YAxisTick[] = [];
  for (let value = 0; value <= maxValue + 1e-9; value += step) {
    ticks.push({ value: Math.round(value), percent: 100 - (value / maxValue) * 100 });
  }
  return ticks;
}

/** dataviz skill, interaction.md: "The crosshair finds the X... snaps to
 * the nearest data position." A pure array scan — no DOM/rect involved —
 * so hover behavior is testable independent of layout. */
export function nearestPointIndex(points: readonly { x: number }[], xPercent: number): number {
  let closest = 0;
  let closestDistance = Infinity;
  points.forEach((point, index) => {
    const distance = Math.abs(point.x - xPercent);
    if (distance < closestDistance) {
      closestDistance = distance;
      closest = index;
    }
  });
  return closest;
}

/** 016-match-score-timeline (US1/US2/US3): 比賽詳情彈出視窗— 逐筆加減分
 * 紀錄 + 雙方比分趨勢圖。**純呈現元件，不注入任何 API service，不知道
 * 任何端點**（research.md #4，`/speckit-implement` 階段修訂）：資料的擷取
 * 完全交給呼叫端（三個既有清單元件），各自呼叫「自己頁面本來就已經在用」
 * 的 service 方法，再把結果餵進來——避免重蹈規劃階段「共用 service 靠
 * groupId 參數決定端點」導致的 I1 那類錯誤。 */
@Component({
  selector: 'app-match-record-detail-dialog',
  imports: [
    TranslatePipe,
    NicknameComponent,
    CourtDiagramComponent,
    MatchDerivedStatsComponent,
    ShareCardDialogComponent,
  ],
  templateUrl: './match-record-detail-dialog.component.html',
  styleUrl: './match-record-detail-dialog.component.scss',
})
export class MatchRecordDetailDialogComponent {
  readonly detail = input<MatchRecordDetailResponse | null>(null);
  readonly loading = input(false);
  readonly loadError = input(false);
  /** 040-match-share-card: the group name and perspective only the caller
   * knows (which list the match was opened from). null = this caller
   * doesn't offer a share card, so no button. */
  readonly shareContext = input<ShareCardContext | null>(null);

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly plotArea = viewChild<ElementRef<HTMLElement>>('plotArea');

  readonly teamANames = computed(() =>
    (this.detail()?.team_a ?? []).map((p) => p.nickname).join('、'),
  );
  readonly teamBNames = computed(() =>
    (this.detail()?.team_b ?? []).map((p) => p.nickname).join('、'),
  );

  /** 032-match-record-scoring-stats research.md Decision 6: singles/doubles
   * derived from the existing participant counts, no separate field. */
  readonly isSinglesMatch = computed(() => {
    const d = this.detail();
    return !d || d.team_a.length + d.team_b.length <= 2;
  });

  /** The Y-axis's fixed ceiling — shared by `chartPoints()` (point placement)
   * and `yTicks()` (gridlines/labels) so the two can never disagree. */
  private readonly maxScore = computed(() => {
    const d = this.detail();
    return Math.max(d?.score_a ?? 0, d?.score_b ?? 0, 1);
  });

  /** research.md #3's point layout, now in `score-trend.ts` so the 040
   * share card draws the exact same shape (040 research.md Decision 4). */
  readonly chartPoints = computed<ChartPoint[] | null>(() => {
    const d = this.detail();
    return d ? buildScoreTrendPoints(d) : null;
  });

  readonly polylineA = computed(
    () => this.chartPoints()?.map((p) => `${p.x},${p.yA}`).join(' ') ?? '',
  );
  readonly polylineB = computed(
    () => this.chartPoints()?.map((p) => `${p.x},${p.yB}`).join(' ') ?? '',
  );

  /** dataviz skill, marks-and-anatomy.md: recessive horizontal gridlines +
   * axis labels, "round to clean numbers" — see `computeYTicks()`. */
  readonly yTicks = computed(() => computeYTicks(this.maxScore()));

  /** dataviz skill, interaction.md: "An HTML/SVG chart is interactive by
   * default." `null` = no hover/touch in progress. Reset alongside
   * `expandedEventIndex` whenever the detail changes (below) so a pointer
   * lingering from a previous match's chart can't show stale data. */
  readonly hoveredIndex = signal<number | null>(null);

  readonly hoveredPoint = computed<ChartPoint | null>(() => {
    const index = this.hoveredIndex();
    const points = this.chartPoints();
    return index !== null && points ? (points[index] ?? null) : null;
  });

  /** dataviz skill, marks-and-anatomy.md's ">= 8px (r >= 4)" marker floor is
   * sized for a point that's an actual read/reference target — exactly what
   * the HOVERED point is, paired with the readout above. A badminton match
   * can have 30-45 scoring events on one compact chart; drawing all of them
   * at that size would overplot the line into a solid bead-string (an
   * anti-pattern this method also guards against — see anti-patterns.md's
   * hover/hit-target guidance, which already separates "the painted mark"
   * from "the interactive treatment"). Resting points therefore stay small
   * (close to this chart's original r=2) and only the hovered one grows to
   * meet the spec's floor. */
  dotRadius(index: number): number {
    return this.hoveredIndex() === index ? 5 : 2.5;
  }

  /** Every value the readout/tooltip shows is also in the point-by-point
   * list right below the chart (interaction.md: "tooltips enhance, they
   * never gate") — so this hover layer only needs to work for pointer/touch;
   * it doesn't need its own parallel keyboard-navigation model. */
  onChartPointerMove(event: PointerEvent): void {
    const points = this.chartPoints();
    const area = this.plotArea()?.nativeElement;
    if (!points || points.length === 0 || !area) {
      return;
    }
    const rect = area.getBoundingClientRect();
    if (rect.width === 0) {
      return;
    }
    const xPercent = ((event.clientX - rect.left) / rect.width) * 100;
    this.hoveredIndex.set(nearestPointIndex(points, xPercent));
  }

  onChartPointerLeave(): void {
    this.hoveredIndex.set(null);
  }

  /** 032-match-record-scoring-stats (US2, Clarifications 2026-09-16): the
   * index within `detail().events` currently expanded to show its landing
   * info — `null` means none expanded. At most one at a time: toggleExpand()
   * collapses the clicked row if it's already the one open, otherwise
   * switches to it (collapsing whichever was open before). */
  readonly expandedEventIndex = signal<number | null>(null);

  private readonly resetExpandedOnDetailChange = effect(() => {
    this.detail();
    this.expandedEventIndex.set(null);
    this.hoveredIndex.set(null);
  });

  /** 035: a row is expandable when there is something to expand INTO —
   * a landing, or a recorded player (whose expansion says "landing not
   * recorded"). A row carrying only an ending type shows its label
   * inline and nothing else, so it gets no clickable affordance. */
  isExpandable(detail: ShotPlacementDetail | null): boolean {
    return (
      detail !== null &&
      (detail.landing_x !== null ||
        detail.scoring_roster_entry_id !== null ||
        detail.losing_roster_entry_id !== null)
    );
  }

  toggleExpand(index: number): void {
    this.expandedEventIndex.set(this.expandedEventIndex() === index ? null : index);
  }

  open(): void {
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.showModal === 'function') {
      nativeDialog.showModal();
    }
  }

  close(): void {
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.close === 'function') {
      nativeDialog.close();
    }
  }

  /** 開賽後經過時間，格式化為「開賽後 X 分 Y 秒」（research.md #3 之時間
   * 顯示格式決策）——分鐘/秒數以純數字回傳，實際文案組合交給模板的
   * i18n 模板字串，不在元件內寫死中文。 */
  elapsedParts(seconds: number): { minutes: number; seconds: number } {
    return { minutes: Math.floor(seconds / 60), seconds: seconds % 60 };
  }
}
