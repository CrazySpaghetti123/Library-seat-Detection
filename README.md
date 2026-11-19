# 南台科技大學資工系實務專題 - 自習室空位即時偵測系統

## 1. 專案簡介

本專案旨在利用電腦視覺技術 (YOLOv8) 解決校園自習室座位資訊不透明及佔位問題。

線上版：<https://crazyspaghetti123.github.io/Library-seat-Detection/>（後端閒置會休眠，第一次開啟約需一分鐘喚醒）

## 2. 核心功能

* **即時偵測**：YOLOv8 + ROI 自動辨識座位是否有人使用。
* **佔位判定**：偵測「人離開但物品仍在」，離席 15 分鐘發網頁內提示，10 分鐘內未確認自動釋放座位。
* **線上預約**：學號登入後於平面圖點選綠色座位預約，30 分鐘內報到（或由偵測自動報到）。
* **視覺化介面**：RWD 網頁平面圖即時變色（綠＝可預約、紅＝使用中/已預約、橘＝疑似佔位）。
* **使用率報表**：逐時使用率、趨勢、樓層比較、佔位行為統計，可匯出 CSV。

## 3. 技術架構簡述

* **AI Model**: YOLOv8 + OpenCV（ROI 判定、去抖動）
* **Backend**: Python / FastAPI（MVC：SQLAlchemy models、Service 層狀態機、REST＋WebSocket controllers）
* **Database**: PostgreSQL（開發期 SQLite，雲端為 Neon；`DATABASE_URL` 切換）
* **Realtime**: WebSocket 推播（座位狀態廣播＋個人通知）
* **Frontend**: 純靜態 HTML／JS＋Bootstrap 5＋SVG 平面圖＋Chart.js（RWD），本機由後端一併提供，雲端放 GitHub Pages
* **Deployment**: GitHub Pages（前端）＋Render 免費方案（後端）＋Neon（資料庫），見 [部署步驟](docs/deployment.md)

## 4. 快速開始

```bash
# 1. 安裝後端依賴
pip install -r requirements.txt

# 2. 建立資料庫 schema 與示範座位（預設 SQLite dev.db）
alembic upgrade head
python scripts/seed_seats.py

# 3. 啟動後端（http://127.0.0.1:8000，學號登入後進入平面圖）
uvicorn src.main:app --reload
```

切換 PostgreSQL／DBaaS：

```bash
set DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/seatdb
alembic upgrade head
```

### 偵測端（需攝影機的機器）

```bash
pip install -r requirements-detection.txt
python -m src.detection.calibrate --source 0 --seat A1 A2 A3 B1 B2 B3 --box   # 立體框選座位 ROI
python -m src.detection.detector --source 0 --show                            # 啟動偵測迴圈（預設桌面優先判定）
```

沒有攝影機時可用模擬器驗證流程：

```bash
python scripts/simulate_detection.py A1 person_present
python scripts/simulate_detection.py A1 person_left_belongings
```

### 測試

```bash
python -m pytest -q
```

### 報表儀表板

啟動後端後開啟 `http://127.0.0.1:8000/admin.html`（後端設定 `ADMIN_TOKEN` 時需輸入管理密碼）。

## 5. 文件連結

* [啟動與展示指南](docs/demo_guide.md)（含 20 秒快速測試模式與模擬器操作步驟）
* [專題內容](docs/project_content.md)
* [技術架構文件](docs/technical_architecture.md)
* [雲端部署步驟](docs/deployment.md)
* [座位判定準確率評估結果](docs/evaluation_results.md)
* [實作規劃](docs/roadmap.md)
* OpenSpec 規格：`openspec/specs/`（seat-booking、seat-detection、seat-timeout、floor-map-web、usage-report、access-control、cloud-deployment）
