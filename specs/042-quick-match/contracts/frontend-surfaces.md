# UI Contract: 快速比賽觸及的畫面

語系 key 一律新增在 `apps/web/src/assets/i18n/zh-TW.json` 與 `en.json`，命名空間 `quickMatch.*`；錯誤碼在 `errors.*`。

## 新路由

| 路由 | 元件 | navShell | 說明 |
|---|---|---|---|
| `quick-match/new` | `features/quick-match/quick-start/` | 有 | 表單（US1）與等待畫面（US4）同一元件，以 `QuickSessionState.state` 切換；送出成功且 `state == playing` → `router.navigate(['/control', token])`；`waiting` → 停在等待畫面並訂閱 court 頻道，收到 `rotation.updated` 才導向控制板 |

## 首頁 `features/home`

- `home__actions` 新增 `quickMatch.cta`（登入與否皆顯示），導向 `quick-match/new`。
- 登入會員：呼叫 `GET /members/me/quick-session`，非 null 時顯示橫幅 `quickMatch.banner.active`（依 `role` 給「回到控制板」或「開啟計分板」）。

## 快速開始表單（`quick-start`）

| 欄位 | 控制 | 規則 |
|---|---|---|
| 比賽模式 | 單打／雙打 segmented，預設單打 | 切換時位置數 2 ↔ 4 |
| 球員位置 | A1 固定（會員：本人暱稱＋「本人」標籤，不可改；訪客：暱稱輸入） | 其餘每個位置：「輸入暱稱」或（會員限定）「從好友挑選」— 好友清單來自 `GET /friends`，已挑過的好友不可再選 |
| 計分制 | 21／15／自訂（自訂展開三個數字欄位） | 重用 `customScoringValidator` |
| 比賽詳細設定 | toggle，預設關 | |
| Turnstile | `TurnstileWidgetComponent` | 與開團相同 |

- 就地驗證訊息：`quickMatch.validation.{size,duplicateNickname,duplicateFriend,nicknameRequired}`。
- 訪客送出前重用 `GroupJoinService.getActiveGuestGroupId()`／`verifyActiveGuestGroupId()` 的「已在別團」前置檢查；會員在別團收到 `ALREADY_ACTIVE_IN_ANOTHER_GROUP` 時依 `detail.group_kind` 顯示 `errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP` 或 `quickMatch.error.activeQuickSession`。
- 訪客送出成功後顯示一次性提示 `quickMatch.keepLinkNotice`（FR-024）。

## 等待畫面（同元件，`state == waiting`）

- 每個位置一列：暱稱、來源標籤、狀態（`quickMatch.slot.{ready,pending,converted}`）、pending 位置顯示倒數（由 `expires_at` 推算）與「不等了，改用暱稱」按鈕（`convert`）。
- 「取消」按鈕 → `app-confirm-dialog` → `cancel` → 回首頁。
- 訂閱 `quickMatch.lineupChanged` → 重新載入；`rotation.updated` → 導向控制板。

## 控制板 `features/control-panel`（`group_kind === 'quick'` 分支）

- 隱藏輪次列與 `next_up` 預告；標題顯示 `quickMatch.label`。
- `current_match` 為空時，原本 `waiting_reason === 'manual_assignment'` 的等待訊息位置改渲染 `<app-quick-actions>`：
  - `state == idle`：上一場結果摘要、「再打一場」（`rematch`）、「換人再打」（展開與表單相同的名單編輯器，`lineup`）、「結束」（`app-confirm-dialog` → `close`）。
  - `state == waiting`（換人再打後等待好友）：與等待畫面相同的名單列。
  - 訪客位置旁顯示「綁定戰績」連結（`guest-access/:guest_binding_token`）。
- `state == playing` 且使用者按「結束」：確認框文字說明進行中的比賽會變成已捨棄。
- 多訂閱 `quickMatch.lineupChanged`。`frozenState` 機制不變。
- `group_disbanded` 畫面文字依 `group_kind`：`quickMatch.closed`。

## 計分板 `features/scoreboard`

- `group_kind === 'quick'`：隱藏輪次、標題 `quickMatch.label`；`group_disbanded` 文字同上。

## 通知與邀請

- `notification-list.component.ts::open()`：`type === 'quick_match_invite'` → `group-invites/:inviteId`。
- 通知列文字：`quickMatch.invite.notification`（`{{inviter}}`、`{{mode}}`）。
- `group-invite-detail`：`group_kind === 'quick'` 時標題與說明改為 `quickMatch.invite.{title,description}`；接受成功後導向 `scoreboard/:scoreboard_token`；`GROUP_INVITE_NOT_PENDING` 顯示 `quickMatch.invite.expired`。

## 對戰紀錄、統計分析、好友對戰紀錄、分享卡

- 列表與詳情：`group_kind === 'quick'` 時活動名稱顯示 `quickMatch.label` 並加標籤樣式（非僅顏色，附文字）。
- 篩選：新增「活動類型：全部／揪團／快速比賽」對應 `group_kind` 查詢參數。
- 分享卡：`share-card-model.ts` 轉換時 `groupName = translate('quickMatch.label')`。
- 「我的團」：篩選新增「包含快速比賽」（`include_quick`），預設關。
