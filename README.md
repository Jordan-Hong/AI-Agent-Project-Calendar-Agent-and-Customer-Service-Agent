Step 1: 複製專案與安裝基礎依賴
--------------------------
git clone <你的GitHub儲存庫網址>

cd refund_calendar_agents

安裝 LangGraph、LangChain 核心以及 OpenAI、MCP 適配器擴充包

pip install langgraph langchain-openai langchain-mcp-adapters python-dotenv google-api-python-client google-auth-oauthlib

Step 2: 安裝 Google Workspace MCP 伺服器與 CLI
--------------------------
下載開源 MCP 伺服器套件
git clone [https://github.com/taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp)

cd google_workspace_mcp

全域安裝 workspace-cli 工具

uv tool install .

或者是使用 pip 安裝

pip install workspace-mcp

cd ..

Step 3: 配置並驗證憑證
--------------------------
依照上方指南設定好專案根目錄下的 .env 檔案。

執行 workspace-cli list 或是運行驗證腳本：

Bash
python bind_with_google.py

終端機會跳出授權 URL，點擊並登入你的 Google 測試帳號，完成 OAuth 2.0 同意程序。驗證成功後本地會生成 token.json。

Step 4: 運行 Agent 系統
----------------------
你可以自由啟動其中一個 Agent 體驗自主 AI 的威力：

**執行自動客服助理：**

python refund_agent.py

**執行日曆管理專家：**

python calendar_agent.py

主要內容
------
#### 🤖 核心代理人功能簡介

****1. 日曆管理專家 (Calendar Agent)**
專門負責管理與查詢 Google Calendar 的互動式助理。採用**讀寫分離的雙層工具架構**來平衡執行效率與操作精準度：
* **唯讀任務 (Fast Read)**：針對查詢今日行程、列出所有日曆等輕量化查詢，系統會直接透過 Python Subprocess 呼叫本地 `workspace-cli` 進行快取讀取，免去 MCP 的來回開銷。
* **增刪改任務 (Full CRUD)**：針對排定會議、更新時間或刪除行程等複雜寫入操作，則調用功能完整的 MCP 工具庫處理。
* **安全守衛機制**：內建防無窮迴圈機制 (Anti-Loop Guard)，避免 AI 重複呼叫工具消耗 Token；且在執行刪除或更新等破壞性操作前，必須經過使用者的明確確認。

**2. 自動客服助理 (Customer Service Agent / 原名 Refund Agent)**
自主運行的電子郵件管理助理，旨在以同理心與高效率全自動化處理客戶服務流程：
* **自動化工作流 (Auto Mode)**：自動搜尋收件匣最新未讀郵件、讀取內文，並精準分類意圖為 `REFUND_REQUEST`、`RETURN_REQUEST` 或 `COMPLAINT` 等。接著會動態調用專業回覆範本，並利用 `thread_id` 實現同一個對話串的「線索對話回覆 (Threaded Reply)」，最終輸出處理狀態總結表。
* **個人助理模式 (Interactive Mode)**：使用者可手動給定收件人與上下文，Agent 會切換角色，站在**消費者視角**代擬語氣禮貌但堅定的信件，並自動以使用者名稱署名。

---

#### 🛠️ 環境配置與資安防護網 (.env)

為了保護你的隱私資安，**本專案嚴禁將任何金鑰或授權憑證寫死在程式碼中**。在第一次運行專案前，你**必須**手動建立一個 `.env` 檔案，並填入以下必要的環境變數才可以順利跑起來：

```ini
# 1. AI 模型 API Token (OpenAI 授權密鑰)
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 2. Google Cloud Platform (GCP) OAuth 2.0 憑證資訊
GOOGLE_OAUTH_CLIENT_ID=你的_client_id_此處
GOOGLE_OAUTH_CLIENT_SECRET=你的_client_secret_此處

# 3. 目標測試與管理之 Google 電子信箱
USER_GOOGLE_EMAIL=你的_email_此處

# 4. 本地開發傳輸設定
OAUTHLIB_INSECURE_TRANSPORT=1**
