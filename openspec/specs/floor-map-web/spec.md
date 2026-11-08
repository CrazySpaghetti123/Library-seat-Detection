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

### Requirement: Non-Color Status Encoding (座位狀態非顏色編碼)

平面圖上的座位狀態 SHALL 除顏色之外，另以至少一種非顏色的視覺屬性（狀態圖示）傳達，使色覺辨識障礙使用者能區分各狀態。圖例 MUST 同時呈現顏色與該非顏色屬性的對應關係。

#### Scenario: Status distinguishable without color (不依賴顏色即可判讀狀態)

- **WHEN** 學生開啟平面圖，且座位 A1 為 `AVAILABLE`、A2 為 `OCCUPIED`、A4 為 `AWAY`、A5 為 `MAINTENANCE`
- **THEN** 每個座位除狀態顏色外另顯示對應的狀態圖示，四種狀態的圖示彼此相異
- **AND** 在僅有灰階、無法辨識色相的情況下仍可由圖示區分出座位狀態

#### Scenario: Legend shows both encodings (圖例呈現雙重編碼)

- **WHEN** 學生檢視平面圖下方的狀態圖例
- **THEN** 圖例中每個狀態同時標示其顏色與狀態圖示

### Requirement: Dark Theme (深色主題)

系統 SHALL 採單一深色主題呈現所有頁面，不提供淺色主題或主題切換。深色主題下，四種座位狀態色彼此 MUST 可區分，且座位標籤文字 MUST 保持可讀。

#### Scenario: Pages render in dark theme regardless of system preference (不受系統偏好影響)

- **WHEN** 使用者的作業系統設定為淺色模式並開啟任一頁面
- **THEN** 頁面仍以深色主題呈現

#### Scenario: Seat states remain legible (座位狀態仍可辨識)

- **WHEN** 頁面呈現平面圖
- **THEN** 四種座位狀態色彼此仍可區分，且座位標籤文字與其底色的對比度足以閱讀

### Requirement: Live Status Event Stream (即時狀態事件流)

平面圖頁 SHALL 以可收合的側欄呈現近期座位狀態變更的事件流，且預設為收合狀態，使平面圖維持為頁面主體。每筆事件 MUST 包含座位編號、變更前後狀態與變更來源（預約／偵測／逾時／管理），並標示發生時間。頁面載入時 MUST 顯示最近的歷史事件；其後收到即時推播時，新事件 MUST 追加至事件流頂端，無須重新整理。

側欄收合期間若有新事件抵達，系統 MUST 於收合標籤上呈現未讀提示。事件流保留的筆數 MUST 有上限，避免長時間開啟造成無限增長。

#### Scenario: Stream is collapsed by default (預設收合)

- **WHEN** 學生初次開啟平面圖頁
- **THEN** 事件流側欄為收合狀態，僅於頁面邊緣顯示可展開的標籤
- **AND** 平面圖置中呈現，不因側欄而偏移

#### Scenario: Expanding reveals the stream (展開後顯示事件流)

- **WHEN** 學生點選事件流的展開標籤
- **THEN** 側欄展開並顯示近期事件，每筆含座位編號、變更前後狀態、來源與發生時間
- **AND** 依時間新到舊排列

#### Scenario: Unread indicator while collapsed (收合期間的未讀提示)

- **WHEN** 事件流側欄為收合狀態，此時有座位狀態變更
- **THEN** 收合標籤上顯示未讀事件數量
- **AND** 學生展開側欄後，未讀提示歸零

#### Scenario: New event appended in real time (即時追加新事件)

- **WHEN** 學生停留在平面圖頁，此時座位 A1 由 `AVAILABLE` 變更為 `RESERVED`
- **THEN** 事件流頂端出現一筆新事件，標示 A1 由可預約轉為已預約、來源為預約
- **AND** 頁面無須重新整理

#### Scenario: Event source is shown in readable form (來源以可讀形式呈現)

- **WHEN** 事件流中有一筆座位因離席逾時而被系統釋放的紀錄
- **THEN** 該筆事件的來源顯示為可理解的中文標示，而非原始的內部識別字串

#### Scenario: Stream length is bounded (事件流長度有上限)

- **WHEN** 平面圖頁持續開啟並累積超過保留上限筆數的事件
- **THEN** 事件流僅保留最新的上限筆數，較舊的事件被移除

