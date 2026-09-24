# Contracts: 團層級「詳細計分模式」開關

完整比照既有 `PATCH /{group_id}/scoreboard-scoring` 的形狀與行為模式（同一個管理員權限依賴、同一種「立即生效、逐場地廣播」語意），只是換一個欄位名稱與路徑。

## `PATCH /{group_id}/detailed-scoring`

管理員限定（既有 `require_admin` 依賴，與 `scoreboard-scoring` 端點相同）。

### Request Body（`DetailedScoringRequest`）

```jsonc
{ "enabled": true }
```

### Response（`DetailedScoringResponse`）

```jsonc
{ "detailed_scoring_enabled": true }
```

### 行為

- 呼叫 `service.set_detailed_scoring(session, group, payload.enabled)`（新函式，比照既有 `set_scoreboard_scoring()`）：立即更新 `group.detailed_scoring_enabled`，**不**遞增 `base_settings_version`（這不是樂觀鎖表單的一部分，research.md Decision 5）。
- 更新後，對該團每一個未刪除的場地廣播既有的 `match.nextRound` 事件（純粹當作「請重新拉取狀態」的既有慣用觸發，比照 `set_scoreboard_scoring()` 既有做法），讓已經開啟的計分板/控制板/管理頁即時反映新設定——但依 FR-006，這個廣播只影響「畫面顯示的團設定值」本身（例如管理頁上開關的呈現），MUST NOT 改變任何已在進行中比賽的 `matches.detailed_scoring_enabled`（那是建立當下就定案的快照，見 data-model.md）。

### 對既有 `GET /groups/{group_id}`／團設定讀取端點的影響

比照 `scoreboard_scoring_enabled` 既有欄位的做法，`detailed_scoring_enabled` 加入既有的 `AdminGroupResponse`（僅管理頁可見，刻意不放進 `GroupPublicResponse`——這個設定跟 `scoreboard_scoring_enabled` 一樣沒有理由出現在公開的加入團流程查詢結果中，比照 `apps/api/app/domains/group/schemas.py` 既有註解的理由）。

## 不新增的介面

- 不新增「場地層級」的對應開關端點——Clarifications 2026-09-16 已定案為團層級，不提供場地各自獨立設定的精細度。
