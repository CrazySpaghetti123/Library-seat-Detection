## Why

目前展示層直接使用 Bootstrap 5.3.3 的出廠樣式，`src/views/static/css/app.css` 僅 42 行且只定義座位色票與 SVG 樣式。結果是介面缺乏辨識度、資訊層次扁平，作為專題成果展示不夠完整。

除了觀感之外，現況有一項實質的可用性缺陷：**座位狀態完全依賴顏色傳達**（綠＝可預約、紅＝使用中、橘＝疑似佔位、灰＝維修中）。紅綠色覺辨識障礙約佔男性人口 8%，這些使用者無法可靠區分「可預約」與「使用中」——也就是這個系統最核心的資訊。此外系統無深色模式，自習室常見的低光環境下長時間瀏覽並不友善。

## What Changes

- 建立設計 token 層：品牌色、中性色階、語意色、字體、間距、圓角、陰影、動效時長全部以 CSS 變數定義，取代散落的 Bootstrap 預設值。
- **新增深色模式**：跟隨系統偏好自動切換，並提供手動切換與 `localStorage` 記憶。
- **座位狀態改為不單靠顏色傳達**：每個狀態除顏色外另以圖示標記區分，色覺辨識障礙使用者亦可判讀。
- 覆寫 Bootstrap 元件樣式（navbar、card、badge、modal、alert、button、form），統一視覺語言。
- 座位圖互動升級：狀態變更的顏色過渡與短暫脈動提示、可點選座位的明確 affordance、座位資訊 tooltip。
- 儀表板圖表主題化：Chart.js 配色改用設計 token，並隨深色模式切換；查詢區與統計區改為數據卡片版面。
- RWD 精修至 360px；WebSocket 連線狀態與載入過程改為更明確的視覺回饋。
- 中文字體採系統字體堆疊（`PingFang TC` / `Microsoft JhengHei` / `Noto Sans TC`），不引入網路字體以免拖慢首屏。

不改動任何後端邏輯、API、資料模型與 WebSocket 協定；不引入建置流程（維持 CDN + 靜態檔）。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `floor-map-web`: 新增兩項需求——座位狀態必須另以顏色以外的視覺屬性傳達（無障礙），以及深色／淺色主題支援。既有的著色語意、即時更新、預約互動、RWD 需求維持不變。

## Impact

- `src/views/static/css/app.css`：擴充為完整設計 token 與元件樣式層。
- `src/views/templates/`：`base.html`（主題切換、字體）、`map.html`、`dashboard.html`、`login.html` 的版面結構調整。
- `src/views/static/js/map.js`：座位狀態圖示渲染、變更動效、tooltip。
- `src/views/static/js/dashboard.js`：Chart.js 配色改讀設計 token、主題切換時重繪。
- 不影響 `src/controllers/`、`src/services/`、`src/models/`、資料庫 schema 與偵測端。
- 既有測試不涉及前端樣式，預期全數維持通過。
