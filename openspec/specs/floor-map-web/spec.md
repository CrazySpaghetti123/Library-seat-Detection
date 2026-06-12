# floor-map-web Specification

## Purpose
提供 RWD 自習室平面圖網頁：依座位狀態著色、WebSocket 即時更新，並作為學生預約座位與接收通知的入口。
## Requirements
### Requirement: Color-Coded Floor Map (狀態著色平面圖)

系統 SHALL 提供自習室平面圖網頁，依資料庫中的座位狀態著色：`AVAILABLE` 為綠色（可預約）、`OCCUPIED` 與 `RESERVED` 為紅色（使用中／已預約）、`AWAY` 為橘色（疑似佔位，不可預約）、`MAINTENANCE` 為灰色（維修中，不可預約）。頁面 MUST 同時顯示該樓層目前可預約座位數。

#### Scenario: Map reflects seat states (平面圖正確著色)

- **WHEN** 學生開啟自習室平面圖頁面，且座位 A1 為 `AVAILABLE`、A2 為 `OCCUPIED`、A3 為 `RESERVED`、A4 為 `AWAY`
- **THEN** 平面圖上 A1 顯示綠色，A2 與 A3 顯示紅色，A4 顯示橘色
- **AND** 頁面顯示目前可預約座位數為 1

### Requirement: Real-Time Map Updates (平面圖即時更新)

座位狀態在資料庫變更後，系統 SHALL 透過 WebSocket 將變更推播給所有開啟平面圖的瀏覽器，頁面 MUST 在 3 秒內反映新狀態，無須使用者手動重新整理。

#### Scenario: Seat state change pushes to browser (狀態變更即時推播)

- **WHEN** 座位 A1 由 `AVAILABLE` 變更為 `RESERVED`
- **THEN** 所有開啟平面圖的瀏覽器在 3 秒內收到推播，A1 由綠色轉為紅色

#### Scenario: Connection drop recovers (斷線自動重連)

- **WHEN** 瀏覽器與伺服器的 WebSocket 連線中斷
- **THEN** 前端自動嘗試重連，重連成功後重新取得全部座位的最新狀態並更新畫面

### Requirement: Booking from the Map (由平面圖預約)

學生 SHALL 能在平面圖上點選綠色座位發起預約；預約時 MUST 以學號識別使用者。非綠色座位 MUST 不可點選預約。

#### Scenario: Reserve via map click (點選綠色座位預約)

- **WHEN** 學生點選綠色座位 A1 並以學號完成預約確認
- **THEN** 系統建立預約紀錄，座位 A1 轉為 `RESERVED`
- **AND** 平面圖上 A1 即時轉為紅色，並向該學生顯示預約成功訊息（含報到期限）

#### Scenario: Non-available seat is not clickable (紅色座位不可預約)

- **WHEN** 學生嘗試點選紅色或橘色座位
- **THEN** 前端不開啟預約對話框，並提示該座位目前不可預約

### Requirement: Responsive Layout (RWD 響應式版面)

平面圖頁面 SHALL 採響應式設計：在桌面與行動裝置（最小 360px 寬）上，座位圖、可用數量與預約操作 MUST 皆可正常顯示與操作。

#### Scenario: Mobile usability (手機操作)

- **WHEN** 學生以 375px 寬的手機瀏覽器開啟平面圖
- **THEN** 平面圖自動縮放至螢幕寬度內，無水平捲軸
- **AND** 座位可正常點選並完成預約流程
