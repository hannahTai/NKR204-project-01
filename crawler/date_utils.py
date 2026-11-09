"""日期工具（utility）：西元／民國換算、日期與月份範圍。各層共用，不含任何業務邏輯。"""
import calendar
import re
from datetime import date, datetime, timedelta

import pandas as pd

DATE_FMT = "%Y%m%d"   # 本專案的日期字串格式，例如 20261106


def date_range(start: str, end: str) -> list[str]:
    """產生 start 到 end 之間（含頭尾）的每一天，格式 YYYYMMDD。

    >>> date_range("20261230", "20270101")
    ['20261230', '20261231', '20270101']
    """
    d = datetime.strptime(start, DATE_FMT).date()
    last = datetime.strptime(end, DATE_FMT).date()
    days = []
    while d <= last:
        days.append(d.strftime(DATE_FMT))
        d += timedelta(days=1)
    return days


def shift(day: str, days: int) -> str:
    """把 YYYYMMDD 往後（正數）或往前（負數）移幾天。

    >>> shift("20261231", 1)
    '20270101'
    """
    d = datetime.strptime(day, DATE_FMT) + timedelta(days=days)
    return d.strftime(DATE_FMT)


def roc_to_date(text: str) -> date:
    """民國日期字串 → date。年月日之間用什麼分隔都可以（. / 年月日）。

    >>> roc_to_date("115.11.06"), roc_to_date("115/10/01"), roc_to_date("115年11月6日")
    (datetime.date(2026, 11, 6), datetime.date(2026, 10, 1), datetime.date(2026, 11, 6))
    """
    y, m, d = re.findall(r"\d+", text)
    return date(int(y) + 1911, int(m), int(d))


def roc_to_dates(s: pd.Series) -> pd.Series:
    """roc_to_date 的整欄版本：一次轉換一整欄民國日期，比逐筆 map 快很多。

    >>> roc_to_dates(pd.Series(["115.11.06", "115/10/01"])).tolist()
    [datetime.date(2026, 11, 6), datetime.date(2026, 10, 1)]
    """
    parts = s.str.extract(r"(\d+)\D+(\d+)\D+(\d+)").astype(int)   # 一次切出年、月、日三欄
    return pd.to_datetime(
        pd.DataFrame({"year": parts[0] + 1911, "month": parts[1], "day": parts[2]})
    ).dt.date


def last_day_of_month(year: int, month: int) -> int:
    """某年某月有幾天，例如 2026 年 2 月 → 28。"""
    return calendar.monthrange(year, month)[1]


def month_range(start: str, end: str) -> list[str]:
    """start 到 end（YYYYMMDD）涵蓋的每個月份，格式 YYYYMM。

    >>> month_range("20261115", "20270102")
    ['202611', '202612', '202701']
    """
    y, m = int(start[:4]), int(start[4:6])
    last = (int(end[:4]), int(end[4:6]))
    months = []
    while (y, m) <= last:
        months.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def prev_month(month: str) -> str:
    """YYYYMM 的上一個月。

    >>> prev_month("202601")
    '202512'
    """
    y, m = int(month[:4]), int(month[4:6])
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y:04d}{m:02d}"


def key_to_date(key: str) -> date:
    """YYYYMMDD 字串 → date。

    >>> key_to_date("20261106")
    datetime.date(2026, 11, 6)
    """
    return datetime.strptime(key, DATE_FMT).date()
