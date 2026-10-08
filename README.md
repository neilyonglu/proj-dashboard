# 專案管理與工時追蹤系統 (Project Dashboard)

> **版本：v1.4.3**

一個基於 Python Flask 開發的輕量級企業內部專案與人員工時管理系統。提供直覺的介面來管理專案進度、人員工作紀錄、並具備甘特圖式的時間軸檢視以及完整的資料庫匯入/匯出功能。

## 🌟 主要功能 (Features)

*   **📊 總覽儀表板 (Dashboard)**：快速檢視目前進行中的專案數量、參與人員總數與當月總工作天數。首頁提供四個日常功能入口；右上角顯示「管理者登入」，密碼正確後直接進入後台，回到首頁時該連結改為「資料庫管理」。
*   **📅 專案時間軸 (Project Timeline)**：以甘特圖 (Gantt Chart) 形式視覺化呈現所有專案的起始與結束時間，並精準標示各人員在專案中的工作區段。
    *   清楚的今天線、月份交替底色與週末背景區隔。
    *   明顯的水平卷軸，滑鼠移到人員工作區段時顯示完整資訊（日期、天數、時數、內容）的浮動提示。
    *   月份區間篩選（修正了選取月份時溢出到下個月的問題）。
*   **📝 工作紀錄追蹤 (Task Tracking)**：記錄個別人員在不同專案中投入的工作天數與內容，並可額外填寫**日班 / 加班 / 夜班時數**（選填，與工作天數並存）。
*   **👥 人員進度管理 (Employee Dashboard)**：專屬的人員檢視頁面，支援自訂大頭貼與顯示名稱，快速查詢特定員工參與的所有專案與總時數。已離職人員（設有辭職日期）不會出現在選單中，但既有連結仍可正常開啟其紀錄。
    *   工作紀錄支援**依月／週／日分組收納**，大量筆數一目了然，可逐組展開／收合。
    *   **刪除紀錄限管理者**：一般使用者僅能查看與編輯，刪除需登入管理者帳號後才顯示。
*   **⏱️ 加班統計 (Overtime Stats)**：依日／月／年／自訂區間統計各人員與各專案的日班、加班、夜班時數，由高到低排序。
*   **🗄️ 資料庫管理 (Database Management)**：受密碼保護的後台管理介面。
    *   **人員名單集中維護**：從「參與人員」分頁的「管理參與人員」新增、修改或移除人員；新增與編輯工作表單只提供人員選擇，不提供名單管理入口。
    *   支援全資料表（專案、工作紀錄、人員、業務代表、專案種類）的**搜尋與管理**，專案狀態篩選可**複選**。
    *   **新增、編輯與刪除**專案種類與業務代表（改名時會自動同步更新關聯專案）；修改人員系統代號時會同步更新所有相關工作紀錄。
    *   **CSV 匯出/匯入**：支援一鍵備份資料為 CSV，並支援上傳 CSV 進行批量新增或覆蓋更新（自動處理 Excel 產生的 BIG5 編碼與 UTF-8-BOM 問題）；工作紀錄匯入會自動略過完全重複的資料，也可選擇「匯入前清空所有工作紀錄」。
    *   **全庫匯出／匯入 (Excel)**：一次匯出整個資料庫成單一 `.xlsx` 檔（每個資料表各一個分頁），也可將該檔上傳回系統，依序匯入業務代表、專案種類、參與人員、專案、工作紀錄；匯入時可選「略過重複」或「覆蓋更新」，並可勾選「匯入前清空整個資料庫」（會先自動備份）。
    *   **資料庫備份/還原**：每天自動備份資料庫一次（啟動時檢查＋伺服器持續運作時每小時檢查一次，保留最近 10 份），並可在後台一鍵「立即備份」、「下載備份」與「還原備份」（還原前會自動先備份目前資料）。
*   **📋 操作日誌 (Activity Log)**：所有寫入操作（新增／編輯／刪除／匯入／備份、登入成功與失敗）皆自動記錄至 `data/instance/logs/` 目錄，格式為 `[時間] IP | 操作 | 細節`，每個月份自動分檔（每檔上限 2000 筆）。

## 🛠️ 技術棧 (Tech Stack)

*   **後端**: Python 3, Flask, Flask-SQLAlchemy
*   **資料庫**: SQLite (`app.db`)
*   **前端**: HTML5, Tailwind CSS (透過 CDN), Material Symbols (Icons)
*   **伺服器**: Waitress (WSGI Production Server)
*   **部署**: Docker (`python:3.12-slim`，非 root 執行)

## 📁 專案結構 (Project Structure)

```text
proj_dashboard/
├── app.py                 # 應用程式進入點（Flask 初始化、設定、啟動）
├── Dockerfile             # python:3.12-slim，非 root 執行，waitress 監聽 5001
├── docker-compose.yml     # build args UID/GID + instance/ 與 avatars/ bind mount
├── requirements.txt       # 鎖版本的執行期相依套件
├── .dockerignore
├── .env                   # 環境變數（需手動建立, 已被 .gitignore 排除）
├── .env.example           # .env 範本
├── core/                  # 核心應用模組
│   ├── extensions.py      # SQLAlchemy db 實例
│   ├── models.py          # 資料庫模型（Project, Task, Personnel, ...）
│   ├── helpers.py         # 工具函式（備份＋每日排程、Migration、表單解析）
│   ├── activity_log.py    # 操作日誌寫入模組
│   └── routes/            # 路由模組
│       ├── main.py        # 儀表板、時間軸、員工頁、加班統計
│       ├── projects.py    # 專案 CRUD
│       ├── tasks.py       # 工時紀錄 CRUD
│       ├── admin.py       # 後台登入、備份 API、CSV/Excel 匯出匯入
│       └── manage.py      # 人員、代表、分類管理
├── data/                  # 主機端執行期資料（bind mount, 已被 .gitignore 排除）
│   ├── instance/          # app.db、backups/（保留最近 10 份）、logs/
│   └── avatars/           # 人員大頭貼
├── static/
└── templates/             # HTML 渲染模板
```

## 🚀 部署 (Docker)

本系統僅以 Docker 部署於 Linux，不提供 Windows exe 打包與 App 內自動更新。

```bash
git clone https://github.com/neilyonglu/proj_dashboard.git
cd proj_dashboard

cp .env.example .env
python3 -c "import secrets; print(secrets.token_hex(32))"   # 產生 SECRET_KEY

# 編輯 .env，填入 SECRET_KEY 與 DB_ADMIN_PASSWORD（兩者皆必填，未填程式拒絕啟動）
nano .env

# 容器以此 UID/GID 執行，確保 bind mount 可寫且檔案歸屬主機使用者
printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env

mkdir -p data/instance data/avatars
docker compose up -d --build
docker compose logs -f
```

預設 `docker-compose.yml` 將主機的 `5001` 埠轉送至容器，可於伺服器開啟 <http://localhost:5001>，或從遠端開啟 `http://<server>:5001`（需網路與防火牆允許）。若只需透過 SSH 通道存取，先將 `ports` 改為 `127.0.0.1:5001:5001`，再建立通道：

```bash
ssh -L 5001:127.0.0.1:5001 <user>@<server>
```

再於本機瀏覽器開啟 <http://localhost:5001>。

### 資料位置

| 主機路徑 | 容器內路徑 | 內容 |
|---|---|---|
| `./data/instance` | `/app/instance` | `app.db`、`backups/`、`logs/` |
| `./data/avatars` | `/app/static/avatars` | 人員大頭貼 |

兩者皆為 bind mount，重建 image 不會被覆蓋，可直接用 `scp` / `rsync` 備份整個 `data/`。

### 更新版本

```bash
git pull
docker compose up -d --build
```

只重建 image，`data/` 完全不動。更新前建議先在後台按一次「立即備份」。

### 常用維運指令

```bash
docker compose ps                  # 檢視容器狀態與健康檢查
docker compose logs -f --tail 100  # 追蹤即時日誌
docker compose restart             # 重啟
docker compose down                # 停止並移除容器（資料保留在 data/）
du -sh data/instance/backups       # 檢查備份佔用空間
docker image prune -f              # 清理重建後殘留的舊 image
```

### 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `SECRET_KEY` | ✅ | Flask session 簽章金鑰 |
| `DB_ADMIN_PASSWORD` | ✅ | 資料庫管理頁密碼 |
| `PORT` | | 監聽埠，預設 `5001` |
| `TZ` | | 時區，image 預設 `Asia/Taipei` |
| `UID` / `GID` | | 容器執行身分，預設 `1000` |

## 💡 使用說明

1. **首次啟動**：系統會自動建立 `data/instance/app.db`，並預先寫入預設的業務代表、專案種類與人員名單。若資料庫為舊版，啟動時會自動補上新欄位（時數欄）。
2. **新增專案**：進入首頁「專案進度表」，點擊右上角「新增專案」，填寫基本資訊。
3. **資料庫管理**：點擊首頁右上角「管理者登入」，輸入 `.env` 中設定的 `DB_ADMIN_PASSWORD`，驗證成功後直接進入後台；回到首頁時，右上角顯示「資料庫管理」。未登入者直接開啟後台網址仍會被導向登入頁。人員名單統一由「參與人員 → 管理參與人員」維護。可在此下載 CSV 備份、匯入修改後的 CSV，用「全部匯出 / 全部匯入 (Excel)」一次備份或還原全部資料表，或使用「立即備份 / 下載備份 / 還原備份」管理整個 `.db` 檔。
4. **資料庫備份與還原**：每天自動在 `data/instance/backups/` 建立一次備份（啟動時檢查一次，之後每小時再檢查一次），最多保留最近 10 份。還原時上傳先前下載的 `.db` 檔，系統會在覆蓋前自動先備份目前資料（`pre_restore`）。
5. **操作日誌**：所有操作記錄在 `data/instance/logs/activity_YYYYMM_NNN.log`，可直接用文字編輯器開啟查閱。

## 驗證管理者入口

使用現有執行期相依套件即可執行 `python smoke_admin.py`。測試使用暫存資料庫，檢查未登入、錯誤密碼、登入成功、首頁入口與工作表單，不讀寫正式資料。Docker 環境可執行：

```bash
docker compose run --rm --no-deps dashboard python smoke_admin.py
```

## 🚀 發布新版本

1. 更新 `app.py` 裡的 `APP_VERSION`，並在下方「版本紀錄」補上 changelog。
2. Commit、push 到 GitHub，視需要建立 tag（例如 `git tag v1.4.3 && git push origin v1.4.3`）。
3. 伺服器上依照上方「更新版本」章節執行 `git pull` + `docker compose up -d --build` 套用新版。

## 📋 版本紀錄 (Changelog)

### v1.4.3
- **管理者入口移至右上角**：移除首頁資料庫管理卡片，改用「管理者登入」連結；密碼驗證成功後直接進入後台，首頁右上角改顯示「資料庫管理」，沿用既有 session 與後端權限檢查。
- **人員名單集中於 DB 管理**：移除新增與編輯工作表單的「管理名單」連結，統一從「參與人員 → 管理參與人員」維護。
- **文件同步**：更新 README、使用手冊與架構文件的入口流程、版本與部署連線說明。

### v1.4.2
- **新增工時只列在職人員**：編輯工時仍保留該紀錄原有人員，即使已辭職。
- **名單管理限管理者**：人員、業務代表與專案種類管理頁加入後端登入驗證，專案表單管理連結只在登入後顯示。

### v1.4.1
- **全庫匯入 (Excel)**：資料庫管理頁新增「全部匯入 (Excel)」，可上傳「全部匯出」產生的 `.xlsx` 檔，依序匯入業務代表、專案種類、參與人員、專案、工作紀錄五張表；支援「略過重複／覆蓋更新」與「匯入前清空整個資料庫」（自動先備份）。此前只能匯出全庫，無法整批匯入回去

### v1.4.0

- **改為 Docker 部署**：新增 `Dockerfile`、`docker-compose.yml`、`requirements.txt`、`.env.example`；容器以非 root 執行，`instance/` 與 `static/avatars/` 改為主機 bind mount
- **移除 Windows 專用程式碼**：刪除 `build.bat`、`tools/installer.py`、`core/updater.py`、`docs/RUNBOOK.md`，以及首頁與後台的「檢查更新／一鍵更新／手動安裝更新」介面。更新方式改為 `git pull` + `docker compose up -d --build`
- **密碼不再有預設值**：`SECRET_KEY` 與 `DB_ADMIN_PASSWORD` 未設定時程式直接拒絕啟動（原本會退回 `admin123`）
- **`.env` 不再覆寫環境變數**：改用 `setdefault`，容器傳入的變數優先於 `.env` 檔內容
- **修正時區與日誌輸出**：image 設定 `TZ=Asia/Taipei` 與 `PYTHONUNBUFFERED=1`，備份檔名、`instance/logs/` 時間與 `docker logs` 皆正常（原本在容器內會是 UTC）
- **修正 CSV 匯入編碼**：實際支援 UTF-8 / UTF-8-BOM / CP950 / BIG5（原本只解 UTF-8，遇 Excel 產生的 BIG5 檔會直接失敗）

### v1.3.2.1
- **專案狀態改回單選**：新增/編輯專案時的狀態欄位改回單選下拉選單（v1.3.2 誤把它也改成可複選）；專案列表、時間軸、資料庫管理頁的狀態「篩選」維持可複選不變

### v1.3.2
- **工作紀錄匯入可選擇先清空**：匯入 CSV 前可勾選「匯入前清空所有工作紀錄」，會先自動備份再清空，避免舊資料與新資料混雜；匯入視窗提示文字也修正為實際的去重規則
- **員工表不顯示離職員工**：`/employee-case` 的員工下拉選單只列出在職人員（透過連結直接開啟離職員工的紀錄仍可正常顯示）
- **專案狀態改為可複選**：新增/編輯專案時可同時勾選多個狀態（例如「進行中」+「等待中」），專案列表與時間軸的狀態篩選也改為可複選

### v1.3.1
- **全庫匯出 (Excel)**：資料庫管理頁新增「全部匯出 (Excel)」，一次匯出整個資料庫成單一 .xlsx 檔，每個資料表各一個分頁
- **手動安裝更新程式**：新增獨立的 `proj_dash_installer.exe`，雙擊即可連線 GitHub 抓取最新版本並安裝，不需要透過網頁介面，`instance/app.db` 與 `instance/backups` 不會被更動
- **自動更新改為只覆寫有變動的檔案**：套用更新前逐檔比對雜湊值，未變動的檔案不再重新寫入，降低重啟風險

### v1.3.0
- **資料庫每日備份修正**：改為啟動時＋背景每小時檢查一次，伺服器長時間不重啟也能確保每天備份一次（原本只在啟動當下判斷，長期不重啟就不會再備份）
- **一鍵自動更新**：首頁與資料庫管理後台可偵測 GitHub 上的新版本，管理者登入後可一鍵下載、自動關閉並重啟為新版（詳見下方「發布新版本」說明）

### v1.2.1
- **員工表專案圓餅圖**：員工資訊卡右側新增「專案分佈」甜甜圈圖，顯示各專案工時佔比；點擊下方分組標頭（年／月／週／日）可即時切換該期間的圓餅圖，tooltip 改為 HTML 浮層不受 canvas 邊界遮擋

### v1.2.0
- **專案詳情頁面**：點擊專案名稱進入專案詳情，含工期/人員/紀錄統計卡、人員工時圓餅圖（可點進員工表）、日/加/夜時數橫條圖
- **員工表「年」分組**：新增「年」分組選項，可依年度收納大量紀錄
- **專案表人員可點**：專案表格與時間軸的人員名稱改為連結，點擊直接跳到該員工工時頁

### v1.1.1
- 修正加班統計頁標題「加班統計」文字改為可點連結，點擊回首頁

### v1.1.0
- 員工表工作紀錄支援依**月／週／日分組**，可折疊展開，大量筆數易於瀏覽
- 刪除工作紀錄／專案限**管理者登入**才可操作（後端同步防護）
- 首頁**資料庫管理**入口未登入時顯示鎖頭，登入後才顯示完整入口
- 新增**操作日誌**系統，自動記錄所有寫入操作、登入事件至 `instance/logs/`
- 加班統計頁新增「首頁」文字超連結

### v1.0.1
- 加班統計（日/月/年/自訂區間，日加夜三欄）
- 員工辭職標記
- 狀態過濾
- 工時模糊下拉

## 📄 授權 (License)

This project is intended for internal company use.
