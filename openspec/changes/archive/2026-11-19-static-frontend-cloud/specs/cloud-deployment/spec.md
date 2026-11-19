## ADDED Requirements

### Requirement: Separately Hosted Static Frontend (前後端分離部署)

系統的網頁前端 SHALL 為純靜態檔案（HTML、CSS、JavaScript），可部署於只能提供靜態檔案的主機；後端只提供 API 與即時推播。前端 MUST 從設定檔讀取後端網址，未設定時視為與前端同一網址。後端 SHALL 在本機開發時一併提供前端靜態檔，使單一伺服器即可完整操作。

前端所需的系統設定（報到期限、開館時段）MUST 由後端 API 提供，不得寫死在前端。

#### Scenario: Frontend served from a static host (由靜態主機提供前端)

- **WHEN** 前端部署於 GitHub Pages 並設定後端網址，學生以手機開啟該網址
- **THEN** 學生可完成登入、檢視平面圖、預約、報到、取消、確認仍在使用與檢視即時動態，行為與本機相同

#### Scenario: Single-server local development (本機單一伺服器)

- **WHEN** 開發者在本機啟動後端並以瀏覽器開啟後端網址
- **THEN** 瀏覽器載入同一份前端，以同源方式呼叫 API，不需另外啟動前端伺服器

#### Scenario: Settings come from the backend (設定值由後端提供)

- **WHEN** 後端的報到期限設定為 30 分鐘
- **THEN** 平面圖的預約確認視窗顯示「預約後請於 30 分鐘內報到」

### Requirement: Cross-Origin API Access (跨來源存取)

後端 SHALL 只允許設定中列出的前端來源以跨來源方式呼叫 API。未設定任何來源時，後端 MUST 不開放跨來源存取。

#### Scenario: Allowed frontend origin (允許的前端來源)

- **WHEN** 後端設定允許 `https://crazyspaghetti123.github.io`，該網址上的前端帶登入憑證呼叫預約 API
- **THEN** 瀏覽器允許該請求，預約正常完成

#### Scenario: Unlisted origin (未列出的來源)

- **WHEN** 其他網站上的網頁以跨來源方式呼叫後端 API
- **THEN** 後端的回應不包含允許該來源的標頭，瀏覽器阻擋該網頁讀取回應

### Requirement: Backend Wake-Up Handling (後端喚醒處理)

後端可能因閒置而休眠，喚醒需要約一分鐘。前端 SHALL 在後端無回應時顯示等待提示並自動重試，後端恢復後自動載入資料，使用者不需手動重新整理。系統 SHALL 提供不存取資料庫的健康檢查端點。

#### Scenario: Backend is asleep when the map opens (開啟平面圖時後端休眠中)

- **WHEN** 學生開啟平面圖，後端在 3 秒內沒有回應
- **THEN** 頁面顯示「伺服器喚醒中，約需一分鐘」並自動重試
- **AND** 後端恢復後，平面圖自動載入座位狀態，提示消失

#### Scenario: Backend unreachable for too long (後端長時間無法連線)

- **WHEN** 自動重試超過 3 分鐘後端仍無回應
- **THEN** 頁面停止重試並顯示「伺服器暫時無法連線，請稍後重新整理」

#### Scenario: Health check (健康檢查)

- **WHEN** 任何人呼叫健康檢查端點
- **THEN** 後端回傳正常狀態，且此請求不建立資料庫連線

#### Scenario: Timers resume after wake-up (醒來後補處理逾時)

- **WHEN** 後端休眠期間，某座位的離席計時已超過提示門檻
- **THEN** 後端醒來後的第一次逾時掃描即處理該座位，計時以原本的離席起點計算

### Requirement: Keep-Alive During Use (使用期間保持清醒)

系統 SHALL 在有人使用時讓後端保持清醒：開啟中的平面圖 MUST 定時（預設每 4 分鐘）經由即時推播連線送出心跳；偵測端 MUST 定時（預設每 10 分鐘，可設定或關閉）呼叫健康檢查端點。

#### Scenario: Map left open (平面圖持續開啟)

- **WHEN** 學生開著平面圖超過 15 分鐘沒有任何操作
- **THEN** 前端持續送出心跳，後端不進入休眠，即時推播連線維持

#### Scenario: Detection running during opening hours (開館期間偵測端運作)

- **WHEN** 偵測端在開館期間持續運作，且沒有任何學生開啟網頁
- **THEN** 偵測端定時呼叫健康檢查，後端保持清醒，離席逾時在門檻到達時即被處理

### Requirement: Managed Database Connection (雲端資料庫連線)

後端 SHALL 接受雲端 PostgreSQL 服務提供的標準連線字串（`postgres://` 或 `postgresql://` 開頭），自動選用系統使用的資料庫驅動；連線 MUST 在使用前檢查是否仍有效，並定期回收，以因應資料庫閒置暫停後連線失效。

#### Scenario: Paste the provider connection string (直接貼上服務提供的連線字串)

- **WHEN** 管理者將雲端資料庫提供的 `postgresql://…?sslmode=require` 連線字串設為資料庫設定
- **THEN** 後端以加密連線成功連上資料庫，不需手動修改字串

#### Scenario: Database resumed after suspension (資料庫暫停後恢復)

- **WHEN** 雲端資料庫因閒置暫停後恢復，連線池中保留了暫停前的連線
- **THEN** 後端在使用前偵測到失效連線並重新建立，請求正常完成，不回傳錯誤

### Requirement: Secrets Outside Version Control (密鑰不進版控)

資料庫連線字串、session 簽章金鑰、偵測端金鑰與管理密碼 SHALL 只透過環境變數提供，MUST NOT 寫入版本控制中的任何檔案（含部署設定檔）。部署設定檔 MUST 將這些值標示為需在部署平台上設定。

#### Scenario: Deployment configuration contains no secrets (部署設定不含密鑰)

- **WHEN** 檢視版本控制中的部署設定檔
- **THEN** 檔案中只有密鑰的名稱與「需在平台設定」的標示，沒有任何實際的密碼、金鑰或連線字串
