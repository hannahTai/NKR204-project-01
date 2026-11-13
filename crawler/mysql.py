"""MySQL 工具：連線、建表、寫入。給 load_stage_to_mysql 用。

帳號、密碼、主機等設定從 .env 讀（見 config.py）。
"""
import urllib.parse

import pandas as pd
import sqlalchemy

from crawler.config import (MYSQL_ACCOUNT, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT,
                            PROJECT_ROOT)

# 建表的 SQL 檔：db/init/ 底下所有 .sql，依檔名排序執行（01_xxx.sql、02_xxx.sql…）
SQL_FILES = sorted((PROJECT_ROOT / "db" / "init").glob("*.sql"))


# ---------- 連線 ----------
def get_engine(database: str = MYSQL_DATABASE) -> sqlalchemy.Engine:
    """建立連線用的 engine。

    database 預設是 .env 設定的資料庫；給空字串 "" 則只連到 MySQL 伺服器（資料庫還不存在時，用來建資料庫）。
    """
    # 密碼裡如果有 @ : / 這些符號，會讓連線字串被切錯，所以先編碼
    password = urllib.parse.quote_plus(MYSQL_PASSWORD)

    # 連線字串格式：mysql+pymysql://帳號:密碼@主機:埠/資料庫?charset=utf8mb4
    #   pymysql：Python 連 MySQL 用的套件
    #   utf8mb4：完整支援中文和 emoji 的編碼
    url = f"mysql+pymysql://{MYSQL_ACCOUNT}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}?charset=utf8mb4"
    return sqlalchemy.create_engine(url)


# ---------- 建表 ----------
def create_tables(drop_first: list[str] | None = None) -> None:
    """建資料庫，再執行 db/init/*.sql 建表。已經存在的就跳過。

    drop_first：要先刪掉再重建的表（欄位改了才用）；不給就不刪。
    """
    # 1. 建資料庫：這時資料庫可能還不存在，所以只連到伺服器（database=""）
    with get_engine("").begin() as conn:
        conn.execute(sqlalchemy.text(
            f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))

    # 2. 連到資料庫，刪表（如果有指定）、建表
    with get_engine().begin() as conn:
        if drop_first:
            for table in drop_first:
                conn.execute(sqlalchemy.text(f"DROP TABLE IF EXISTS {table}"))

        # 一個 .sql 檔裡有好幾句 SQL，用分號切開，一句一句執行
        for sql_file in SQL_FILES:
            sql_text = sql_file.read_text(encoding="utf-8")
            for statement in sql_text.split(";"):
                if statement.strip():   # 跳過空白（例如最後一個分號後面）
                    conn.execute(sqlalchemy.text(statement))


# ---------- 寫入 ----------
def upload_data_to_mysql(conn, table: str, df: pd.DataFrame) -> None:
    """把 df 加到表的最後面（不刪舊資料）。

    method="multi"、chunksize=1000：一句 INSERT 帶 1000 列，比一列一句快很多。
    """
    if df.empty:   # 沒資料就不用寫
        return
    df.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=1000)


def replace_table(conn, table: str, df: pd.DataFrame) -> None:
    """清空整張表，再寫入 df。

    用 DELETE 清空（不是 DROP 刪表）：DELETE 可以放在交易裡，失敗時能復原。
    """
    conn.execute(sqlalchemy.text(f"DELETE FROM {table}"))
    upload_data_to_mysql(conn, table, df)
