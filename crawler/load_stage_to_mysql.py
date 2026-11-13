"""L（載入）：把 transform_stage 產出的 parquet 寫進 MySQL，每張表整張換掉。

    uv run python -m crawler.load_stage_to_mysql              # 平常用這個
    uv run python -m crawler.load_stage_to_mysql --recreate   # db/init/*.sql 的欄位改了才用：先刪表再重建

流程：讀 parquet → 確認表都在 → 每張表「清空 → 寫入」。
所有表放在同一個交易裡：全部成功才生效，中途失敗就全部復原，可以直接重跑。
"""
import argparse
import json

import pandas as pd

from crawler import mysql
from crawler.config import STAGE_DIR

MANIFEST_PATH = STAGE_DIR / "manifest.json"


# ---------- 1. 讀 parquet ----------
def load_tables() -> dict[str, pd.DataFrame]:
    """讀 manifest 列出的表，回傳 {表名: DataFrame}，例如 {"stage_notice": 573 列的表, ...}。"""
    # 沒有 manifest 代表 T 還沒跑過（或沒跑完）
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"找不到 {MANIFEST_PATH}，請先跑 transform_stage")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    table_names = manifest["tables"]   # 例如 ["stage_notice", "stage_notice_clause", ...]

    tables = {}
    for name in table_names:
        tables[name] = pd.read_parquet(STAGE_DIR / f"{name}.parquet")
    return tables


# ---------- 2. 寫進 MySQL ----------
def write_tables(tables: dict[str, pd.DataFrame]) -> None:
    """每張表「清空 → 寫入」，全部放在同一個交易裡。"""
    engine = mysql.get_engine()

    # with engine.begin()：開一個交易
    #   區塊跑完沒出錯 → 全部生效
    #   中途出錯       → 這個區塊裡做過的事全部復原，資料庫維持原狀
    with engine.begin() as conn:
        for name, df in tables.items():
            mysql.replace_table(conn, name, df)   # 清空這張表，再寫入 df
            print(f"{name:24s} 寫入 {len(df):6d} 列")


# ---------- 執行 ----------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true", help="先刪表再重建（db/init/*.sql 改了用這個）")
    args = parser.parse_args()

    tables = load_tables()                                # 1. 讀 parquet

    # 確認資料庫和表都在：不存在就建立，已存在就跳過
    # 加 --recreate 才先刪表：刪表會立刻生效、沒辦法復原（MySQL 的 DDL 不能放進交易），所以平常不刪
    if args.recreate:
        mysql.create_tables(drop_first=list(tables))
    else:
        mysql.create_tables()

    write_tables(tables)                                  # 2. 寫進 MySQL


if __name__ == "__main__":
    main()
