## 1. 後端 ROI API

- [x] 1.1 `RoiRequest` 新增選填的 `top`、`floor`，`points` 改為 3～16 點；驗證 `top`／`floor` 剛好 4 點、`floor` 需搭配 `top`、座標為非負整數（design D2）
- [x] 1.2 `set_seat_roi()` 依請求內容存成 `{"points", "top"?, "floor"?}`，未提供的欄位不寫入
- [x] 1.3 新增 `tests/test_roi_api.py`：四點 ROI、立體框選 ROI 皆可儲存並由 `GET /api/seats` 讀回；外輪廓不足 3 點、桌面非 4 點、只有地板投影時回傳 400 且原 ROI 不變；座位不存在回傳 404

## 2. 標定工具

- [x] 2.1 `save_roi()` 接受四點 list 或 `box_record()` 的 dict，dict 原樣送出
- [x] 2.2 移除 `--box` 必須搭配 `--out` 的限制，更新 help 文字
- [x] 2.3 `fetch_existing_rois()` 保留完整 ROI 結構，畫面上以 `roi_polygon()` 取外輪廓顯示

## 3. 偵測程式

- [x] 3.1 `fetch_calibrated_seats()` 回傳完整 ROI（dict），未標定座位照舊記警告並跳過
- [x] 3.2 新增 `--match {desk-first,per-seat}`（預設 `desk-first`）；`desk-first` 搭配 `--person-anchor center` 時以 argparse 回報錯誤（design D3）
- [x] 3.3 `run()` 依模式判定：`desk-first` 每畫格呼叫一次 `assign_layered()`，`per-seat` 沿用逐席 `classify_seat()`（取外輪廓）
- [x] 3.4 `--show` 畫出外輪廓與桌面（桌面用細線），桌面優先模式下判定點固定為接地點
- [x] 3.5 啟動時以 INFO 記錄判定模式，並提示哪些座位沒有桌面資料（以外輪廓代替）
- [x] 3.6 更新 `detector.py` 模組 docstring 的判定規則說明
- [x] 3.7 補測試：`fetch_calibrated_seats()` 同時處理四點與立體框選 ROI；argparse 的模式衝突檢查

## 4. 文件

- [x] 4.1 更新 `docs/technical_architecture.md` 偵測端章節：立體框選、桌面優先與 `--match` 參數
- [x] 4.2 更新 `CLAUDE.md` 偵測與標定指令（`--box` 可直接寫入後端）
- [x] 4.3 `openspec/specs/seat-detection/spec.md` 由 `openspec archive` 套用 delta，不手動編輯
- [x] 4.4 執行 `python -m pytest -q` 與 `openspec validate desk-first-box-roi --strict`

## 5. 驗證

- [x] 5.1 以 2026-11-08 照片集重跑 `scripts/evaluate_photos.py`，確認桌面優先結果與歸檔時一致（yolov8s 81.2%）
  - 2026-11-19 重跑：桌面優先 81.2%、接地點 73.6%、框中心 52.1%（yolov8s），與歸檔時相同
- [x] 5.2 啟動後端，以 `calibrate.py --box` 對照片集的空桌照標定並寫入後端，再以 `detector.py --source <照片或影片> --show` 確認讀到立體框選 ROI、畫面繪出桌面與外輪廓
  - 2026-11-19：以 `calibrate.save_roi()` 將照片集的 6 席立體框選寫入後端，`fetch_calibrated_seats()` 讀回與 rois.json 完全一致；偵測程式以桌面優先啟動、無缺桌面提示；`--show` 畫面輸出確認外輪廓（粗線）與桌面（細線）正確繪出；改由後端讀 ROI 跑評估亦為 81.2%。點選介面本身未改動，未重新手動點選
- [ ] 5.3 另拍一組照片（同教室或不同角度），只跑評估、不改規則，記錄桌面優先與逐席判定的準確率，確認規則不是只對第一批資料有效
