## ADDED Requirements

### Requirement: Seat Booking (座位預約)

系統必須允許具有權限的使用者預訂目前閒置的座位，並妥善變更座位狀態以防止重複預約。

#### Scenario: Successfully reserve an available seat (成功預訂閒置座位)

- **WHEN** 一名使用者嘗試預訂一個狀態為 `AVAILABLE` 的座位
- **THEN** 系統會建立一筆專屬的預約紀錄
- **AND** 該座位的狀態會立即更新為 `RESERVED`
- **AND** 回傳預約成功的確認訊息

#### Scenario: Fail to reserve an occupied or reserved seat (預訂失敗)

- **WHEN** 使用者嘗試預訂一個狀態為 `OCCUPIED` (有人坐) 或已被 `RESERVED` (已預約) 的座位
- **THEN** 系統應拒絕該預約請求，並拋出「無法預訂此座位」的錯誤
- **AND** 座位原本的狀態不得被更改
