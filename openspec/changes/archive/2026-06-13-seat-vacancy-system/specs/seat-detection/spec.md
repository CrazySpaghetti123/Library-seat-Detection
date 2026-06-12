# seat-detection Delta Specification

## ADDED Requirements

### Requirement: ROI Seat Calibration (座位區域標定)

系統 SHALL 提供座位區域標定機制：每個座位對應攝影機畫面中的一個 ROI（四點座標區塊），標定結果 MUST 與資料庫中的座位編號一一對應並可持久化保存。

#### Scenario: Define ROI for a seat (為座位定義 ROI)

- **WHEN** 管理者在標定工具中為座位 A1 框選畫面上的四點座標區塊並儲存
- **THEN** 系統將該 ROI 與座位 A1 綁定並寫入設定檔／資料庫
- **AND** 後續偵測流程依此 ROI 判定座位 A1 的狀態

#### Scenario: Reject detection without calibration (未標定不得偵測)

- **WHEN** 偵測程式啟動時發現某攝影機畫面尚無任何 ROI 標定
- **THEN** 系統記錄警告並跳過該畫面的座位判定，不得產生任意狀態變更

### Requirement: Person Occupancy Detection (人員入座偵測)

系統 SHALL 使用 YOLOv8 偵測畫面中的「人」，當偵測框中心點落在某座位的 ROI 內且持續超過去抖動門檻（預設連續 5 秒）時，MUST 將該座位實際狀態判定為「有人使用」。

#### Scenario: Person sits down (偵測到人入座)

- **WHEN** YOLOv8 在座位 A1 的 ROI 內連續 5 秒以上偵測到「人」
- **THEN** 系統將座位 A1 判定為有人使用，狀態更新為 `OCCUPIED`
- **AND** 寫入一筆狀態變更紀錄（時間戳、來源為偵測端）

#### Scenario: Brief occlusion does not flip state (短暫遮擋不誤判)

- **WHEN** 座位 A1 為 `OCCUPIED`，且「人」的偵測僅中斷少於去抖動門檻（如有人走過遮擋鏡頭 2 秒）
- **THEN** 座位 A1 的狀態維持 `OCCUPIED` 不變，不產生狀態變更紀錄

### Requirement: Idle Belongings Detection (疑似佔位偵測)

系統 SHALL 辨識「人已離開但物品（背包、筆電、書本等）仍在 ROI 內」的情形，並將其標記為疑似佔位事件，作為離席逾時計時（seat-timeout）的觸發來源。

#### Scenario: Person leaves but belongings remain (人離開、物品仍在)

- **WHEN** 座位 A1 為 `OCCUPIED`，YOLOv8 連續 5 秒以上未在 ROI 內偵測到「人」，但仍偵測到「背包／筆電／書本」等物品
- **THEN** 系統發出「疑似佔位開始」事件（含座位編號與離席起始時間）給逾時處理流程
- **AND** 在偵測畫面上以明顯標記（如橘色框與文字）標示該座位為疑似佔位

#### Scenario: Person and belongings both gone (人與物品皆離開)

- **WHEN** 座位 A1 為 `OCCUPIED`，且 ROI 內連續 5 秒以上偵測不到「人」也偵測不到任何物品
- **THEN** 系統發出「座位已淨空」事件給逾時處理流程

### Requirement: State Change Synchronization (狀態變更同步)

偵測端 SHALL 只在座位判定結果發生變化時更新資料庫，並且每次更新 MUST 同時寫入狀態歷史紀錄（供使用率報表使用）。

#### Scenario: Only changed states are written (僅變更時寫入)

- **WHEN** 連續多個偵測週期中座位 A1 的判定結果皆為「有人使用」且資料庫已是 `OCCUPIED`
- **THEN** 系統不重複寫入資料庫，僅更新記憶體中的最後偵測時間

#### Scenario: Detection survives database outage (資料庫斷線重試)

- **WHEN** 偵測端寫入資料庫失敗（連線中斷）
- **THEN** 偵測流程不得中止，狀態變更進入待送佇列並於連線恢復後依序補寫
