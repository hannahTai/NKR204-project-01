"""設定：從環境變數讀取（可寫在專案根目錄的 .env），讀不到就用預設值。"""
import os
import pathlib

import dotenv

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent   # common/ 的上一層
dotenv.load_dotenv(PROJECT_ROOT / ".env")                       # 已有的環境變數不會被覆蓋

# 資料來源
TWSE_BASE = os.environ.get("TWSE_BASE", "https://www.twse.com.tw/rwd/zh")
TWSE_OPENAPI_BASE = os.environ.get("TWSE_OPENAPI_BASE", "https://openapi.twse.com.tw/v1")
MOPS_BASE = os.environ.get("MOPS_BASE", "https://mops.twse.com.tw/mops/api")

# 請求間隔（秒），太快會被擋
SLEEP_SECONDS = float(os.environ.get("SLEEP_SECONDS", "1.0"))
SLEEP_SECONDS_MOPS = float(os.environ.get("SLEEP_SECONDS_MOPS", "0.6"))

# 存放位置
RAW_DIR = pathlib.Path(os.environ.get("RAW_DIR", PROJECT_ROOT / "data" / "raw"))
STAGE_DIR = pathlib.Path(os.environ.get("STAGE_DIR", PROJECT_ROOT / "data" / "stage"))   # T 的產出（parquet＋manifest），L 從這裡讀

# MySQL
MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
MYSQL_ACCOUNT = os.environ.get("MYSQL_ACCOUNT", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", "tw_stock")
