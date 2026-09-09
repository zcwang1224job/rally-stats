# API Contract: 比賽加減分紀錄與趨勢圖

延伸既有 `specs/005-member-view` 之 `GET /groups/{group_id}/match-records`
與 `GET /members/me/match-records`；新增各自的單場比賽詳情端點。錯誤代碼
皆為語意化字串（憲章原則 VIII），由前端依語系檔轉換顯示。皆為唯讀端點，
不改變任何資料。

## `GET /groups/{group_id}/match-records/{match_id}`（新增）

**用途**：團內對戰紀錄分頁（現役成員/訪客）點進某場比賽的詳情
（FR-001/002/003/007）。

**Auth**：沿用既有 `resolve_active_roster_membership()`——與同層級既有
`GET /groups/{group_id}/match-records` 完全相同的授權語意（Guest 現役
`guest_session_token` 或 Member 現役成員 Bearer token 擇一）。

**Path params**：`group_id`（UUID）、`match_id`（UUID）。

**回應** `200`：`MatchRecordDetailResponse`（見 data-model.md）：

```json
{
  "match_id": "uuid",
  "round_number": 3,
  "team_a": [{ "roster_entry_id": "uuid", "nickname": "小明", "team": "A" }],
  "team_b": [{ "roster_entry_id": "uuid", "nickname": "小華", "team": "B" }],
  "score_a": 21,
  "score_b": 18,
  "winner_team": "A",
  "started_at": "2026-09-01T10:00:00Z",
  "ended_at": "2026-09-01T10:15:00Z",
  "record_completeness": "complete",
  "events": [
    { "side": "A", "delta": 1, "score_a": 1, "score_b": 0, "elapsed_seconds": 12 },
    { "side": "B", "delta": 1, "score_a": 1, "score_b": 1, "elapsed_seconds": 34 },
    { "side": "A", "delta": -1, "score_a": 0, "score_b": 1, "elapsed_seconds": 41 }
  ]
}
```

**錯誤**：
- `MEMBERSHIP_REQUIRED`（403）：既有語意，不重複——訪客 token 無效/非
  現役、或 Member 非此團現役成員。
- `MATCH_NOT_FOUND`（404）：`match_id` 不存在、非 `completed` 狀態、或其
  `group_id` 不等於路徑上的 `group_id`（刻意統一回傳同一錯誤，不透露
  「這個 match_id 其實存在但屬於別的團」，比照 007-live-scoreboard
  `scoring-api.md` 既有先例）。

`record_completeness == "none"` 或 `"partial"` 皆不是錯誤——`200`，
`events` 分別為空陣列或不完整陣列，前端依 FR-006/006a 顯示對應提示。

---

## `GET /members/me/match-records/{match_id}`（新增）

**用途**：會員跨團對戰紀錄清單、或「我的團 → 歷史」清單，點進某場比賽的
詳情（FR-001/002/003/007）——這兩個清單皆已登入會員視角，且皆已採
「曾經」而非「現役」的較寬鬆授權基準，故共用同一支端點。

**Auth**：`require_member`（比照既有 `GET /members/me/match-records`，
不要求信箱已驗證），之後沿用既有 `verify_ever_group_member(session,
match.group_id, member.id)`——只要此會員「曾經」是這場比賽所屬團的正式
成員（不論現役／已離開／已被踢除）即可，與既有 `GET
/members/me/groups/{group_id}/history` 完全相同的授權語意。

**Path params**：`match_id`（UUID）。

**回應** `200`：`MatchRecordDetailResponse`——形狀與上一個端點完全相同
（見上方範例）。

**錯誤**：
- `MEMBER_TOKEN_INVALID`（401）：既有語意——未登入。
- `MATCH_NOT_FOUND`（404）：`match_id` 不存在或非 `completed` 狀態。
- `GROUP_MEMBERSHIP_NEVER_HELD`（403）：該會員從未是這場比賽所屬團的
  正式成員（既有語意，沿用 014-member-groups-history）。

## 兩端點的共通行為

- 皆為唯讀，不改變任何資料、不觸發任何即時廣播（Ably）。
- `events` 一律依 `elapsed_seconds`（即 `created_at`）升冪排序；`created_at`
  剛好相同時（並發加減分，見 `test_score_concurrency.py`），以 `id` 為次要
  排序鍵確保順序具確定性（data-model.md）。
- `winner_team`/`score_a`/`score_b`/`started_at`/`ended_at` 為比賽的正式
  最終結果，與 `events` 陣列最後一筆的 `score_a`/`score_b` 在
  `record_completeness == "complete"` 或 `"partial"` 時必然一致（因為
  記錄只可能漏開頭，不可能漏結尾——見 spec.md Assumptions）；
  `"none"` 時 `events` 為空，仍照常回傳最終比分供 FR-007 之基本資訊
  呈現。
