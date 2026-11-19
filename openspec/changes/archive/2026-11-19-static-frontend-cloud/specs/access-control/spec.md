## ADDED Requirements

### Requirement: Student Sign-In Token (學生登入憑證)

系統 SHALL 讓學生以學號換取登入憑證（token）。學號 MUST 為英數 4～15 碼，系統將其轉為大寫後簽發 token，有效期 12 小時。需要辨識學生身分的 API MUST 從請求的 `Authorization: Bearer` 標頭取得 token 並驗證簽章與期限；即時推播連線 MUST 能以 token 識別學生，以傳送個人通知。

學號登入不需要密碼，屬於專題階段的已知限制。

#### Scenario: Sign in with a valid student ID (以學號登入)

- **WHEN** 學生以學號 `b11023001` 登入
- **THEN** 系統回傳 token 與學號 `B11023001`
- **AND** 之後帶此 token 呼叫預約 API 時，系統以 `B11023001` 作為預約者

#### Scenario: Reject malformed student ID (拒絕格式錯誤的學號)

- **WHEN** 學生以學號 `B1`（少於 4 碼）或含符號的字串登入
- **THEN** 系統拒絕並回傳錯誤訊息「學號格式不正確（英數 4–15 碼）」，不簽發 token

#### Scenario: Missing or invalid token (未登入或憑證無效)

- **WHEN** 請求預約、報到、取消、確認仍在使用或讀取通知時，沒有帶 token、token 簽章不符或已超過 12 小時
- **THEN** 系統回傳 401，前端導回登入頁

#### Scenario: Real-time channel identifies the student (即時推播識別學生)

- **WHEN** 已登入的學生開啟平面圖，以 token 建立即時推播連線
- **THEN** 該連線同時收到座位狀態廣播與該學生的個人通知（離席警示、座位遭釋放等）

#### Scenario: Anonymous real-time connection (未帶憑證的即時推播)

- **WHEN** 即時推播連線沒有帶 token 或 token 無效
- **THEN** 連線仍可建立並收到座位狀態廣播，但不會收到任何個人通知

### Requirement: Detection Client Authentication (偵測端身分驗證)

設定偵測端金鑰後，系統 SHALL 只接受帶有正確金鑰的偵測事件。金鑰比對 MUST 使用固定時間的比較方式。偵測端 MUST 在即時上報與離線佇列補送時都帶上金鑰。

#### Scenario: Event with valid key (帶正確金鑰的偵測事件)

- **WHEN** 系統已設定偵測端金鑰，偵測端以正確金鑰上報座位 A1 的 `person_present` 事件
- **THEN** 系統依偵測事件處理流程更新座位 A1

#### Scenario: Event without valid key (未帶或金鑰錯誤)

- **WHEN** 系統已設定偵測端金鑰，請求沒有帶金鑰或金鑰錯誤
- **THEN** 系統回傳 401，不處理任何事件，座位狀態不變

#### Scenario: Offline queue keeps the key (離線補送帶金鑰)

- **WHEN** 偵測端在後端無法連線期間累積事件，連線恢復後補送
- **THEN** 補送請求帶有偵測端金鑰，事件依序被接受

### Requirement: Administrator Authentication (管理者身分驗證)

設定管理密碼後，系統 SHALL 要求 ROI 標定與所有報表 API（含 CSV 匯出）帶上正確的管理密碼。報表頁 MUST 在第一次查詢前詢問管理密碼，並在密碼錯誤或失效時重新詢問；密碼只保存在目前的瀏覽器分頁。

#### Scenario: Report query with valid admin password (以正確管理密碼查詢報表)

- **WHEN** 系統已設定管理密碼，管理者在報表頁輸入正確密碼並查詢使用率
- **THEN** 報表頁顯示圖表，之後在同一分頁的查詢與 CSV 匯出不需再次輸入

#### Scenario: Report query without valid admin password (未帶或密碼錯誤)

- **WHEN** 系統已設定管理密碼，報表或 ROI 標定請求沒有帶密碼或密碼錯誤
- **THEN** 系統回傳 401，不回傳任何報表資料、不修改 ROI
- **AND** 報表頁提示密碼錯誤並重新詢問

### Requirement: Development Mode Without Keys (未設定金鑰的開發模式)

偵測端金鑰或管理密碼未設定時，系統 SHALL 不對對應端點做驗證，以便本機開發與測試；並 MUST 在啟動時記錄警告，列出未受保護的端點。

#### Scenario: Keys not configured (未設定金鑰)

- **WHEN** 系統啟動時沒有設定偵測端金鑰與管理密碼
- **THEN** 偵測事件、ROI 標定與報表 API 不需金鑰即可呼叫
- **AND** 啟動紀錄中出現警告，指出這些端點未受保護
