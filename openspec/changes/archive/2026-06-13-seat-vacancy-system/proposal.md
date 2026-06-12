# Proposal: seat-vacancy-system

## Why

自習室常見「找不到位子」與「佔位（人不在但物品佔著座位）」兩大痛點，學生無法在到場前得知空位狀況，座位周轉率低落。本變更要把現有的記憶體內預約原型，擴展為一套完整的自習室空位偵測與預約系統：以 YOLOv8 即時偵測座位使用狀態、提供 RWD 平面圖與線上預約、自動處理離席逾時釋放，並產出空間使用率報表，作為兩學期專題的系統藍圖。

## What Changes

- 建立 FastAPI + SQLAlchemy 的 MVC 後端架構，取代現行單檔主控台模擬；資料層初期使用 PostgreSQL（開發期可用 SQLite，透過連線字串切換），上線後遷移至 DBaaS。
- **BREAKING**：完全棄用原訂的 Firebase Realtime Database 方案，前端即時更新改由後端 WebSocket 推播；`docs/technical_architecture.md` 與 `docs/roadmap.md` 同步改寫。
- 新增 YOLOv8 + ROI 佔位偵測：辨識「有人」「人離開但物品仍在（疑似佔位）」並更新座位狀態。
- 擴充座位狀態機與預約規則：新增報到（check-in）、取消、疑似佔位（AWAY）等狀態轉換。
- 新增離席逾時流程：偵測到離席持續 15 分鐘 → 網頁內通知提示；提示後 10 分鐘內未確認「仍在使用」→ 座位釋放回 AVAILABLE。
- 新增 RWD 自習室平面圖網頁：綠色＝可預約、紅色＝使用中／已預約，狀態即時變色。
- 新增校園空間使用率分析報表：依時段／樓層統計使用率、佔位率、尖峰時段。

## Capabilities

### New Capabilities

- `seat-detection`: YOLOv8 + ROI 影像偵測，判定每個座位的實際使用狀態（有人／空位／物品佔位），並將狀態變化同步至資料庫。
- `seat-timeout`: 離席逾時偵測、網頁內提示與確認機制、逾時自動釋放座位。
- `floor-map-web`: RWD 自習室平面圖，依座位狀態著色並透過 WebSocket 即時更新；提供學生點選座位進行預約的入口。
- `usage-report`: 座位狀態歷史紀錄之彙整與使用率分析報表（時段、樓層、佔位行為統計）。

### Modified Capabilities

- `seat-booking`: 新增報到、取消與逾時釋放相關的需求——預約後須於時限內報到否則自動釋放；座位狀態機納入 AWAY（疑似佔位）狀態；預約紀錄需保存時間戳以供報表使用。

## Impact

- **程式碼**：`src/` 重構為 MVC 分層（models / services / controllers / views）；`src/main.py` 改為應用程式進入點（FastAPI app），原主控台模擬改寫為自動化測試或示範腳本。
- **相依套件**：新增 fastapi、uvicorn、SQLAlchemy、psycopg、ultralytics（YOLOv8）、opencv-python、jinja2 等；需建立依賴清單（requirements.txt 或 pyproject.toml）。
- **資料庫**：新建 PostgreSQL schema（seats、bookings、seat_status_log、users 等資料表）；本機尚未安裝 PostgreSQL，開發初期以 SQLite 銜接。
- **文件**：`docs/technical_architecture.md`、`docs/roadmap.md` 中 Firebase 相關內容全面改寫為 PostgreSQL + WebSocket 架構。
- **既有規格**：`openspec/specs/seat-booking/spec.md` 將透過本變更的 delta spec 擴充。
