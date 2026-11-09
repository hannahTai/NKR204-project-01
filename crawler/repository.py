"""資料儲存層（repository）：只負責「怎麼把資料存下去、怎麼讀回來」。

這個檔案的邊界：
    知道 raw 檔放哪個目錄、MySQL 的連線字串與資料表名稱。
    不知道資料是從哪個 API 來的，也不知道資料被整理過什麼。

換儲存目標（本機檔案 → GCS、MySQL → Cloud SQL）時，只有這個檔案要改。

兩種儲存：
  raw   data/raw/<source>/<key>.json，信封格式：
            {"meta": {source, key, url, request_body, http_status, body_format, fetched_at},
             "body": API 回應（JSON 就存 JSON；不是 JSON 就存原始文字）}
        失敗的回應另存 <key>.error.json，不會蓋掉之前成功的檔
  MySQL stage 層的表；建表 SQL 在 db/init/
"""
import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests
from sqlalchemy import Engine, bindparam, create_engine, text

from crawler.config import (
    MYSQL_ACCOUNT, MYSQL_DATABASE, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, PROJECT_ROOT, RAW_DIR,
)

INIT_DIR = PROJECT_ROOT / "db" / "init"


# ==================== raw ====================
def raw_path(source: str, key: str, ok: bool = True) -> Path:
    """成功：data/raw/<source>/<key>.json；失敗：data/raw/<source>/<key>.error.json"""
    return RAW_DIR / source / (f"{key}.json" if ok else f"{key}.error.json")


def parse_body(resp: requests.Response) -> dict | list | str:
    """回應是 JSON 就回傳解析後的資料；不是（例如被擋時的 HTML 錯誤頁）就回傳原始文字。"""
    try:
        return resp.json()
    except ValueError:
        return resp.text


def save_raw_response(source: str, key: str, resp: requests.Response) -> Path:
    """把一個 HTTP 回應原樣存成 raw 檔，回傳檔案路徑；失敗時「存完才報錯」。

    先存再報錯：被擋的時候對方會回 HTML 錯誤頁，
    存下來才看得到它到底回了什麼，而不是只剩一行 Python 錯誤訊息。
    同一個 source + key 再存一次會覆蓋舊檔 → 重跑幾次，檔案數量都一樣。
    """
    body = parse_body(resp)
    ok = resp.ok and not isinstance(body, str)          # resp.ok = 狀態碼 2xx
    request_body = resp.request.body                     # POST 送出的內容；GET 為 None
    if isinstance(request_body, bytes):
        request_body = json.loads(request_body)

    envelope = {
        "meta": {
            "source": source,
            "key": key,
            "url": resp.url,                             # 含參數的完整網址，可貼到瀏覽器重現
            "request_body": request_body,                # POST 的參數不在網址裡，要靠這個重現
            "http_status": resp.status_code,
            "body_format": "text" if isinstance(body, str) else "json",
            # 帶時區的抓取時間：推算上游每天幾點發布、追查上游事後更正
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "body": body,
    }

    path = raw_path(source, key, ok)
    path.parent.mkdir(parents=True, exist_ok=True)       # 第一次執行時資料夾還不存在
    with path.open("w", encoding="utf-8") as f:
        # ensure_ascii=False：中文直接寫中文；indent=2：打開就看得懂
        json.dump(envelope, f, ensure_ascii=False, indent=2)

    if not ok:
        raise RuntimeError(f"{source} {key} 抓取失敗：HTTP {resp.status_code}；回應內容已存到 {path}")
    return path


def load_raw(source: str, key: str) -> dict | None:
    """讀回一份成功的 raw 檔，回傳整個信封（meta + body）；沒有這個檔就回傳 None。"""
    path = raw_path(source, key)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_raw(source: str) -> list[str]:
    """某個來源所有「成功」的 raw 檔的 key，依名稱排序（失敗的 .error.json 不列）。"""
    folder = RAW_DIR / source
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json") if not p.name.endswith(".error.json"))


# ==================== MySQL ====================
def get_engine(with_database: bool = True) -> Engine:
    """建立 MySQL 連線。with_database=False 用在資料庫還不存在、要先建立它的時候。

    quote_plus：密碼含 @ : % 等符號時先編碼，否則連線字串會被切歪
    """
    db = f"/{MYSQL_DATABASE}" if with_database else "/"
    url = (f"mysql+pymysql://{MYSQL_ACCOUNT}:{quote_plus(MYSQL_PASSWORD)}"
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
            # 一個檔案可能有多個 SQL 敘述：用分號切開，跳過只有註解的片段
            for stmt in sql_file.read_text(encoding="utf-8").split(";"):
                code = [line for line in stmt.splitlines()
                        if line.strip() and not line.strip().startswith("--")]
                if code:
                    conn.execute(text(stmt))


def replace_days(conn, table: str, days: list[date], df: pd.DataFrame) -> None:
    """把某張表「這些日子」的資料整批換掉：先刪掉這些日子的舊資料，再一次寫入新的。

    days 要包含「這次處理過的所有日子」，連沒開市、沒有資料的日子也要給，
    這樣表裡那些日子才會被清空，和最新的 raw 一致。

    為什麼不用 append 或 upsert（ON DUPLICATE KEY UPDATE）：
      append 重跑會重複寫入；upsert 只能新增或更新，刪不掉「上次有、這次沒有」的列
      （上游更正、某檔股票從那天的名單被拿掉，upsert 會讓它永遠留在表裡）。
      整批換掉，重跑幾次結果都一樣。

    效能：DELETE 一次；INSERT 用 to_sql 的 method="multi"
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
