## 1. 時區換算

- [x] 1.1 `config.py` 新增 `TIMEZONE`（預設 `Asia/Taipei`）；`requirements.txt` 加入 `tzdata`
- [x] 1.2 `report_service.py` 新增當地↔UTC 換算函式；`hourly_usage`、`daily_trend` 的查詢區間改為當地開館時段換算成 UTC
- [x] 1.3 `_accumulate` 以當地整點切小時桶（桶鍵為當地時間），逐時表以當地小時查詢
- [x] 1.4 `idle_stats` 的呼叫端（`reports.py`、`usage_csv`）以當地日界換算 UTC

## 2. 前端

- [x] 2.1 `dashboard.js` 預設日期改用瀏覽器當地日期

## 3. 測試

- [x] 3.1 既有 `tests/test_reports.py` 固定在 `TIMEZONE=UTC` 執行，結果不變
- [x] 3.2 新增台灣時區測試：逐時使用率（對應 spec「Hours follow local time」）、開館時段外不計入、每日趨勢、佔位統計日界（對應「Day boundary follows local time」）、CSV 的小時欄為當地時間
- [x] 3.3 執行 `python -m pytest -q` 與 `openspec validate report-local-timezone --strict`
