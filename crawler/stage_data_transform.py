"""整理資料：raw → stage 表（pandas）。

只做清洗與型別轉換，不做判斷：官方公告了什麼就留什麼。
欄位用整欄運算（.str、to_numeric），不用逐列迴圈。
"""
import re
import warnings

import pandas as pd

from crawler.date_utils import roc_to_date, roc_to_dates
from crawler.transform_utils import chinese_number, fetched_at, rows_to_frame, strip_html, to_number


# ---------- 注意股 ----------
# 丟掉的欄位：編號（全部是 1）、累計次數（是查詢回傳的筆數，不是個股累計）
NOTICE_FIELDS = ["編號", "證券代號", "證券名稱", "累計次數", "注意交易資訊", "日期", "收盤價", "本益比"]
NOTICE_COLUMNS = ["trade_date", "stock_id", "stock_name", "reason_text", "close_price", "pe_ratio"]
NOTICE_CLAUSE_COLUMNS = ["trade_date", "stock_id", "clause"]


def notice_to_frame(raws: list[dict]) -> pd.DataFrame:
    return rows_to_frame(raws, NOTICE_FIELDS, "注意股")


def transform_notice(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """→ (stage_notice, stage_notice_clause)"""
    if df.empty:
        return pd.DataFrame(columns=NOTICE_COLUMNS), pd.DataFrame(columns=NOTICE_CLAUSE_COLUMNS)

    notices = pd.DataFrame({
        "trade_date": roc_to_dates(df["日期"]),
        "stock_id": df["證券代號"].str.strip(),
        "stock_name": df["證券名稱"].str.strip(),
        "reason_text": strip_html(df["注意交易資訊"]),
        "close_price": to_number(df["收盤價"]),
        "pe_ratio": to_number(df["本益比"]),
    })

    # 每列抓出所有「第X款」，一個款次一列；index 第 0 層是原本的列號
    found = notices["reason_text"].str.extractall(r"第([一二三四五六七八九十]+)款")[0]
    row_ids = found.index.get_level_values(0)
    if row_ids.nunique() < len(notices):
        raise ValueError("有注意股找不到款次，格式可能改了")

    clauses = notices.loc[row_ids, ["trade_date", "stock_id"]].copy()
    clauses["clause"] = found.map(chinese_number).to_numpy()
    clauses = clauses.drop_duplicates().sort_values(NOTICE_CLAUSE_COLUMNS).reset_index(drop=True)
    return notices, clauses


# ---------- 處置股 ----------
# 同一筆公告會出現在好幾天的 raw → 依（公布日期, 代號）去重，留最後抓到的
# 同一份 raw 裡（公布日期, 代號）重複且內容不同 → 同一天有兩則處置，去重只會留一則，所以發出警告
# 丟掉的欄位：編號、累計（隨查詢區間變動）、備註（只有連結）
# 公布日期偶爾帶 *（意義未確認），存成 has_star_mark
PUNISH_FIELDS = ["編號", "公布日期", "證券代號", "證券名稱", "累計", "處置條件",
                 "處置起迄時間", "處置措施", "處置內容", "備註"]


def punish_to_frame(raws: list[dict]) -> pd.DataFrame:
    raws = sorted(raws, key=fetched_at)   # 舊 → 新
    return rows_to_frame(raws, PUNISH_FIELDS, "處置股", extra={"fetched_at": fetched_at})   # 用來分辨每列來自哪份 raw


def transform_punish(df: pd.DataFrame) -> pd.DataFrame:
    """→ stage_punish"""
    period = df["處置起迄時間"].str.extract(r"(\S+)～(\S+)")
    minutes = df["處置內容"].str.extract(r"約每([一二三四五六七八九十]+)分鐘")[0]   # 撮合間隔
    out = pd.DataFrame({
        "announce_date": roc_to_dates(df["公布日期"]),
        "stock_id": df["證券代號"].str.strip(),
        "stock_name": df["證券名稱"].str.strip(),
        "trigger_condition": df["處置條件"].str.strip(),
        "period_start": roc_to_dates(period[0]),
        "period_end": roc_to_dates(period[1]),
        "measure_type": df["處置措施"].str.strip(),
        "match_interval_minutes": minutes.dropna().map(chinese_number).astype("Int64"),
        "content": df["處置內容"].str.strip(),
        "has_star_mark": df["公布日期"].str.startswith("*"),
    })
    same_raw = out.assign(fetched_at=df["fetched_at"]).drop_duplicates()   # 完全相同的列不算
    conflicts = same_raw[same_raw.duplicated(["fetched_at", "announce_date", "stock_id"], keep=False)]
    if not conflicts.empty:
        listed = conflicts[["announce_date", "stock_id", "measure_type"]].drop_duplicates().to_string(index=False)
        warnings.warn(f"處置股：同一天同一檔有多則處置，只會留下一則，請確認：\n{listed}")
    out = out.drop_duplicates(["announce_date", "stock_id"], keep="last")
    return out.sort_values(["announce_date", "stock_id"]).reset_index(drop=True)


# ---------- 注意累計可能達處置標準名單 ----------
PUNISH_WATCHLIST_FIELDS = ["編號", "證券代號", "證券名稱", "近期達本公司「公布注意交易資訊」標準之情形"]


def title_date(raw: dict):
    """從 title（例如「115年11月06日 公布…」）取出資料日期。"""
    return roc_to_date(re.search(r"\d+年\d+月\d+日", raw["body"]["title"]).group())


def punish_watchlist_to_frame(raws: list[dict]) -> pd.DataFrame:
    return rows_to_frame(raws, PUNISH_WATCHLIST_FIELDS, "注意累計名單", extra={"data_date": title_date})


def transform_punish_watchlist(df: pd.DataFrame) -> pd.DataFrame:
    """→ stage_punish_watchlist"""
    progress = df[PUNISH_WATCHLIST_FIELDS[3]].str.replace("<br>", "\n")   # 多行情形換成換行
    out = pd.DataFrame({
        "data_date": df["data_date"],
        "stock_id": df["證券代號"].str.strip(),
        "stock_name": df["證券名稱"].str.strip(),
        "progress_text": strip_html(progress),
    })
    return out.drop_duplicates(["data_date", "stock_id"], keep="last").reset_index(drop=True)


# ---------- 每日市場成交 → 交易日 ----------
MARKET_DAILY_FIELDS = ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"]


def market_daily_to_frame(raws: list[dict]) -> pd.DataFrame:
    return rows_to_frame(raws, MARKET_DAILY_FIELDS, "市場成交資訊")


def transform_trading_day(df: pd.DataFrame) -> pd.DataFrame:
    """→ stage_trading_day（每列是一個有交易的日子）"""
    out = pd.DataFrame({
        "trade_date": roc_to_dates(df["日期"]),
        "volume_shares": to_number(df["成交股數"]).astype("Int64"),
        "amount_twd": to_number(df["成交金額"]).astype("Int64"),
        "trade_count": to_number(df["成交筆數"]).astype("Int64"),
        "taiex_index": to_number(df["發行量加權股價指數"]),
        "taiex_change_points": to_number(df["漲跌點數"]),
    })
    return out.drop_duplicates("trade_date", keep="last").sort_values("trade_date").reset_index(drop=True)


# ---------- 開休市日期 ----------
HOLIDAY_FIELDS = ["日期", "名稱", "說明"]


def holiday_to_frame(raws: list[dict]) -> pd.DataFrame:
    return rows_to_frame(raws, HOLIDAY_FIELDS, "開休市日期")


def transform_holiday(df: pd.DataFrame) -> pd.DataFrame:
    """→ stage_holiday（照官方原樣，也含「開始交易日」這類有交易的日子）"""
    out = pd.DataFrame({
        "holiday_date": pd.to_datetime(df["日期"]).dt.date,   # 這支 API 是西元
        "holiday_name": df["名稱"].str.strip(),
        "description": df["說明"].str.strip(),
    })
    return out.drop_duplicates("holiday_date", keep="last").sort_values("holiday_date").reset_index(drop=True)


# ---------- 上市公司 ----------
def transform_company(raw: dict | None) -> pd.DataFrame:
    """最新一份公司清單 → stage_company"""
    df = pd.DataFrame(raw["body"] if raw else [],
                      columns=["公司代號", "公司簡稱", "公司名稱", "產業別", "上市日期"])
    return pd.DataFrame({
        "company_id": df["公司代號"].str.strip(),
        "short_name": df["公司簡稱"].str.strip(),
        "full_name": df["公司名稱"].str.strip(),
        "industry_code": df["產業別"].str.strip(),
        "listed_date": pd.to_datetime(df["上市日期"], format="%Y%m%d").dt.date,
        "snapshot_date": pd.to_datetime(raw["meta"]["key"]).date() if raw else None,
    })


# ---------- 公司重大訊息 ----------
# 格式和其他來源不同：{"code", "result": {"titles", "data"}}；code 406 = 那個月沒有公告
ANNOUNCEMENT_TITLES = ["公司代號", "公司名稱", "發言日期", "發言時間", "主旨", "詳細資料"]


def announcement_to_frame(raws: list[dict]) -> pd.DataFrame:
    rows = []
    for raw in raws:
        result = raw["body"].get("result") or {}
        if not result.get("data"):
            continue
        titles = [t["main"] for t in result["titles"]]
        if titles != ANNOUNCEMENT_TITLES:
            raise ValueError(f"重大訊息欄位改變：{titles}")
        rows += result["data"]
    return pd.DataFrame(rows, columns=ANNOUNCEMENT_TITLES)


def transform_announcement(df: pd.DataFrame) -> pd.DataFrame:
    """→ stage_announcement"""
    keys = ["company_id", "announce_date", "serial_number"]
    out = pd.DataFrame({
        "company_id": df["公司代號"].str.strip(),
        "announce_date": roc_to_dates(df["發言日期"]),
        "serial_number": df["詳細資料"].str["parameters"].str["serialNumber"].astype(int),  # 當天第幾則
        "announce_time": df["發言時間"].str.strip(),
        "company_name": df["公司名稱"].str.strip(),
        "subject": df["主旨"].str.replace(r"\s*\n\s*", "", regex=True).str.strip(),  # 接回被換行切斷的主旨
    })
    return out.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)
