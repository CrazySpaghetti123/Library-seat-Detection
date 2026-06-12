## Why
圖書館座位系統不僅需要偵測目前座位有沒有人，更需要讓學生能夠事前預訂。透過標準化的狀態管理與預訂系統，我們能最大化座位的利用率，並避免未經預約的佔位爭議。

## What Changes
1. **定義座位狀態**：實作 `SeatStatus` 的基礎結構 (包含 `AVAILABLE`, `OCCUPIED`, `RESERVED`, `MAINTENANCE`)。
2. **實作預訂邏輯**：建立預訂功能，包含檢查座位是否為 `AVAILABLE`，若可預訂則建立系統紀錄並將狀態切換為 `RESERVED`。

## Capabilities
### New Capabilities
- `Seat Booking`: 允許學生確保一個閒置座位的使用權。
- `Seat State Management`: 透過統一的資料型別來辨識並傳遞座位狀態變化。

## Impact
- 新增負責定義座位與狀態的基礎檔案 (如 `src/models/seat.ts` 或對等的 Python 檔)。
- 新增負責處理預訂與驗證邏輯的業務層 (如 `src/services/bookingService.ts`)。
