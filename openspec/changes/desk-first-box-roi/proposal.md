## Why

2026-11-08 的教室實拍評估（24 張、6 席、兩排）發現：攝影機斜視時，後排座位的 ROI 往畫面下方延伸，會蓋到前排的桌面。坐在桌子遠側的人，下半身被自己的桌子擋住，YOLO 偵測框的底邊（接地點）停在**自己桌面的遠端邊緣**。目前每個座位各自獨立判定，所以前排有人時，同一個接地點也落進後排的 ROI，後排會被誤判為有人。物品放在前排桌上時也有相同問題。

評估工具裡已實作並比較過「立體框選＋桌面優先」：yolov8s 的整體準確率由 73.6%（接地點逐席判定）提升到 81.2%，被遮擋座位由 40% 提升到 100%，走道誤判由 1 次降到 0 次。但這套做法目前只存在於離線評估：後端 API 只接受四點 ROI，實機偵測程式也只會逐席判定。本變更把它接進實際的標定與偵測流程。

## What Changes

- **ROI 格式擴充**：座位 ROI 除了外輪廓 `points`（3 點以上的多邊形），可另外帶 `top`（桌面四角）與 `floor`（桌腳落地的投影）。原有的四點 ROI 仍然有效，不需要重新標定。
- **後端 API**：`PUT /api/seats/{label}/roi` 放寬四點限制，接受立體框選的格式並驗證各欄位的點數。
- **標定工具**：`calibrate.py --box` 可直接寫入後端，不再強制搭配 `--out`。
- **BREAKING**（行為變更，非 API 變更）：偵測程式預設改用**桌面優先**判定：人（接地點）和物品（框中心）都先比對各席的桌面，不在任何桌面時才比對外輪廓；**每個偵測只歸給一席**，多席都符合時取桌面中心最近的一席。
- 偵測程式新增 `--match {desk-first,per-seat}`（預設 `desk-first`），保留舊的逐席判定，供對照實驗與現場回退；`--person-anchor` 只在 `per-seat` 模式下有作用。
- `--show` 畫面同時畫出外輪廓與桌面，方便現場確認標定結果。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `seat-detection`：
  - `ROI Seat Calibration`：ROI 由「四點座標區塊」改為「外輪廓多邊形，可附帶桌面與地板投影」，並新增立體框選的情境。
  - `Person Occupancy Detection`：判定方式改為桌面優先、每個偵測只歸一席；接地點與切回框中心的設定保留，新增前後排重疊的情境。
  - `Idle Belongings Detection`：物品同樣先比對桌面、只歸一席。

## Impact

- `src/controllers/api.py`：`RoiRequest` 結構與驗證規則。
- `src/detection/calibrate.py`：`save_roi()` 送出立體框選格式；`--box` 不再要求 `--out`；讀取既有 ROI 時保留完整結構。
- `src/detection/detector.py`：`fetch_calibrated_seats()` 回傳完整 ROI；`run()` 依 `--match` 選擇判定方式；`--show` 繪圖。
- `tests/`：新增 ROI API 的測試；偵測判定沿用 `assign_layered()` 既有測試並補上實機路徑需要的情境。
- 資料庫：`seats.roi` 本來就是 JSON 欄位，**不需要 migration**。
- 前端、預約與逾時流程不受影響。
- 限制：桌面優先規則是看過這 24 張照片後才定的，需要另拍一組照片驗證，避免只對這批資料有效。
