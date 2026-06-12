# usage-report Delta Specification

## ADDED Requirements

### Requirement: Seat Status History Logging (座位狀態歷史紀錄)

系統 SHALL 將每一次座位狀態變更寫入歷史紀錄表，內容 MUST 包含：座位編號、變更前後狀態、時間戳、變更來源（偵測端／預約系統／逾時釋放／管理者）。歷史紀錄為使用率報表的唯一資料來源。

#### Scenario: Every transition is logged (每次轉換都留紀錄)

- **WHEN** 座位 A1 由 `AVAILABLE` 經預約轉為 `RESERVED`
- **THEN** 歷史紀錄表新增一筆：seat=A1, from=AVAILABLE, to=RESERVED, source=booking, 含時間戳

### Requirement: Usage Rate Report (空間使用率報表)

系統 SHALL 依歷史紀錄產出空間使用率分析，至少包含：各時段（每小時）平均使用率、每日／每週使用率趨勢、尖峰時段、各樓層比較。使用率定義為（`OCCUPIED`＋`RESERVED`＋`AWAY` 的座位時數）÷（總座位開放時數）。

#### Scenario: Hourly usage rate (時段使用率)

- **WHEN** 管理者查詢某日 3 樓自習室的使用率報表
- **THEN** 系統回傳該日每小時的使用率百分比與當日尖峰時段
- **AND** 數值與歷史紀錄表中的狀態區間計算一致

#### Scenario: Empty data handled (無資料時段)

- **WHEN** 查詢的日期區間內沒有任何歷史紀錄
- **THEN** 系統回傳使用率 0% 並標示「該區間無資料」，不得拋出錯誤

### Requirement: Idle-Occupancy Statistics (佔位行為統計)

報表 SHALL 統計佔位行為：佔位逾時釋放事件次數、平均離席時間、佔位率最高的時段與座位，作為管理單位改善空間管理的依據。

#### Scenario: Idle events aggregated (佔位事件彙總)

- **WHEN** 管理者查詢本週佔位行為統計
- **THEN** 系統回傳本週佔位逾時釋放總次數、平均離席時長，以及佔位次數前五名的座位

### Requirement: Report Dashboard and Export (報表檢視與匯出)

管理者 SHALL 能透過網頁儀表板以圖表檢視上述報表，並 MUST 能將查詢結果匯出為 CSV 檔。

#### Scenario: Export to CSV (匯出 CSV)

- **WHEN** 管理者在儀表板選定日期區間並點選「匯出 CSV」
- **THEN** 系統下載包含該區間逐時使用率與佔位統計的 CSV 檔案
