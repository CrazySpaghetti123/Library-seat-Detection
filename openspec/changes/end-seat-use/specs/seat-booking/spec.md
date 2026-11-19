## ADDED Requirements

### Requirement: End of Use (結束使用)

已報到的使用者 SHALL 能主動「結束使用」自己的座位。按下後座位進入收拾中，系統 MUST 在 `LEAVE_CHECK_SECONDS`（預設 30 秒，可由設定調整）後檢查該座位最新的偵測結果：人與物品皆已離開才釋放；人或物品仍在則不釋放，並在下一個 `LEAVE_CHECK_SECONDS` 後再次檢查，直到離開為止。該座位從未收到任何偵測結果時，系統 MUST 在第一次檢查即釋放。

收拾中的座位對其他使用者仍顯示為使用中。收拾中的使用者 SHALL 能按「繼續使用」取消結束。釋放時預約 MUST 以結束原因 `checked_out` 結束，座位回到 `AVAILABLE`，並通知使用者。

#### Scenario: Release after the user has left (離開後釋放)

- **WHEN** 使用者對已報到的座位 A1 按下「結束使用」，30 秒後檢查時 A1 最新的偵測結果為「人與物品皆離開」
- **THEN** A1 釋放回 `AVAILABLE`，預約結束原因為 `checked_out`，使用者收到座位已釋放的通知，平面圖即時更新

#### Scenario: User still packing (仍在收拾)

- **WHEN** 使用者按下「結束使用」，30 秒後檢查時 A1 最新的偵測結果為「有人」
- **THEN** A1 維持原狀態、不釋放，系統排定 30 秒後再次檢查
- **AND** 之後偵測結果變為「人與物品皆離開」，下一次檢查時釋放 A1

#### Scenario: Belongings left behind (物品仍在座位上)

- **WHEN** 檢查時 A1 最新的偵測結果為「人離開但物品仍在」
- **THEN** 系統不釋放 A1，30 秒後再次檢查

#### Scenario: Seat without detection data (座位沒有偵測資料)

- **WHEN** 使用者對從未收到任何偵測結果的座位按下「結束使用」
- **THEN** 系統在 30 秒後的第一次檢查即釋放該座位

#### Scenario: Resume use (繼續使用)

- **WHEN** 收拾中的使用者在座位釋放前按下「繼續使用」
- **THEN** 系統取消結束使用，不再檢查，座位與預約維持使用中

#### Scenario: Only the checked-in owner can end use (僅本人且已報到可結束)

- **WHEN** 使用者對非本人的預約，或尚未報到的預約按下「結束使用」
- **THEN** 系統拒絕請求，預約與座位狀態不變（尚未報到的預約應使用「取消預約」）
