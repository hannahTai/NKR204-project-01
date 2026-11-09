"""用 raw 重算 stage 表。

    uv run python -m crawler.stage                                  # 全部重算
    uv run python -m crawler.stage --start 20261028                 # 只重算 10/28
    uv run python -m crawler.stage --start 20261027 --end 20261031  # 只重算這幾天
    uv run python -m crawler.stage --csv                            # 輸出 CSV 到 data/stage/
"""
import argparse

import pandas as pd
from sqlalchemy import text

from crawler import repository
from crawler import transformer as t
from crawler.config import CSV_OUTPUT_DIR
from crawler.date_utils import date_range, key_to_date

# 每張表用哪個日期欄位決定「屬於哪一天」；公司清單是快照，沒有日期
DATE_COLUMNS = {
    "stage_notice": "trade_date",
    "stage_notice_clause": "trade_date",
    "stage_punish": "announce_date",
    "stage_punish_watchlist": "data_date",
    "stage_trading_day": "trade_date",
    "stage_holiday": "holiday_date",
    "stage_company": None,
    "stage_announcement": "announce_date",
}


def load_all(source: str) -> list[dict]:
    return [repository.load_raw(source, key) for key in repository.list_raw(source)]


def build_all() -> dict[str, pd.DataFrame]:
    """{表名: DataFrame}，用全部的 raw 算（不到一秒）。"""
    notices, clauses = t.transform_notice(t.notice_to_frame(load_all("notice")))
    company_keys = repository.list_raw("companies")
    latest_companies = repository.load_raw("companies", company_keys[-1]) if company_keys else None
    return {
        "stage_notice": notices,
        "stage_notice_clause": clauses,
        "stage_punish": t.transform_punish(t.punish_to_frame(load_all("punish"))),
        "stage_punish_watchlist": t.transform_punish_watchlist(
            t.punish_watchlist_to_frame(load_all("punish_watchlist"))),
        "stage_trading_day": t.transform_trading_day(t.market_daily_to_frame(load_all("market_daily"))),
        "stage_holiday": t.transform_holiday(t.holiday_to_frame(load_all("holiday"))),
        "stage_company": t.transform_company(latest_companies),
        "stage_announcement": t.transform_announcement(t.announcement_to_frame(load_all("announcements"))),
    }


def only_days(tables: dict[str, pd.DataFrame], days: list) -> dict[str, pd.DataFrame]:
    """每張表只留指定日期的列；沒有日期的表（公司清單）拿掉。"""
    return {name: df[df[DATE_COLUMNS[name]].isin(days)]
            for name, df in tables.items() if DATE_COLUMNS[name]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="YYYYMMDD；不給就全部重算")
    parser.add_argument("--end", help="YYYYMMDD；不給就等於 --start")
    parser.add_argument("--csv", action="store_true", help="只輸出 CSV")
    args = parser.parse_args()

    tables = build_all()
    days = None
    if args.start:
        days = [key_to_date(d) for d in date_range(args.start, args.end or args.start)]
        tables = only_days(tables, days)

    if args.csv:
        CSV_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            df.to_csv(CSV_OUTPUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")  # sig：Excel 不亂碼
            print(f"{name:24s} {len(df):6d} 列")
        return

    repository.init_db()
    engine = repository.get_engine()
    with engine.begin() as conn:   # 同一個交易：全部成功或全部不變
        for name, df in tables.items():
            if days is None:
                repository.replace_table(conn, name, df)
            else:
                repository.replace_days(conn, name, DATE_COLUMNS[name], days, df)
            print(f"{name:24s} 寫入 {len(df):6d} 列")
    with engine.connect() as conn:
        for name in tables:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            print(f"{name:24s} 表內共 {count:6d} 列")


if __name__ == "__main__":
    main()
