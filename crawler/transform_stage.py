"""T（轉換）：把 data/raw/ 的原始 JSON 整理成 8 張表，每張表存成一個 parquet。

    uv run python -m crawler.transform_stage         # 產出 data/stage/<表名>.parquet
    uv run python -m crawler.transform_stage --csv   # 另外輸出 CSV（方便用 Excel 檢查）

流程：讀 raw → 轉成表 → 存檔。不連網路、不連資料庫，可以放心重跑。
每次都從全部 raw 重算，轉換規則改了會自動套用到所有日期。
真正的轉換規則寫在 stage_data_transform.py，這支只負責讀檔、呼叫轉換、存檔。
"""
import argparse
import json

import pandas as pd

from crawler import date_utils, raw_file
from crawler import stage_data_transform as t
from crawler.config import STAGE_DIR

MANIFEST_PATH = STAGE_DIR / "manifest.json"

# 要讀的 raw 來源（對應 data/raw/ 底下的資料夾名稱）
SOURCES = ["notice", "punish", "punish_watchlist", "market_daily", "holiday", "companies", "announcements"]


# ---------- 1. 讀 raw ----------
def load_raws() -> dict[str, list[dict]]:
    """讀所有 raw 檔。

    回傳 {來源: [raw, raw, ...]}，例如 {"notice": [11/03 的 raw, 11/04 的 raw, ...], ...}
    每個 raw 是一個 JSON 檔的內容。
    """
    raws = {}
    for source in SOURCES:
        keys = raw_file.list_raw(source)   # 這個來源有哪些檔，例如 ["20261103", "20261104", ...]

        # 公司清單每天一份、一份 1.6MB，轉換只用到最新一份，所以只讀最後一個
        if source == "companies":
            keys = keys[-1:]

        raws[source] = []
        for key in keys:
            raws[source].append(raw_file.load_raw(source, key))
    return raws


# ---------- 2. 轉成表 ----------
def build_tables(raws: dict[str, list[dict]]) -> dict[str, pd.DataFrame]:
    """把 raw 轉成 8 張表，回傳 {表名: DataFrame}。

    大多分兩步，都寫在 stage_data_transform.py：
      xxx_to_frame：把每份 raw 的資料列攤平成一張表
      transform_xxx：清理、轉換（民國轉西元、去 HTML、文字轉數字、去重複）
    """
    # 注意股：一筆注意可能有好幾款，所以會產出兩張表
    notice_df = t.notice_to_frame(raws["notice"])
    notices, notice_clauses = t.transform_notice(notice_df)

    # 處置股
    punish_df = t.punish_to_frame(raws["punish"])
    punishes = t.transform_punish(punish_df)

    # 注意累計可能達處置標準名單
    watchlist_df = t.punish_watchlist_to_frame(raws["punish_watchlist"])
    watchlists = t.transform_punish_watchlist(watchlist_df)

    # 每日市場成交 → 交易日
    market_df = t.market_daily_to_frame(raws["market_daily"])
    trading_days = t.transform_trading_day(market_df)

    # 開休市日期
    holiday_df = t.holiday_to_frame(raws["holiday"])
    holidays = t.transform_holiday(holiday_df)

    # 上市公司清單：只用最新一份；還沒抓過就是空表
    latest_company_raw = raws["companies"][-1] if raws["companies"] else None
    companies = t.transform_company(latest_company_raw)

    # 重大訊息
    announcement_df = t.announcement_to_frame(raws["announcements"])
    announcements = t.transform_announcement(announcement_df)

    return {
        "stage_notice": notices,
        "stage_notice_clause": notice_clauses,
        "stage_punish": punishes,
        "stage_punish_watchlist": watchlists,
        "stage_trading_day": trading_days,
        "stage_holiday": holidays,
        "stage_company": companies,
        "stage_announcement": announcements,
    }


# ---------- 3. 存檔 ----------
def write_outputs(tables: dict[str, pd.DataFrame], csv: bool = False) -> None:
    """每張表存成 data/stage/<表名>.parquet，最後寫 manifest.json。"""
    STAGE_DIR.mkdir(parents=True, exist_ok=True)   # 資料夾不存在就建立

    for name, df in tables.items():
        df.to_parquet(STAGE_DIR / f"{name}.parquet", index=False)
        if csv:
            # utf-8-sig：Excel 打開中文才不會亂碼
            df.to_csv(STAGE_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    # manifest 最後才寫，代表「全部都寫完了」：中途當掉就不會有新的 manifest，L 不會讀到寫一半的資料
    manifest = {
        "created_at": date_utils.now().isoformat(),
        "tables": list(tables),   # 有哪些表，例如 ["stage_notice", "stage_notice_clause", ...]
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- 執行 ----------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", action="store_true", help="另外輸出 CSV")
    args = parser.parse_args()

    raws = load_raws()                       # 1. 讀 raw
    tables = build_tables(raws)              # 2. 轉成表
    write_outputs(tables, csv=args.csv)      # 3. 存檔

    for name, df in tables.items():
        print(f"{name:24s} {len(df):6d} 列")
    print("→", STAGE_DIR)


if __name__ == "__main__":
    main()
