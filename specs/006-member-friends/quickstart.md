# Quickstart: 會員與好友系統

## 前置準備

```bash
# 本地開發 .env 需設定 EMAIL_BACKEND=log（預設），驗證信/重設信內容會寫入應用程式日誌，
# 從日誌複製連結中的 token 手動測試，不需真實 SMTP/SES 設定。
```

## 情境 1：註冊 → 未驗證登入 → Email 驗證 → 設定暱稱（對應 spec US1）

```bash
curl -s -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" \
  -d '{"email":"tester@example.com","password":"abc12345","confirm_password":"abc12345","turnstile_token":"test-token"}'
```

**預期**：HTTP 201；回傳 `member_id`/`user_number`；日誌出現一封含驗證連結（`/auth/verify-email/{token}`）的信件內容。

```bash
curl -s -X POST http://localhost:8000/auth/login -H "Content-Type: application/json" \
  -d '{"email":"tester@example.com","password":"abc12345"}'
```

**預期**：HTTP 200，成功登入且 `member.verification_status == "unverified"`（未驗證帳號仍可登入，FR-009）。

```bash
TOKEN=$(從日誌複製)
curl -s http://localhost:8000/auth/verify-email/$TOKEN
```

**預期**：HTTP 200 `{"verified": true}`；之後 `GET /members/me` 之 `verification_status` 變為 `"verified"`；若此帳號從未設定過暱稱，前端 MUST 接續導向設定暱稱流程（`PATCH /members/me/nickname`）。

## 情境 2：忘記密碼 → 所有裝置 session 失效（對應 spec US2）

```bash
curl -s -X POST http://localhost:8000/auth/forgot-password -H "Content-Type: application/json" \
  -d '{"email":"tester@example.com"}'
```

**預期**：HTTP 200 `{"sent": true}`（不論帳號是否存在，回應皆相同）；日誌出現重設連結。

```bash
RESET_TOKEN=$(從日誌複製)
curl -s -X POST http://localhost:8000/auth/reset-password/$RESET_TOKEN -H "Content-Type: application/json" \
  -d '{"new_password":"newpass123","confirm_new_password":"newpass123"}'
```

**預期**：HTTP 200；舊 `access_token`/`refresh_token` 之後呼叫任何受保護端點皆回傳 `MEMBER_TOKEN_INVALID`（`token_version` 已 +1）。

## 情境 3：修改密碼保留本裝置（對應 spec US3）

```bash
ACCESS_TOKEN=$(重新登入取得)
curl -s -X PATCH http://localhost:8000/members/me/password -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_password":"newpass123","new_password":"newpass456","confirm_new_password":"newpass456"}'
```

**預期**：HTTP 200，回傳新的 `access_token`/`refresh_token`（本裝置沿用新 token 繼續使用）；舊 `access_token` 立即失效。

## 情境 4：忘記管理 PIN 碼（對應 spec US4）

```bash
# 先以 tester@example.com 登入身份建立一個團（001 端點，帶 Authorization header）
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/forgot-admin-pin \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**預期**：HTTP 200，回傳新 `admin_pin`/`admin_token`；舊管理 Token 立即失效。

## 情境 5：搜尋並發送好友邀請（對應 spec US5、US6）

```bash
curl -s "http://localhost:8000/members/search?user_number=$OTHER_USER_NUMBER" -H "Authorization: Bearer $ACCESS_TOKEN"
curl -s -X POST http://localhost:8000/friends/requests -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" -d "{\"addressee_user_number\":\"$OTHER_USER_NUMBER\"}"
```

**預期**：搜尋回傳 `friendship_status: "none"`；發送成功後 HTTP 201，該會員之後再次搜尋同一使用者編號 MUST 顯示 `"pending_outgoing"`。

## 驗收對照

| Quickstart 情境 | 對應 spec 驗收情境 |
|---|---|
| 1 | US1 #1, #5, #6, #7 |
| 2 | US2 #1, #2 |
| 3 | US3 #5 |
| 4 | US4 #1, #2 |
| 5 | US5 #2 |
