"""回補注意股：uv run python -m crawler.backfill

過渡用工具：接上 Airflow 之後，回補改由 Airflow 處理。
"""
import time
from datetime import date

from crawler.extract.twse import extract_notice
from crawler.utils.dates import date_range


def backfill(start: str, end: str, sleep: float = 1.0) -> list[str]:
    """一天一天抓，回傳失敗的日期。某天失敗不會中斷整批。"""
    failed = []
    for d in date_range(start, end):
        try:
            print(d, "→", extract_notice(d).name)
        except Exception as e:
            print(d, "✗", e)
            failed.append(d)
        time.sleep(sleep)   # 間隔一下，太快會被證交所擋
    return failed


if __name__ == "__main__":
    today = date.today().strftime("%Y%m%d")
    failed = backfill("20261001", today)
    print("失敗：", failed or "無")
