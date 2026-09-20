import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { IconComponent } from '../../../shared/icon/icon.component';
import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { TranslatePipe } from '@ngx-translate/core';
import { ApiError } from '../../../core/api/api-error';
import {
  ParticipantSummary,
  RoundPhase,
  RosterScheduleStatus,
  RoundMatchesResponse,
  RoundMatchSummary,
  Team,
  WaitingOnRest,
} from './schedule.models';
import { ScheduleService } from './schedule.service';

/** 011-round-robin-scheduling: 本輪賽程清單——讓管理員能看到整份預先排好
 * 的循環賽賽程（queued/in_progress/completed/abandoned 全部列出），而不
 * 只是每個場地目前這一場。預設收合，展開時才拉取資料，避免大團（賽程可能
 * 高達數十甚至數百場）在未開啟此區塊時也持續輪詢一份大清單。
 *
 * 018-plan-then-start: `roundPhase` 為 'awaiting_start' 或 'in_progress'
 * （即已規劃或已開打）時，改為自動展開；每一場「尚未結束」（queued/
 * in_progress）的比賽都能調整參賽選手，已完成/已捨棄的比賽維持唯讀。
 * 提供兩種調整方式：點兩位不同場次的選手互換場次
 * （`pick`/`swapPlannedMatchPlayers`），或直接把某位選手換成指定的另一人
 * （`changeTo`/`changeMatchPlayer`）——前者是「跟誰換」，後者是「換成
 * 誰」，各自對應不同情境（互相調度 vs. 找候補）。拖曳可調整叫號順序
 * （`onDrop`/`reorderPlannedMatches`）——後續需求：即使賽程已經開打
 * （'in_progress'），只要某場比賽還「排隊中」（`isReorderable`）就還能
 * 拖曳調整，已經上場或打完的比賽維持原位不能拖。
 *
 * `errorKey`（載入失敗）與 `actionErrorKey`（互換/變更/排序失敗）刻意分開
 * ——模板只在 `errorKey` 有值時才會整個隱藏清單內容，若跟動作錯誤共用同一
 * 個signal，一次失敗的互換操作就會讓已經載入好的賽程整個消失。`saving`
 * 在請求進行中停用互動控制項（避免快速連點送出互相衝突的調整），
 * `actionSuccess` 是動作成功後的短暫確認提示——否則互換/變更成功時唯一
 * 的回饋只是名字悄悄換掉，很容易被忽略。 */
@Component({
  selector: 'app-round-matches-list',
  imports: [TranslatePipe, DragDropModule, IconComponent],
  templateUrl: './round-matches-list.component.html',
  styleUrl: './round-matches-list.component.scss',
})
export class RoundMatchesListComponent {
  readonly groupId = input.required<string>();
  readonly roundPhase = input<RoundPhase | null>(null);
  readonly roster = input<RosterScheduleStatus[]>([]);
  /** 父層每重新讀取一次賽程就加一；清單展開時跟著安靜地重新載入。以前清單
   * 只在展開或按「重新整理」時才載入，比賽打完、換下一場、有人加入後，
   * 剩餘場數與比分都停在舊資料。 */
  readonly refreshKey = input(0);

  editable(): boolean {
    const phase = this.roundPhase();
    return phase === 'awaiting_start' || phase === 'in_progress';
  }

  private readonly scheduleService = inject(ScheduleService);

  readonly expanded = signal(false);
  readonly loading = signal(false);
  readonly errorKey = signal<string | null>(null);
  readonly actionErrorKey = signal<string | null>(null);
  readonly roundNumber = signal<number | null>(null);
  readonly matches = signal<RoundMatchSummary[]>([]);
  readonly firstPick = signal<{ matchId: string; rosterEntryId: string } | null>(null);
  // 018-plan-then-start UX polish: `saving` disables the pick/change/drag
  // controls while a request is in flight (prevents a fast double-click
  // from firing two conflicting adjustments); `actionSuccess` is a brief
  // confirmation flash after one lands, same pattern as AdminPageComponent's
  // `saveSuccess`/`copiedPin` — otherwise a swap/change/reorder's only
  // feedback is the names quietly changing, easy to miss.
  readonly saving = signal(false);
  readonly actionSuccess = signal(false);

  // 本輪進度摘要：還剩幾場、預估多久打完、誰這輪沒有排到。循環賽一輪可能
  // 有數十場，沒有這些資訊時管理員看不出這一輪還要打多久。
  readonly remainingCount = signal(0);
  readonly estimatedRemainingMinutes = signal<number | null>(null);
  readonly sittingOutNames = signal<string | null>(null);

  /** 037-rest-ready-toggle FR-021: queued matches waiting on resting
   * players. `stalled` = the round can't go on without them. */
  readonly waitingOnRest = signal<WaitingOnRest | null>(null);
  readonly waitingOnRestNames = computed(
    () => this.waitingOnRest()?.players.map((p) => p.nickname).join(', ') ?? '',
  );
  /** Whether the group auto-advances: a stalled round then moves on by
   * itself, so the "mark them ready or end the round" hint is only for
   * groups where the admin has to act. */
  readonly autoNextRound = input(false);

  private applyResponse(response: RoundMatchesResponse): void {
    this.roundNumber.set(response.round_number);
    this.matches.set(response.matches);
    this.remainingCount.set(response.remaining_count);
    this.estimatedRemainingMinutes.set(response.estimated_remaining_minutes);
    const names = response.sitting_out.map((entry) => entry.nickname);
    this.sittingOutNames.set(names.length > 0 ? names.join(', ') : null);
    this.waitingOnRest.set(response.waiting_on_rest ?? null);
  }

  restEffectKey(match: RoundMatchSummary): string | null {
    switch (match.rest_effect) {
      case 'held':
        return 'restToggle.effectHeld';
      case 'substitute':
        return 'restToggle.effectSubstitute';
      default:
        return null;
    }
  }

  private flashSuccess(): void {
    this.actionSuccess.set(true);
    setTimeout(() => this.actionSuccess.set(false), 2000);
  }

  // 舒適排版需求: 清單一律可以手動收合（`toggle()`），所以自動展開只能在
  // 「剛變成可編輯」那一次觸發——如果每次 `roundPhase` 訊號變動（例如
  // awaiting_start -> in_progress）都重新展開，管理員手動收合後一遇到
  // 賽程狀態變化就會被強制打開，形同收合功能失效。
  private wasEditable = false;

  constructor() {
    // Signal inputs aren't resolved yet at constructor time (NG0950) — mirrors
    // PartnershipSettingsComponent's pattern for the same reason.
    effect(() => {
      const isEditable = this.editable();
      if (isEditable && !this.wasEditable) {
        this.expanded.set(true);
        this.load();
      }
      this.wasEditable = isEditable;
    });

    effect(() => {
      const key = this.refreshKey();
      untracked(() => {
        if (key === this.lastRefreshKey) {
          return;
        }
        this.lastRefreshKey = key;
        this.refresh();
      });
    });
  }

  private lastRefreshKey = 0;

  /** 背景更新：不顯示載入狀態、不清掉操作訊息。管理員正在點選要互換的
   * 球員、或調整還在送出時先跳過，免得清單在手底下變動。 */
  private refresh(): void {
    if (!this.expanded() || this.loading() || this.saving() || this.firstPick() !== null) {
      return;
    }
    this.scheduleService.getRoundMatches(this.groupId()).subscribe({
      next: (response) => {
        if (!this.saving() && this.firstPick() === null) {
          this.applyResponse(response);
        }
      },
      // 背景更新失敗時保留現有清單；下次重新讀取或手動重新整理會再試。
      error: () => undefined,
    });
  }

  toggle(): void {
    const next = !this.expanded();
    this.expanded.set(next);
    if (next) {
      this.load();
    }
  }

  load(): void {
    this.loading.set(true);
    this.errorKey.set(null);
    this.actionErrorKey.set(null);
    this.actionSuccess.set(false);
    this.firstPick.set(null);
    this.scheduleService.getRoundMatches(this.groupId()).subscribe({
      next: (response) => {
        this.applyResponse(response);
        this.loading.set(false);
      },
      error: (error: ApiError) => {
        this.loading.set(false);
        this.errorKey.set(error.i18nKey);
      },
    });
  }

  vsLabel(match: RoundMatchSummary): string {
    const teamA = match.participants.filter((p) => p.team === 'A').map((p) => p.nickname);
    const teamB = match.participants.filter((p) => p.team === 'B').map((p) => p.nickname);
    return `${teamA.join(' / ')} vs ${teamB.join(' / ')}`;
  }

  participantsByTeam(match: RoundMatchSummary, team: Team): ParticipantSummary[] {
    return match.participants.filter((p) => p.team === team);
  }

  /** 018-plan-then-start: 只有還沒結束的比賽才能調整參賽選手——已完成/
   * 已捨棄的比賽維持唯讀，避免改動已經打完的紀錄。 */
  isAdjustable(match: RoundMatchSummary): boolean {
    return match.status === 'queued' || match.status === 'in_progress';
  }

  /** 018-plan-then-start 後續需求: 只有還「排隊中」的比賽才能拖曳調整叫號
   * 順序——已經上場（in_progress）或打完的比賽，順序已經生效/不再有意義，
   * 拖不動。跟 `isAdjustable` 分開判斷：互換/變更選手涵蓋 in_progress，
   * 拖曳排序不涵蓋。 */
  isReorderable(match: RoundMatchSummary): boolean {
    return match.status === 'queued';
  }

  /** 018-plan-then-start: 「換成誰」下拉選單的候選名單——排除這場比賽
   * 已經在場上的人（避免明顯的重複選取），其餘由後端做權威驗證（例如
   * 選到目前正在別場比賽中的人，會被拒絕並顯示錯誤）。 */
  changeCandidates(match: RoundMatchSummary): RosterScheduleStatus[] {
    const currentIds = new Set(match.participants.map((p) => p.roster_entry_id));
    return this.roster().filter(
      (entry) => entry.status === 'active' && !currentIds.has(entry.roster_entry_id),
    );
  }

  /** 037 FR-029: marks a resting player in the swap and change pickers;
   * they stay selectable — the admin has the final say. */
  isResting(rosterEntryId: string): boolean {
    return this.roster().some((entry) => entry.roster_entry_id === rosterEntryId && !!entry.resting);
  }

  isSelected(matchId: string, rosterEntryId: string): boolean {
    const first = this.firstPick();
    return first !== null && first.matchId === matchId && first.rosterEntryId === rosterEntryId;
  }

  pick(matchId: string, rosterEntryId: string): void {
    const first = this.firstPick();
    if (!first) {
      this.firstPick.set({ matchId, rosterEntryId });
      return;
    }
    if (first.matchId === matchId && first.rosterEntryId === rosterEntryId) {
      this.firstPick.set(null);
      return;
    }
    if (first.matchId === matchId) {
      // Swapping within the same match is a no-op for "who plays whom" —
      // only cross-match swaps change anything.
      this.firstPick.set({ matchId, rosterEntryId });
      return;
    }
    this.actionErrorKey.set(null);
    this.saving.set(true);
    this.scheduleService
      .swapPlannedMatchPlayers(this.groupId(), first.matchId, first.rosterEntryId, matchId, rosterEntryId)
      .subscribe({
        next: (response) => {
          this.applyResponse(response);
          this.firstPick.set(null);
          this.saving.set(false);
          this.flashSuccess();
        },
        error: (error: ApiError) => {
          this.actionErrorKey.set(error.i18nKey);
          this.firstPick.set(null);
          this.saving.set(false);
        },
      });
  }

  /** 018-plan-then-start: 直接把某位選手換成下拉選單選到的另一人——跟
   * `pick`（互換）互不影響，選了就送出，不需要先選第二個對象。 */
  changeTo(matchId: string, oldRosterEntryId: string, newRosterEntryId: string): void {
    if (!newRosterEntryId) {
      return;
    }
    this.actionErrorKey.set(null);
    this.saving.set(true);
    this.scheduleService
      .changeMatchPlayer(this.groupId(), matchId, oldRosterEntryId, newRosterEntryId)
      .subscribe({
        next: (response) => {
          this.applyResponse(response);
          this.saving.set(false);
          this.flashSuccess();
        },
        error: (error: ApiError) => {
          this.actionErrorKey.set(error.i18nKey);
          this.saving.set(false);
        },
      });
  }

  /** 018-plan-then-start: 拖放結束後，樂觀地先在畫面上套用新順序，再送去
   * 後端持久化；若後端拒絕（例如某場比賽在送出前剛好被派上場地），用伺服器
   * 回應的真實順序覆蓋回去，而不是留著一個其實沒生效的畫面順序。
   *
   * 後續需求：清單同時顯示 queued/in_progress/completed/abandoned 全部
   * 狀態，但只有「排隊中」的比賽才有叫號順序可調（`isReorderable`）——
   * 拖動時可能把一場排隊中的比賽拖過已經上場/打完的比賽旁邊，所以送給
   * 後端的不是整份清單的順序，而是排完序後、只取「排隊中」那些比賽 id
   * 的相對順序。 */
  onDrop(event: CdkDragDrop<RoundMatchSummary[]>): void {
    if (event.previousIndex === event.currentIndex) {
      return;
    }
    const reordered = [...this.matches()];
    moveItemInArray(reordered, event.previousIndex, event.currentIndex);
    this.matches.set(reordered);

    const queuedOrder = reordered
      .filter((match) => this.isReorderable(match))
      .map((match) => match.match_id);

    this.actionErrorKey.set(null);
    this.saving.set(true);
    this.scheduleService.reorderPlannedMatches(this.groupId(), queuedOrder).subscribe({
      next: (response) => {
        this.applyResponse(response);
        this.saving.set(false);
        this.flashSuccess();
      },
      error: (error: ApiError) => {
        this.actionErrorKey.set(error.i18nKey);
        this.saving.set(false);
        this.load();
      },
    });
  }
}
