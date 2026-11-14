"""producer 決定要抓哪些重大訊息：用暫存的 raw 目錄，不連網路。執行：uv run pytest"""
import datetime
import json

import pytest

from pipeline.extract import producer as pc
from pipeline.extract import raw_file
from common.date_utils import month_end, prev_month


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_file, "RAW_DIR", tmp_path)
    return tmp_path


def write_raw(raw_dir, source, key, body, fetched_at="2026-11-13T21:00:00+08:00"):
    path = raw_dir / source / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"meta": {"fetched_at": fetched_at}, "body": body}, ensure_ascii=False), encoding="utf-8")


def setup_day(raw_dir, day="20261113"):
    """今天：2330 被列注意、0050 處置（ETF，不在公司清單）。"""
    write_raw(raw_dir, "companies", day, [{"公司代號": "2330 "}, {"公司代號": "2317"}])
    write_raw(raw_dir, "notice", day, {"data": [["1", "2330"]]})
    write_raw(raw_dir, "punish", day, {"data": [["1", "x", "0050"]]})


def keys(jobs):
    return [args for _, args in jobs]


def test_month_utils():
    assert prev_month("20260115") == "202512"
    assert prev_month("202611") == "202610"
    assert month_end("202602") == datetime.date(2026, 2, 28)


def test_is_complete(raw_dir):
    assert not pc.is_complete("2330", "202610")                                     # 沒有檔
    write_raw(raw_dir, "announcements", "2330_202610", {}, "2026-10-20T21:00:00+08:00")
    assert not pc.is_complete("2330", "202610")                                     # 月中抓的
    write_raw(raw_dir, "announcements", "2330_202610", {}, "2026-11-02T21:00:00+08:00")
    assert pc.is_complete("2330", "202610")                                         # 月底後抓的


def test_prev_month_fetched_until_complete(raw_dir, monkeypatch):
    monkeypatch.setattr(pc, "today_yyyymmdd", lambda: "20261113")
    setup_day(raw_dir)
    assert keys(pc.build_mops_jobs("20261113", "20261113")) == [("2330", 2026, 10), ("2330", 2026, 11)]

    write_raw(raw_dir, "announcements", "2330_202610", {}, "2026-11-12T21:00:00+08:00")   # 月底後抓的完整檔
    write_raw(raw_dir, "announcements", "2330_202611", {}, "2026-11-12T21:00:00+08:00")   # 本月：照樣重抓
    assert keys(pc.build_mops_jobs("20261113", "20261113")) == [("2330", 2026, 11)]
    assert keys(pc.build_mops_jobs("20261113", "20261113", refetch=True)) == [("2330", 2026, 10), ("2330", 2026, 11)]


def test_last_month_gaps_filled_even_if_not_watched_today(raw_dir, monkeypatch):
    """10 月被關注過、今天沒被列的公司：10 月不完整或沒有檔都要補；完整的跳過；權證不算。"""
    monkeypatch.setattr(pc, "today_yyyymmdd", lambda: "20261113")
    setup_day(raw_dir)                                                                     # 今天只有 2330
    write_raw(raw_dir, "notice", "20261020", {"data": [["1", "2317"], ["2", "030039"]]})  # 10/20：2317、權證
    write_raw(raw_dir, "punish", "20261027", {"data": [["1", "x", "2330"]]})              # 10/27：2330 處置中
    write_raw(raw_dir, "announcements", "2330_202610", {}, "2026-11-12T21:00:00+08:00")   # 2330 10 月已完整
    # 2317 從沒抓成功過（沒有檔）也要補
    assert keys(pc.build_mops_jobs("20261113", "20261113")) == [("2317", 2026, 10), ("2330", 2026, 11)]

    write_raw(raw_dir, "announcements", "2317_202610", {}, "2026-10-20T21:00:00+08:00")   # 只查到 10/20
    assert ("2317", 2026, 10) in keys(pc.build_mops_jobs("20261113", "20261113"))
