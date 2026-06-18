import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Annotated, Sequence, TypedDict
from dotenv import load_dotenv
import subprocess
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

load_dotenv()

# ==========================================
# 1. 時間與時區設定 (UTC+8 台灣時間)
# ==========================================
tz_tw = timezone(timedelta(hours=8))
current_time_tw = datetime.now(tz_tw).isoformat()

# ==========================================
# 2. 狀態記憶體定義
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# ==========================================
# 3. System Prompt
# ==========================================
CALENDAR_SYSTEM_PROMPT = f"""
You are an interactive AI assistant that manages Google Calendar.
The user's primary email address is: {os.getenv('USER_GOOGLE_EMAIL')}
The current system date and time is: {current_time_tw}

CRITICAL ARCHITECTURE RULES (READ-ONLY vs CRUD):
1. For ANY read-only tasks (e.g., checking what's on today, listing calendars, searching events), you MUST ONLY use the specific `cli_` prefixed tools 
(e.g., `cli_list_calendars`, `cli_today_events`).
2. For ANY write, update, or delete tasks (e.g., scheduling a meeting, deleting an event), you MUST ONLY use the MCP tool `manage_event`.
3. NEVER attempt to create an event using a CLI tool. NEVER attempt to search for events using an MCP tool.

CRITICAL ANTI-LOOP INSTRUCTIONS:
1. WHEN CREATING AN EVENT, YOU ARE STRICTLY FORBIDDEN FROM CALLING `Calendar`. Do not check the calendar list.
2. You ALREADY KNOW the correct calendar ID. The `calendarId` for the user's primary calendar is exactly: "{os.getenv('USER_GOOGLE_EMAIL')}".
3. To create an event, IMMEDIATELY call `manage_event` using `calendarId="{os.getenv('USER_GOOGLE_EMAIL')}"`.

CRITICAL TOOL USAGE RULES:
1. NEVER call `create_calendar` (creating a new calendar). This is forbidden.
2. ALWAYS use `manage_event` for scheduling meetings or tasks.
3. DO NOT GUESS. If you are unsure which tool to use, check the tool descriptions.

Tool Execution Rules:
- You have access to Google Calendar MCP tools (e.g., `manage_event` to create/update/delete events).
- Every time you call ANY tool, you MUST explicitly provide the `user_google_email` argument.
- Format `start` and `end` times in ISO 8601 with timezone (e.g., 2026-05-27T18:00:00+08:00).
- ALWAYS ask for explicit confirmation from the user before executing a DELETE or UPDATE operation.
"""

# ==========================================
# 4. CLI Tool definitions (Read-only tools for calendar queries)
# ==========================================
# 輔助函式：用來將字典格式化為 gws 能接受的單引號 JSON 字串
def _format_params(params_dict: dict) -> str:
    return json.dumps(params_dict)

@tool
def cli_list_calendars() -> str:
    """Use this tool to get the list of all calendars the user has. (CLI Read-only)"""
    print("\n[系統提示] 🚀 執行 官方 gws 工具: list_calendars")
    
    # 修正 1：改為官方接受的 calendarList
    cmd = ["gws", "calendar", "calendarList", "list"]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    
    # 1修正 2：只攔截 returncode != 0 的致命錯誤
    if result.returncode != 0:
        print(f"⚠️ [CLI 致命錯誤]: {result.stderr}")
        return f"Error: {result.stderr}"
    
    # 如果只是印出 keyring 等提示訊息，就當作 Info 印出來就好，不中斷程式
    if result.stderr:
        print(f"ℹ️ [CLI 提示訊息]: {result.stderr.strip()}")
        
    print(f"✅ [CLI 成功]: 取得 {len(result.stdout)} 字元資料")
    return result.stdout

@tool
def cli_today_events() -> str:
    """Use this tool to find out what is on the calendar for TODAY. (CLI Read-only)"""
    print("\n[系統提示] 🚀 執行 官方 gws 工具: today_events")
    now = datetime.now(timezone.utc)
    time_min = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    time_max = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    params = {"calendarId": "primary", "timeMin": time_min, "timeMax": time_max, "singleEvents": True}
    
    cmd = ["gws", "calendar", "events", "list", "--params", _format_params(params)]
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    
    if result.returncode != 0:
        print(f"⚠️ [CLI 致命錯誤]: {result.stderr}")
        return f"Error: {result.stderr}"
    if result.stderr:
        print(f"ℹ️ [CLI 提示訊息]: {result.stderr.strip()}")
        
    print(f"✅ [CLI 成功]: 取得 {len(result.stdout)} 字元資料")
    return result.stdout

@tool
def cli_list_events(time_min: str, time_max: str) -> str:
    """Use this tool to show events within a specific time range. (CLI Read-only)
    Args:
        time_min: Start time in ISO format (e.g., 2026-05-29T00:00:00Z).
        time_max: End time in ISO format (e.g., 2026-05-29T23:59:59Z).
    """
    print(f"\n[系統提示] 🚀 執行 官方 gws 工具: list_events ({time_min} to {time_max})")
    params = {"calendarId": "primary", "timeMin": time_min, "timeMax": time_max, "singleEvents": True}
    
    cmd = ["gws", "calendar", "events", "list", "--params", _format_params(params)]
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    
    if result.returncode != 0:
        print(f"⚠️ [CLI 致命錯誤]: {result.stderr}")
        return f"Error: {result.stderr}"
    if result.stderr:
        print(f"ℹ️ [CLI 提示訊息]: {result.stderr.strip()}")
        
    print(f"✅ [CLI 成功]: 取得 {len(result.stdout)} 字元資料")
    return result.stdout

@tool
def cli_get_event(event_id: str) -> str:
    """Use this tool to get details for a specific meeting/event. (CLI Read-only)"""
    print(f"\n[系統提示] 🚀 執行 官方 gws 工具: get_event ({event_id})")
    params = {"calendarId": "primary", "eventId": event_id}
    
    cmd = ["gws", "calendar", "events", "get", "--params", _format_params(params)]
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    
    if result.returncode != 0:
        print(f"⚠️ [CLI 致命錯誤]: {result.stderr}")
        return f"Error: {result.stderr}"
    if result.stderr:
        print(f"ℹ️ [CLI 提示訊息]: {result.stderr.strip()}")
        
    print(f"✅ [CLI 成功]: 取得 {len(result.stdout)} 字元資料")
    return result.stdout

@tool
def cli_tool_list() -> str:
    """Use this tool for debugging or discovering available workspace tools. (CLI Read-only)"""
    print("\n[系統提示] 🚀 執行 官方 gws 工具: tool_list")
    cmd = ["gws", "schema", "calendar"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    
    if result.returncode != 0:
        print(f"⚠️ [CLI 致命錯誤]: {result.stderr}")
        return f"Error: {result.stderr}"
    if result.stderr:
        print(f"ℹ️ [CLI 提示訊息]: {result.stderr.strip()}")
        
    print(f"✅ [CLI 成功]: 取得 {len(result.stdout)} 字元資料")
    return result.stdout

# 將五個 CLI 工具打包成一個 List，方便後續綁定
CALENDAR_CLI_TOOLS = [
    cli_list_calendars, cli_today_events, cli_list_events, cli_get_event, cli_tool_list
]
# ==========================================
# 5. Agent 建構 (純 MCP 架構)
# ==========================================
async def build_calendar_agent(mcp_session):
    all_mcp_tools = await load_mcp_tools(mcp_session)
    
    # 嚴格過濾：只留下 MCP 裡的「寫入/修改/刪除」工具
    mcp_crud_tools = [
        t for t in all_mcp_tools 
        if t.name in ["manage_event"]
    ]
    
    # 拼裝終極工具箱：CLI 負責讀 + MCP 負責寫
    all_agent_tools = mcp_crud_tools + CALENDAR_CLI_TOOLS
    
    print(f"\n🛠️ [系統檢查] 最終綁定給大腦的日曆工具: {[t.name for t in all_agent_tools]}")
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    llm_with_tools = llm.bind_tools(all_agent_tools)

    def agent_node(state: AgentState):
        messages = [SystemMessage(content=CALENDAR_SYSTEM_PROMPT)] + state["messages"]
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        messages = state["messages"]
        last_message = messages[-1]
        
        if last_message.tool_calls:
            tool_names = [t["name"] for t in last_message.tool_calls]
            print(f"\n🧠 [大腦決策] GPT-4o 決定呼叫工具: {tool_names}")
            
            # --- 🛡️ 防無窮迴圈機制 (Anti-Loop Guard) ---
            if len(messages) >= 3:
                prev_ai_message = messages[-3]
                if hasattr(prev_ai_message, "tool_calls") and prev_ai_message.tool_calls:
                    prev_tools = [t["name"] for t in prev_ai_message.tool_calls]
                    if tool_names == prev_tools:
                        print("⚠️ [系統守衛] 偵測到 AI 陷入無窮迴圈，強制阻斷！")
                        return END
            # ---------------------------------------------
            
            return "tool_node"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent_node", agent_node)
    workflow.add_node("tool_node", ToolNode(all_agent_tools))
    workflow.set_entry_point("agent_node")
    workflow.add_conditional_edges("agent_node", should_continue)
    workflow.add_edge("tool_node", "agent_node")

    return workflow.compile()

# ==========================================
# 6. 執行模式 1：互動模式 (Interactive Mode)
# ==========================================
async def run_interactive_chat(agent):
    print("\n📅 [Interactive Mode] 已啟動！(輸入 'exit' 或 'quit' 離開)")
    print("你可以問我：'我有什麼日曆？'、'幫我查明天的活動' 或 '幫我排一個會議'")
    
    state = {"messages": []}
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['exit', 'quit']:
            print("再見！")
            break
            
        state["messages"].append(HumanMessage(content=user_input))
        result_state = await agent.ainvoke(state)
        
        ai_response = result_state["messages"][-1].content
        print(f"\nAgent: {ai_response}")
        
        state = result_state

# ==========================================
# 7. 執行模式 2：自動模式 (Auto Mode)
# ==========================================
async def run_auto_mode(agent):
    print("\n🚀 [Auto Mode] 自動日曆摘要執行中...\n")
    
    queries = [
        "What calendars do I have?",
        "What's on my calendar today?",
        "Show me my events for the next 7 days."
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"--- 任務 {i} ---")
        print(f"執行指令: {query}")
        
        state = {"messages": [HumanMessage(content=query)]}
        result_state = await agent.ainvoke(state)
        
        ai_response = result_state["messages"][-1].content
        print(f"\n🤖 Agent 回報:\n{ai_response}\n")
        print("=" * 40 + "\n")
        
    print("✅ 自動摘要報告完畢，程式結束。")

# ==========================================
# 8. 程式進入點與終端機選單
# ==========================================
async def main():
    env_vars = os.environ.copy()
    env_vars.update({
        'GOOGLE_OAUTH_CLIENT_ID': os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),
        'GOOGLE_OAUTH_CLIENT_SECRET': os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', ''),
        'USER_GOOGLE_EMAIL': os.getenv('USER_GOOGLE_EMAIL', '') 
    })
    config = {
        'workspace': {
            'command': 'uvx',
            # 把 --permissions calendar:full 加回來，強迫要完整權限
            'args': ['workspace-mcp', '--single-user', '--permissions', 'calendar:full'],
            'transport': 'stdio',
            'env': env_vars
        }
    }
    client = MultiServerMCPClient(config)
    print("啟動 MCP Server (Calendar 權限)...")
    
    async with client.session('workspace') as session:
        agent = await build_calendar_agent(session)
        
        print("\n==================================")
        print("  📅 歡迎使用 Calendar Agent")
        print("==================================")
        print("請選擇啟動模式：")
        print("1. Interactive Mode (互動問答 - 自由查詢或新增行程)")
        print("2. Auto Mode (自動摘要 - 執行預設的 3 個報告)")
        
        choice = input("\n請輸入 1 或 2: ").strip()
        
        if choice == '1':
            await run_interactive_chat(agent)
        elif choice == '2':
            await run_auto_mode(agent)
        else:
            print("無效的選擇，程式已安全結束。")

if __name__ == "__main__":
    asyncio.run(main()) 