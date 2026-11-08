## ADDED Requirements

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
