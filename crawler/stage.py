"""重算 stage 層：raw → transformer → MySQL 的 stage 表。

三層：raw（原樣）→ stage（清洗、統一欄名）→ app（規則引擎的成品，之後做）

    uv run python -m crawler.stage          # 寫進 MySQL
    uv run python -m crawler.stage --csv    # 只輸出 CSV 到 data/stage/（不碰資料庫，檢查用）

每次都從 raw 全部重算：stage 是 raw 的衍生資料，整理規則改了，重跑這支就好，不必重抓。
"""
import argparse

from sqlalchemy import text

from crawler import repository, transformer
from crawler.config import CSV_OUTPUT_DIR
from crawler.date_utils import key_to_date


def build_notice():
    """注意股 raw → (處理過的日子, stage_notice, stage_notice_clause)。整批轉換一次。"""
    keys = repository.list_raw("twse_notice")
    df = transformer.notice_to_frame([repository.load_raw("twse_notice", k) for k in keys])
    notices, clauses = transformer.transform_notice(df)
    return [key_to_date(k) for k in keys], notices, clauses


def main() -> None:
    parser = argparse.ArgumentParser(description="raw → stage")
    parser.add_argument("--csv", action="store_true", help="只輸出 CSV，不寫資料庫")
    args = parser.parse_args()

    days, notices, clauses = build_notice()

    if args.csv:
        CSV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # utf-8-sig：讓 Excel 打開時中文不會變亂碼
        notices.to_csv(CSV_OUTPUT_DIR / "stage_notice.csv", index=False, encoding="utf-8-sig")
        clauses.to_csv(CSV_OUTPUT_DIR / "stage_notice_clause.csv", index=False, encoding="utf-8-sig")
        print(f"{len(days)} 天 → 注意股 {len(notices)} 列、款次 {len(clauses)} 列 → {CSV_OUTPUT_DIR}")
        return

    repository.init_db()
    engine = repository.get_engine()
    # 一個交易（transaction）：兩張表一起成功或一起失敗，不會只寫一半
    with engine.begin() as conn:
        repository.replace_days(conn, "stage_notice", days, notices)
        repository.replace_days(conn, "stage_notice_clause", days, clauses)
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM stage_notice")).scalar()
        c = conn.execute(text("SELECT COUNT(*) FROM stage_notice_clause")).scalar()
    print(f"處理 {len(days)} 天 → stage_notice {n} 列、stage_notice_clause {c} 列")


if __name__ == "__main__":
    main()
