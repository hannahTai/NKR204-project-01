"""專案設定：所有常數與路徑集中在這裡，其他模組從這裡 import。"""
from pathlib import Path

TWSE_BASE = "https://www.twse.com.tw/rwd/zh"

# 專案根目錄：config.py 在 crawler/ 裡，往上兩層就是根目錄
#   Path(__file__)          → .../NKR204-project-02/crawler/config.py
#   .resolve().parent       → .../NKR204-project-02/crawler
#   .parent                 → .../NKR204-project-02
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
