"""HTTP 請求工具：所有抓資料的任務共用。"""
import requests

HEADERS = {   # 不像瀏覽器的請求會被擋
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "application/json",
}
TIMEOUT = 30  # 秒


def http_get(url: str, params: dict) -> requests.Response:
    return requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)


def http_post(url: str, body: dict) -> requests.Response:
    return requests.post(url, json=body, headers=HEADERS, timeout=TIMEOUT)
