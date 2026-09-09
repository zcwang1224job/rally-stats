import { Component, ElementRef, computed, input, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchRecordDetailResponse, ScoreEventSummary } from '../api/group-member-view.models';

interface ChartPoint {
  x: number;
  yA: number;
  yB: number;
}

/** 016-match-score-timeline (US1/US2/US3): 比賽詳情彈出視窗— 逐筆加減分
 * 紀錄 + 雙方比分趨勢圖。**純呈現元件，不注入任何 API service，不知道
 * 任何端點**（research.md #4，`/speckit-implement` 階段修訂）：資料的擷取
 * 完全交給呼叫端（三個既有清單元件），各自呼叫「自己頁面本來就已經在用」
 * 的 service 方法，再把結果餵進來——避免重蹈規劃階段「共用 service 靠
 * groupId 參數決定端點」導致的 I1 那類錯誤。 */
@Component({
  selector: 'app-match-record-detail-dialog',
  imports: [TranslatePipe],
  templateUrl: './match-record-detail-dialog.component.html',
  styleUrl: './match-record-detail-dialog.component.scss',
})
export class MatchRecordDetailDialogComponent {
  readonly detail = input<MatchRecordDetailResponse | null>(null);
  readonly loading = input(false);
  readonly loadError = input(false);

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  readonly teamANames = computed(() =>
    (this.detail()?.team_a ?? []).map((p) => p.nickname).join('、'),
  );
  readonly teamBNames = computed(() =>
    (this.detail()?.team_b ?? []).map((p) => p.nickname).join('、'),
  );

  /** research.md #3: chart x-axis is elapsed seconds since match start.
   * For a `"complete"` record, a synthetic (0, 0:0) origin point is
   * prepended — the match really did start there. For `"partial"`, that
   * origin is unknown and MUST NOT be fabricated (FR-006a), so the chart
   * starts at the first recorded event's already-elevated score. */
  readonly chartPoints = computed<ChartPoint[] | null>(() => {
    const d = this.detail();
    if (!d || d.events.length === 0) {
      return null;
    }
    const events: ScoreEventSummary[] =
      d.record_completeness === 'complete'
        ? [{ side: 'A', delta: 1, score_a: 0, score_b: 0, elapsed_seconds: 0 }, ...d.events]
        : d.events;
    const maxElapsed = Math.max(events[events.length - 1].elapsed_seconds, 1);
    const maxScore = Math.max(d.score_a, d.score_b, 1);
    return events.map((event) => ({
      x: (event.elapsed_seconds / maxElapsed) * 100,
      yA: 100 - (event.score_a / maxScore) * 100,
      yB: 100 - (event.score_b / maxScore) * 100,
    }));
  });

  readonly polylineA = computed(
    () => this.chartPoints()?.map((p) => `${p.x},${p.yA}`).join(' ') ?? '',
  );
  readonly polylineB = computed(
    () => this.chartPoints()?.map((p) => `${p.x},${p.yB}`).join(' ') ?? '',
  );

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
