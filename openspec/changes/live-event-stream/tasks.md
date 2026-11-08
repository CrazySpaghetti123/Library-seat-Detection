## 1. 後端：事件資料露出

- [x] 1.1 `SeatStateService` 的 `on_transition_hooks` 型別註記改為 `Callable[[int, str, str, str, str], None]`，並於 `transition()` 呼叫時多傳 `from_status.value` 與 `source`
- [x] 1.2 `ws.manager.publish_seat_update` 簽章配合擴充，`seat_update` 訊息加入 `from_status` 與 `source` 欄位
- [x] 1.3 新增 `GET /api/seats/events`：讀 `seat_status_logs` 依 `created_at` 倒序，join 座位取得 label，回傳 `{events: [...]}`
- [x] 1.4 `limit` 查詢參數預設 20、上限 100，避免無界查詢

## 2. 前端：事件流面板

- [x] 2.1 `map.html` 新增可收合側欄：預設收合、邊緣停靠展開標籤，平面圖置中
- [x] 2.1b 側欄開關邏輯（展開／收合／Esc 關閉／`localStorage` 記憶）與收合期間的未讀計數
- [x] 2.2 `map.js` 新增 `loadEvents()`，頁面載入時取回近期事件並渲染
- [x] 2.3 `map.js` 新增 `renderEvent()`，歷史與即時事件共用同一套渲染邏輯
- [x] 2.4 WebSocket 收到 `seat_update` 時追加新事件至頂端，超出上限則移除最舊者
- [x] 2.5 來源映射為中文標籤（預約／偵測／逾時／管理），未知來源回退為原始字串
- [x] 2.6 時間以相對時間呈現（「3 分鐘前」），`title` 保留完整時間；naive UTC 需補 `Z` 再轉本地時間
- [x] 2.7 新事件加入短暫進場動畫，包在 `prefers-reduced-motion` 例外中

## 3. 樣式

- [x] 3.1 `app.css` 加入事件流面板樣式，沿用既有玻璃表面與設計 token
- [x] 3.2 狀態徽章沿用座位狀態色，來源標籤各給色票以便掃視
- [x] 3.3 固定高度 + 內部捲動，360px 下正常呈現

## 4. 測試

- [x] 4.1 更新 `tests/test_state_machine.py` 的 `test_transition_hook_invoked`，假 hook 簽章改為五參數並驗證 `from_status` 與 `source` 正確傳入
- [x] 4.2 新增 `GET /api/seats/events` 的測試：回傳順序為新到舊、含必要欄位、`limit` 生效且超出上限被夾住
- [x] 4.3 執行 `python -m pytest -q` 確認全數通過

## 5. 驗證

- [ ] 5.1 實際操作預約 → 確認事件流即時出現對應事件且來源正確
- [ ] 5.2 重新整理頁面 → 確認歷史事件由 API 正確載入且排序正確
- [ ] 5.3 360px 寬下確認事件流版面正常
