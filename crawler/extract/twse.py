import requests

from crawler.config import TWSE_BASE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

TIMEOUT = 30


def fetch_notice(date: str) -> dict:
    """抓某一個交易日的注意股（全部上市股票）。

    date: 西元 YYYYMMDD，例如 "20261106"
    回傳: API 回應的 JSON（dict），原封不動

    每日排程和回補都用這個函式：每日 = 抓今天，回補 = 一天一天呼叫。
    """
    url = f"{TWSE_BASE}/announcement/notice"
    params = {
        "response": "json",
        "querytype": "1",
        "startDate": date,
        "endDate": date,      # 起訖同一天 = 只抓這一天
        "sortKind": "DATE",   # 依日期排序
    }
    # params 交給 requests 組網址：它會自動處理 ? 和 &，以及特殊字元的編碼
    resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)

    # HTTP 狀態碼不是 2xx（例如 403 被擋、500 伺服器錯誤）就直接丟出例外，
    # 不要讓錯誤的回應被當成正常資料往下傳
    resp.raise_for_status()

    return resp.json()


if __name__ == "__main__":
    for d in ["20261106", "20261108"]:   # 週五（交易日）、週日（沒開市）
        result = fetch_notice(d)
        print(result)
        print("-----")