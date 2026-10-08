# 專案 Agent 工作規範

適用於此儲存庫的後續修改。使用者當次指示優先；以繁體中文溝通。

## 固定工作順序

1. **告知要修改的功能**：動手前簡短說明目標、影響範圍與預期行為。一般修改先告知再執行；使用者要求逐步教學時，每步附指令、範例與判讀，完成後等待使用者說下一步，不一次推進多步。使用者明確授權批次調整時，可完成該批範圍。
2. **更新功能**：先讀相關程式與呼叫流程，依 ponytail 原則重用現有功能，採最小可行修改，不新增推測性的抽象、套件或腳手架。
3. **更新文檔**：同步修改受影響的 README.md、使用手冊.md、docs/ARCHITECTURE.md、設定範本及操作指令，避免留下舊入口或失效指令。README 只保留 dashboard 啟動與操作內容；技術架構留在 docs/ARCHITECTURE.md，開發、部署與 CI 操作留在 docs/MAINTAINERS.md；Agent 發布規則留在本檔。版本變更紀錄只寫入 GitHub Release，不在 README 新增 changelog。
4. **更新版本號**：只有程式碼內容有變動才更新版本；純文件、教學文字或格式調整不升版。每批程式碼修改更新一次版本，預設增加 patch；新功能或不相容變更依實際影響增加 minor 或 major。同步 app.py 的 APP_VERSION、pyproject.toml 的 version、文件中的目前版本，執行 uv lock 更新鎖檔。整理本次變更供發布時寫入 GitHub Release，不在 README 記錄版本歷史。

## 驗證與精簡

- 本機環境使用 Python 3.12 與 uv；安裝用 `uv sync --locked`，啟動用 `uv run app.py`。
- 依修改風險執行必要驗證，保留可重跑的指令與結果。小型文案、樣式或入口調整可用直接檢查，不固定新增 smoke test 或專用測試檔。
- 涉及資料寫入、權限或非簡單邏輯時，執行能驗證實際行為的最小測試；使用暫存資料，避免動到正式資料。需要長期防止回歸時才保留測試檔。
- 驗證後做 ponytail code review，檢查可刪除的重複邏輯、多餘抽象與不必要依賴。不得省略資料安全、錯誤處理或後端權限驗證。
- 相依套件以 pyproject.toml 和 uv.lock 為準。修改依賴後執行下列指令，將 Docker 的 requirements.txt 一起更新：

  ```bash
  uv export --locked --no-hashes --no-header --no-annotate --no-emit-project --output-file requirements.txt
  ```

- 提交前執行 `git diff --check`，確認 .env、.venv、資料庫、備份、日誌及大頭貼沒有被提交。

## 確定要 Push 時

- 使用者明確要求 push，或本次工作已獲授權包含發布時，完成程式、文件、版本與驗證後再提交推送；僅要求本機修改時不自行發布。
- Push 的工作範圍包含該版本的 tag 與 GitHub Release 資訊維護，不能只推程式碼就宣告發布完成。
- 版本歷史以 GitHub Releases 為準，保留既有 Release；不另建 README changelog 或重複的版本紀錄文件。未獲發布授權時，只準備變更摘要，不自行發布。
- 推送前整理 Release notes：版本、功能變更、修正、必要的設定或資料遷移、驗證結果；內容須符合實際提交，不宣稱尚未完成的功能。
- 確認目標分支與遠端最新提交，再 commit、push。tag 採 `v<版本號>`，指向本次發布的 commit；建立或更新對應 GitHub Release，標題與版本一致。
- 已發布的 tag 不得默默移動或覆寫；有新的修改就使用新版本。若工具、權限或登入不足，完成可做的部分並明確報告未完成的 Release 步驟，不宣稱發布成功。
- 推送後確認遠端 commit、tag 與 Release 對應一致，回報 commit、版本、Release 連結及驗證結果。

## GitHub Actions CI 與自動部署

- 已有 .github/workflows/deploy.yml 與 scripts/deploy.sh 草稿；未獲准 push、完成 runner 與 server 設定、驗證實際執行前，不宣稱 CI 或部署已啟用。詳細操作維護於 docs/MAINTAINERS.md。
- CI 至少檢查 uv 鎖檔／依賴一致性、與變更相關的驗證及 Docker 建置。版本、tag 和 Release 的一致性應在發布流程檢查。
- 自動部署只能在對應 commit 的 CI 通過後執行；觸發方式、正式分支及目標伺服器依使用者設定，不自行猜測。
- 已有自動 tag／Release／部署 workflow 時，使用既有流程，避免 agent 手動操作產生重複發布；查核執行結果再回報。
- SSH 金鑰、伺服器連線與其他秘密使用 GitHub Secrets／Environment，不寫入程式碼、文件或日誌。
- 部署須保留 .env、資料庫、備份、日誌與大頭貼；需要資料遷移時先備份，記錄可執行的復原方式。
- 回報時區分「程式已 push」、「Release 已發布」、「CI 通過」及「伺服器已部署」，未驗證的狀態不可宣稱完成。
