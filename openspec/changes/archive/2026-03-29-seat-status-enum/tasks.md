## 1. 資料結構與模型 (Models)

- [ ] 1.1 在 `src/models/Seat.ts` 建立 `SeatStatus` (Enum 共四種狀態)。
- [ ] 1.2 建立 `Seat` 與 `BookingRecord` 的基本型別定義 (Interface/Type)。

## 2. 業務邏輯層 (Services)

- [ ] 2.1 建立 `src/services/BookingService.ts`。
- [ ] 2.2 實作 `reserveSeat` 函式：檢查目標座位狀態是否為 `AVAILABLE`，若成功則改為 `RESERVED` 並回傳預約資料。
- [ ] 2.3 在該函式中實作防禦機制：若狀態為 `OCCUPIED` 或 `RESERVED`，則拋出預約失敗的錯誤。

## 3. 實作驗證 (Verification)

- [ ] 3.1 在 `src/index.ts` 中寫一小段測試腳本，模擬一個學生請求預約空位、接著另一名學生嘗試預約同一座位的流程。
