"""日期工具：台北時間的今天、民國轉西元、日期與月份範圍。"""
import calendar
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

DATE_FMT = "%Y%m%d"              # 例如 20261106
TAIPEI = ZoneInfo("Asia/Taipei")  # 「今天」以台北時間為準，不受機器時區影響


def now() -> datetime:
    return datetime.now(TAIPEI)


def today() -> date:
    return now().date()


def today_key() -> str:
    """今天，YYYYMMDD。"""
    return today().strftime(DATE_FMT)


def key_to_date(key: str) -> date:
    """YYYYMMDD → date。"""
    return datetime.strptime(key, DATE_FMT).date()


def shift(day: str, days: int) -> str:
    """YYYYMMDD 加減天數。

    >>> shift("20261231", 1)
    '20270101'
    """
    return (key_to_date(day) + timedelta(days=days)).strftime(DATE_FMT)


def date_range(start: str, end: str) -> list[str]:
    """start 到 end 的每一天（含頭尾）。

    >>> date_range("20261230", "20270101")
    ['20261230', '20261231', '20270101']
    """
    first = key_to_date(start)
    days = (key_to_date(end) - first).days
    return [(first + timedelta(days=i)).strftime(DATE_FMT) for i in range(days + 1)]


def month_range(start: str, end: str) -> list[str]:
    """start 到 end 涵蓋的月份，YYYYMM。

    >>> month_range("20261115", "20270102")
    ['202611', '202612', '202701']
    """
    y, m = int(start[:4]), int(start[4:6])
    months = []
    while f"{y:04d}{m:02d}" <= end[:6]:
        months.append(f"{y:04d}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def prev_month(month: str) -> str:
    """YYYYMM 的上一個月。

    >>> prev_month("202601")
    '202512'
    """
    first_day = date(int(month[:4]), int(month[4:]), 1)
    return (first_day - timedelta(days=1)).strftime("%Y%m")


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def roc_to_date(text: str) -> date:
    """民國日期 → date，分隔符號不拘。

    >>> roc_to_date("115.11.06"), roc_to_date("115年11月6日")
    (datetime.date(2026, 11, 6), datetime.date(2026, 11, 6))
    """
    y, m, d = re.findall(r"\d+", text)
    return date(int(y) + 1911, int(m), int(d))


def roc_to_dates(s: pd.Series) -> pd.Series:
    """roc_to_date 的整欄版（比逐筆轉換快）。

    >>> roc_to_dates(pd.Series(["115.11.06", "*115/10/01"])).tolist()
    [datetime.date(2026, 11, 6), datetime.date(2026, 10, 1)]
    """
    ymd = s.str.extract(r"(\d+)\D+(\d+)\D+(\d+)").astype(int)
    return pd.to_datetime(pd.DataFrame({"year": ymd[0] + 1911, "month": ymd[1], "day": ymd[2]})).dt.date
