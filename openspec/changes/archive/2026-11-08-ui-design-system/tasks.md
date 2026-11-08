## 1. 設計 token 層

- [x] 1.1 在 `app.css` 建立 `:root` token：品牌色、中性色階、語意色（success/danger/warning/info）、字體堆疊、間距、圓角、陰影、動效時長
- [x] 1.2 覆寫 Bootstrap 的 `--bs-*` 變數（primary、body-bg、body-color、border-radius、font-family），使既有元件自動套用新視覺
- [x] 1.3 為四個座位狀態定義淺色主題色票，取代現行的 Bootstrap 原色
- [x] 1.4 定義 `[data-bs-theme="dark"]` 下的完整 token 覆寫，含深色專用的座位狀態色

## 2. 深色主題（單一主題，見 design D2）

- [x] 2.1 `<html>` 固定 `data-bs-theme="dark"` 並加上 `<meta name="color-scheme" content="dark">`，使原生控制項一併深色
- [x] 2.2 移除主題切換按鈕與初始化 script；token 因無需分支而直接定義於 `:root`
- [x] 2.3 確認四種座位狀態色與白色標籤文字的對比度達 WCAG AA（4.5:1）

## 3. 座位狀態非顏色編碼

- [x] 3.1 `map.js` 的 `render()` 為每個座位額外繪製狀態圖示 `<text>` 節點
- [x] 3.2 `paint()` 依狀態更新圖示字元：AVAILABLE ✓、OCCUPIED/RESERVED ●、AWAY ⏱、MAINTENANCE ✕
- [x] 3.3 `map.html` 的圖例改為同時呈現顏色方塊與狀態圖示
- [x] 3.4 調整座位方塊內標籤與圖示的排版，確保 360px 寬下兩者皆清晰可辨

## 4. 元件與版面

- [x] 4.1 覆寫 navbar 樣式：品牌區、主題切換、導覽連結的視覺層次
- [x] 4.2 覆寫 card / badge / modal / alert / button / form 樣式，統一圓角、陰影、間距
- [x] 4.3 `map.html`：頁首資訊列改為數據卡片呈現（可預約數、連線狀態），提升資訊層次
- [x] 4.4 `login.html`：登入卡片改版，加入系統名稱與說明文字
- [x] 4.5 `dashboard.html`：查詢表單與四個圖表卡片的版面調整，加入 KPI 數據卡片列

## 5. 互動與動效

- [x] 5.1 座位填色加上 `transition`，狀態變更時平滑過渡
- [x] 5.2 WebSocket 推送更新時，對該座位加一次性脈動 class，動畫結束後移除
- [x] 5.3 可點選座位（AVAILABLE）加上明確的 hover/focus affordance
- [x] 5.4 座位加上 tooltip 或 `<title>` 顯示座位編號與狀態文字
- [x] 5.5 所有動效包在 `@media (prefers-reduced-motion: reduce)` 的例外處理中
- [x] 5.6 WebSocket 連線狀態徽章改版：連線中／已連線／斷線重連的視覺區隔更明確

## 6. 圖表主題化

- [x] 6.1 `dashboard.js` 改由 `getComputedStyle` 讀取 CSS 變數取得圖表配色，取代硬編碼色值
- [x] 6.2 圖表軸線、格線、文字顏色改用 token，深色主題下正確呈現
- [x] 6.3 主題切換時重建已有資料的圖表，不重新請求 API

## 7. 毛玻璃表面（design D7）

- [x] 7.1 新增玻璃 token（半透明表面、亮邊、模糊半徑、飽和度）與 body 光暈 token，深淺色各一組
- [x] 7.2 body 加上三層固定 radial-gradient 光暈，作為 `backdrop-filter` 的取樣來源
- [x] 7.3 navbar / card / stat-tile / conn-badge / modal / alert / form control 套用玻璃表面與亮邊
- [x] 7.4 navbar 改為 sticky 置頂，讓內容自其下透出
- [x] 7.5 座位改雙層矩形（毛玻璃底板 + 半透明狀態色），無邊框、文字無描邊（design D8）
- [x] 7.6 `@supports not (backdrop-filter)` 降級為不透明表面
- [x] 7.7 `prefers-reduced-transparency: reduce` 時關閉模糊與透明
- [x] 7.8 行動裝置模糊半徑降為 10px 以控制繪製成本

## 8. 驗證

- [x] 8.1 手動檢查矩陣：桌面／360px 手機 × 四種座位狀態，確認皆正常（2026-11-08 以 Edge 自動化驗收：1280px 與 360px 下四種狀態皆正常、無水平捲動；順帶修正 360px 導覽列「登出」折行、收合標籤遮住最右一行座位）
- [x] 8.2 以灰階模式（或色盲模擬）檢視平面圖，確認四種狀態仍可區分（灰階、紅色盲、綠色盲、藍色盲模擬截圖：四種狀態靠圖示 ✓●⏱✕ 皆可區分；但僅看顏色時，灰階下可預約與維修中、紅綠色盲下可預約與使用中明度接近，辨識依賴圖示）
- [x] 8.3 確認頁面固定以深色呈現，不受系統淺色偏好影響（單一主題，見 design D2）（系統設為淺色偏好下 body 背景仍為 rgb(13,17,23)，重新整理後不變）
- [x] 8.4 執行 `python -m pytest -q` 確認後端測試未受影響
- [x] 8.5 實際操作預約、報到、離席警示流程，確認改版未破壞既有互動（預約 → 報到 → 偵測離席 → 離席警示倒數 → 按「我仍在使用」回復使用中，桌面與手機皆無 JS 錯誤）
