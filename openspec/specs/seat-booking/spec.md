# seat-booking Specification

## Purpose
管理自習室座位的線上預約生命週期：預約、報到（含偵測自動報到）、取消與逾期釋放，並保證座位狀態一致與一人一位。
## Requirements
### Requirement: Seat Booking (座位預約)

系統 SHALL 允許具有權限的使用者預訂目前閒置的座位，並 MUST 妥善變更座位狀態以防止重複預約。座位狀態包含 `AVAILABLE`（空閒）、`RESERVED`（已預約）、`OCCUPIED`（使用中）、`AWAY`（疑似佔位）、`MAINTENANCE`（維修中），僅 `AVAILABLE` 的座位 SHALL 可被預約。

#### Scenario: Successfully reserve an available seat (成功預訂閒置座位)

- **WHEN** 一名使用者嘗試預訂一個狀態為 `AVAILABLE` 的座位
- **THEN** 系統會建立一筆專屬的預約紀錄（含預約時間戳與報到期限）
- **AND** 該座位的狀態會立即更新為 `RESERVED`
- **AND** 回傳預約成功的確認訊息與報到期限

#### Scenario: Fail to reserve an unavailable seat (預訂失敗)

- **WHEN** 使用者嘗試預訂一個狀態為 `OCCUPIED`（有人坐）、`RESERVED`（已預約）、`AWAY`（疑似佔位）或 `MAINTENANCE`（維修中）的座位
- **THEN** 系統應拒絕該預約請求，並拋出「無法預訂此座位」的錯誤
- **AND** 座位原本的狀態不得被更改

### Requirement: Check-In (預約報到)

預約成功後，使用者 SHALL 於報到期限（預設 30 分鐘，系統設定值）內完成報到；報到可由使用者於網頁操作，或由偵測端偵測到本人入座自動完成。報到後座位狀態 MUST 由 `RESERVED` 轉為 `OCCUPIED`。

#### Scenario: Manual check-in (網頁報到)

- **WHEN** 使用者於報到期限內在網頁按下「報到」
- **THEN** 座位狀態由 `RESERVED` 轉為 `OCCUPIED`，預約紀錄標記為已報到

#### Scenario: Auto check-in by detection (偵測自動報到)

- **WHEN** 座位為 `RESERVED`，偵測端在該座位 ROI 內偵測到「人」並通過去抖動門檻
- **THEN** 系統自動完成報到，座位狀態轉為 `OCCUPIED`
- **AND** 以網頁內通知告知使用者已自動完成報到

#### Scenario: No-show auto release (逾期未報到自動釋放)

- **WHEN** 預約後超過報到期限仍未報到
- **THEN** 系統取消該筆預約並將座位釋放回 `AVAILABLE`
- **AND** 記錄一筆「逾期未報到」事件，並以網頁內通知告知使用者

### Requirement: One Active Booking per Student (一人一位)

使用者以學號登入系統；同一學號 SHALL 同時間僅能持有一筆有效的預約或使用中座位，避免一人佔用多個座位。

#### Scenario: Reject second concurrent booking (拒絕重複持有座位)

- **WHEN** 學號 B11023001 已持有一筆有效預約（或正在使用座位），又嘗試預約另一個 `AVAILABLE` 座位
- **THEN** 系統拒絕該請求並提示「您已持有座位，請先取消或結束使用」
- **AND** 兩個座位的狀態皆不變

#### Scenario: Book again after release (釋放後可再預約)

- **WHEN** 學號 B11023001 的前一筆預約已取消、釋放或結束，再嘗試預約一個 `AVAILABLE` 座位
- **THEN** 系統允許預約並建立新的預約紀錄

### Requirement: Booking Cancellation (取消預約)

使用者 SHALL 能在報到前取消自己的預約；取消後座位 MUST 立即釋放回 `AVAILABLE`。使用者 MUST 不得取消他人的預約。

#### Scenario: Cancel own booking (取消自己的預約)

- **WHEN** 使用者對自己尚未報到的預約按下「取消」
- **THEN** 預約紀錄標記為已取消，座位釋放回 `AVAILABLE`，平面圖即時更新

#### Scenario: Cannot cancel others' booking (不可取消他人預約)

- **WHEN** 使用者嘗試取消非本人建立的預約
- **THEN** 系統拒絕並回傳權限錯誤，預約與座位狀態不變

### Requirement: Booking Records for Reporting (預約紀錄供報表)

每筆預約 SHALL 完整保存生命週期時間戳（建立、報到、取消、釋放），供使用率報表（usage-report）統計使用。

#### Scenario: Booking lifecycle is traceable (預約生命週期可追溯)

- **WHEN** 一筆預約歷經建立、報到、最終因逾時釋放結束
- **THEN** 該預約紀錄包含建立時間、報到時間與結束時間／結束原因，可被報表查詢
