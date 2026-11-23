## MODIFIED Requirements

### Requirement: Separately Hosted Static Frontend (前後端分離部署)

系統的網頁前端 SHALL 為純靜態檔案（HTML、CSS、JavaScript），可部署於只能提供靜態檔案的主機；後端只提供 API 與即時推播。前端 MUST 從設定檔讀取後端網址，未設定時視為與前端同一網址。後端 SHALL 在本機開發時一併提供前端靜態檔，使單一伺服器即可完整操作。

設定了前端正式網址（`FRONTEND_URL`）時，後端 MUST NOT 提供前端檔案；瀏覽器開啟後端的非 API 網址時，後端 SHALL 轉址到前端正式網址的同一路徑。`/api/` 開頭的路徑 MUST NOT 轉址。

前端所需的系統設定（報到期限、開館時段）MUST 由後端 API 提供，不得寫死在前端。

#### Scenario: Frontend served from a static host (由靜態主機提供前端)

- **WHEN** 前端部署於 GitHub Pages 並設定後端網址，學生以手機開啟該網址
- **THEN** 學生可完成登入、檢視平面圖、預約、報到、取消、確認仍在使用與檢視即時動態，行為與本機相同

#### Scenario: Single-server local development (本機單一伺服器)

- **WHEN** 開發者在本機啟動後端（未設定前端正式網址）並以瀏覽器開啟後端網址
- **THEN** 瀏覽器載入同一份前端，以同源方式呼叫 API，不需另外啟動前端伺服器

#### Scenario: Cloud backend redirects to the official frontend (雲端後端轉址到正式前端)

- **WHEN** 後端設定前端正式網址為 `https://crazyspaghetti123.github.io/Library-seat-Detection`，有人以瀏覽器開啟後端的 `/map.html`
- **THEN** 後端回應轉址到 `https://crazyspaghetti123.github.io/Library-seat-Detection/map.html`，不回傳前端檔案

#### Scenario: API paths are never redirected (API 路徑不轉址)

- **WHEN** 後端設定了前端正式網址，有程式呼叫不存在的 `/api/unknown`
- **THEN** 後端回傳 404，不轉址

#### Scenario: Settings come from the backend (設定值由後端提供)

- **WHEN** 後端的報到期限設定為 30 分鐘
- **THEN** 平面圖的預約確認視窗顯示「預約後請於 30 分鐘內報到」
