"""存取資料：raw 檔（data/raw/<來源>/<key>.json）與 MySQL。"""
import json
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests
from sqlalchemy import Engine, bindparam, create_engine, text

from crawler import date_utils
from crawler.config import (
    MYSQL_ACCOUNT, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, PROJECT_ROOT, RAW_DIR,
)


# ---------- raw ----------
def raw_path(source: str, key: str, ok: bool = True) -> Path:
    """成功存 <key>.json；失敗存 <key>.error.json，不會蓋掉成功的檔。"""
    return RAW_DIR / source / (f"{key}.json" if ok else f"{key}.error.json")


def parse_body(resp: requests.Response) -> dict | list | str:
    """JSON 就解析；不是 JSON（例如被擋時的 HTML）就回傳原文。"""
    try:
        return resp.json()
    except ValueError:
        return resp.text


def save_raw_response(source: str, key: str, resp: requests.Response) -> Path:
    """把回應原樣存檔（含網址、狀態碼、抓取時間），失敗時存完再報錯。"""
    body = parse_body(resp)
    ok = resp.ok and not isinstance(body, str)
    request_body = resp.request.body   # POST 的參數；GET 為 None
    envelope = {
        "meta": {
            "source": source,
            "key": key,
            "url": resp.url,
            "request_body": json.loads(request_body) if request_body else None,
            "http_status": resp.status_code,
            "fetched_at": date_utils.now().isoformat(timespec="seconds"),
        },
        "body": body,
    }
    path = raw_path(source, key, ok)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    if not ok:
        raise RuntimeError(f"{source} {key} 抓取失敗（HTTP {resp.status_code}），回應已存到 {path}")
    return path


def load_raw(source: str, key: str) -> dict | None:
    path = raw_path(source, key)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_raw(source: str) -> list[str]:
    """某來源所有成功 raw 的 key，排序後回傳。"""
    files = (RAW_DIR / source).glob("*.json")
    return sorted(p.stem for p in files if not p.name.endswith(".error.json"))


# ---------- MySQL ----------
def get_engine(with_database: bool = True) -> Engine:
    db = MYSQL_DATABASE if with_database else ""
    # quote_plus：密碼含 @ : 等符號時避免連線字串被切錯
    url = (f"mysql+pymysql://{MYSQL_ACCOUNT}:{quote_plus(MYSQL_PASSWORD)}"
           f"@{MYSQL_HOST}:{MYSQL_PORT}/{db}?charset=utf8mb4")
    return create_engine(url)


def init_db() -> None:
    """建資料庫與資料表（已存在就跳過）。"""
    with get_engine(with_database=False).begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4"))
    with get_engine().begin() as conn:
        for sql_file in sorted((PROJECT_ROOT / "db" / "init").glob("*.sql")):
            for statement in sql_file.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    conn.execute(text(statement))


def replace_table(conn, table: str, df: pd.DataFrame) -> None:
    """清空整張表再寫入 df：重跑結果不變，上游刪掉的資料也會跟著消失。"""
    conn.execute(text(f"DELETE FROM {table}"))
    if not df.empty:
        df.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=1000)


def replace_days(conn, table: str, date_column: str, days: list, df: pd.DataFrame) -> None:
    """只換掉指定日期的資料：刪掉這些日期，再寫入 df（df 只含這些日期）。"""
    delete = text(f"DELETE FROM {table} WHERE {date_column} IN :days")
    conn.execute(delete.bindparams(bindparam("days", expanding=True)), {"days": days})
    if not df.empty:
        df.to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=1000)
