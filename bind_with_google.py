import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from dotenv import load_dotenv

load_dotenv()

async def test_auth_full():
    config = {
        'workspace': {
            'command': 'uvx',
            'args': [
                'workspace-mcp', 
                '--single-user', 
                '--tool-tier', 'core', 
                '--permissions', 'calendar:full', 'gmail:full'       # 已經於console.cloud.google設定好scope了，這邊直接給full權限就好
            ],
            'transport': 'stdio',
            'env': {
                'GOOGLE_OAUTH_CLIENT_ID': os.getenv('GOOGLE_OAUTH_CLIENT_ID', ''),
                'GOOGLE_OAUTH_CLIENT_SECRET': os.getenv('GOOGLE_OAUTH_CLIENT_SECRET', '')
            }
        }
    }
    
    client = MultiServerMCPClient(config)
    print('正在拉起 MCP Server（日曆 + Gmail）...')
    
    async with client.session('workspace') as session:
        tools = await load_mcp_tools(session)
        calendar_tool = next(t for t in tools if t.name == 'list_calendars')
        
        print('\n🚨 準備向 Google 請求真實資料！')
        request_args = {"user_google_email": "jordan104026@gmail.com"}
        
        try:
            result = await calendar_tool.ainvoke(request_args) 
            print('\n【🎉 驗證大成功】成功取得你的日曆資料！')
            print('回傳內容：', str(result)[:300], '...') 
        except Exception as e:
            print(f'\n【需要授權】請立刻點擊下方網址！\n')
            print(str(e))
            print('\n🛡️ 防護罩已啟動！接收站將強制保持開啟 120 秒...')
            
            # 因為還在 async with 區塊內，這 120 秒內 port 8000 絕對活得好好的！
            for i in range(120, 0, -1):
                print(f"接收站穩定運作中，倒數: {i} 秒... (請在瀏覽器完成授權)", end='\r')
                await asyncio.sleep(1)
            print("\n時間到，防護罩解除，接收站關閉。")

if __name__ == "__main__":
    asyncio.run(test_auth_full())






#try:
        #tools = await client.get_tools()
        #print(f'\n【大成功】完全體連線成功！共載入 {len(tools)} 個工具！')
        #print('可用工具清單：', [t.name for t in tools])

        # 測試工具
        # 1. 拿菜單
        #tools = await client.get_tools()
        
        # 2. 從菜單裡找到「查詢日曆 (list_calendars)」這個工具
        #calendar_tool = next(t for t in tools if t.name == 'list_calendars')
        
        # 3. 真實點餐 (執行工具)
        #print('\n🚨 準備向 Google 請求真實資料！')
        #print('👉 請注意你的螢幕，瀏覽器應該要彈出來了！')
        #request_args = {
         #   "user_google_email": "jordan104026@gmail.com"  # <--- 請在這裡填入你剛才設定的測試信箱
        #}
        # ainvoke 是 LangChain 非同步執行工具的方法
        #result = await calendar_tool.ainvoke(request_args) 
        
        #print('\n【🎉 驗證大成功】成功取得你的日曆資料！')
        #print('回傳內容擷取：', str(result)[:200], '...') # 只印前200字免得洗版

        
    #except Exception as e:
        #for i in range(120, 0, -1):
          #  print(f"接收站關閉倒數: {i} 秒... (若瀏覽器顯示授權成功即可關閉終端機)", end='\r')
           # await asyncio.sleep(1)
        #print("\n時間到，接收站已關閉。")
        #print(f'連線發生錯誤: {e}')*/