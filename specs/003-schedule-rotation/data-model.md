# Phase 1 Data Model: 賽程與輪替名單

沿用 `specs/architecture.md` §2 已定案的 DDL（`matches`、`match_participants`、`pair_history`、`partnerships` 四張表——本 feature 首次實際寫入，DDL 原文照錄於下）。`groups.current_round_number`／`groups.auto_next_round` 與 `roster_entries.wait_count`／`status`／`joined_at` 皆已由 001 建立，本 feature 不新增欄位，僅賦予其排點語意。

## 1. Match（比賽）— 本 feature 擁有

```sql
CREATE TABLE matches (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id         UUID NOT NULL REFERENCES groups(id),
    court_id         UUID REFERENCES courts(id),
    round_number     INT NOT NULL,
    status           VARCHAR(16) NOT NULL DEFAULT 'queued', -- queued | in_progress | completed | abandoned
    score_a          INT NOT NULL DEFAULT 0,
    score_b          INT NOT NULL DEFAULT 0,
    winner_team      VARCHAR(1),
    target_score      INT NOT NULL,
    deuce_threshold    INT NOT NULL,
    cap_score          INT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    ended_at          TIMESTAMPTZ
);
CREATE INDEX ix_matches_group_round ON matches (group_id, round_number);
CREATE INDEX ix_matches_court_status ON matches (court_id, status);
CREATE UNIQUE INDEX ux_matches_court_in_progress ON matches (court_id) WHERE status = 'in_progress';
```

**本 feature 寫入規則**：

| 欄位 | 演算法模式（建立當下） | 手動安排（建立當下） |
|---|---|---|
| `court_id` | `NULL`（見 research.md #7，稍後於同一交易內領取階段填入） | 建立當下即綁定（FR-011） |
| `status` | `queued`，領取階段轉 `in_progress` | 直接 `in_progress`（MUST NOT 經過 `queued`，FR-011） |
| `target_score`/`deuce_threshold`/`cap_score` | 建立當下複製自 `groups` 當時生效值（快照，FR-012 / 001 FR-016 精神） | 同左 |
| `score_a`/`score_b`/`winner_team`/`started_at`/`ended_at`/評分本身 | 屬 007 spec 範圍，本 feature 僅在建立/領取時寫入 `started_at` | 同左 |

**狀態轉換**（`completed`/`abandoned` 之間的轉換由 007 spec 或本 feature 之捨棄流程觸發，二者皆為終態）：

```
queued ──(場地領取，本 feature)──▶ in_progress ──(達標/提前結束，007 spec)──▶ completed
   │                                    │
   └──(Next Round 強制捨棄／場地刪除／團解散，本 feature 呼叫或串接)──▶ abandoned ◀──┘
```

## 2. MatchParticipant（比賽參與者）— 本 feature 擁有

```sql
CREATE TABLE match_participants (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id         UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    roster_entry_id  UUID NOT NULL REFERENCES roster_entries(id),
    team             VARCHAR(1) NOT NULL
);
CREATE INDEX ix_match_participants_match ON match_participants (match_id);
CREATE INDEX ix_match_participants_roster ON match_participants (roster_entry_id);
```

單打比賽：2 筆記錄，`team` 各為 `'A'`/`'B'`。雙打：4 筆，A/A/B/B。

## 3. PairHistory（配對紀錄）— 本 feature 擁有

```sql
CREATE TABLE pair_history (
    group_id    UUID NOT NULL REFERENCES groups(id),
    player_lo_id UUID NOT NULL REFERENCES roster_entries(id),
    player_hi_id UUID NOT NULL REFERENCES roster_entries(id),
    pair_count   INT NOT NULL DEFAULT 0,
    PRIMARY KEY (group_id, player_lo_id, player_hi_id)
);
```

`player_lo_id`/`player_hi_id`：兩個 `roster_entry_id` 依 UUID 字串排序，較小者為 `lo`，避免 `(A,B)`/`(B,A)` 重複列。**計數語意**：任兩人同場出現（不分隊友/對手）即 `+1`，於比賽建立當下立即累加，不因比賽終態為 `abandoned` 而扣回（見 research.md #5）；跨排程機制持續累計，不因切換而歸零（FR-024）。

## 4. Partnership（固定搭檔）— 本 feature 擁有

```sql
CREATE TABLE partnerships (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id     UUID NOT NULL REFERENCES groups(id),
    player_a_id  UUID NOT NULL REFERENCES roster_entries(id),
    player_b_id  UUID NOT NULL REFERENCES roster_entries(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (player_a_id <> player_b_id)
);
CREATE UNIQUE INDEX ux_partnership_player_a ON partnerships (player_a_id);
CREATE UNIQUE INDEX ux_partnership_player_b ON partnerships (player_b_id);
```

僅於 `scheduling_mechanism = 'fixed_partner'` 期間存在有意義的記錄；切換離開時全數刪除（FR-024）。兩條唯一索引確保任一人至多同時存在一筆搭檔關係（不論作為 `player_a` 或 `player_b`）——**實作限制**：新增/更新搭檔時 MUST 檢查目標兩人是否已各自存在於 `player_a_id`/`player_b_id` 任一欄，若有須先刪除舊記錄，因兩條獨立唯一索引無法阻止「A 已是某筆的 `player_a`，又被塞進另一筆的 `player_b`」這類跨欄位衝突，需在應用層以交易內先刪後建保證。

## 5. RosterEntry（輪替名單項目）— 001 擁有，本 feature 賦予排點語意

| 欄位 | 本 feature 讀寫規則 |
|---|---|
| `wait_count` | `NULL` = 無限大（FR-004）。Round 產生時：上場者 `SET wait_count = 0`；active 且未上場者 `SET wait_count = COALESCE(wait_count, 0) + 1`（research.md #9）。手動安排：建立比賽當下歸零參與者；Round 邊界時未被排入任何比賽者 +1（FR-014）。 |
| `status` | `active`/`left`/`kicked`。轉為非 `active` 時觸發 FR-039～041 賽程表收斂與（固定搭檔模式下）Partnership 清理。 |
| `joined_at` | 用於 FR-005 次要排序（等待輪數相同時較早加入者優先）與 FR-020 初始搭檔配對順序。 |

## 6. Group（團）— 001 擁有，本 feature 賦予語意

| 欄位 | 本 feature 讀寫規則 |
|---|---|
| `current_round_number` | 初始為 1（001 已建立預設值）。首次 Next Round（手動或自動）生成的就是第 1 輪，維持不變；第二次起每次成功後 `+= 1`（FR-002）——避免第一次按 Next Round 就把第 1 輪跳過、直接產生第 2 輪。 |
| `auto_next_round` | 僅演算法排程機制下有意義（FR-034）；`scheduling_mechanism` 切為 `manual` 時系統自動設為 `false` 並提示（FR-016，見 contracts）。 |
| `scheduling_mechanism` | 切換僅影響下一個 Round（FR-003）；切入/切出 `fixed_partner` 觸發 Partnership 副作用（research.md #4）。 |
| `match_mode` | 與 `scheduling_mechanism` 之 FR-042 組合驗證，見 research.md #3。 |

## 7. 演算法決策彙總（跨實體）

| 階段 | 適用模式 | 排序/分組依據 | 對應 FR |
|---|---|---|---|
| 階段一：誰上場（個人） | 公平輪替、個人全混搭 | `wait_count` DESC（NULL 最大）→ `joined_at` ASC | FR-005 |
| 階段一：誰上場（隊伍） | 固定搭檔循環賽 | 隊伍優先度 = MAX(兩隊員 wait_count)，同上次要排序 | FR-018 |
| 階段二：個人配對 | 公平輪替、個人全混搭第一步 | `pair_history.pair_count` 最小優先，貪婪法 | FR-008, FR-025 |
| 階段二：隊伍對戰配對 | 固定搭檔循環賽、個人全混搭第二步 | 跨隊個人配對次數加總最小，貪婪法 | FR-019, FR-025 |

## 8. Migration 範圍

新增 `matches`、`match_participants`、`pair_history`、`partnerships` 四張表（DDL 見上）；`groups`、`roster_entries`、`courts` 三表不需變更（欄位皆已存在）。
