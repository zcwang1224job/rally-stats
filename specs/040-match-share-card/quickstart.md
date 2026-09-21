# Quickstart: 驗證單場比賽分享圖卡（040-match-share-card）

**Plan**: [plan.md](./plan.md) | 契約：[contracts/](./contracts/) | 模型：[data-model.md](./data-model.md)

## 前置條件

- 本機 docker 的 Postgres（`infra-db-1`，localhost:5432）已啟動。
- 在 worktree 中執行時，依 `docs/local-development.md` 以及專案慣例：後端把主 checkout 的 venv 加到 PATH；前端 `ln -s` 主 checkout 的 `node_modules`。

## 1. 自動化測試

```bash
# 後端：只跑本功能相關的三個檔案（完整 suite 約 20 分鐘，合併前另外跑）
cd apps/api
python -m pytest tests/contract/test_group_match_record_detail.py \
                 tests/contract/test_member_match_record_detail.py \
                 tests/unit/domains/member/test_personal_settings.py -q

# 前端
cd apps/web
npx ng test --watch=false
npx ng lint
npx ng build
```

**預期**：全部通過；`share-card-highlights.spec.ts` 涵蓋 research Decision 7 表格中每一個門檻的「剛好達標／差 1」兩側。

## 2. 實際畫面驗收

用 `apps/api/scripts/seed_dashboard_demo.py` 在測試資料庫建立示範資料（demo 會員與 300 場比賽），再以 worktree 的前後端（:8001／:4300）開啟。

| # | 步驟 | 預期結果（對應需求） |
|---|---|---|
| 1 | 「我的對戰紀錄」→ 點一場**我方贏**的比賽 →「分享圖卡」 | 預覽出現；我方在上方、徽章為「勝利」；亮點最多 3 個，數字與詳情區塊一致（US1、US3、FR-010、FR-016） |
| 2 | 同上，換一場**我方輸**的比賽 | 我方仍在上方、徽章為「落敗」；不出現逆轉勝、延長賽勝出、大比分勝出這類亮點（FR-013） |
| 3 | 從「團內對戰紀錄」開啟同一場比賽 | 勝方在上方，徽章為「勝」／「WIN」，不出現「勝利」「落敗」字樣（FR-017） |
| 4 | 開啟一場逐分紀錄為 partial 或 none 的舊比賽 | 沒有走勢圖、亮點、平均每分耗時，版面沒有空框（FR-009、SC-004） |
| 5 | 開啟一場簡易計分、紀錄完整的比賽 | 走勢圖照常顯示；不出現主動得分亮點（FR-014） |
| 6 | 開啟一場 11 分制的比賽 | 門檻依換算：逆轉落後 3、連得 3、分差 5 才會出現亮點；連得 2 分不會出現（FR-012） |
| 7 | 雙打且暱稱達 20 字 | 兩種配色、兩種語言下都沒有文字重疊或超出邊界（SC-005） |
| 8 | 「下載圖片」 | 檔案為 1080×1350 PNG，檔名 `rally-stats-YYYYMMDD-x-y.png`，內容與預覽相同（FR-020、SC-006） |
| 9 | 切換暗色後再下載 | 下載的圖片為暗色（FR-024） |
| 10 | 桌機 Chrome（localhost）「複製圖片」後貼到聊天軟體 | 貼上的是同一張圖（FR-022） |
| 11 | 以 `http://<LAN IP>:4300` 從手機開啟 | 「複製圖片」不出現（非 secure context），下載仍可用 |
| 12 | 手機以 HTTPS 環境（staging）按「分享」→ 選 LINE | 聊天室收到的是圖片檔，不是連結（FR-021）；取消分享時沒有錯誤提示（FR-023） |
| 13 | 切換成英文後重新開啟預覽 | 圖卡上所有固定文字都是英文（SC-008） |
| 14 | 同一場比賽重複開關預覽 5 次後下載 | 5 張圖完全相同（SC-007，可用 `shasum` 比對） |
| 15 | 螢幕閱讀器（VoiceOver）聚焦預覽圖 | 會唸出雙方隊伍、比分與勝方（FR-028） |

## 3. 契約抽查

```bash
curl -s "http://localhost:8001/members/me/match-records/<match_id>" \
  -H "Authorization: Bearer <token>" | jq '.target_score'
```

**預期**：輸出該場比賽建立時的分制；之後修改團的分制並重打一次，輸出不變（[contracts/match-record-detail-api.md](./contracts/match-record-detail-api.md)）。
