# TronClass 課業助理：Streamlit + SQLite + Ollama / Cloudflare Claude

依《期中報告討論整理：AI 語言模型系統整合》建立的 System 1 基礎程式。聊天頁與自動測試共用 `answer()`，從 SQLite 讀出目前學生可見的完整資料，再交給單一模型。公告改期、作業欄位未更新、討論區非官方資訊等情境原樣保留，供測試觀察模型表現。

期中維持「單一 LLM + 基本 prompt + 資料」，尚未加入 MCP、RAG、Coordinator、驗證 agent 或自動更正答案。這些模組可於期末接入既有介面。

## 本次交付與 Ollama 接手

已完成 Streamlit 聊天／資料查詢、SQLite 唯讀資料層、可替換的模型 adapter、批次測試入口，以及 26 項程式整合測試。實際 Ollama 模型尚未聯調；目前 Cloudflare Claude 的實測則因帳戶餘額不足回傳 HTTP 402，不代表已完成模型回答驗證。

Ollama 負責人可先指定已安裝模型，再啟動同一個介面；若 Ollama 位於另一台機器，修改 `OLLAMA_BASE_URL` 即可：

```powershell
$env:LLM_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://localhost:11434/v1"
$env:OLLAMA_MODEL = "填入 ollama list 顯示的完整名稱"
.venv\Scripts\python.exe -m streamlit run app.py
```

模型 HTTP 串接集中在 `tronclass/llm.py`，System 1 流程及基本 prompt 分別在 `tronclass/system1.py`、`prompts/system1.txt`；前端透過 `tronclass/factory.py` 呼叫共用契約。正式 AI 測試題尚需由目前 3 題示例擴充至 15–20 題，每題重複 5–10 次，並人工整理 Verification Log。

## Cloudflare → Claude

介面左側可切換 **Cloudflare → Claude** 與 **Ollama（本機）**，不需改動 System 1、SQLite 或測試題。Cloudflare 使用帳戶 REST API 的 Anthropic Messages 格式，預設模型為 `anthropic/claude-haiku-4.5`。底層 adapter 會把共用 messages 中的 system 訊息移到 Anthropic 的 `system` 欄位，其餘對話順序保持一致。

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

需要 Python 3.11 以上。使用 Ollama 時需另行安裝、啟動服務；使用 Cloudflare 時依上方設定。資料查詢頁不需要模型服務。在專案根目錄執行（PowerShell）：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 由團隊選定並安裝模型；程式不會自動下載大型模型。
ollama list
$env:OLLAMA_MODEL = "填入已安裝模型的完整名稱與 tag"
.venv\Scripts\python.exe -m streamlit run app.py
```

若本機尚未啟動 Ollama，可另外開終端機執行 `ollama serve`；已在背景執行時不必重複啟動。左側「檢查模型連線」會查詢可用模型。連線失敗會顯示錯誤，不會產生假的 AI 回答。

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

`.env.example` 是環境變數參考，程式**不會自動讀取 `.env`**。Cloudflare 也可從上述本機 secrets.toml 讀取設定。聊天頁可切換服務、模型、temperature、情境時間；Ollama 網址可修改，Cloudflare 網址由帳戶設定產生。Ollama 模型名稱不設預設值，也不會自動下載模型。

| 環境變數 | 預設值 |
|---|---|
| `TRONCLASS_DB_PATH` | `sample_data/course.db`，相對路徑以專案根目錄起算 |
| `TRONCLASS_STUDENT_ID` | `S11200001` |
| `LLM_PROVIDER` | `ollama`，可由本機 `[app] provider` 選為 `cloudflare` |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | 空白，需填已安裝的完整名稱 |
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
- 時間、耗時、provider、請求／回傳模型名稱、temperature、實際適用的 seed、輸出上限、網址、情境時間。
- 可見資料、prompt、完整 messages 的 SHA-256，以及服務回傳的 token usage／finish reason。
- 執行錯誤、人工正誤欄位及備註。連線錯誤記為 error，**不算 AI 回答錯誤**。

CSV 的 `human_correct`、`review_notes` 供整理 Verification Log；目前不做關鍵字自動判分，也不把 HTTP 成功當正確。請先人工標記有效回答，再以相同題目和標準比較 System 1 / System 2。

正式測試請額外留存 `ollama list`、`ollama show <模型>` 的輸出與模型 digest；名稱或 tag 本身不能保證權重沒有改變。temperature 0 與固定 seed 也不保證跨版本／硬體完全一致。

## 程式測試

```powershell
.venv\Scripts\python.exe -m pytest -q
```

使用原始 SQLite fixture、Streamlit AppTest、本機模擬 HTTP 模型服務，不需要下載模型。測試隔離本機與環境中的 Cloudflare 憑證，僅使用假 token。這些測試驗證程式整合，實際模型推理與錯誤率需另行執行上方 AI 測試。

## 範例資料

`sample_data/` 由原 repository 的 `tronclass-ai-assistant-data-github.zip` 解出，保留原始 README、JSON／Markdown、附件、建庫程式，沒有修改課程內容。

SQLite 連線使用 `mode=ro`、參數化查詢。課程依 mock schema 的 `student_course_grades` 對應；個人紀錄限目前學生、教材限 `visibility='student'`、未公布的分數與評語不送入 UI 或模型。原始教師資料保留作為 fixture，但不包含在學生匯出中。

這是固定模擬學生的本機原型，環境變數中的學號不是登入驗證。未來若接真實多使用者服務，需由登入身分決定 student_id。

每次查詢建立並關閉唯讀連線，不共用跨執行緒 SQLite 物件。聊天與測試都從資料庫產生 context，不使用可能過期或含未遮蔽欄位的 `all_data_for_prompt.md`。

模型介面依 [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)；介面測試使用 [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest)。
