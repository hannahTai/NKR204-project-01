"""raw 層：把 API 的回應連同「怎麼抓到的」一起存成 JSON 檔。

檔案格式（信封）：
    {
      "meta": {"source", "key", "url", "request_body", "http_status", "body_format", "fetched_at"},
      "body": API 回應（JSON 就存 JSON；不是 JSON 就存原始文字）
    }

這個模組只管「存在哪、怎麼存」，不知道資料是從哪個 API 來的。
之後要改存到 GCS 或 MySQL，只改這裡，extract 那邊不用動。
"""
import json
from datetime import datetime
from pathlib import Path

from crawler.config import RAW_DIR


def raw_path(source: str, key: str, ok: bool = True) -> Path:
    """raw 檔的路徑。

    成功：data/raw/<source>/<key>.json
    失敗：data/raw/<source>/<key>.error.json
    失敗的回應另存一個檔名，才不會把之前抓成功的資料蓋掉。
    """
    suffix = ".json" if ok else ".error.json"
    return RAW_DIR / source / f"{key}{suffix}"


def save_raw(
    source: str,
    key: str,
    body: dict | list | str,
    *,
    url: str,
    http_status: int,
    ok: bool = True,
    request_body: dict | None = None,
) -> Path:
    """存一份回應，回傳檔案路徑。

    source:      資料來源名稱，例如 "twse_notice"
    key:         這次請求的識別，例如日期 "20261106"
    body:        回應內容；JSON 就傳解析後的 dict/list，不是 JSON 就傳原始文字
    url:         實際請求的完整網址（含參數），出問題時可以貼到瀏覽器重現
    http_status: HTTP 狀態碼
    ok:          這次請求是否成功；False 時存成 <key>.error.json
    request_body: POST 請求送出的內容（GET 沒有，傳 None）；
                  公告來源用 POST，參數不在網址裡，要靠這個欄位才能重現請求

    同一個 source + key 再存一次會覆蓋舊檔 → 重跑幾次，檔案數量都一樣
    """
    envelope = {
        "meta": {
            "source": source,
            "key": key,
            "url": url,
            "request_body": request_body,
            "http_status": http_status,
            # body 是 JSON 還是原始文字；解析程式讀檔時靠這個判斷
            "body_format": "text" if isinstance(body, str) else "json",
            # 帶時區的抓取時間，例如 2026-11-09T22:30:15+08:00
            # 用途：推算上游每天幾點發布、追查上游事後更正
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "body": body,
    }

    path = raw_path(source, key, ok)

    # 第一次執行時資料夾還不存在：
    #   parents=True  → 中間缺的資料夾一起建
    #   exist_ok=True → 已經存在就不報錯
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        # ensure_ascii=False → 中文直接寫中文，不會變成 \u6ce8\u610f
        # indent=2           → 排版過，打開就看得懂
        json.dump(envelope, f, ensure_ascii=False, indent=2)

    return path


def load_raw(source: str, key: str) -> dict | None:
    """讀回一份成功的 raw 檔，回傳整個信封（meta + body）；沒有這個檔就回傳 None。"""
    path = raw_path(source, key)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)
