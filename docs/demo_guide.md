# 啟動與展示指南 (Demo Guide)

從零把系統跑起來、並用「20 秒快速模式」完整演示離席逾時流程的步驟整理。
所有指令都在專案根目錄（`c:\Users\User\Desktop\NTUST\Project`）的 PowerShell 執行。

---

## 一、首次安裝（只需做一次）

```powershell
pip install -r requirements.txt             # Web 後端依賴
pip install -r requirements-detection.txt   # 偵測端依賴（YOLOv8，僅跑偵測的機器需要）
```

---

## 二、選擇資料庫

`DATABASE_URL` 決定用哪顆資料庫，**每開一個新的 PowerShell 視窗都要重新設定**：

```powershell
# 選項 A：PostgreSQL（本機已安裝 18）
$env:DATABASE_URL = 'postgresql+psycopg://postgres:你的密碼@localhost:5432/seatdb'

# 選項 B：SQLite（什麼都不設，自動使用 dev.db）
```

第一次使用某顆資料庫時要先建表＋塞示範座位：

```powershell
alembic upgrade head
python scripts/seed_seats.py    # 12 席（3F，A1–A6、B1–B6）
```

---

## 三、啟動後端（測試用 20 秒快速模式）

**視窗 1**——計時參數以「分鐘」為單位、可用小數，0.33 ≈ 20 秒：

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://postgres:你的密碼@localhost:5432/seatdb'

# 20 秒快速模式（正式預設值：15 / 10 / 30 / 5 分鐘）
$env:AWAY_THRESHOLD_MINUTES   = '0.33'   # 離席 20 秒 → 轉 AWAY 並發提示
$env:CONFIRM_WINDOW_MINUTES   = '0.33'   # 提示後 20 秒未確認 → 釋放
$env:VACANT_THRESHOLD_MINUTES = '0.33'   # 人與物品皆離開 20 秒 → 直接釋放
$env:CHECKIN_DEADLINE_MINUTES = '1'      # 預約後 1 分鐘內要報到
$env:SCHEDULER_INTERVAL_SECONDS = '5'    # 排程每 5 秒掃描（預設 15 秒，調短讓觸發更即時）

uvicorn src.main:app --reload
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即啟動成功，此視窗保持開啟。

> 手機要連的話改用 `uvicorn src.main:app --host 0.0.0.0`，
> 手機瀏覽器開 `http://電腦IP:8000`（兩台裝置須在同一 Wi-Fi）。

> **本分支（feature/nodejs-socketio-gateway）需另開視窗 1.5 啟動 Node 即時推播閘道**，見下節。

---

## 三之二、啟動 Node.js + Socket.IO 閘道（僅本分支）

本分支的即時推播由獨立的 Node 服務承載，FastAPI 以 HTTP 通知它。
**視窗 1.5**（首次需先 `npm install`）：

```powershell
cd node-gateway
npm install            # 首次安裝（express + socket.io）
node server.js         # 啟動於 3001 埠，視窗保持開啟
```

看到「即時推播閘道已啟動：http://0.0.0.0:3001」即成功。前端會自動連到
`頁面主機:3001`，本機與手機經 IP 連線皆適用（手機需防火牆放行 TCP 3001）。

- 三服務關係：瀏覽器 ─Socket.IO→ Node(3001)；瀏覽器/偵測端 ─HTTP→ FastAPI(8000)；
  FastAPI 狀態變更 ─HTTP POST→ Node ─Socket.IO→ 瀏覽器。
- 整合測試（後端＋閘道皆啟動、A1 為 AVAILABLE 時）：
  `cd node-gateway; npm install; node test_fullchain.mjs` → 應印出 `PASS`。
- 閘道環境變數：`GATEWAY_PORT`（預設 3001）、`GATEWAY_SECRET`（需與 FastAPI 的
  `GATEWAY_SECRET` 一致，預設皆為 `dev-gateway-secret`）。

---

## 四、展示流程（不需攝影機，用模擬器）

**視窗 2**——瀏覽器先開 `http://127.0.0.1:8000`，輸入學號登入：

| 步驟 | 操作 | 預期畫面 |
|---|---|---|
| 1 | 瀏覽平面圖 | 12 席全綠、「可預約：12 席」 |
| 2 | 點綠色座位 A1 → 確認預約 | A1 變紅，顯示報到期限 |
| 3 | `python scripts/simulate_detection.py A1 person_present` | 自動報到，「我的預約」變「使用中」 |
| 4 | `python scripts/simulate_detection.py A1 person_left_belongings` | （開始離席計時，畫面暫無變化） |
| 5 | 等約 20–25 秒 | A1 變橘，跳出離席警示橫幅＋「我仍在使用」＋倒數 |
| 6a | 按「我仍在使用」 | A1 回紅，計時重新開始（會再次提示） |
| 6b | 或什麼都不做再等約 20–25 秒 | A1 變回綠色，收到「座位已被釋放」通知 |
| 7 | 開 `http://127.0.0.1:8000/admin/reports` | 使用率圖表與佔位統計反映剛剛的活動 |

其他可模擬的事件：

```powershell
python scripts/simulate_detection.py A1 person_present           # 人（重新）入座
python scripts/simulate_detection.py A1 person_left_belongings   # 人離開、物品還在
python scripts/simulate_detection.py A1 seat_vacant              # 人和物品都離開
```

---

## 五、測試後重置

座位狀態存在資料庫，重啟 uvicorn 不會消失（刻意設計：伺服器重啟不中斷計時）。
想一鍵歸零（清空預約／事件／通知／歷史，座位全部回綠）：

```powershell
$env:DATABASE_URL = '同視窗 1 的設定'   # 確保重置到同一顆資料庫
python scripts/reset_seats.py
```

---

## 六、接攝影機跑真實偵測

```powershell
# 1. 標定座位 ROI（--source 0 = 內建/第一支攝影機，也可給影片路徑）
#    操作：點四個角點框住「椅子＋桌面」 → 按 s 儲存、r 重來、q 離開
python -m src.detection.calibrate --source 0 --seat A1

# 2. 啟動偵測迴圈（按 q 離開）
python -m src.detection.detector --source 0 --show --hold 2 --conf 0.25 --model yolov8s.pt
```

| 參數 | 預設 | 說明 |
|---|---|---|
| `--hold` | 5 | 去抖動秒數，測試時調短至 2 反應更快 |
| `--conf` | 0.35 | 偵測信心門檻，物品認不到時調低（再低會開始誤判） |
| `--model` | yolov8n.pt | 換 `yolov8s.pt` 辨識力較好（首次自動下載約 22MB） |

`--show` 畫面解讀：**ROI 框**紅＝有人、橘＋`[IDLE?]`＝疑似佔位、綠＝空位；
**偵測框**白＝人、黃＝物品（標類別與信心分數，調試辨識問題看這裡）。

**測試道具建議**（COCO 預訓練模型的視角限制）：

- ✅ 可靠：**水壺／杯子**留桌上、**筆電**、立著且光線充足的背包
- ❌ 認不到：平放的手機、攤平的背包、桌上的書——屬預訓練資料視角差異，
  正式部署前以實際場域影像微調模型解決（roadmap 第二學期項目）
- 就算物品漏判，人離開後仍會走「淨空釋放」路徑，座位不會卡死

偵測端只透過 HTTP 與後端溝通，後端離線時事件會暫存 `detection_queue.jsonl`，
恢復後自動補送。

> 家中單座位測試：`python scripts/_setup_home_seat.py` 會把座位主檔換成單一
> A1（HOME 樓層、平面圖置中）；要恢復 12 席示範環境見第七節常見問題。

---

## 七、常見問題

- **環境變數沒生效**：`$env:` 只屬於當前視窗，開新視窗要重設；Ctrl+C 後在同一視窗重啟則仍有效。
- **重啟後座位還是紅的**：正常，狀態在資料庫（見「五、測試後重置」）。
- **主控台中文亂碼**：執行前 `$env:PYTHONIOENCODING='utf-8'`（cp950 主控台限制）。
- **跑單元測試**：`python -m pytest -q`（測試固定用 in-memory SQLite，不會動到你的資料）。
- **恢復 12 席示範環境**（單座位測試後）：psql 執行 `TRUNCATE bookings, idle_events, notifications, seat_status_logs; DELETE FROM seats;` 再跑 `python scripts/seed_seats.py`。
- **手機連不上**：確認用電腦的區網 IP（`ipconfig` 查）、uvicorn 加 `--host 0.0.0.0`；Windows 防火牆需放行 TCP 8000（公用網路預設封鎖進入連線）。
