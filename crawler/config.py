"""設定層：集中管理所有「會因環境而變」的值，其他模組從這裡 import。

用 os.environ.get() 讀環境變數，讀不到才用預設值。
同一份程式在本機、在容器、在雲端都不用改任何一行，只換環境變數。
本機開發時，環境變數寫在專案根目錄的 .env（不 commit；欄位範本見 .env.example）。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 專案根目錄：config.py 在 crawler/ 裡，往上兩層就是根目錄
#   Path(__file__)          → .../NKR204-project-02/crawler/config.py
#   .resolve().parent       → .../NKR204-project-02/crawler
#   .parent                 → .../NKR204-project-02
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 讀 .env；已經有同名的環境變數時（例如 Docker 注入的），以環境變數為準
load_dotenv(PROJECT_ROOT / ".env")

# ---------- 怎麼拿：資料來源位址 ----------
TWSE_BASE = os.environ.get("TWSE_BASE", "https://www.twse.com.tw/rwd/zh")              # 網站背後的 JSON 端點（無公開文件）
TWSE_OPENAPI_BASE = os.environ.get("TWSE_OPENAPI_BASE", "https://openapi.twse.com.tw/v1")  # OpenAPI（有規格，但不能帶參數）
MOPS_BASE = os.environ.get("MOPS_BASE", "https://mops.twse.com.tw/mops/api")            # 公司公告查詢 API

# 連續請求之間的間隔（秒），太快會被擋
SLEEP_SECONDS = float(os.environ.get("SLEEP_SECONDS", "1.0"))
SLEEP_SECONDS_MOPS = float(os.environ.get("SLEEP_SECONDS_MOPS", "0.6"))

# ---------- 怎麼存：raw 檔與 MySQL ----------
RAW_DIR = Path(os.environ.get("RAW_DIR", PROJECT_ROOT / "data" / "raw"))
CSV_OUTPUT_DIR = Path(os.environ.get("CSV_OUTPUT_DIR", PROJECT_ROOT / "data" / "stage"))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))   # 環境變數都是字串，要轉 int
MYSQL_ACCOUNT = os.environ.get("MYSQL_ACCOUNT", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")  # 密碼不給預設值，沒設就是空的
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "notice_tracker")
