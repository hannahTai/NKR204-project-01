"""所有資料來源共用的擷取工具：發 HTTP 請求、把回應存成 raw 檔。

各來源的模組（twse.py、之後的 mops.py）只需要知道「網址和參數是什麼」，
其餘的請求設定和存檔流程都在這裡。
"""
from pathlib import Path

import requests

from crawler.storage.raw import save_raw

# 資料源會擋不像瀏覽器的請求，所以假裝成 Chrome
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = 30  # 秒；沒設的話，伺服器不回應時程式會一直卡住


def http_get(url: str, params: dict) -> requests.Response:
    """發 GET 請求，回傳 HTTP 回應（不檢查成敗）。

    params 交給 requests 組網址：它會自動處理 ? 和 &，以及特殊字元的編碼。
    """
    return requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)


def http_post(url: str, body: dict) -> requests.Response:
    """發 POST 請求（body 以 JSON 送出），回傳 HTTP 回應（不檢查成敗）。"""
    return requests.post(url, json=body, headers=HEADERS, timeout=TIMEOUT)


def parse_body(resp: requests.Response) -> dict | list | str:
    """回應是 JSON 就回傳解析後的資料；不是（例如 HTML 錯誤頁）就回傳原始文字。"""
    try:
        return resp.json()
    except ValueError:
        return resp.text


def save_response(source: str, key: str, resp: requests.Response,
                  request_body: dict | None = None) -> Path:
    """把一個 HTTP 回應存成 raw 檔，再判斷成敗；失敗時存完才報錯。

    先存再報錯：被擋的時候對方會回 HTML 錯誤頁，
    存下來才看得到它到底回了什麼，而不是只剩一行 Python 錯誤訊息。
    """
    body = parse_body(resp)

    ok = resp.ok and not isinstance(body, str)   # resp.ok = 狀態碼 2xx

    path = save_raw(
        source, key, body,
        url=resp.url,                # 含參數的完整網址
        http_status=resp.status_code,
        ok=ok,
        request_body=request_body,   # POST 的參數（GET 為 None）
    )

    if not ok:
        raise RuntimeError(
            f"{source} {key} 抓取失敗：HTTP {resp.status_code}，"
            f"{'回應不是 JSON' if isinstance(body, str) else '回應是 JSON'}；"
            f"回應內容已存到 {path}"
        )
    return path
