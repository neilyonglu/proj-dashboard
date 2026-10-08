# 開發與部署指南

目前版本：v1.4.4。使用者操作請看 [README](../README.md) 與 [使用手冊](../使用手冊.md)；程式模組請看 [架構文件](ARCHITECTURE.md)。版本變更只記錄於 GitHub Releases。

## 1. 部署設定與目前進度

| 項目 | 本專案設定 | 設定位置 |
|---|---|---|
| Server | Ubuntu 24.04、x86_64，已有 Docker Compose | server |
| 部署目錄 | `/home/genton/Proj/proj-dashboard` | workflow 的 DEPLOY_PATH |
| Runner 標籤 | `self-hosted`、`Linux`、`X64`、`proj-dashboard` | runner 與 workflow |
| Runner 工作目錄 | `/home/genton/Proj/actions-runner/proj-daashboard/_work` | runner，與部署目錄分開 |
| Compose project name | `proj-dashboard`（server 已完成移轉） | server `.env` 的 COMPOSE_PROJECT_NAME |
| 主機 port | `5001`（目前網站沿用） | server `.env` 的 DASHBOARD_PORT |
| 容器內 port | 固定 5001 | Compose 與既有健康檢查 |
| 通知 | GitHub Actions 內建通知 | 個人 GitHub 通知設定 |

不用提供 webhook、SSH 部署密鑰或把正式環境密碼交給 CI。若儲存庫改為 private，server 的 clone 需具備讀取 GitHub 的權限，例如唯讀 deploy key。workflow 的 checkout 權限不會自動套用到 server 的另一份 clone。

設定檔已完成時仍不代表 CI／部署已啟用；需獲准 push、具備 server 與 runner 設定，再驗證完整 CI／部署。已確認 server 原部署在 main、工作區乾淨，Compose 5.5.1 支援 --wait／--wait-timeout。repo 與部署資料夾改名後，server origin 及現有容器已依逐步操作更新；依使用者回報，runner 已註冊為 genton-server、背景服務正常且工具與 Docker 權限檢查通過；server 名稱移轉、.env 補設定及 Compose 修改 stash 已完成。GitHub 完整 CI／自動部署尚未執行。

## 2. deploy.yml 逐段說明

檔案：[.github/workflows/deploy.yml](../.github/workflows/deploy.yml)。

| 區段 | 做什麼 | 為什麼 |
|---|---|---|
| `on.push.branches: [main]` | 只有 push 到 main 會觸發 | 不把其他分支自動部署到正式 server |
| `permissions.contents: read` | Actions token 只有讀取程式碼的權限 | 這個 workflow 不負責 push、tag 或 Release |
| `jobs.ci.runs-on: ubuntu-24.04` | 在 GitHub-hosted Ubuntu x64 runner 執行 | CI 不使用正式 server 的資料與密碼 |
| `checkout.ref: github.sha` | checkout 觸發本次 push 的 commit | 後續 main 更新不會改變本次驗證對象 |
| `persist-credentials: false` | 不在 checkout 留下 Git 認證 | CI 與部署不需要寫入 GitHub |
| `setup-uv` | 安裝與本機一致的 uv 0.12.9 | 檢查鎖檔並執行 server 腳本測試 |
| `Check locked dependencies` | 禁止追蹤 .env、檢查 uv.lock、比較 Docker requirements | 防止秘密入庫或本機／Docker 依賴不同步 |
| `Build Docker image` | 建置本次 SHA 的 CI image | 先驗證 Dockerfile 與依賴可建置 |
| `Test application inside the image` | 在 image 內跑 stdlib unittest、確認沒有 .env | 驗證應用、權限與舊資料庫補欄，不讀正式資料 |
| `Test deployment guards` | 用暫存 Git repo、模擬 Docker 執行部署腳本 | 驗證 exact SHA、分支、乾淨目錄、互斥與衝突處理 |
| `Check running container health` | 啟動 CI 容器，等最多 120 秒 | 真正測試啟動與 Dockerfile 的健康檢查；不用主機 port |
| `deploy.needs: ci` | 等 CI 成功才執行部署 | CI 任一步驟失敗，deploy 就不會執行 |
| `deploy.if` | 再確認 ref 是 main | 避免將來修改觸發條件時誤部署其他分支 |
| `deploy.runs-on` | 選擇符合全部標籤的 self-hosted runner | 避免交給同台 server 上其他專案的 runner |
| `concurrency` | 同一 repo 的部署一次只能跑一個，不取消正在部署的 job | 避免兩次建置／更新互相干擾 |
| `Deploy the tested commit` | 傳入部署路徑、github.sha、repository 並執行 deploy.sh | server 使用剛才 CI 通過的 SHA |

健康檢查使用 Dockerfile 既有的 HTTP 首頁檢查；首頁也會查詢資料庫。CI 以一次性的測試環境變數啟動，不建立正式 `.env`。CI 的測試檔透過唯讀 mount 使用，不放進正式 image。

GitHub concurrency 不保證所有排隊部署的順序，也可能取代尚未開始的 pending job。腳本只允許向前更新；已被 server 較新版本超越的舊 SHA 會失敗，避免版本倒退。

參考：[GitHub runner 選擇](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)、[concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)。

## 3. Server 腳本做什麼

檔案：[scripts/deploy.sh](../scripts/deploy.sh)。流程如下：

1. 檢查部署路徑、40 字元 SHA、repository；確認部署路徑是 Git 根目錄。
2. 取得 `.git/dashboard-deploy.lock` 的 flock，阻擋同目錄的其他自動／手動部署。
3. 確認 server checkout 是 main，沒有已修改或未追蹤檔案。被 Git 忽略的 .env、data/ 不算工作區修改。
4. 確認 origin 對應這個 GitHub repo，且 server .env 存在、可讀、被忽略且未追蹤。
5. `git fetch origin <tested SHA>`，禁止該 commit 追蹤 .env，只以 `git merge --ff-only <tested SHA>` 更新 main。沒有 git pull 最新 main、reset --hard 或自動 stash。
6. 確認 HEAD 就是 CI 通過的 SHA，工作區仍乾淨。
7. 由 Compose 解析 .env，不 source 或印出秘密。檢查必要密碼、同名 project 是否屬於別的目錄／服務、容器名稱及 port 是否衝突。既有同一專案容器占用自己的 port 可正常更新。
8. 執行 `docker compose build`，再執行 `docker compose up --detach --remove-orphans --wait --wait-timeout 120`。
9. 健康檢查未通過時印出容器狀態與最近日誌，讓 Actions 明確失敗；成功時回報實際部署的 SHA。

CI image 不上傳 registry；server 依需求重新建置相同 commit，build 失敗時不執行 up。up 失敗不會自動回滾。現有 .env、資料庫、大頭貼、備份與日誌保留在 server。應用啟動沿用既有備份與資料庫補欄流程。

Docker 會做最後的 port 綁定檢查；若其他程式在盤點後占用 port，up 仍會失敗，不會停止或刪除另一個專案。

參考：[Compose project name](https://docs.docker.com/compose/how-tos/project-name/)、[compose up 的 --wait](https://docs.docker.com/reference/cli/docker/compose/up/)。

## 4. Server 安裝步驟

### 4.1 先盤點，這一步不更動其他專案

以 genton 登入 server：

```bash
docker compose version
docker compose ls --all
docker ps -a --format 'table {{.Names}}\t{{.Ports}}'
sudo ss -ltnp
```

確認 `docker compose up --help` 支援 `--wait`、`--wait-timeout`。本專案不再設定固定 container_name 或共用的 image tag，Compose 會依 project name 產生名稱。

如果現有 dashboard 已在運作，先查它的 Compose project name 與 working_dir：

```bash
docker inspect <現有dashboard容器名稱> --format '{{ index .Config.Labels "com.docker.compose.project" }}'
docker inspect <現有dashboard容器名稱> --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
```

本次依使用者要求將 project name 改為 proj-dashboard，並沿用原 port 5001；其他專案不得共用此 project name。若既有容器沒有正確 Compose 標籤，請先辨識它的來源，再安排本專案自己的移轉，不執行全 server 的 down 或 prune。

### 改名後的首次移轉紀錄與原則

本次已依使用者回報完成手動移轉與舊資源清理；以下記錄改名時需要處理的事項。

原 Compose project name 與容器名稱為 `proj_dashboard`，容器的 working_dir 標籤仍指向 `/home/genton/Proj/proj_dashboard`。新名稱為 `proj-dashboard`，新目錄為 `/home/genton/Proj/proj-dashboard`。這些舊標籤不會隨資料夾改名自動更新。

移轉須安排短暫停機：先保存原 Compose 設定並確認 data/ 的 bind mount 實際來源、備份資料，準備並成功建置新設定，再明確選取舊 project 停止及移除它的容器（不刪資料、不使用 --volumes），最後從新目錄啟動新 project 並檢查健康。不要在 port 5001 仍由舊容器占用時直接執行自動部署；部署腳本會拒絕此衝突。

新容器預期名稱為 `proj-dashboard-dashboard-1`，project 標籤為 `proj-dashboard`，working_dir 為新目錄。舊名稱只在此移轉說明中保留，不能全域替換後就當作 server 已移轉完成。實際移轉指令需依當下 server 設定確認後，逐步操作。

### 4.2 準備 genton 與部署目錄

```bash
sudo apt-get update
sudo apt-get install -y git python3 util-linux iproute2
docker info
```

若 genton 沒有 Docker 權限，管理者可執行 `sudo usermod -aG docker genton`，重新登入後再確認 docker info；若 runner service 已啟動，也須重啟該 service 取得新的群組。

若目錄還沒有 clone：

```bash
mkdir -p /home/genton/Proj
git clone --branch main https://github.com/neilyonglu/proj-dashboard.git /home/genton/Proj/proj-dashboard
```

若已經有 clone，就直接檢查，不要覆寫：

```bash
cd /home/genton/Proj/proj-dashboard
git branch --show-current
git status --short
git remote get-url origin
```

repo 改名後，既有 clone 的 origin 也要更新：

```bash
git remote set-url origin https://github.com/neilyonglu/proj-dashboard.git
git remote get-url origin
```

分支須是 main；有修改時先自行保存或提交，不讓部署腳本刪掉它們。第一次啟用必須等本次變更獲准 push，server 才能取得 workflow、Compose 與腳本。

### 4.3 只在 server 設定 .env

已有 .env 時保留並編輯，沒有才執行 `cp .env.example .env`：

```bash
cd /home/genton/Proj/proj-dashboard
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
id -u genton
id -g genton
```

填入 SECRET_KEY、自己的 DB_ADMIN_PASSWORD，以及盤點後的 COMPOSE_PROJECT_NAME、DASHBOARD_PORT 和 genton 的 UID、GID。容器內 HOST/PORT 已固定為 0.0.0.0/5001；主機 port 改 DASHBOARD_PORT，不要改 PORT。

```text
SECRET_KEY=<隨機值>
DB_ADMIN_PASSWORD=<你的管理密碼>
COMPOSE_PROJECT_NAME=proj-dashboard
DASHBOARD_PORT=5001
UID=<id -u genton的結果>
GID=<id -g genton的結果>
```

SECRET_KEY、DB_ADMIN_PASSWORD、UID 與 GID 是佔位值，需替換；本專案已確認使用 proj-dashboard 與主機 port 5001。不要把 server 的 .env 放入 Git、Actions secrets 或 build args。

```bash
mkdir -p data/instance data/avatars
docker compose config --quiet
git check-ignore .env data/instance data/avatars
```

`config --quiet` 驗證設定而不印出已展開的密碼。資料目錄須由 genton 建立／可寫；UID/GID 必須匹配，否則容器無法寫入 SQLite。

### 4.4 安裝專案專用 runner

GitHub repo → Settings → Actions → Runners → New self-hosted runner，選 Linux、x64。使用 UI 顯示的最新版下載、SHA256 驗證與解壓指令；不要套用過期的下載版本或把註冊 token 寫入文件。

將 runner 放在獨立的新目錄，例如：

```bash
mkdir -p /home/genton/Proj/actions-runner/proj-daashboard
cd /home/genton/Proj/actions-runner/proj-daashboard
# 在此執行 GitHub UI 的下載、校驗與解壓指令
./config.sh --url https://github.com/neilyonglu/proj-dashboard --token <UI提供的註冊token> --name genton-server --labels proj-dashboard --work _work
sudo ./svc.sh install genton
sudo ./svc.sh start
sudo ./svc.sh status
```

保留預設 self-hosted／Linux／X64 標籤，另加 proj-dashboard。只有本專案 runner 使用這個專用標籤。runner 的 _work 與部署 clone 必須分開，checkout 的清理不會碰 server .env 或資料。

在 GitHub Runners 頁確認此 runner 為 Idle；以 genton 確認 Git、python3、flock、ss 與 Docker 可執行。若 runner 已有同名安裝，先辨識 service 與用途，不覆蓋另一專案的 runner。

參考：[新增 self-hosted runner](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners)、[安裝為 service](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application)。

### 4.5 通知與首次驗證

GitHub 個人 Settings → Notifications → System → Actions，選 On GitHub 或 Email；需要只看失敗時選 Only notify for failed workflows。依個人帳號通知設定訂閱此 repo 的 Actions，沒有 webhook 或額外通知 job。

獲准 push main 後，到 Actions 查看此 run：先 ci 成功，再 deploy 執行。CI 失敗會跳過部署；runner 未上線／標籤不符時部署會排隊。

server 確認：

```bash
cd /home/genton/Proj/proj-dashboard
git rev-parse HEAD
docker compose ps
```

HEAD 必須和該 Actions run 的 commit 一致；容器為 healthy，然後開啟 server 實際網址。檢查首頁與管理者登入。通知只表示 workflow 狀態，不代表每個收到郵件的人都已完成網站人工驗證。

參考：[GitHub Actions 通知設定](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications)。

## 5. 故障排查與復原

| 失敗訊息 | 如何處理 |
|---|---|
| Must be on main / detached HEAD | 確認 clone 與分支，先保存修改再切回 main |
| Uncommitted or untracked changes | 查看 git status，人工保存／處理；不自動 stash 或 reset |
| Origin does not match | 檢查是否指定了其他 repo 的部署目錄 |
| .env missing / required values | 檢查 server .env 及檔案權限，勿印出或貼出密碼 |
| Local main ahead/diverged | 舊 CI 不會覆蓋較新部署；若是本機提交，先人工處理分歧 |
| Project/container/port conflict | 依盤點結果改本專案 .env，或安排本專案自己的移轉 |
| Build failed | 舊容器仍運作；從 Actions build 日誌修正問題後再 push |
| Startup/health check failed | 查看本專案 docker compose logs、資料目錄權限與健康檢查 |

需要復原時，先停止本專案的 runner service，確認乾淨工作區與先前已驗證的 SHA，備份 data/，再人工切到該 SHA、執行 compose build/up。完成後切回 main 並修正新版；部署腳本不會自動做降版。若新版已改資料庫結構，先評估舊版相容性，必要時從備份還原 .db。

不得刪除 .env、data/ 或使用全 server 的 docker system prune 作為復原方式。

## 6. 開發與發布

本機使用 Python 3.12 與 uv。開發用環境變數啟動，正式 .env 只留在 server，例如 PowerShell：

```powershell
uv sync --locked
$env:SECRET_KEY = uv run python -c "import secrets; print(secrets.token_hex(32))"
$env:DB_ADMIN_PASSWORD = '自行設定本機測試密碼'
$env:HOST = '127.0.0.1'
uv run app.py
```

應用測試用 `uv run --locked python -m unittest discover -s tests -p test_app.py -v`。Linux 部署腳本測試用 `uv run --locked python -m unittest discover -s tests -p test_deploy.py -v`；Windows 會跳過 Linux 腳本測試。測試用暫存資料庫／Git repo，不改正式 server。

依賴以 pyproject.toml、uv.lock 為準，修改後同步 Docker requirements：

```bash
uv export --locked --no-hashes --no-header --no-annotate --no-emit-project --output-file requirements.txt
```

依 AGENTS.md 先告知功能，再更新功能、文件及版本。發布前同步 app.py、pyproject.toml、文件版本並 uv lock；取得 push 授權後才提交、push、維護對應 tag／GitHub Release。此 CI/CD workflow 不會自行建立 tag 或 Release。

最後回報需分別確認 push、Release、CI、server 部署狀態；本機測試通過不等於 GitHub 或 server 已執行。
