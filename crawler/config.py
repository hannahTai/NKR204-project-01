"""專案設定：所有常數與路徑集中在這裡，其他模組從這裡 import。"""
import os
from pathlib import Path

from dotenv import load_dotenv

TWSE_BASE = "https://www.twse.com.tw/rwd/zh"           # 網站背後的 JSON 端點（無公開文件）
TWSE_OPENAPI_BASE = "https://openapi.twse.com.tw/v1"   # OpenAPI（有規格，但不能帶參數）
MOPS_BASE = "https://mops.twse.com.tw/mops/api"        # 公司公告查詢 API

# 專案根目錄：config.py 在 crawler/ 裡，往上兩層就是根目錄
#   Path(__file__)          → .../NKR204-project-02/crawler/config.py
#   .resolve().parent       → .../NKR204-project-02/crawler
#   .parent                 → .../NKR204-project-02
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# ---------- 資料庫（從環境變數讀；本機開發時寫在專案根目錄的 .env） ----------
# .env 不 commit（含密碼）；欄位範本見 .env.example
# 已經有同名的環境變數時（例如 Docker 注入的），以環境變數為準，不會被 .env 蓋掉
load_dotenv(PROJECT_ROOT / ".env")

MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))   # 環境變數都是字串，要轉 int
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")    # 密碼不給預設值，沒設就是空的
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "notice_tracker")
