"""日期工具。"""
import calendar
from datetime import date, datetime, timedelta

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


def roc_to_ymd(year: int | str, month: int | str, day: int | str) -> str:
    """民國年月日 → 西元 YYYYMMDD。

    >>> roc_to_ymd(115, 11, 6)
    '20261106'
    """
    return date(int(year) + 1911, int(month), int(day)).strftime(DATE_FMT)


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
