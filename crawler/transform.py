"""raw → staging：uv run python -m crawler.transform

    uv run python -m crawler.transform          # 解析後寫進 MySQL
    uv run python -m crawler.transform --csv    # 只輸出 CSV 到 data/staging/（不碰資料庫，檢查用）
"""
import argparse

from sqlalchemy import text

from crawler.config import PROJECT_ROOT
from crawler.staging import notice
from crawler.storage.db import get_engine, init_db, replace_days
from crawler.storage.raw import list_raw, load_raw
from crawler.utils.dates import key_to_date

STAGING_DIR = PROJECT_ROOT / "data" / "staging"


def transform_notice():
    """讀所有注意股 raw → 整批轉換一次。回傳 (處理過的日子, stg_notice, stg_notice_clause)。"""
    keys = list_raw("twse_notice")
    df = notice.to_frame([load_raw("twse_notice", k) for k in keys])
    notices, clauses = notice.transform(df)
    return [key_to_date(k) for k in keys], notices, clauses


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="raw → staging")
    parser.add_argument("--csv", action="store_true", help="只輸出 CSV，不寫資料庫")
    args = parser.parse_args()

    days, notices, clauses = transform_notice()

    if args.csv:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        # utf-8-sig：讓 Excel 打開時中文不會變亂碼
        notices.to_csv(STAGING_DIR / "notice.csv", index=False, encoding="utf-8-sig")
        clauses.to_csv(STAGING_DIR / "notice_clause.csv", index=False, encoding="utf-8-sig")
        print(f"{len(days)} 天 → 注意股 {len(notices)} 列、款次 {len(clauses)} 列 → {STAGING_DIR}")
    else:
        init_db()
        engine = get_engine()
        # 一個交易（transaction）：兩張表一起成功或一起失敗，不會只寫一半
        with engine.begin() as conn:
            replace_days(conn, "stg_notice", days, notices)
            replace_days(conn, "stg_notice_clause", days, clauses)
        with engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM stg_notice")).scalar()
            c = conn.execute(text("SELECT COUNT(*) FROM stg_notice_clause")).scalar()
        print(f"處理 {len(days)} 天 → stg_notice {n} 列、stg_notice_clause {c} 列")
