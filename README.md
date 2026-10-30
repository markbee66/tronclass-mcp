# TronClass 課業助理：Streamlit + SQLite + Ollama / Cloudflare Claude

依《期中報告討論整理：AI 語言模型系統整合》建立的 System 1 基礎程式。聊天頁與自動測試共用 `answer()`，從 SQLite 讀出目前學生可見的完整資料，再交給單一模型。公告改期、作業欄位未更新、討論區非官方資訊等情境原樣保留，供測試觀察模型表現。

期中維持「單一 LLM + 基本 prompt + 資料」，尚未加入 MCP、RAG、Coordinator、驗證 agent 或自動更正答案。這些模組可於期末接入既有介面。

## 本次交付與 Ollama 接手

已完成 Streamlit 聊天／資料查詢、SQLite 唯讀資料層、可替換的模型 adapter、批次測試入口，以及程式整合測試。2026-10-30 已在學校虛擬機驗證 Ollama 模型 API 的 GPU 推論、HTTPS 連線與金鑰保護；這不代表完整課業問答正確率已驗證。目前 Cloudflare Claude 的實測則因帳戶餘額不足回傳 HTTP 402，不代表已完成模型回答驗證。

Ollama 負責人可先指定已安裝模型，再啟動同一個介面。遠端共用模型請依下方介面步驟輸入網址與金鑰；CLI／批次評估仍可使用 `OLLAMA_BASE_URL` 與 `OLLAMA_API_KEY`。以下為本機啟動範例：

```powershell
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://localhost:11434/v1"
$env:OLLAMA_MODEL = "填入 ollama list 顯示的完整名稱"
.venv\Scripts\python.exe -m streamlit run app.py
```

模型 HTTP 串接集中在 `tronclass/llm.py`，System 1 流程及基本 prompt 分別在 `tronclass/system1.py`、`prompts/system1.txt`；前端透過 `tronclass/factory.py` 呼叫共用契約。正式 AI 測試題尚需由目前 3 題示例擴充至 15–20 題，每題重複 5–10 次，並人工整理 Verification Log。

## 共用學校虛擬機的 Ollama API

組員在自己的電腦執行本專案，SQLite 查詢、Streamlit 介面與 Python 流程仍在組員電腦；模型推論透過 API 交給學校虛擬機的 GPU。組員不用安裝 Ollama、下載模型、安裝 Tailscale 或登入 Cloudflare。

### 組員設定

#### 從 Streamlit 介面連線（建議）

1. 依下方「啟動」建立 Python 虛擬環境、安裝套件，再執行 `.venv\Scripts\python.exe -m streamlit run app.py`。開啟 `http://localhost:8501`；這是你電腦上的介面，XAMPP 不負責啟動它。
2. 左側「模型服務」選 **Ollama**，「Ollama 連線方式」選 **遠端 Ollama API**。底層仍使用 `provider=ollama`。
3. 在 **API base URL** 貼上負責人提供的目前網址，必須包含 `/v1`，例如 `https://<目前入口>/v1`。遠端含金鑰連線必須使用 HTTPS；只有 localhost／loopback 可用 HTTP。網址不可包含金鑰、帳密或 query string。
4. 在遮蔽的 **API key** 欄位輸入負責人私下提供的金鑰（公開示例：`fake-team-key-do-not-use`）。金鑰只留在目前 Streamlit session，不會存檔或修改全域環境變數；介面不會自動讀取 `OLLAMA_API_KEY`。
5. **模型名稱** 唯讀顯示 `tronclass-system1:latest`，遠端模式沒有模型輸入框或下拉選單，一般組員只需設定 API 網址與 API key。按 **檢查連線** 後會查詢 `/models` 並確認該模型存在；不存在就顯示明確錯誤，不會改用其他模型。畫面 rerun 不會自動查詢清單。
6. 檢查成功後送出課業問題。檢查連線與問答共用目前網址、金鑰及固定模型設定，請求由 Python 後端發送，Quick Tunnel 使用 `stream=false`。切換網址、金鑰或連線方式會清除過期連線狀態、模型清單及原對話，需重新檢查。清單存在只代表服務列出該模型，實際推論仍需送出問題驗收。
7. 使用完畢按 **清除連線／金鑰**，移除遠端網址、金鑰與對話，唯讀模型名稱保留。session 結束後需重新輸入。切換到 **本機 Ollama** 可連接沒有金鑰的本機服務，仍可手動輸入或從模型清單選擇模型；原有 **Cloudflare → Claude** 的模型設定與憑證功能保留。

遠端模型的唯一執行設定來源是 `tronclass/config.py` 的 `REMOTE_OLLAMA_MODEL`。開發者要調整部署模型時只修改此常數並重新啟動 Streamlit；介面顯示、連線檢查與問答都引用這個值，不受 `OLLAMA_MODEL` 或舊 session 模型欄位覆寫。此為介面使用設定，API 閘道不新增模型限制，仍只負責既有頻率限制及安全保護。CLI／本機 Ollama 仍可使用 `OLLAMA_MODEL`。

若缺少設定，依欄位提示補齊；HTTP 401 請確認金鑰，404 請確認完整模型名稱、`/v1` 與目前入口，429 請依 `Retry-After` 提示等待，頻率限制由伺服器控制。逾時請稍後重試或聯絡負責人；入口失效／離線時取得新網址再檢查。為保護金鑰，程式不跟隨重新導向，請使用正確 API 入口。

#### CLI／環境變數方式（保留相容性）

先取得已包含本節金鑰支援的專案版本；如果先前手動套用過 `tronclass-api-key.patch`，請先檢查自己的 diff，勿重複套用。依下方「啟動」建立 Python 3.11 以上的 `.venv` 並安裝依賴，再向虛擬機負責人私下取得三項資料：

| 項目 | 範例／說明 |
|---|---|
| API base URL | `https://<目前入口>.trycloudflare.com/v1`，需包含 `/v1` |
| 模型名稱 | 本次部署為 `tronclass-system1:latest`，由 `qwen3:8b` 建立，context 設為 32768 |
| API key | 負責人提供的組員存取金鑰，不是 Cloudflare token 或 Ollama 雲端金鑰 |

CLI／批次評估可在專案根目錄的同一個 PowerShell 設定：

```powershell
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "https://<目前入口>.trycloudflare.com/v1"
$env:OLLAMA_MODEL = "tronclass-system1:latest"
# 將金鑰貼在密碼欄，避免把它直接寫進命令歷史。
$apiCredential = Get-Credential -UserName "api" -Message "請在密碼欄貼上組員 API key"
$env:OLLAMA_API_KEY = $apiCredential.GetNetworkCredential().Password

# 先測模型清單；後續批次命令請參考下方「批次 AI 測試」。
Invoke-RestMethod "$env:OLLAMA_BASE_URL/models" -Headers @{Authorization = "Bearer $env:OLLAMA_API_KEY"}
```

以上環境設定保留給 CLI／批次評估使用；Streamlit 請依上方介面步驟輸入網址與金鑰，再按「檢查連線」。`localhost:8501` 是組員自己的介面，不是虛擬機 API。程式會在模型清單與問答請求都加上 `Authorization: Bearer ...`；CLI 金鑰從環境讀取，介面金鑰由目前 session 注入，不放入 `Settings`、模型 metadata 或匯出紀錄。本機無驗證的 Ollama 不需要金鑰。

即使入口使用 Cloudflare Tunnel，`LLM_PROVIDER` 仍是 `ollama`；下方「Cloudflare → Claude」是另一種由雲端模型運算、使用不同憑證與計費的服務。

### 虛擬機負責人的啟動、停用與換金鑰

API 閘道只做金鑰驗證、路徑保護與每分鐘頻率限制，不限制已安裝模型、輸出 token、上下文、訊息長度或工具呼叫參數。OpenAI 相容的 `tools`、`tool_calls`、工具訊息與生成參數會原樣轉送；模型及 Ollama 自身的限制仍適用。MCP 工具由組員的 client 執行，這個模型 API 不提供虛擬機的 shell 或檔案操作。

虛擬機端需要 PowerShell 7、Python 3.11 以上、官方 cloudflared；Ollama 必須只監聽本機 11434。在專案根目錄執行：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-gateway.txt
# 第一次或要撤銷舊金鑰時使用 -RotateKey。
.\tools\Start-SharedOllamaApi.ps1 -RotateKey -RequestsPerMinute 30
```

啟動腳本先確認 Ollama 與閘道都只監聽本機、驗證匿名請求被拒絕，再建立 Tunnel。任何啟動步驟失敗都會停止此次建立的程序。金鑰不出現在程序參數、終端輸出或存取 log。

- 私有狀態目錄是 `$env:LOCALAPPDATA\TronClassOllamaAPI`，不在 Git checkout 裡；ACL 僅授權目前 Windows 使用者與 SYSTEM。管理員或已取得同一使用者權限的程式仍可能讀取，這不是整台虛擬機的安全保證。
- 在狀態目錄的 `endpoint.txt` 查看 API base URL、`api-key.txt` 取得金鑰，私下交給組員；不要貼到公開 README、issue、PR、截圖或聊天紀錄。金鑰、入口、程序狀態與 log 檔名也已加入 `.gitignore`。
- 預設所有組員共用 **30 次／滑動 60 秒**，模型清單與問答都計入；超過時回傳 `429` 與 `Retry-After`。沒有每小時配額或同時執行數限制；單次複雜任務仍可能消耗大量 GPU／記憶體，請觀察壓力測試。
- 調整頻率：先停止再以 `Start-SharedOllamaApi.ps1 -RequestsPerMinute 120` 啟動；不帶 `-RotateKey` 會保留金鑰。限制由虛擬機端設定，client 不能自行提高。重啟會重置記憶體中的計數。
- 緊急停止：執行 `.\tools\Stop-SharedOllamaApi.ps1`。只停止記錄且啟動時間匹配的閘道／Tunnel 程序，本機 Ollama 保留。
- 金鑰疑似外洩：先停止，再以 `-RotateKey` 啟動，私下重新發送新金鑰與新入口。只刪 README 或把 repo 改私人不會撤銷憑證。
- 本機預檢：`Start-SharedOllamaApi.ps1 -RotateKey -LocalOnly` 不建立 Tunnel；測完先停止，再正常啟動。
- Quick Tunnel 免費且不需帳號或網域，但重啟後網址會改、沒有 uptime 保證，且官方不支援 SSE。閘道本身能轉送串流，但 **Quick Tunnel 請用 `stream=false`**；要測 SSE，請改用支援 SSE 的 named tunnel 或其他 HTTPS 入口並實測。網域註冊費另計。[免費入口](https://developers.cloudflare.com/workers/wrangler/commands/tunnel/)、[限制](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- 虛擬機及 Tunnel 需持續運作；沒有開機自動啟動。Cloudflare 提供傳輸入口，模型仍在虛擬機運算；問題與回答會經過 Cloudflare，不要用未獲授權的真實學生資料測試。
- 對外只提供帶金鑰的 `GET /v1/models` 與 `POST /v1/chat/completions`；管理 API、docs、其他路徑、query 憑證及帶 Origin 的瀏覽器跨站請求都被拒絕。不跟隨上游重新導向、不把組員金鑰轉送給 Ollama，也不回傳上游錯誤細節。
- 腳本不修改 Windows／學校防火牆，不開放 11434 或 11435 的外網入站。既有 SSH、SMB、系統服務與更新仍由虛擬機／學校管理員維護。
- 問答下載及批次 JSONL／CSV 改記 `connection`（例如 `remote_https`），不記錄真實 `base_url`；設定中的 DB／prompt 路徑只輸出檔名，模型與其他實驗參數保留。這不會清除過去匯出的檔案，也不會遮蔽使用者自己寫進問題或答案的內容。

| 症狀 | 處理方式 |
|---|---|
| HTTP 401 | 介面更新 API key 欄位；CLI 確認 `OLLAMA_API_KEY`；不要在錯誤回報貼金鑰 |
| HTTP 429 | 按 `Retry-After` 等待；大量測試由負責人調高頻率 |
| HTTP 404 | 確認網址含 `/v1`、入口未更換、路徑屬於允許的 API |
| HTTP 502／530、DNS 或連線錯誤 | 檢查本機 Ollama、閘道與 Tunnel |
| 模型繁忙、逾時或任務太長 | 檢查 GPU／Ollama、模型 context 與 client timeout；閘道不額外限制生成長度，Tunnel 自身限制仍適用 |

## Cloudflare → Claude

介面左側可切換 **Cloudflare → Claude** 與 **Ollama**（本機或遠端），不需改動 System 1、SQLite 或測試題。Cloudflare 使用帳戶 REST API 的 Anthropic Messages 格式，預設模型為 `anthropic/claude-haiku-4.5`。底層 adapter 會把共用 messages 中的 system 訊息移到 Anthropic 的 `system` 欄位，其餘對話順序保持一致。

將 `.streamlit/secrets.example.toml` 複製為 `.streamlit/secrets.toml`，只在本機填入帳戶 ID 與 token。該檔已被 Git 忽略；金鑰不放在 `Settings`、模型 metadata 或匯出紀錄中。環境變數可覆寫同名設定，程式不會自動讀取上層 `.env`。

```toml
[app]
provider = "cloudflare"

[cloudflare]
CLOUDFLARE_ACCOUNT_ID = "填入帳戶 ID"
CLOUDFLARE_API_TOKEN = "只在本機填入 token"
CLOUDFLARE_MODEL = "anthropic/claude-haiku-4.5"
```

端點由帳戶 ID 組成 `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/messages`；未指定 `CLOUDFLARE_GATEWAY_ID` 時使用帳戶的 default Gateway。這條路徑使用 Cloudflare token，第三方模型透過 Unified Billing 計費，需 Workers AI Read 權限與可用 credits。[Cloudflare 官方 REST API 說明](https://developers.cloudflare.com/ai-gateway/usage/rest-api/)

「檢查憑證」只確認 token 是否 active，不代表模型權限、計費或額度已通過。實際問答收到 HTTP 402 時，請先確認 Unified Billing 與 credits；401／403 則需檢查權限或帳戶範圍。錯誤不會被偽裝為模型回答。

Cloudflare 模式每次送出 `cf-aig-skip-cache: true`，避免批次重複測試拿到 Gateway 快取回答。Claude 不支援 seed，因此實際結果與 CSV 的 seed 記為空值，JSON metadata 另記 `seed_applied=false`；Settings 中的 seed 僅供切回 Ollama 使用。[快取設定](https://developers.cloudflare.com/ai-gateway/features/caching/)

## 啟動

需要 Python 3.11 以上。使用本機 Ollama 時需另行安裝、啟動服務；共用遠端模型的組員依上方步驟設定即可；使用 Cloudflare 時依上方設定。資料查詢頁不需要模型服務。在專案根目錄執行（PowerShell）：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 由團隊選定並安裝模型；程式不會自動下載大型模型。
ollama list
$env:OLLAMA_MODEL = "填入已安裝模型的完整名稱與 tag"
.venv\Scripts\python.exe -m streamlit run app.py
```

若本機尚未啟動 Ollama，可另外開終端機執行 `ollama serve`；已在背景執行時不必重複啟動。左側「檢查連線」會查詢可用模型。連線失敗會顯示錯誤，不會產生假的 AI 回答。

開啟 `http://localhost:8501`：

- **課業問答**：多輪對話、模型／耗時／未驗證狀態、對話與執行紀錄匯出。
- **資料查詢**：依課程篩選公告、作業、教材與附件文字、個人成績、測驗、點名等。設定、資料或 prompt 改變會重開對話，避免混用舊設定。

### Ollama context window

學生可見資料約 4 萬字元，並非 token 數；還需加上 prompt、歷史訊息及輸出空間。請依模型 tokenizer、支援長度與硬體設定足夠的 context，確認服務實際載入的 context，避免把輸入截斷造成的故障誤當模型推理錯誤。

Ollama 的 OpenAI 相容介面無法在單次請求指定 context size，官方建議建立含 `num_ctx` 的 Modelfile。請把 `Modelfile.example` 的 `FROM` 改為團隊選定的已安裝模型；`32768` 是設定範例，仍需確認對所選模型足夠。[Ollama 官方說明](https://docs.ollama.com/api/openai-compatibility#setting-the-local-context-size)

```powershell
# 先修改 Modelfile.example 的 FROM，再建立固定設定模型。
ollama create tronclass-system1 -f Modelfile.example
$env:OLLAMA_MODEL = "tronclass-system1"
```

長對話也要確認剩餘 context；程式不會自行裁切歷史。輸出達長度上限時，介面會提示，執行紀錄保留 `finish_reason`。

## 分工與擴充位置

| 工作 | 檔案／入口 | 約定 |
|---|---|---|
| Streamlit 介面 | `app.py` | 顯示、設定、對話狀態、匯出；推理／驗證流程留在後端 |
| SQLite 資料層 | `tronclass/database.py` | `CourseRepository.snapshot(student_id)`；未來可供 MCP Server 重用 |
| System 1 | `tronclass/system1.py`、`prompts/system1.txt` | `answer(AnswerRequest)`；基本 prompt 與完整可見資料 |
| 模型連線 | `tronclass/llm.py` | Ollama OpenAI 相容 API、Cloudflare Anthropic Messages API；共用 `Completion` |
| 後端契約 | `tronclass/contracts.py` | `AnswerRequest` / `AnswerResult` / `AssistantBackend` |
| 後端組裝 | `tronclass/factory.py` | UI 與測試都從這裡取得 backend |
| 批次 AI 測試 | `evaluation/run.py` | 共用 `answer()`，不依賴 UI 或 System 1 內部方法 |
| 題目與標準答案 | `evaluation/cases.example.json` | 目前 3 題示例；留給題目負責人擴充為正式 15–20 題 |
| 程式回歸測試 | `tests/` | 不等於 AI 正確率測試 |

```python
from tronclass.config import Settings
from tronclass.contracts import AnswerRequest
from tronclass.factory import create_backend

settings = Settings.from_env()
result = create_backend(settings).answer(AnswerRequest(
    question="資料結構作業三何時截止？",
    student_id=settings.student_id,
    reference_time=settings.reference_time,
    history=[],
))
print(result.answer)
```

System 2 可新增獨立 Coordinator，實作 `AssistantBackend.answer()` 後調整 factory；不要在 `app.py` 加 MCP 呼叫或驗證迴圈。`AnswerResult` 已預留 `tool_calls`、`sources`、`verification`，前端能顯示這些欄位。System 1 預設為空、未驗證，不會把模型自行聲稱的來源當成程式驗證結果。

## 設定

`.env.example` 是環境變數參考，程式**不會自動讀取 `.env`**。Cloudflare 也可從上述本機 secrets.toml 讀取設定。聊天頁可切換服務、temperature、情境時間；本機 Ollama 與 Cloudflare 可調整模型，遠端 Ollama 使用上述集中設定的唯讀模型。Ollama 網址可修改，Cloudflare 網址由帳戶設定產生。本機 Ollama 模型名稱不設預設值，程式不會自動下載模型。

| 環境變數 | 預設值 |
|---|---|
| `TRONCLASS_DB_PATH` | `sample_data/course.db`，相對路徑以專案根目錄起算 |
| `TRONCLASS_STUDENT_ID` | `S11200001` |
| `LLM_PROVIDER` | `ollama`，可由本機 `[app] provider` 選為 `cloudflare` |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | 空白，需填已安裝的完整名稱 |
| `OLLAMA_API_KEY` | CLI／批次使用，遠端閘道有金鑰保護時必填，不匯出；Streamlit 改用 session 密碼欄位 |
| `CLOUDFLARE_ACCOUNT_ID` | 空白，使用 Cloudflare 時必填 |
| `CLOUDFLARE_API_TOKEN` | 只從本機設定或環境讀取，不匯出 |
| `CLOUDFLARE_MODEL` | `anthropic/claude-haiku-4.5` |
| `CLOUDFLARE_GATEWAY_ID` | 空白，使用帳戶 default Gateway |
| `LLM_TEMPERATURE` | `0` |
| `LLM_SEED` | `42` |
| `LLM_TIMEOUT_SECONDS` | `180` |
| `LLM_MAX_TOKENS` | `2048` |
| `REFERENCE_TIME` | `2026-10-31T09:00:00+08:00` |

情境時間固定於範例最新公告（10/30 20:45）之後，供重現測試，不代表實際今天。正式比較時請與資料、prompt 一起固定。資料層不另行推算截止日或判定公告優先級。

## 批次 AI 測試

只驗證題目、SQLite 與 prompt，不呼叫模型：

```powershell
.venv\Scripts\python.exe -m evaluation.run --dry-run
```

使用 Ollama 時，依模型設定執行：

```powershell
$env:OLLAMA_MODEL = "你們固定的模型名稱"
.venv\Scripts\python.exe -m evaluation.run --cases evaluation/cases.example.json --repeat 5
```

使用 Cloudflare 時，可保留本機 secrets.toml 的 `[app] provider="cloudflare"`，或設定 `$env:LLM_PROVIDER="cloudflare"`，再執行同一個 evaluation 命令。此模式會使用帳戶額度；請先確認小型問答成功，再執行大量測試。程式不會在兩種服務間自動 fallback，以免混用不同模型的實驗結果。

每題獨立重複 5 次；多輪測試可在題目增加 `history` 陣列，`role` 限 `user` / `assistant`。正式測試可改為 5–10 次，不會把上一題回答帶入下一題。

結果逐次立即寫入 `results/` 的 JSONL 與 UTF-8 CSV，既有檔案不會被覆寫。可用 `--output results/run_name.jsonl` 指定新檔名。保存內容包含：

- 問題、預期答案、題型、人工判分標準、實際回答。
- 時間、耗時、provider、請求／回傳模型名稱、temperature、實際適用的 seed、輸出上限、連線類型（不含真實 API 網址）、情境時間。
- 可見資料、prompt、完整 messages 的 SHA-256，以及服務回傳的 token usage／finish reason。
- 執行錯誤、人工正誤欄位及備註。連線錯誤記為 error，**不算 AI 回答錯誤**。

CSV 的 `human_correct`、`review_notes` 供整理 Verification Log；目前不做關鍵字自動判分，也不把 HTTP 成功當正確。請先人工標記有效回答，再以相同題目和標準比較 System 1 / System 2。

正式測試請額外留存 `ollama list`、`ollama show <模型>` 的輸出與模型 digest；名稱或 tag 本身不能保證權重沒有改變。temperature 0 與固定 seed 也不保證跨版本／硬體完全一致。

## 程式測試

```powershell
.venv\Scripts\python.exe -m pytest -q
```

使用原始 SQLite fixture、Streamlit AppTest、本機模擬 HTTP 模型服務，不需要下載模型。測試隔離本機設定與環境中的 Ollama／Cloudflare 憑證，僅使用假金鑰與假服務，涵蓋 session 隔離、設定切換及匯出防洩漏。這些測試驗證程式整合，實際模型推理與錯誤率需另行執行上方 AI 測試。

## 範例資料

`sample_data/` 由原 repository 的 `tronclass-ai-assistant-data-github.zip` 解出，保留原始 README、JSON／Markdown、附件、建庫程式，沒有修改課程內容。

SQLite 連線使用 `mode=ro`、參數化查詢。課程依 mock schema 的 `student_course_grades` 對應；個人紀錄限目前學生、教材限 `visibility='student'`、未公布的分數與評語不送入 UI 或模型。原始教師資料保留作為 fixture，但不包含在學生匯出中。

這是固定模擬學生的本機原型，環境變數中的學號不是登入驗證。未來若接真實多使用者服務，需由登入身分決定 student_id。

每次查詢建立並關閉唯讀連線，不共用跨執行緒 SQLite 物件。聊天與測試都從資料庫產生 context，不使用可能過期或含未遮蔽欄位的 `all_data_for_prompt.md`。

模型介面依 [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)；介面測試使用 [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)。
