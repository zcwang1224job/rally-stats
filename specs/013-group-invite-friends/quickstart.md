# Quickstart: 邀請好友加入組團

## 前置條件

- 後端、前端服務皆已啟動。
- 會員 A（團長）以會員身分建立一個團（`created_by_member_id` 非
  null），已完成信箱驗證，持有該團的 `admin_token`（管理頁存取）。
- 會員 B、C 皆已完成信箱驗證，且 B 與 A 已是好友關係（C 與 A 不是）。

## 情境 1：團長從好友列表送出邀請（US1，FR-001~004）

1. 呼叫 `GET /groups/{group_id}/invitable-friends`（以 A 的
   `admin_token`）。
   **預期**：好友 B 出現，`invite_status="not_invited"`；若好友清單也
   包含 C 之外的非好友，C 本身不會出現在清單中（此清單本來就只列好友）。
2. 呼叫 `POST /groups/{group_id}/invites` body
   `{ "invitee_member_id": "<B的member_id>" }`。
   **預期**：`201`，`status="pending"`。
3. 重複呼叫步驟 2（同一位 B）。
   **預期**：`409 INVITE_ALREADY_PENDING`（FR-003）。
4. 再次呼叫 `GET .../invitable-friends`。
   **預期**：B 的 `invite_status="pending"`。

## 情境 2：受邀好友即時收到通知並接受（US2，FR-005~007，SC-001~002、SC-005）

1. 以 B 的 `access_token` 呼叫 `GET /notifications/unread-count`。
   **預期**：`unread_count` 因情境 1 步驟 2 而為 `1`（2 秒內，若 B 當下
   在線，Ably 事件已推播——quickstart 僅驗證 REST 層，即時性見
   `specs/012-realtime-notifications/quickstart.md` 之既有驗證方式）。
2. 呼叫 `GET /notifications`，取得該筆通知的
   `group_invite.invite_id`。
3. 呼叫 `GET /group-invites/{invite_id}`。
   **預期**：`status="pending"`、`group_name` 與 `inviter_nickname`
   正確。
4. 呼叫 `POST /group-invites/{invite_id}/accept`。
   **預期**：`200`，回傳 `group_id`/`roster_entry_id`——即使該團設有
   通關密碼，也不需要在請求中附上密碼（FR-007，SC-005）。
5. 呼叫 `GET /friends`（B 的視角，既有端點）確認 A 仍是好友——邀請本身
   不影響好友關係。

## 情境 3：額滿時接受失敗，團長收到通知（US3，FR-013，SC-006）

前置：另建一個 `max_members=1` 且已有 1 位現有成員的團（A 建立、A 自己
即為那 1 位）。

1. A 對 C 送出邀請（先讓 C 與 A 成為好友，重用既有好友系統端點）。
2. C 呼叫 `POST /group-invites/{invite_id}/accept`。
   **預期**：`409 GROUP_FULL`。
3. 立即以 A 的 `access_token` 呼叫 `GET /notifications`。
   **預期**：出現一則 `type="group_invite_capacity_full"` 的新通知。
4. 呼叫 `GET /groups/{group_id}/invitable-friends`（A 視角）。
   **預期**：C 的 `invite_status` 仍為 `"pending"`（FR-013(a)，未被標記
   為失敗或結束）。

## 情境 4：好友關係解除，待回覆邀請自動失效（US2 Edge Case，FR-014，SC-007）

1. A 對 B 送出邀請（`status="pending"`）。
2. B 呼叫既有好友系統端點解除與 A 的好友關係
   （`DELETE /friends/{friend_request_id}`）。
3. B 呼叫 `GET /group-invites/{invite_id}`。
   **預期**：`status="invalidated"`。
4. B 呼叫 `POST /group-invites/{invite_id}/accept`。
   **預期**：`409 GROUP_INVITE_NOT_PENDING`，不得成功加入。

## 情境 5：團解散後，待回覆邀請自動失效（Edge Cases，research.md #2/#5）

1. A 對 B 送出邀請（`status="pending"`）。
2. A 呼叫既有的 `POST /groups/{group_id}/disband`。
3. B 呼叫 `GET /group-invites/{invite_id}`。
   **預期**：`status="invalidated"`。

## Edge Case 驗證：已透過其他管道先行加入

1. A 對 B 送出邀請。
2. B 不理會通知，直接透過既有「加入團」流程（組團編號或連結）加入該團。
3. A 呼叫 `GET /groups/{group_id}/invitable-friends`。
   **預期**：B 的 `invite_status="already_member"`（優先於底層
   `GroupInvite` 仍是 `pending` 的事實，research.md #8）。

## Edge Case 驗證：匿名建團無邀請功能（FR-012）

1. 以匿名方式（不勾選會員身分）建立一個團。
2. 呼叫 `GET /groups/{group_id}/invitable-friends`（以該團的
   `admin_token`）。
   **預期**：`403 GROUP_NOT_MEMBER_CREATED`。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/契約/整合測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 2 之「2 秒內同步」比照 012 quickstart 情境 1 之既有精神，人工
  抽測即可，非嚴格自動化效能測試（SC-001 為 SHOULD 等級）。
