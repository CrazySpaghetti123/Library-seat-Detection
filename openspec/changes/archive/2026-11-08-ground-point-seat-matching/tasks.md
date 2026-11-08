## 1. 偵測端判定邏輯

- [x] 1.1 在 `src/detection/detector.py` 新增錨點常數與 `anchor_point(class_id, x1, y1, x2, y2, person_anchor)` 純函式：人依 `person_anchor` 取底部中心或幾何中心，其餘類別一律取幾何中心
- [x] 1.2 將 `classify_seat()` 的 `detections` 結構由 `(class_id, cx, cy)` 改為 `(class_id, x1, y1, x2, y2)`，並新增 `person_anchor` 參數（預設 `ground`），改為在函式內呼叫 `anchor_point()` 決定比對點
- [x] 1.3 更新 `run()` 中組裝 `detections` 的程式碼，改為傳入完整 bbox，並將 `person_anchor` 一路傳入 `classify_seat()`
- [x] 1.4 更新 `detector.py` 模組 docstring 的判定規則說明，載明人用接地點、物品用框中心

## 2. CLI 與可觀測性

- [x] 2.1 新增 `--person-anchor {ground,center}` 參數，預設 `ground`，help 文字說明用途為對照實驗與現場回退
- [x] 2.2 `--show` 模式下於人的偵測框上標出實際使用的比對點（小圓點），方便現場確認判定依據
- [x] 2.3 啟動時以 INFO 記錄目前採用的錨點模式

## 3. 測試

- [x] 3.1 新增 `tests/test_detection_anchor.py`，測試 `anchor_point()`：人取底部中心、物品取幾何中心、`center` 模式下人取幾何中心
- [x] 3.2 測試「坐姿者框中心溢出 ROI 但接地點在內」→ 判定為 `person_present`（對應 specs 同名 scenario）
- [x] 3.3 測試「前方走道經過者框覆蓋 ROI 但接地點在外」→ 不判定為 `person_present`（對應 specs 同名 scenario）
- [x] 3.4 測試 `person_anchor="center"` 時上述兩情境回到舊行為，確認回退路徑有效
- [x] 3.5 測試物品判定不受 `person_anchor` 影響，仍以幾何中心比對
- [x] 3.6 執行 `python -m pytest -q` 確認既有測試全數通過

## 4. 文件

- [x] 4.1 更新 `docs/technical_architecture.md` 偵測端章節，說明接地點判定與其幾何理由
- [x] 4.2 於偵測端文件補上攝影機架設指引：建議俯角 30~45° 高角度斜視，並說明正俯視與水平視角各自的問題
- [x] 4.3 `openspec/specs/seat-detection/spec.md` 由 `openspec archive` 於歸檔時套用 delta，不手動編輯

## 5. 現場驗證

- [x] 5.1 以標註照片集執行 `scripts/evaluate_photos.py`，取得接地點與框中心的準確率對照（拍攝清單與標註範本見 `scripts/eval_shot_plan.txt`）
  - 2026-11-08 教室實拍 24 張、6 席（俯角約 35~40°）：接地點 63.9% vs 框中心 42.4%（yolov8n）、73.6% vs 52.1%（yolov8s）；「有人」召回率 94~100% vs 25~31%，走道誤判 1 vs 8
- [x] 5.2 若判定仍有偏差，檢查相機俯角是否過低，必要時調整架設角度而非回退規則
  - 俯角足夠，剩餘偏差非角度問題：(1) YOLO 未偵測到物品（COCO 預訓練限制，待場域微調）；(2) 斜視角下後排 ROI 往下延伸蓋到前排桌面，前排的人框底停在自己桌面而被後排重複計入。(2) 以「立體框選＋桌面優先」解決，於後續 change 處理
- [x] 5.3 視實機結果決定是否微調既有座位的 ROI（預期可貼合桌椅輪廓、不再需要向上外擴）
  - 決定：不在此 change 微調四點 ROI；改由後續 change 引入立體框選（多點 ROI，後端 API 需放寬四點限制）
