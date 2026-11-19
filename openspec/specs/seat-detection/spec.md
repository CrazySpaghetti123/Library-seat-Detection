# seat-detection Specification

## Purpose
以 YOLOv8 + ROI 影像偵測判定每個座位的實際使用狀態（有人／空位／物品佔位），經去抖動後將狀態變化同步至後端。
## Requirements
### Requirement: ROI Seat Calibration (座位區域標定)

系統 SHALL 提供座位區域標定機制：每個座位對應攝影機畫面中的一個 ROI，標定結果 MUST 與資料庫中的座位編號一一對應並可持久化保存。

ROI 由**外輪廓**（3 點以上的多邊形）構成，並可附帶**桌面**（四點）與**地板投影**（四點）。地板投影 MUST 與桌面一併提供。只有外輪廓的四點 ROI 仍為有效標定。

系統 SHALL 提供立體框選：管理者依序點選桌面四角與兩支前腳的落地點，系統推算後腳落點，並以桌面與地板投影的凸包作為外輪廓。

#### Scenario: Define ROI for a seat (為座位定義 ROI)

- **WHEN** 管理者在標定工具中為座位 A1 框選畫面上的四點座標區塊並儲存
- **THEN** 系統將該 ROI 與座位 A1 綁定並寫入資料庫
- **AND** 後續偵測流程依此 ROI 判定座位 A1 的狀態

#### Scenario: Box calibration for a seat (立體框選座位)

- **WHEN** 管理者以立體框選為座位 A1 點選桌面四角與兩支前腳落地點並儲存
- **THEN** 系統將外輪廓、桌面與地板投影一併寫入座位 A1 的 ROI
- **AND** 後續偵測流程可使用桌面區域進行桌面優先判定

#### Scenario: Reject malformed ROI (拒絕格式錯誤的 ROI)

- **WHEN** 標定請求的外輪廓少於 3 點，或桌面、地板投影不是剛好 4 點，或只提供地板投影而沒有桌面
- **THEN** 系統拒絕該請求並回傳錯誤，座位原有的 ROI 保持不變

#### Scenario: Reject detection without calibration (未標定不得偵測)

- **WHEN** 偵測程式啟動時發現某攝影機畫面尚無任何 ROI 標定
- **THEN** 系統記錄警告並跳過該畫面的座位判定，不得產生任意狀態變更

### Requirement: Person Occupancy Detection (人員入座偵測)

系統 SHALL 使用 YOLOv8 偵測畫面中的「人」，並以偵測框的**底部中心點（接地點，即框底邊中點）**作為該人所在位置的判定點；當該接地點被歸屬到某座位且持續超過去抖動門檻（預設連續 5 秒）時，MUST 將該座位實際狀態判定為「有人使用」。

採用接地點而非框幾何中心的理由是：ROI 定義於座位上，而人為立體物件，在非正俯視的攝影機視角下框的幾何中心會沿透視方向偏離座位，且偏移量隨座位與相機的距離而變。

系統預設以**桌面優先**決定接地點歸屬的座位：

- 先比對各座位的桌面；不在任何桌面內時，才比對各座位的外輪廓。
- **每個偵測只歸屬一個座位**；同時符合多個座位時，取桌面中心距離最近的座位。
- 座位的 ROI 沒有桌面時，以外輪廓代替桌面。

理由是斜視角下人坐在桌子遠側時，下半身被自己的桌子遮擋，偵測框底邊停在自己桌面的遠端邊緣；而後排座位的外輪廓會向畫面下方延伸並覆蓋前排桌面，若各座位獨立判定，同一個人會被重複計入。

系統 SHALL 提供設定選項切換為**逐席判定**（各座位獨立比對外輪廓，不做唯一歸屬）；在逐席判定下，可再將人的判定點切換回框幾何中心。

#### Scenario: Person sits down (偵測到人入座)

- **WHEN** YOLOv8 連續 5 秒以上偵測到「人」，且其接地點歸屬於座位 A1
- **THEN** 系統將座位 A1 判定為有人使用，狀態更新為 `OCCUPIED`
- **AND** 寫入一筆狀態變更紀錄（時間戳、來源為偵測端）

#### Scenario: Brief occlusion does not flip state (短暫遮擋不誤判)

- **WHEN** 座位 A1 為 `OCCUPIED`，且「人」的偵測僅中斷少於去抖動門檻（如有人走過遮擋鏡頭 2 秒）
- **THEN** 座位 A1 的狀態維持 `OCCUPIED` 不變，不產生狀態變更紀錄

#### Scenario: Seated person whose box center overflows the ROI (坐姿者框中心溢出 ROI)

- **WHEN** 有人坐在座位 A1，其偵測框因人體高度而向畫面上方延伸，使框的幾何中心落在 A1 的 ROI 之外，但框底部中心點仍落在 A1 的 ROI 內
- **THEN** 系統判定座位 A1 為有人使用，不因框中心溢出而漏判

#### Scenario: Person walking in front of a seat is not counted (前方走道經過者不計入)

- **WHEN** 有人站立或行經座位 A1 前方（位於相機與座位之間的走道，未入座），其偵測框因人體高度而向畫面上方延伸並覆蓋 A1 的 ROI，但框底部中心點不在任何座位的 ROI 內
- **THEN** 系統不將座位 A1 判定為有人使用

#### Scenario: Front-row person not counted for the back row (前排的人不計入後排)

- **WHEN** 座位 A1 在前排、B1 在其正後方，B1 的外輪廓向下延伸覆蓋 A1 的桌面；有人坐在 A1，其接地點落在 A1 的桌面內，同時也落在 B1 的外輪廓內
- **THEN** 系統只判定座位 A1 為有人使用，B1 不受影響

#### Scenario: Back-row person on own desk (後排的人歸屬自己的座位)

- **WHEN** 有人坐在後排座位 B1，其接地點落在 B1 的桌面內
- **THEN** 系統判定座位 B1 為有人使用，前排座位不受影響

#### Scenario: Fallback to outline when outside every desk (不在任何桌面時退回外輪廓)

- **WHEN** 有人坐在座位 A1 但側身或拉開椅子，其接地點不在任何座位的桌面內，但落在 A1 的外輪廓內
- **THEN** 系統判定座位 A1 為有人使用

#### Scenario: Per-seat matching mode (切換為逐席判定)

- **WHEN** 偵測端設定為逐席判定
- **THEN** 系統對每個座位獨立比對外輪廓，一個偵測可同時計入多個座位，其餘去抖動與上報流程不變

#### Scenario: Fallback to box center (切換回框中心判定)

- **WHEN** 偵測端設定為逐席判定，且以框幾何中心作為人的判定點
- **THEN** 系統改以框幾何中心比對 ROI，其餘判定流程與去抖動行為不變

### Requirement: Idle Belongings Detection (疑似佔位偵測)

系統 SHALL 辨識「人已離開但物品（背包、筆電、書本、水壺等）仍在座位上」的情形，並將其標記為疑似佔位事件，作為離席逾時計時（seat-timeout）的觸發來源。物品的判定點 SHALL 使用偵測框的幾何中心：物品框尺寸小、幾何中心與接地點差異不具實質影響，且物品常被桌沿或其他物件部分遮擋而使框底邊較不穩定。

物品歸屬座位的方式與人相同：預設桌面優先、每個偵測只歸屬一個座位；逐席判定模式下各座位獨立比對外輪廓。

#### Scenario: Person leaves but belongings remain (人離開、物品仍在)

- **WHEN** 座位 A1 為 `OCCUPIED`，YOLOv8 連續 5 秒以上沒有「人」歸屬於 A1，但仍有「背包／筆電／書本／水壺」等物品歸屬於 A1
- **THEN** 系統發出「疑似佔位開始」事件（含座位編號與離席起始時間）給逾時處理流程
- **AND** 在偵測畫面上以明顯標記（如橘色框與文字）標示該座位為疑似佔位

#### Scenario: Item on front-row desk not counted for the back row (前排桌上的物品不計入後排)

- **WHEN** 水壺放在前排座位 A1 的桌面上，其框中心同時落在後排座位 B1 向下延伸的外輪廓內
- **THEN** 系統只將該水壺歸屬於座位 A1

#### Scenario: Person and belongings both gone (人與物品皆離開)

- **WHEN** 座位 A1 為 `OCCUPIED`，且連續 5 秒以上沒有任何人或物品歸屬於 A1
- **THEN** 系統發出「座位已淨空」事件給逾時處理流程

### Requirement: State Change Synchronization (狀態變更同步)

偵測端 SHALL 只在座位判定結果發生變化時更新資料庫，並且每次更新 MUST 同時寫入狀態歷史紀錄（供使用率報表使用）。

#### Scenario: Only changed states are written (僅變更時寫入)

- **WHEN** 連續多個偵測週期中座位 A1 的判定結果皆為「有人使用」且資料庫已是 `OCCUPIED`
- **THEN** 系統不重複寫入資料庫，僅更新記憶體中的最後偵測時間

#### Scenario: Detection survives database outage (資料庫斷線重試)

- **WHEN** 偵測端寫入資料庫失敗（連線中斷）
- **THEN** 偵測流程不得中止，狀態變更進入待送佇列並於連線恢復後依序補寫

### Requirement: Latest Detection Result Recorded (保存最新偵測結果)

後端 SHALL 為每個座位保存最近一次收到的偵測結果（有人／人離開但物品仍在／人與物品皆離開）與收到時間，不論該結果是否造成座位狀態改變。從未收到偵測結果的座位 MUST 能被辨識為「沒有偵測資料」。此結果供「結束使用」判斷使用者是否已離開。

#### Scenario: Result recorded without a state change (狀態未變也保存結果)

- **WHEN** 座位 A1 為 `AVAILABLE`，偵測端送來「人與物品皆離開」
- **THEN** A1 狀態不變，但 A1 的最新偵測結果記為「人與物品皆離開」及收到時間

#### Scenario: Newer result replaces older one (新結果取代舊結果)

- **WHEN** A1 最新偵測結果為「有人」，之後偵測端送來「人離開但物品仍在」
- **THEN** A1 的最新偵測結果改為「人離開但物品仍在」

#### Scenario: Seat never detected (從未偵測的座位)

- **WHEN** 座位 B3 從未收到任何偵測事件
- **THEN** B3 的最新偵測結果為空，表示沒有偵測資料

