## Why

全系統以 naive UTC 儲存時間（`utcnow()`），但報表把「開館 08:00–22:00」與查詢日期直接套在 UTC 時間上。台灣是 UTC+8，所以報表實際統計的是台灣時間 16:00 到隔天 06:00，逐時使用率的「10 時」其實是台灣 18 時。上雲後開館時段將改為 10:00–20:00，報表必須以台灣時間計算才有意義。

報表頁的預設日期也以 UTC 計算，在台灣凌晨 0～8 點開啟時會預設成前一天。

## What Changes

- 新增時區設定 `TIMEZONE`（預設 `Asia/Taipei`）。資料庫仍維持 naive UTC，不改 schema、不轉換既有資料。
- 逐時使用率、每日趨勢、樓層比較、CSV 匯出：查詢日期與開館時段視為當地時間，換算成 UTC 後查詢；小時分組以當地整點為準，回傳的「時」為當地時間。
- 佔位行為統計：查詢的起訖日期以當地日界（00:00～23:59:59）換算成 UTC。
- 報表頁的預設日期改用瀏覽器的當地日期。
- `requirements.txt` 加入 `tzdata`（Windows 沒有系統時區資料庫）。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `usage-report`：`Usage Rate Report` 與 `Idle-Occupancy Statistics` 明定日期、時段與小時皆以設定的當地時區計算。

## Impact

- `src/config.py`、`src/services/report_service.py`、`src/controllers/reports.py`、`src/views/static/js/dashboard.js`、`requirements.txt`。
- `tests/test_reports.py`：既有測試固定在 UTC 下執行（驗證區間切分邏輯不變），另加台灣時區的測試。
- 既有資料不需轉換；報表數字會改變（改為正確的台灣時段）。
