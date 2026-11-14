"""raw 檔：data/raw/<來源>/<key>.json，存 API 的原始回應。"""
import json
import pathlib

import requests

from common import date_utils
from common.config import RAW_DIR


def raw_path(source: str, key: str, ok: bool = True) -> pathlib.Path:
    """成功存 <key>.json；失敗存 <key>.error.json，不會蓋掉成功的檔。"""
    return RAW_DIR / source / (f"{key}.json" if ok else f"{key}.error.json")


def parse_body(resp: requests.Response) -> dict | list | str:
    """JSON 就解析；不是 JSON（例如被擋時的 HTML）就回傳原文。"""
    try:
        return resp.json()
    except ValueError:
        return resp.text


def save_raw_response(source: str, key: str, resp: requests.Response) -> pathlib.Path:
    """把回應原樣存檔（含網址、狀態碼、抓取時間），同一個 key 直接覆蓋；失敗時存完再報錯。"""
    body = parse_body(resp)
    ok = resp.ok and not isinstance(body, str)
    request_body = resp.request.body   # POST 的參數；GET 為 None
    envelope = {
        "meta": {
            "source": source,
            "key": key,
            "url": resp.url,
            "request_body": json.loads(request_body) if request_body else None,
            "http_status": resp.status_code,
            "fetched_at": date_utils.now().isoformat(timespec="seconds"),
        },
        "body": body,
    }
    path = raw_path(source, key, ok)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    if not ok:
        raise RuntimeError(f"{source} {key} 抓取失敗（HTTP {resp.status_code}），回應已存到 {path}")
    return path


def load_raw(source: str, key: str) -> dict | None:
    path = raw_path(source, key)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def list_raw(source: str) -> list[str]:
    """某來源所有的 key（不含 .error.json），排序後回傳。"""
    files = (RAW_DIR / source).glob("*.json")
    return sorted(p.stem for p in files if "." not in p.stem)
