"""日期工具。"""
from datetime import datetime, timedelta

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
