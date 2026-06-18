import os
import json
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# 載入 .env 檔案中的變數
load_dotenv()

# ==========================================
# Configuration
# ==========================================
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = "primary"
TIMEZONE = "Asia/Taipei"

# ==========================================
# Load & Refresh Credentials (自動讀取 .env)
# ==========================================
creds = None

# 如果有舊的 token.json，直接讀取
if os.path.exists(TOKEN_FILE):
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes=SCOPES)

# 如果沒有有效的憑證，則啟動登入流程
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        # 動態從 .env 抓取 Client ID 與 Secret 來建構設定
        client_config = {
            "installed": {
                "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        # 啟動本地端伺服器進行驗證
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=0)
        
    # 將取得的憑證存成 token.json，供下次使用
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    print("✅ Token refreshed and saved.\n")

# ==========================================
# Build Service
# ==========================================
service = build("calendar", "v3", credentials=creds)

# ==========================================
# Events to Create
# ==========================================
events = [
    {
        "summary": "Team Standup",
        "start": "2026-06-02T09:00:00",
        "end":   "2026-06-02T10:00:00"
    },
    {
        "summary": "Research Meeting",
        "start": "2026-06-02T14:00:00",
        "end":   "2026-06-02T15:00:00"
    },
    {
        "summary": "Project Review",
        "start": "2026-06-03T10:00:00",
        "end":   "2026-06-03T11:00:00"
    },
    {
        "summary": "Student Advising",
        "start": "2026-06-03T15:00:00",
        "end":   "2026-06-03T16:00:00"
    },
    {
        "summary": "Faculty Meeting",
        "start": "2026-06-04T09:00:00",
        "end":   "2026-06-04T10:30:00"
    },
    {
        "summary": "PhD Progress Review",
        "start": "2026-06-04T14:00:00",
        "end":   "2026-06-04T15:00:00"
    },
    {
        "summary": "Industry Collaboration Meeting",
        "start": "2026-06-05T11:00:00",
        "end":   "2026-06-05T12:00:00"
    },
    {
        "summary": "Lab Weekly Meeting",
        "start": "2026-06-05T15:00:00",
        "end":   "2026-06-05T16:00:00"
    },
    {
        "summary": "Grant Proposal Discussion",
        "start": "2026-06-06T09:00:00",
        "end":   "2026-06-06T10:00:00"
    },
    {
        "summary": "Research Seminar",
        "start": "2026-06-06T15:00:00",
        "end":   "2026-06-06T16:00:00"
    }
]

# ==========================================
# Create Events
# ==========================================
created_count = 0
failed_count = 0

for idx, e in enumerate(events):
    body = {
        "summary": e["summary"],
        "start": {
            "dateTime": e["start"],
            "timeZone": TIMEZONE
        },
        "end": {
            "dateTime": e["end"],
            "timeZone": TIMEZONE
        }
    }

    try:
        result = service.events().insert(
            calendarId=CALENDAR_ID,
            body=body
        ).execute()

        print(
            f"[{idx + 1}/{len(events)}] ✓ Created: {e['summary']} "
            f"(id: {result.get('id')})"
        )
        created_count += 1

    except HttpError as err:
        print(
            f"[{idx + 1}/{len(events)}] ✗ FAILED: {body['summary']} "
            f"— HTTP {err.resp.status}: {err.reason}"
        )
        failed_count += 1

    except Exception as ex:
        print(
            f"[{idx + 1}/{len(events)}] ✗ UNEXPECTED ERROR: {body['summary']} — {ex}"
        )
        failed_count += 1

print(f"\nDone. {created_count} created, {failed_count} failed.")