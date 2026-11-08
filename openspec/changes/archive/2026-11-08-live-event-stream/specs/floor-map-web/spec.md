## ADDED Requirements

### Requirement: Live Status Event Stream (即時狀態事件流)

平面圖頁 SHALL 以可收合的側欄呈現近期座位狀態變更的事件流，且預設為收合狀態，使平面圖維持為頁面主體。每筆事件 MUST 包含座位編號、變更前後狀態與變更來源（預約／偵測／逾時／管理），並標示發生時間。頁面載入時 MUST 顯示最近的歷史事件；其後收到即時推播時，新事件 MUST 追加至事件流頂端，無須重新整理。

側欄收合期間若有新事件抵達，系統 MUST 於收合標籤上呈現未讀提示。事件流保留的筆數 MUST 有上限，避免長時間開啟造成無限增長。

#### Scenario: Stream is collapsed by default (預設收合)

- **WHEN** 學生初次開啟平面圖頁
- **THEN** 事件流側欄為收合狀態，僅於頁面邊緣顯示可展開的標籤
- **AND** 平面圖置中呈現，不因側欄而偏移

#### Scenario: Expanding reveals the stream (展開後顯示事件流)

- **WHEN** 學生點選事件流的展開標籤
- **THEN** 側欄展開並顯示近期事件，每筆含座位編號、變更前後狀態、來源與發生時間
- **AND** 依時間新到舊排列

#### Scenario: Unread indicator while collapsed (收合期間的未讀提示)

- **WHEN** 事件流側欄為收合狀態，此時有座位狀態變更
- **THEN** 收合標籤上顯示未讀事件數量
- **AND** 學生展開側欄後，未讀提示歸零

#### Scenario: New event appended in real time (即時追加新事件)

- **WHEN** 學生停留在平面圖頁，此時座位 A1 由 `AVAILABLE` 變更為 `RESERVED`
- **THEN** 事件流頂端出現一筆新事件，標示 A1 由可預約轉為已預約、來源為預約
- **AND** 頁面無須重新整理

#### Scenario: Event source is shown in readable form (來源以可讀形式呈現)

- **WHEN** 事件流中有一筆座位因離席逾時而被系統釋放的紀錄
- **THEN** 該筆事件的來源顯示為可理解的中文標示，而非原始的內部識別字串

#### Scenario: Stream length is bounded (事件流長度有上限)

- **WHEN** 平面圖頁持續開啟並累積超過保留上限筆數的事件
- **THEN** 事件流僅保留最新的上限筆數，較舊的事件被移除
