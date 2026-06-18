import asyncio
import os
from typing import Annotated, Sequence, TypedDict
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from typing import TypedDict, Annotated, List, Dict
import operator

from datetime import datetime, timezone, timedelta

# 建立台灣時區 (UTC+8)
tz_tw = timezone(timedelta(hours=8))
current_time_tw = datetime.now(tz_tw).isoformat()
current_date_tw = datetime.now(tz_tw).strftime("%Y/%m/%d") # 產生如 2026/05/26 的格式


class RefundAgentState(TypedDict):
    messages: Annotated[List, operator.add]
    refund_records: Annotated[Dict, operator.add] # 用來儲存 {thread_id: status}

load_dotenv()

# ==========================================
# 1. 狀態記憶體定義
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# ==========================================
# 2. System Prompt (Refund Agent 專屬)
# ==========================================
REFUND_SYSTEM_PROMPT = """
You are an AI assistant managing a Gmail account. Your persona depends on the task you are given:

Your goal is to handle refund requests with empathy and efficiency.
- ALWAYS maintain a polite and professional tone.
- If the refund is approved, clearly state the timeline.
- If more info is needed, explicitly ask the user for details like Order ID.
- ALWAYS check the provided order details before finalizing the email content.
- NEVER use placeholders like "[Your Name]" or "[Your Company]". 
- ALWAYS sign off the email exactly as "Customer Support Team" (or "Jordan's AI Support Agent"2).

The current system date and time is: {current_time_tw}
The current base date for Gmail search queries is: {current_date_tw}

# --- ROLE 1: AUTO MODE (Customer Service Agent) ---
Your 6-step workflow for auto mode:
1. SEARCH inbox for 10 the latest unread emails.
2. READ each email's content.
3. CLASSIFY the intent into one of: REFUND_REQUEST, RETURN_REQUEST, COMPLAINT, OTHER.
** Definition of COMPLAINT: The title or content should contain specific complaint details or negative sentiment(like "disappointed", "poor service" or "mad"), not just the word "complaint". **
4. DRAFT reply based on classification:
   - REFUND_REQUEST: Send refund approval (mention 3-5 day processing).
   - RETURN_REQUEST: Send return instructions with a prepaid label.
   - COMPLAINT: Send empathetic acknowledgement and promise a 24hr follow-up.
   - OTHER: Skip, do not send a reply.
5. SEND threaded reply (You MUST use the thread_id to reply in the same thread).
6. REPORT summary of what you did.
Found [X] the latest unread emails
• [sender_email] - "[Subject]" -> [CLASSIFICATION] -> [Replied / Skipped ✓]

# --- ROLE 2: INTERACTIVE MODE (Personal Assistant) ---
When the user explicitly provides a target email, subject, and context to write a new email, you act as the user's PERSONAL ASSISTANT.
- Draft the email from the USER'S perspective (e.g., as a consumer writing a complaint or requesting a refund from a seller).
- The tone should be polite but firm, highly professional, and effective.
- NEVER sign off as "Customer Support Team". Sign off generically (e.g., "Sincerely, [My Name]" or omit the name placeholder).
- IMMEDIATELY send it using `send_gmail_message`.

Important Rules:
- If you are uncertain, use `create_gmail_draft` instead of sending directly.
- NEVER reply to emails classified as OTHER.
"""

# ==========================================
# 3. Agent 建構與執行邏輯
# ==========================================
async def build_refund_agent(mcp_session):
    all_mcp_tools = await load_mcp_tools(mcp_session)
    
    # 篩選 Gmail 相關的工具
    gmail_tools = [t for t in all_mcp_tools if "gmail" in t.name]
    
    print(f"\n🛠️ [系統檢查] 綁定給大腦的 Gmail 工具: {[t.name for t in gmail_tools]}")
    
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    llm_with_tools = llm.bind_tools(gmail_tools)

    def agent_node(state: AgentState):
        # 將系統時間變數格式化塞入 Prompt 中
        formatted_prompt = REFUND_SYSTEM_PROMPT.format(
            current_time_tw=current_time_tw, 
            current_date_tw=current_date_tw
        )
        messages = [SystemMessage(content=formatted_prompt)] + state["messages"]
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
                        print("⚠️ [系統守衛] 偵測到 AI 陷入無窮迴圈 (連續呼叫相同工具)，強制阻斷！")
                        return END
            # ---------------------------------------------
            return "tool_node"
        return END

    workflow = StateGraph(AgentState)
    workflow.add_node("agent_node", agent_node)
    workflow.add_node("tool_node", ToolNode(gmail_tools))
    workflow.set_entry_point("agent_node")
    workflow.add_conditional_edges("agent_node", should_continue)
    workflow.add_edge("tool_node", "agent_node")

    return workflow.compile()

# ==========================================
# 4. 執行模式 1：互動模式 (Interactive Mode)
# ==========================================
async def run_interactive_mode(agent):
    print("\n✉️ [Interactive Mode] 手動客服發信啟動！")
    print("請依照提示輸入發信資訊，AI 將自動為您潤飾並寄出。")
    
    while True:
        to_email = input("\n (輸入 'exit' 離開) 目標郵件地址 (To): ").strip()
        if to_email.lower() in ['exit', 'quit']:
            break
            
        subject = input("👉 信件標題 (Subject): ").strip()
        context = input("👉 簡述內容 (Context): ").strip()
        name = input("👉 寄件人姓名 (Your Name): ").strip()
        
        # 組合使用者的輸入，形成明確的 Prompt
        prompt = f"""
        Please act as my personal assistant (ROLE 2). I need to send an email to a company/seller.
        Please write a clear, polite, but firm email ON MY BEHALF based on these details:
        
        - Target Email: {to_email}
        - Subject: {subject}
        - What happened / My demand: {context}
        - Writer: {name}
        
        Draft the full content strictly from MY perspective (as the customer), and send it directly using the `send_gmail_message` tool. 
        DO NOT sign off as Customer Support.
        - NEVER use placeholders like "[Your Name]" or "[Your Company]". 
        - ALWAYS sign off the email exactly as "{name}".
        """
        
        print("\n⏳ AI 正在為您撰寫並發送郵件...")
        state = {"messages": [HumanMessage(content=prompt)]}
        result_state = await agent.ainvoke(state)
        
        ai_response = result_state["messages"][-1].content
        print(f"\n🤖 Agent 回報:\n{ai_response}")

# ==========================================
# 5. 執行模式 2：自動模式 (Auto Mode)
# ==========================================
async def run_auto_mode(agent):
    print("\n🚀 [Auto Mode] 自動退款信件處理程序啟動...\n")
    
    # 給予明確的啟動指令，並強調整理最後的表格
    query = """
    Please process 10 the latest unread emails in my inbox now. Classify them into REFUND_REQUEST, RETURN_REQUEST, COMPLAINT, or OTHER based on their content.
    ** Definition of COMPLAINT: The title or content should contain specific complaint details or negative sentiment(like "disappointed", "poor service" or "mad"), not just the word "complaint". **
    After you have successfully classified and replied to the necessary emails using tools,
    output the final summary report EXACTLY as formatted in your system instructions.
    - NEVER use placeholders like "[Your Name]" or "[Your Company]". 
    - ALWAYS reply the email exactly with "Dear Customer," as the greeting.
    - ALWAYS sign off the email exactly as "Customer Support Team".
    """
    
    state = {"messages": [HumanMessage(content=query)]}
    result_state = await agent.ainvoke(state)
    
    ai_response = result_state["messages"][-1].content
    print("\n==================================")
    print("       📊 最終處理狀態總結")
    print("==================================")
    print(ai_response)
    print("==================================")

# ==========================================
# 6. 程式進入點與終端機選單
# ==========================================
async def main():
    config = {
        'workspace': {
            'command': 'uvx',
            # 確保使用 gmail:full 權限
            'args': ['workspace-mcp', '--single-user', '--tool-tier', 'core', '--permissions', 'gmail:full'],
            'transport': 'stdio',
            'env': {
                'GOOGLE_OAUTH_CLIENT_ID': os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),
                'GOOGLE_OAUTH_CLIENT_SECRET': os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', ''),
                'USER_GOOGLE_EMAIL': os.getenv('USER_GOOGLE_EMAIL', '')
            }
        }
    }
    client = MultiServerMCPClient(config)
    print("啟動 MCP Server (Gmail 權限)...")
    
    async with client.session('workspace') as session:
        agent = await build_refund_agent(session)
        
        print("\n==================================")
        print("  ✉️ 歡迎使用 Refund Agent")
        print("==================================")
        print("請選擇啟動模式：")
        print("1. Interactive Mode (手動提供資訊，AI 潤飾並寄出)")
        print("2. Auto Mode (自動讀取收件匣、分類並回覆)")
        
        choice = input("\n請輸入 1 或 2: ").strip()
        
        if choice == '1':
            await run_interactive_mode(agent)
        elif choice == '2':
            await run_auto_mode(agent)
        else:
            print("無效的選擇，程式已安全結束。")

if __name__ == "__main__":
    asyncio.run(main())