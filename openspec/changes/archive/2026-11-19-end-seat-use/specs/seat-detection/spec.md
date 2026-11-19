## ADDED Requirements

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
