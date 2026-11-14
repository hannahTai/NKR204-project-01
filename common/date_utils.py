"""日期工具：台北時間的今天、民國轉西元。
"""
import datetime
import re
import zoneinfo

import pandas as pd

DATE_FMT = "%Y%m%d"                       # 例如 20261106
TAIPEI = zoneinfo.ZoneInfo("Asia/Taipei")  # 「今天」以台北時間為準，不受機器時區影響


def now() -> datetime.datetime:
    return datetime.datetime.now(TAIPEI)


def today() -> datetime.date:
    return now().date()


def today_yyyymmdd() -> str:
    """今天的日期字串，例如 "20261113"。"""
    return today().strftime(DATE_FMT)


def roc_to_date(text: str) -> datetime.date:
    """民國日期 → date，分隔符號不拘。

    >>> roc_to_date("115.11.06"), roc_to_date("115年11月6日")
    (datetime.date(2026, 11, 6), datetime.date(2026, 11, 6))
    """
    y, m, d = re.findall(r"\d+", text)
    return datetime.date(int(y) + 1911, int(m), int(d))


def roc_to_dates(s: pd.Series) -> pd.Series:
    """roc_to_date 的整欄版（比逐筆轉換快）。

    >>> roc_to_dates(pd.Series(["115.11.06", "*115/10/01"])).tolist()
    [datetime.date(2026, 11, 6), datetime.date(2026, 10, 1)]
    """
    ymd = s.str.extract(r"(\d+)\D+(\d+)\D+(\d+)").astype(int)
    return pd.to_datetime(pd.DataFrame({"year": ymd[0] + 1911, "month": ymd[1], "day": ymd[2]})).dt.date


def prev_month(yyyymm: str) -> str:
    """上個月，跨年也對；傳 YYYYMMDD 也可以（只看前 6 碼）。

    >>> prev_month("202611"), prev_month("20260115")
    ('202610', '202512')
    """
    return (pd.Period(f"{yyyymm[:4]}-{yyyymm[4:6]}", "M") - 1).strftime("%Y%m")


def month_end(yyyymm: str) -> datetime.date:
    """某個月的最後一天。

    >>> month_end("202602")
    datetime.date(2026, 2, 28)
    """
    return pd.Period(f"{yyyymm[:4]}-{yyyymm[4:6]}", "M").end_time.date()
