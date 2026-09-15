# Contracts: 加分時記錄發球者與站位資訊

本功能**不新增、不修改任何對外 API 端點或回應欄位**。

- FR-005（Clarifications 2026-09-15）明確排除本次範圍新增任何查看/
  顯示介面；因此沒有任何新端點需要把 `score_serve_records` 的內容
  暴露給前端。
- 既有 `POST /courts/by-token/{token}/matches/{match_id}/score`
  （`apply_score_delta()`）的請求/回應形狀（`ScoreRequest` /
  `ScoreMutationResult`）**完全不變**——本功能在該端點既有的資料庫
  交易內，多寫入一筆 `ScoreServeRecord`（`delta > 0` 時）或什麼都不做
  （`delta < 0` 時），但不改變該端點回傳給呼叫端的任何欄位。
- 既有 `GET /courts/by-token/{token}/state`（`court_live_state()`）
  的回應形狀（`CourtStateResponse`）同樣**不變**。

未來若 `029-serve-rotation-display`（計分板發球站位顯示）或任何後續
功能需要把 `serving_team`／站位資訊透過 API 呈現給前端，屬於該功能
自己的契約設計範圍，SHOULD 直接讀取本功能建立的 `matches` 新欄位
（即時顯示用）或 `score_serve_records`（歷史查詢用），而不需要修改
本功能本身。
