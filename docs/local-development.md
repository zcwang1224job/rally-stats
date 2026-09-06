# 本地端啟用 API 與 Web 服務操作手冊（Docker Compose）

本文件說明如何用 **Docker Compose** 一次啟動 Rally Stats 的資料庫
（PostgreSQL）、後端（`apps/api`，FastAPI）與前端（`apps/web`，Angular 20 +
Nginx），並正確設定容器啟動時需要的環境變數。

## 目錄

1. [前置需求](#1-前置需求)
2. [設定環境變數](#2-設定環境變數)
3. [建置並啟動所有服務](#3-建置並啟動所有服務)
4. [初始化資料庫（一次性）](#4-初始化資料庫一次性)
5. [驗證服務](#5-驗證服務)
6. [環境變數詳細說明](#6-環境變數詳細說明)
7. [常用操作](#7-常用操作)
8. [執行測試與程式碼品質檢查（非 Docker）](#8-執行測試與程式碼品質檢查非-docker)
9. [常見問題排解](#9-常見問題排解)
10. [讓區網（LAN）內其他裝置存取](#10-讓區網lan內其他裝置存取)

---

## 1. 前置需求

| 工具 | 版本要求 | 用途 |
|---|---|---|
| Docker（含 Docker Compose v2） | 任意近期版本 | 啟動資料庫、後端、前端三個服務 |

```bash
docker --version
docker compose version
```

跑測試與 lint（第 8 節）另需要本機安裝 Python 3.12 與 Node 20——測試/型別
檢查工具鏈目前沒有容器化，仍須在本機虛擬環境中執行。

---

## 2. 設定環境變數

後端所有必要環境變數集中在 `apps/api/.env`（`docker-compose.yml` 透過
`env_file` 讀取，並在其中把 `DATABASE_URL` 覆寫為指向 Docker 網路內的 `db`
服務，其餘變數原樣傳入 `backend` 容器）：

```bash
cd apps/api
cp .env.example .env
```

`.env.example` 內有 6 個必要變數，其中 2 個**必須**自行產生真正隨機的值
（其餘可直接沿用範例中的測試用值）：

```bash
# JWT_SECRET
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# PASSWORD_ENCRYPTION_KEY（32 bytes，base64 編碼）
python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

把兩個指令的輸出分別貼到 `.env` 的 `JWT_SECRET=` 與
`PASSWORD_ENCRYPTION_KEY=`。每個變數的完整說明見
[第 6 節](#6-環境變數詳細說明)。

`.env` 已被 `.gitignore` 排除，不會被提交到版本控制。

前端唯一需要的環境變數是 `TURNSTILE_SITE_KEY`，由 `infra/docker-compose.yml`
在 `frontend` 服務啟動時代入（預設值是 Cloudflare 保證永遠通過驗證的測試
金鑰，本機開發通常不需要另外設定）。若要覆寫，可在 `infra/` 目錄下建立
`.env`：

```bash
# infra/.env（選用，僅需要真實 Turnstile 金鑰時才建立）
TURNSTILE_SITE_KEY=<你的真實 Turnstile site key>
```

---

## 3. 建置並啟動所有服務

```bash
cd infra
docker compose up -d --build
```

第一次執行會依序建置 `backend`（Python 3.12 + 安裝套件）與
`frontend`（Node 20 建置 Angular production bundle，再打包進 Nginx image）
兩個映像檔，並啟動全部三個容器。之後若原始碼沒有變動，可省略 `--build`
直接 `docker compose up -d`。

確認三個容器皆已啟動且健康：

```bash
docker compose ps
```

預期會看到 `db`、`backend`、`frontend` 三個服務皆為 `Up`（`db`、`backend`
兩者有 healthcheck，狀態會顯示 `healthy`）。

---

## 4. 初始化資料庫（一次性）

`docker compose up` 只會啟動服務，**不會自動執行資料庫 migration**。首次
啟動（或每次新增 migration 後）都需要手動在 `backend` 容器內執行一次：

```bash
docker exec infra-backend-1 alembic upgrade head
```

確認目前版本已是最新：

```bash
docker exec infra-backend-1 alembic current
```

> 容器名稱格式為 `<compose 專案名>-<服務名>-1`；若你的專案資料夾名稱不是
> `rally-stats`（Compose 專案名預設取自資料夾名稱），容器名稱前綴會不同，
> 可先用 `docker compose ps` 確認實際容器名稱。

---

## 5. 驗證服務

```bash
# 後端健康檢查
curl http://localhost:8000/health
# 預期: {"status":"ok"}

# 前端首頁
curl -o /dev/null -s -w "%{http_code}\n" http://localhost:4200/
# 預期: 200

# 前端 -> 後端的 /api 反向代理（瀏覽器實際呼叫的路徑）
curl http://localhost:4200/api/health
# 預期: {"status":"ok"}
```

瀏覽器開啟 `http://localhost:4200`，前端所有 API 請求都會打到同源的
`/api/...`，由 `frontend` 容器內的 Nginx 反向代理轉給 `backend` 容器（見
`apps/web/nginx.conf` 的 `location /api/` 區塊），瀏覽器端不需要處理跨來源
（CORS）問題。

互動式 API 文件（Swagger UI）：`http://localhost:8000/docs`（直接對後端
容器的對外 port，不經過前端代理）。

---

## 6. 環境變數詳細說明

| 變數 | 傳入方式 | 說明 | 本機開發建議值 |
|---|---|---|---|
| `DATABASE_URL` | `docker-compose.yml` 的 `environment:` 覆寫 | PostgreSQL 非同步連線字串 | 已固定指向 Docker 網路內的 `db` 服務，通常不需調整 |
| `JWT_SECRET` | `apps/api/.env`（`env_file`） | 簽發管理員 / 會員 Token 的簽章密鑰 | 第 2 節指令產生的隨機字串 |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | 後端走 `apps/api/.env`；前端走 `docker-compose.yml` 的 `environment:`（見下方說明） | Cloudflare Turnstile 人機驗證金鑰 | 兩邊都直接沿用 Cloudflare 官方測試金鑰 `1x00000000000000000000AA` / `1x0000000000000000000000000000000AA`，保證永遠通過驗證 |
| `PASSWORD_ENCRYPTION_KEY` | `apps/api/.env`（`env_file`） | 團通關密碼可還原加密用的 AES-256-GCM 金鑰（32 bytes，base64） | 第 2 節指令產生的隨機值，**不可**留用範例字面字串 |
| `ABLY_API_KEY` | `apps/api/.env`（`env_file`） | Ably 即時通訊服務金鑰 | 若需要驗證即時同步功能（計分板/控制板/戰績即時更新），需一組真實金鑰（見下方）；否則填任意 `xxx.yyy:zzz` 格式的假值即可，服務仍會正常啟動，只是即時事件發布會失敗（被記錄但不影響其他 API 行為） |

### 前端 `TURNSTILE_SITE_KEY` 如何生效

前端的 production build（`environment.prod.ts`）在編譯時把 Turnstile site
key 寫成佔位字串 `__TURNSTILE_SITE_KEY__`，因為這個值屬於「執行環境」而非
「編譯期」的設定。`frontend` 容器啟動時，`apps/web/docker-entrypoint.sh`
會在 Nginx 真正開始服務前，把打包好的 JS 檔案中所有
`__TURNSTILE_SITE_KEY__` 取代成 `TURNSTILE_SITE_KEY` 環境變數的值——這也是
`docker-compose.yml` 需要在 `frontend` 服務裡宣告這個變數的原因。

### 取得真實 `ABLY_API_KEY`（選用）

1. 前往 [ably.com](https://ably.com/) 註冊免費帳號並建立一個 App。
2. 在該 App 的 **API Keys** 頁面複製任一組金鑰（格式類似
   `AbCdEf.GhIjKl:MnOpQrStUvWxYz`）。
3. 貼到 `apps/api/.env` 的 `ABLY_API_KEY=`，然後重新啟動 `backend` 容器
   （`docker compose restart backend`）讓新設定生效。

---

## 7. 常用操作

```bash
cd infra

# 查看 log（加 -f 持續追蹤）
docker compose logs backend
docker compose logs -f frontend

# 修改 apps/api 或 apps/web 原始碼後，重新建置並套用
docker compose up -d --build backend
docker compose up -d --build frontend

# 只重啟某服務（例如改了 .env 之後）
docker compose restart backend

# 停止所有服務（保留資料庫資料的 volume）
docker compose down

# 停止並清除資料庫資料（會清空 PostgreSQL 資料，需要重新走一次第 4 節）
docker compose down -v
```

---

## 8. 執行測試與程式碼品質檢查（非 Docker）

測試套件與 lint/型別檢查工具鏈目前未容器化，仍需要本機的 Python
虛擬環境與 Node 套件：

### 後端

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 測試會用到獨立的 rally_stats_test 資料庫（首次需手動建立一次）：
docker exec infra-db-1 psql -U rally -d postgres -c "CREATE DATABASE rally_stats_test;"

python -m pytest -q          # 完整測試套件（自動對 rally_stats_test 跑 migration）
ruff check app tests         # lint
mypy app                     # 型別檢查（strict mode）
```

> 上述指令假設 `infra-db-1`（第 3 節啟動的 PostgreSQL 容器）仍在執行——測試
> 資料庫與 Docker Compose 的 `db` 服務是同一個 PostgreSQL 執行個體，只是
> 資料庫名稱不同。

### 前端

```bash
cd apps/web
npm install
npm test                     # Vitest 單元測試
npm run lint                 # ESLint
npm run build                # 正式建置（驗證編譯無誤）
```

---

## 9. 常見問題排解

**`docker compose up` 之後呼叫 API 出現 `relation "..." does not exist`**
忘記執行第 4 節的一次性 migration。每次拉新 commit 後若有新增 migration，
都需要重跑 `docker exec infra-backend-1 alembic upgrade head`。

**改了 `apps/api` 或 `apps/web` 的程式碼，但容器裡的行為沒有變化**
`backend`/`frontend` 容器目前都是把程式碼「編譯進映像檔」的方式運作
（`frontend` 是 production build 產物；`backend` 雖然掛了原始碼 volume，
但 `gunicorn` 沒有開啟熱重載），改完程式碼需要
`docker compose up -d --build <service>` 重新建置才會生效。若要邊改邊測、
即時看到程式碼變化（不需每次重新建置映像檔），可改為在本機直接執行
`uvicorn app.main:app --reload`（後端，第 8 節已建好的 venv）與
`ng serve`（前端），並沿用第 3 節 Docker 啟動的 PostgreSQL（`db` 服務）
作為資料庫；本文件的 Docker 流程則較適合驗證「完整部署情境下服務是否
正常」。

**前端打 API 出現 404 或連不上**
確認 `apps/web/nginx.conf` 有 `location /api/` 的 proxy 設定（本文件版本
已包含）；若你自行改過 `nginx.conf` 或 `Dockerfile`，需要
`docker compose up -d --build frontend` 讓改動生效。

**Turnstile 驗證元件在畫面上顯示錯誤 / 一直無法通過**
確認 `docker compose ps` 看到的 `frontend` 容器是用本文件版本的
`Dockerfile`/`docker-entrypoint.sh` 建置的（舊映像檔可能還殘留
`__TURNSTILE_SITE_KEY__` 佔位字串未被取代）；用
`docker compose up -d --build frontend` 重新建置。

**Ably 即時同步沒有反應（但其餘功能正常）**
確認 `apps/api/.env` 的 `ABLY_API_KEY` 是否為第 6 節取得的真實金鑰；若填的
是假值，`backend` 容器 log（`docker compose logs backend`）會看到
`AblyAuthException: ... no application id found in request`，這是預期
行為，不代表服務啟動失敗。

**`bcrypt` 相關 Warning（`(trapped) error reading bcrypt version`）**
已知的 `passlib`/`bcrypt` 版本相容性警告，不影響功能，可忽略。

**Port 已被占用（`8000`、`4200` 或 `5432`）**
修改 `infra/docker-compose.yml` 對應服務的 `ports:` 對外 port（冒號左邊
的數字），例如把 `"8000:8000"` 改成 `"8001:8000"`；記得同步調整
`apps/web/environment.prod.ts` 之外若有寫死 port 的地方。

---

## 10. 讓區網（LAN）內其他裝置存取

`frontend`（`4200`）與 `backend`（`8000`）兩個服務的 `ports:` 都是
`"HOST:CONTAINER"` 的簡寫格式，Docker 預設就會把 host port 綁定在
`0.0.0.0`（所有網路介面），**不需要修改 `docker-compose.yml` 就已經能從
同一個區網內的其他裝置連到**
`http://<這台主機的區網 IP>:4200`。`db`（`5432`）則刻意改成只綁定
`127.0.0.1`（見 `infra/docker-compose.yml` 內註解）——`backend` 是透過
Docker 內部網路以服務名稱 `db` 連線，不需要對外開放，開放只會讓區網內任何
人都能嘗試連進這組開發用的 Postgres（帳密是明碼的 `rally`/`rally_dev`）。

真正會擋住區網裝置的，是後端設定裡兩個寫死 `localhost` 的地方，需要在
`apps/api/.env` 加上（或取消註解）這兩個變數，換成這台主機的區網 IP：

```bash
# 先找出這台主機的區網 IP（macOS）：
ipconfig getifaddr en0        # Wi-Fi；有線網路通常是 en1，可用
                              # `ifconfig | grep 'inet 192\.'` 找出正確介面

# 加進 apps/api/.env（假設區網 IP 是 192.168.1.50）：
FRONTEND_BASE_URL=http://192.168.1.50:4200
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://192.168.1.50:4200
```

| 變數 | 影響範圍 | 不設定會發生什麼 |
|---|---|---|
| `FRONTEND_BASE_URL` | 註冊驗證信、忘記密碼信、好友邀請等信件內連結的網域 | 信件連結仍是 `http://localhost:4200/...`，在其他裝置上打開會連不到，只有寄信這台主機自己能點開 |
| `CORS_ALLOWED_ORIGINS` | 瀏覽器直接呼叫 `backend` 對外 port（`8000`）時的來源檢查 | 前端主要流程不受影響（`/api/...` 是透過 `frontend` 容器內 Nginx 同源代理，見第 5 節），但若要從其他裝置直接打 `http://192.168.1.50:8000/docs` 之類的網址測 API，跨來源請求會被擋下 |

改完 `.env` 後重啟後端讓設定生效（不需要重新 build，這兩個都是執行期讀取
的環境變數）：

```bash
cd infra
docker compose restart backend
```

驗證（從另一台裝置的瀏覽器，或用 `curl` 從另一台機器）：

```bash
curl http://192.168.1.50:4200/           # 前端首頁
curl http://192.168.1.50:4200/api/health # 前端 -> 後端 proxy
```

**macOS 防火牆**：如果上述從其他裝置測試仍然連不上（同區網內 `ping` 得到
主機、但連不到這兩個 port），檢查「系統設定 → 網路 → 防火牆」是否開啟了
「封鎖所有連入連線」；Docker Desktop 的連入連線需要防火牆允許才能被區網
其他裝置存取，這一步在 `docker-compose.yml` 或應用程式碼裡都無法解決。
