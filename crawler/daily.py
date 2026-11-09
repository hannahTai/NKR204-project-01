"""每日排程：uv run python -m crawler.daily

每個交易日晚上跑一次，做兩件事：
1. 有歷史的資料源：抓「今天」這一天（和回補用同一套程式，見 backfill.run）
   - 開休市日期：今年（一年一個請求，每天重抓也很便宜）
   - 市場成交：本月（每天收盤會多一列，所以本月要每天重抓）
   - 注意股、處置股：今天
   - 公司重大訊息：今天被列注意的公司，本月＋上個月
2. 沒有歷史的資料源：只能每天存當下這一份
   - 注意累計名單：錯過的那天就永遠拿不到了
   - 上市公司基本資料：只有當下的快照（公司會上市、下市、改名）

建議時間：每個交易日晚上（名單在收盤後公布，確切時間待實測）。
"""
from datetime import date

from crawler.backfill import run
from crawler.extract.twse import extract_companies, extract_notetrans

if __name__ == "__main__":
    today = date.today().strftime("%Y%m%d")

    # 1. 有歷史的：範圍只有今天
    failed = run(today, today)

    # 2. 沒有歷史的：抓當下這一份
    for name, extract in [
        ("注意累計名單", extract_notetrans),
        ("上市公司基本資料", extract_companies),
    ]:
        print(f"===== {name}")
        try:
            print(name, "→", extract().name)
        except Exception as e:
            print(name, "✗", e)
            failed.append(name)

    print("\n失敗：", failed or "無")
    if failed:
        raise SystemExit(1)   # 讓排程工具知道這次沒成功
