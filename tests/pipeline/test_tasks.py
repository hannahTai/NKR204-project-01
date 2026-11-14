"""tasks.py：抓完存檔前的檢查（不連網路，用假的回應）。"""
import json

import pytest
import requests

from pipeline.extract import api_twse, raw_file, tasks


def fake_response(body: dict) -> requests.Response:
    """做一個像 requests.get 回來的回應。"""
    url = "https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?response=json&date=20260101"
    resp = requests.Response()
    resp.status_code = 200
    resp._content = json.dumps(body).encode("utf-8")
    resp.url = url
    resp.request = requests.Request("GET", url).prepare()
    return resp


def test_holiday_saved_when_year_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_file, "RAW_DIR", tmp_path)
    monkeypatch.setattr(api_twse, "fetch_holiday", lambda year: fake_response({"queryYear": 2026, "data": []}))

    path = tasks.download_holiday(2026)

    assert path.name == "2026.json"


def test_holiday_wrong_year_saved_as_error(tmp_path, monkeypatch):
    """API 回了別年（11 月起不帶 date 會回下一年）→ 不能存成 2026.json。"""
    monkeypatch.setattr(raw_file, "RAW_DIR", tmp_path)
    monkeypatch.setattr(api_twse, "fetch_holiday", lambda year: fake_response({"queryYear": 2027, "data": []}))

    with pytest.raises(RuntimeError, match="要 2026 年，回傳的是 2027 年"):
        tasks.download_holiday(2026)

    assert not (tmp_path / "holiday" / "2026.json").exists()
    assert (tmp_path / "holiday" / "2026.error.json").exists()
