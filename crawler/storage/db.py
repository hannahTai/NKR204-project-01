"""資料庫：連線、建表、寫入。其他模組不直接寫 SQL 連線字串。"""
from datetime import date
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import Engine, bindparam, create_engine, text

from crawler.config import (
    MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER, PROJECT_ROOT,
)

INIT_DIR = PROJECT_ROOT / "db" / "init"


def get_engine(with_database: bool = True) -> Engine:
    """建立 MySQL 連線。with_database=False 用在資料庫還不存在、要先建立它的時候。

    quote_plus：密碼含 @ : % 等符號時先編碼，否則連線字串會被切歪（教材 config 同樣做法）
    """
    db = f"/{MYSQL_DATABASE}" if with_database else "/"
    url = (f"mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}"
           f"@{MYSQL_HOST}:{MYSQL_PORT}{db}?charset=utf8mb4")
    return create_engine(url)


def init_db() -> None:
    """建立資料庫（不存在才建），再依序執行 db/init/*.sql 建表。重跑不會出錯。"""
    with get_engine(with_database=False).begin() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    with get_engine().begin() as conn:
        for sql_file in sorted(INIT_DIR.glob("*.sql")):
            # 一個檔案可能有多個 SQL 敘述，用分號切開逐一執行
            for stmt in sql_file.read_text(encoding="utf-8").split(";"):
                if stmt.strip() and not all(
                    line.strip().startswith("--") or not line.strip() for line in stmt.splitlines()
                ):
                    conn.execute(text(stmt))


def replace_days(conn, table: str, days: list[date], df: pd.DataFrame) -> None:
    """把某張表「這些日子」的資料整批換掉：先刪掉這些日子的舊資料，再一次寫入新的。

    days 要包含「這次處理過的所有日子」，連沒開市、沒有資料的日子也要給，
    這樣表裡那些日子才會被清空，和最新的 raw 一致。

    為什麼不用 upsert（ON DUPLICATE KEY UPDATE）：
    upsert 只能新增或更新，刪不掉「上次有、這次沒有」的列。
    如果上游更正、某檔股票從那天的名單被拿掉，upsert 會讓它永遠留在表裡。
    整批換掉，重跑幾次結果都一樣。

    效能：DELETE 一次、INSERT 用 to_sql 的 method="multi"
    （一個 INSERT 帶多列，每 1000 列一批），而不是一列一個 INSERT。
    """
    if not days:
        return
    conn.execute(
        text(f"DELETE FROM {table} WHERE trade_date IN :days").bindparams(
            bindparam("days", expanding=True)),
        {"days": days},
    )
    if not df.empty:
        df.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=1000)
