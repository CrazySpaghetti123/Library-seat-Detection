## Context

`seat_status_logs.created_at` 與 `idle_events` 的時間都是 naive UTC（為了 SQLite 與 PostgreSQL 一致）。`ReportService` 以 `datetime.combine(day, time(OPEN_HOUR))` 產生查詢區間，再以 `cursor.replace(minute=0, …)` 切小時桶，兩者都把 UTC 當成當地時間。

## Goals / Non-Goals

**Goals:** 報表的日期、開館時段、逐時分組都以當地時間計算；儲存格式不變。

**Non-Goals:** 不把資料庫改成 timezone-aware；不支援每個樓層不同時區；前端平面圖與事件流的時間顯示本來就由瀏覽器轉為當地時間，不需改動。

## Decisions

### D1：只在報表邊界換算時區

新增兩個轉換函式：當地日期＋時 → naive UTC、naive UTC → 當地 naive 時間。查詢區間在進入 `_busy_seconds_by_hour` 前換成 UTC；切小時桶時把時間轉成當地、取整點，桶的鍵為當地 naive 時間，桶的結束點再換回 UTC 比較。

如此狀態區間的重建邏輯完全不變，只有邊界與分組改為當地時間。即使時區不是整點偏移（如 UTC+5:30），小時桶也對齊當地整點。

**替代方案**：資料庫改存當地時間或 aware datetime。捨棄原因是要轉換既有資料，且 SQLite 不支援時區。

### D2：時區以 IANA 名稱設定

`TIMEZONE=Asia/Taipei`，使用標準函式庫 `zoneinfo`。Windows 沒有系統時區資料庫，加入 `tzdata` 套件。台灣沒有日光節約時間；其他時區在日光節約切換日，該日的小時數可能是 23 或 25，逐時表仍以開館時段的整點列出。

### D3：既有測試固定在 UTC

既有報表測試驗證的是「狀態區間切分」，在 `TIMEZONE=UTC` 下執行，結果與原本相同；另以 `Asia/Taipei` 新增測試，驗證換算。

## Risks / Trade-offs

- **[報表數字改變]** 修正後的數字與先前的報表不同 → 這是更正錯誤；報告中引用的評估結果不受影響（評估使用照片，不使用報表）。
