# seat-timeout Delta Specification

## ADDED Requirements

### Requirement: Away Detection and Notification (離席逾時提示)

當偵測端回報某 `OCCUPIED` 座位「人已離開但物品仍在」且持續達提示門檻（預設 15 分鐘）時，系統 SHALL 將該座位狀態轉為 `AWAY`（疑似佔位），並透過網頁內通知提示該座位的使用者，通知 MUST 包含確認按鈕與釋放倒數時間。

#### Scenario: Away threshold reached (離席達 15 分鐘)

- **WHEN** 座位 A1 的「疑似佔位開始」事件持續 15 分鐘未解除
- **THEN** 座位 A1 狀態由 `OCCUPIED` 轉為 `AWAY`
- **AND** 系統對該座位目前的使用者發送網頁內通知：「您已離席超過 15 分鐘，請於 10 分鐘內確認仍在使用，否則座位將被釋放」
- **AND** 平面圖上該座位顯示為疑似佔位狀態

#### Scenario: Person returns before threshold (門檻前返回)

- **WHEN** 座位 A1 處於疑似佔位計時中（未滿 15 分鐘），偵測端回報「人」重新出現在 ROI 內
- **THEN** 計時器取消，座位維持 `OCCUPIED`，不發送任何通知

### Requirement: Confirmation Keeps the Seat (確認保留座位)

收到離席通知的使用者 SHALL 能在釋放倒數（預設 10 分鐘）內於網頁按下「我仍在使用」確認；確認後座位 MUST 回復 `OCCUPIED` 並重新開始離席計時。

#### Scenario: User confirms in time (限時內確認)

- **WHEN** 座位 A1 為 `AWAY`，使用者於通知後 10 分鐘內按下「我仍在使用」
- **THEN** 座位 A1 狀態回復為 `OCCUPIED`
- **AND** 離席計時歸零重新計算（若人仍未回到座位，15 分鐘後會再次觸發提示）

#### Scenario: Person physically returns (本人返回座位)

- **WHEN** 座位 A1 為 `AWAY`，偵測端回報「人」重新出現在該座位 ROI 內並通過去抖動門檻
- **THEN** 視同完成確認，座位 A1 回復 `OCCUPIED`，倒數取消

### Requirement: Timeout Auto-Release (逾時自動釋放)

若使用者未在釋放倒數內完成確認且本人未返回，系統 SHALL 將座位釋放回 `AVAILABLE`，結束原使用紀錄，並記錄一筆「佔位逾時釋放」事件供報表統計。

#### Scenario: No confirmation, seat released (未確認即釋放)

- **WHEN** 座位 A1 為 `AWAY` 且通知發出後 10 分鐘內未收到確認、人也未返回
- **THEN** 座位 A1 狀態轉為 `AVAILABLE`，平面圖即時轉為綠色可預約
- **AND** 系統記錄一筆佔位逾時釋放事件（座位編號、使用者、離席起訖時間）
- **AND** 對該使用者發送網頁內通知告知座位已被釋放

#### Scenario: Cleared seat short-circuit release (人與物品皆離開的快速釋放)

- **WHEN** 座位 A1 為 `OCCUPIED`，偵測端回報「座位已淨空」（人與物品皆不在）且持續達淨空門檻（預設 5 分鐘）
- **THEN** 座位 A1 直接釋放回 `AVAILABLE`，不需經過提示與確認流程

### Requirement: Configurable Timers (計時參數可設定)

提示門檻、釋放倒數與淨空門檻 SHALL 為系統設定值（預設 15／10／5 分鐘），MUST 可由設定檔調整而無須修改程式碼。

#### Scenario: Admin changes thresholds (調整參數)

- **WHEN** 管理者將提示門檻由 15 分鐘改為 10 分鐘並重新載入設定
- **THEN** 之後的離席計時依新門檻 10 分鐘觸發提示
