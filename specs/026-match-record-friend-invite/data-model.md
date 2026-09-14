# Data Model: 從對戰紀錄／即時戰況頁面加好友

本 feature 不新增資料表，也不新增獨立的好友邀請機制——沿用並擴充下列既有
實體。詳細決策依據見 research.md。

## 1. `Member`（既有實體，`app/domains/member/models.py`）

新增一個欄位，與既有 `allow_search`/`share_match_records_with_friends`
（022 引入）完全同型：

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---|---|
| `allow_friend_invite_from_match_pages` | `BOOLEAN NOT NULL` | `true` | FR-006/007：是否允許其他會員透過對戰紀錄／即時戰況頁面對自己發送好友邀請；與既有 `allow_search` 完全獨立、互不連動（Clarifications）。 |

**Migration**：新增一個 Alembic revision（沿用既有
`ebde39e08b3a_member_auth_and_friend_tables.py` 建立
`allow_search`/`share_match_records_with_friends` 時的同一種
`op.add_column(..., server_default="true")` 寫法），不需要資料回填
（`server_default` 已確保既有列自動補值為 `true`）。

## 2. `ParticipantSummary`（既有共用型別，`app/domains/schedule/schemas.py`）

新增一個**可選、預設為 `None`** 的欄位：

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---|---|
| `member_id` | `str \| None` | `None` | 對應 `RosterEntry.member_id`——`None` 代表此參與者是 Guest（訪客）身分。**僅在兩個既授權的對戰紀錄建構路徑填入真實值**（FR-001a/b）：`_build_match_record_summaries()`（團內對戰紀錄）、跨團對戰紀錄的對應建構函式（`member/service.py`）。`_match_participants_payload()`／`court_live_state()`（公開計分板/控制板端點與 Ably 廣播 payload）與 `build_round_matches_list()`（管理頁「本輪賽程清單」）**刻意維持 `None`**，不在這三處的建構程式碼中查詢或填入此欄位；**實作後調整（2026-09-14）**：`build_schedule_snapshot()` 回應中 `current_match`/`next_up` 底下的 `ParticipantSummary.member_id` 也同樣維持 `None`——即時戰況（US2）的 `member_id` 改由下方第 2a 節的 `RosterScheduleStatus` 承載，`ParticipantSummary` 不再是即時戰況入口的安全落點（見 research.md 頂部附註）。 |

此型別本身不變動既有 `roster_entry_id`/`nickname`/`team` 三個欄位的語意
或既有呼叫點的既有行為，加欄位對既有序列化輸出是向後相容的（既有前端
消費者若不認得這個新欄位，行為不受影響）。

## 2a. `RosterScheduleStatus`（既有共用型別，`app/domains/schedule/schemas.py`；
**實作後調整新增**）

即時戰況（US2）的安全落點。`build_schedule_snapshot()` 回應
（`ScheduleResponse.roster: list[RosterScheduleStatus]`）餵給團內成員視圖
「賽程」頁新增的輪替名單區塊，以及團長／管理員「開團管理頁」的輪替名單
分頁——兩者皆需登入／管理員權杖驗證，從未被任何無需登入的公開端點或
Ably 廣播 payload 消費，因此可安全承載 `member_id`：

| 欄位 | 型別 | 預設值 | 說明 |
|---|---|---|---|
| `member_id` | `str \| None` | `None` | 對應 `RosterEntry.member_id`——`None` 代表此團員是 Guest（訪客）身分。在 `build_schedule_snapshot()` 建構 `roster` 列表的迴圈中填入，涵蓋該團所有現役團員（不限於是否正在比賽中，FR-011）。 |

此型別既有的 `roster_entry_id`/`nickname`/`currently_playing`/
`wait_count` 等欄位語意不變。

## 3. `FriendRequest`（既有實體，`app/domains/friend/models.py`）— 不變動

好友邀請的建立、狀態機（`pending -> accepted/rejected`、
`accepted -> unfriended`）、重複發送防呆（DB partial unique index）完全
沿用既有定義，本 feature 不新增欄位、不新增狀態值。差異僅在於「如何定位
`addressee`」多了一條新路徑（見下方 API 層）。

## 4. 新增 API 層 request/response 形狀（`app/domains/friend/schemas.py`）

```python
class FriendRequestCreateByMemberId(BaseModel):
    addressee_member_id: str


class InviteCandidatesRequest(BaseModel):
    member_ids: list[str]  # 去重後、由前端從畫面上實際可見的參與者收集
    # 未設硬性上限（刻意決定，非遺漏）——見 contracts/
    # friend-invite-from-pages-api.md「未設硬性上限」段落


class InviteCandidateStatus(BaseModel):
    member_id: str
    friendship_status: str  # "none" | "friends" | "pending_outgoing" | "pending_incoming"
    invite_eligible: bool
    # true 僅當 friendship_status == "none" 且目標
    # allow_friend_invite_from_match_pages == True 且目標為現役已驗證會員


class InviteCandidatesResponse(BaseModel):
    candidates: list[InviteCandidateStatus]
```

`FriendRequestResponse`（既有，`friend_request_id`/`status`）直接重用，
`POST /friends/requests/by-member` 與既有 `POST /friends/requests` 回傳
完全相同的形狀。

## 5. `PrivacySettingsRequest`/`PrivacySettingsResponse`（既有，
`app/domains/member/schemas.py`）— 各新增一個對應欄位

```python
class PrivacySettingsRequest(BaseModel):
    allow_search: bool | None = None
    share_match_records_with_friends: bool | None = None
    allow_friend_invite_from_match_pages: bool | None = None  # 新增

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "PrivacySettingsRequest":
        if (
            self.allow_search is None
            and self.share_match_records_with_friends is None
            and self.allow_friend_invite_from_match_pages is None  # 新增
        ):
            raise ValueError("at least one privacy field must be provided")
        return self


class PrivacySettingsResponse(BaseModel):
    allow_search: bool
    share_match_records_with_friends: bool
    allow_friend_invite_from_match_pages: bool  # 新增
```

`MemberPublicResponse`（登入回應／`GET /members/me` 內嵌的會員資訊）同步
新增 `allow_friend_invite_from_match_pages: bool` 欄位，比照既有
`allow_search`/`share_match_records_with_friends` 兩欄位的既有位置。

## 6. 前端對應型別（`apps/web/src/app/core/api/*.ts`、
`.../schedule.models.ts`）

- `ParticipantSummary`（`schedule.models.ts`）新增 `member_id?: string | null`
  （US1 對戰紀錄頁使用；`current_match`/`next_up` 底下的值恆為
  `null`/`undefined`，不供 US2 使用）。
- `RosterScheduleStatus`（`schedule.models.ts`）新增
  `member_id?: string | null`（US2 即時戰況輪替名單使用，實作後調整新增）。
- 新增 `InviteCandidateStatus`/`InviteCandidatesResponse`
  （`friend.models.ts`），與後端形狀一致。
- `PrivacySettings` 相關既有介面新增
  `allow_friend_invite_from_match_pages: boolean`。
- `AddFriendButtonComponent` 新增 `iconStyle?: boolean`/`nickname?: string | null`
  input（FR-016，圖示樣式與 `aria-label` 插值）。

## 實體關係圖（僅示意本 feature 新增/擴充的部分）

```text
Member (既有)
├── allow_search                          (022，不變)
├── share_match_records_with_friends      (022，不變)
└── allow_friend_invite_from_match_pages  (新增，本 feature)

RosterEntry (既有)
└── member_id ──┬─────────────────┐ (nullable，既有；本 feature 首次把它投影進 API 回應)
                │                 │
ParticipantSummary (既有共用型別)   RosterScheduleStatus (既有共用型別)      FriendRequest (既有，狀態機不變)
├── roster_entry_id                ├── roster_entry_id                     ├── requester_id
├── nickname                        ├── nickname                            ├── addressee_id
├── team                            ├── currently_playing / wait_count      └── status: pending|accepted|
└── member_id (新增，僅 US1 的        └── member_id (新增，US2 即時戰況              rejected|unfriended
    2 個對戰紀錄建構函式填入)             輪替名單填入，實作後調整)
```
