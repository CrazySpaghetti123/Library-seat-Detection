# 雲端部署步驟

上線後的架構：

| 元件 | 平台 | 網址 |
|---|---|---|
| 網頁前端 | GitHub Pages | `https://crazyspaghetti123.github.io/Library-seat-Detection/` |
| 後端（API、即時推播、逾時排程） | Render 免費方案 | `https://seat-system-xxxx.onrender.com`（建立後才知道） |
| 資料庫 | Neon 免費方案 | 只有後端會連線 |
| 偵測端 | 教室的電腦 | 只把座位狀態事件傳到後端，影像不上傳 |

照順序做：**Neon → Render → GitHub Pages → 偵測端**。全程不需要付費。

> **repo 是公開的**：資料庫連線字串、金鑰、管理密碼只能填在 Render 後台或本機環境變數，絕對不要寫進任何檔案或 commit。

---

## 〇、先準備兩組密鑰

在 PowerShell 執行兩次，各記下一組（存在密碼管理工具裡）：

```
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

- 第一組當**偵測端金鑰**（`DETECTION_API_KEY`）：偵測電腦上報座位狀態時使用。
- 第二組當**管理密碼**（`ADMIN_TOKEN`）：開報表頁、用標定工具寫入 ROI 時輸入。

---

## 一、Neon（資料庫）

1. 到 <https://neon.com> 註冊（可直接用 GitHub 帳號登入）。
2. 建立專案：
   - Region 選 **AWS Asia Pacific (Singapore)**，與 Render 同區，延遲最低。
   - Postgres 版本用預設值即可。
3. **把運算上限鎖在 0.25 CU**（重要）：
   - 左側欄最上方的專案／分支選單確認是預設分支（新專案通常叫 `production`，舊專案可能叫 `main`）→ 點左側欄 **Postgres database ›** 展開子選單 → **Computes** → 運算右側的 **Edit**。
   - 建立專案後出現的「onboard your agent」是讓 AI 工具連線 Neon 用的，本專案不需要，直接略過。
   - Autoscaling 的最小值與最大值都設為 **0.25 CU**。
   - Scale to zero（閒置自動暫停）免費方案固定為 5 分鐘，不用調整。
   - 按 **Save** 後會跳出「Endpoint is updated successfully!」，Computes 頁的 Size 顯示 0.25 CU 即完成。
   - 原因：免費方案每月 100 CU-hours，最大值若維持預設，負載一高用量會放大數倍。
4. 取得連線字串：專案首頁 → **Connect**。
   - **取消勾選「Connection pooling」**，使用一般連線。主機名稱**不能**有 `-pooler`。
   - 原因：系統使用的 psycopg 3 會自動使用 prepared statement，和 pooled 連線（PgBouncer）的 transaction 模式衝突。
   - 字串長得像：`postgresql://neondb_owner:密碼@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
   - 直接整串複製即可，系統會自動轉換成需要的格式。
5. 在本機建立資料表與 6 個座位（PowerShell，在專案資料夾）：

   ```
   $env:DATABASE_URL = '貼上 Neon 的連線字串'
   $env:PYTHONIOENCODING = 'utf-8'
   alembic upgrade head
   python scripts/seed_seats.py --reset
   ```

   連線字串**一定要用單引號 `'...'` 包起來**（字串裡有 `&`，沒包會出現「不允許使用 & 符號字元」）。`alembic` 輸出應為 `Context impl PostgresqlImpl`；若顯示 `SQLiteImpl`，代表 `DATABASE_URL` 沒設成功，跑到的是本機 dev.db。

   看到 `總計 6 席` 即完成。之後若要讓這個視窗回到本機資料庫，關掉視窗重開即可。

---

## 二、Render（後端）

1. 到 <https://render.com> 註冊，用 GitHub 帳號登入，並授權 Render 讀取 `Library-seat-Detection` repo。
   - 如果註冊過程要求付款資訊，先停下來告訴我。
2. 右上角 **New** → **Blueprint** → 選 `Library-seat-Detection`。Render 會讀取 repo 裡的 `render.yaml`。
3. 填入標記為需手動設定的三個值：

   | 名稱 | 填入 |
   |---|---|
   | `DATABASE_URL` | Neon 的連線字串（第一節第 4 步） |
   | `DETECTION_API_KEY` | 第〇節的第一組密鑰 |
   | `ADMIN_TOKEN` | 第〇節的第二組密鑰 |

   `SECRET_KEY` 會自動產生；`ALLOWED_ORIGINS`、時區、開館時段（10–20）已寫在 `render.yaml`。
4. 按 **Apply** 開始部署，第一次約 3～5 分鐘。
5. 部署完成後，在服務頁面上方複製網址，例如 `https://seat-system-xxxx.onrender.com`。
6. 用瀏覽器開 `網址/api/health`，看到 `{"ok":true}` 表示後端正常。
   - 直接開後端網址（不加 `/api/...`）會自動轉到 github.io：後端只提供 API，網頁一律由 GitHub Pages 提供（`render.yaml` 的 `FRONTEND_URL`）。
7. 到 **Logs** 確認**沒有**出現「未受保護」的 WARNING。有的話表示某個金鑰沒填到。

之後每次 push 到 main，Render 會自動重新部署。

---

## 三、GitHub Pages（前端）

1. 開 repo 頁面 → **Settings** → **Pages** → Build and deployment 的 **Source** 選 **GitHub Actions**。
2. **Settings** → **Secrets and variables** → **Actions** → **Variables** 分頁 → **New repository variable**：
   - Name：`API_BASE`
   - Value：Render 的網址，例如 `https://seat-system-xxxx.onrender.com`（結尾不要加 `/`）
   - 後端網址不是秘密，用 Variables 即可，不必用 Secrets。
3. **Actions** 分頁 → 左側「部署前端到 GitHub Pages」→ **Run workflow**。
4. 完成後開 `https://crazyspaghetti123.github.io/Library-seat-Detection/`。

之後每次 push 到 main 且 `frontend/` 有變動，就會自動重新發布。

---

## 四、上線檢查

用手機開 github.io 網址，逐項確認：

- [ ] 登入後看到 6 席平面圖，右上角顯示「即時連線中」
- [ ] 預約、報到、取消都正常，即時動態有出現事件
- [ ] 報表頁（網址後面加 `admin.html`）會詢問管理密碼；輸入錯誤會被拒絕，輸入正確後顯示圖表
- [ ] 用電腦執行下列指令，結果應為 **401**（沒帶金鑰被拒絕）：

  ```
  python scripts/simulate_detection.py A1 person_present --api https://seat-system-xxxx.onrender.com
  ```

- [ ] 帶上金鑰再執行一次，結果應為 **200**，平面圖上 A1 變成使用中：

  ```
  python scripts/simulate_detection.py A1 person_present --api https://seat-system-xxxx.onrender.com --api-key 偵測端金鑰
  ```

- [ ] 測完把 A1 還原：送 `seat_vacant`。A1 **不會馬上**變回可預約，要等 `VACANT_THRESHOLD_MINUTES`（預設 5 分鐘）確認人和物品都離開才會釋放，這是正常行為。

---

## 五、偵測端（教室電腦）

在教室電腦的 PowerShell 設定（每開一個新視窗都要重設）：

```
$env:DETECTION_API_KEY = '偵測端金鑰'
$env:ADMIN_TOKEN = '管理密碼'
```

標定 ROI（寫入雲端）：

```
python -m src.detection.calibrate --source 0 --seat A1 A2 A3 B1 B2 B3 --box --api https://seat-system-xxxx.onrender.com
```

啟動偵測：

```
python -m src.detection.detector --source 0 --model yolov8s.pt --api https://seat-system-xxxx.onrender.com --open-hours 10-20
```

- 偵測程式每 10 分鐘呼叫一次 `/api/health`，讓後端在開館時段保持清醒，離席逾時才能準時處理。
- `--open-hours 10-20` 讓心跳只在開館時段送出。**閉館後請關閉偵測程式**，或至少確認心跳只在開館時段送出；否則後端整天醒著，Neon 的免費額度會不夠。

---

## 六、免費額度與休眠

**用量估算**（開館 10:00–20:00，一個月 31 天）：

| 服務 | 預估用量 | 免費額度 | 超過時 |
|---|---|---|---|
| Render | 約 318 小時 | 750 小時／月 | 服務暫停到下個月 |
| Neon | 約 80 CU-hours | 100 CU-hours／月 | 運算暫停到下個月 |

都不會自動扣款。Neon 剩下的額度，大約可容納 240 次閉館時段有人打開網頁、把後端叫醒。

**休眠行為**：

- 後端 15 分鐘沒有收到請求就會休眠，下一個請求要等約 1 分鐘喚醒。
- 這段期間網頁會顯示「伺服器喚醒中，約需一分鐘…」，醒來後自動載入。
- 平面圖開著時每 4 分鐘送一次心跳，有人在看就不會休眠。
- **展示前先打開網頁，等後端醒來再開始。**
- 休眠期間不會處理離席逾時；醒來後的第一次掃描會補處理，計時從原本的離席時間起算。

---

## 七、疑難排解

| 症狀 | 原因與處理 |
|---|---|
| 一直顯示「伺服器喚醒中」，最後變成「暫時無法連線」 | Render 部署失敗或服務暫停 → 到 Render 的 Logs 查看；或 `API_BASE` 填錯 → 修正後重跑 Actions |
| 瀏覽器開發者工具出現 CORS 錯誤 | `ALLOWED_ORIGINS` 必須剛好是 `https://crazyspaghetti123.github.io`，不含路徑、結尾沒有 `/` |
| Render Logs 出現 `password authentication failed` | `DATABASE_URL` 貼錯；到 Neon 重新複製 |
| Render Logs 出現 `prepared statement ... does not exist` | 用了 pooled 連線字串（主機名有 `-pooler`）→ 改用一般連線 |
| 偵測程式記錄「金鑰錯誤」 | `DETECTION_API_KEY` 和 Render 上的不一致；事件會留在 `detection_queue.jsonl`，修正後重啟即補送 |
| 報表頁一直說管理密碼錯誤 | 和 Render 上的 `ADMIN_TOKEN` 不一致；關掉分頁重開再輸入 |
| 登入後過一陣子被登出 | 登入憑證有效期 12 小時，重新以學號登入即可 |

**回到本機展示**：雲端出問題時，本機照舊執行 `uvicorn src.main:app`，開 `http://127.0.0.1:8000` 即可，不受雲端影響。
