"""T（transform_stage）→ L（load_stage_to_mysql）之間的 parquet＋manifest：不連資料庫。執行：uv run pytest"""
import datetime

import pandas as pd
import pytest

from crawler import load_stage_to_mysql as load
from crawler import transform_stage as transform


@pytest.fixture
def stage_dir(tmp_path, monkeypatch):
    for module in (transform, load):
        monkeypatch.setattr(module, "STAGE_DIR", tmp_path)
        monkeypatch.setattr(module, "MANIFEST_PATH", tmp_path / "manifest.json")
    return tmp_path


def test_l_reads_what_t_wrote(stage_dir):
    d = datetime.date(2026, 11, 13)
    tables = {
        "stage_notice": pd.DataFrame({"trade_date": [d], "stock_id": ["033569"], "close_price": [24.8]}),
        "stage_company": pd.DataFrame({"company_id": ["2330"]}),
    }
    transform.write_outputs(tables)
    loaded = load.load_tables()
    assert list(loaded) == ["stage_notice", "stage_company"]
    row = loaded["stage_notice"].iloc[0]
    assert (row["trade_date"], row["stock_id"], row["close_price"]) == (d, "033569", 24.8)   # 型態、開頭的 0 都保留


def test_l_only_reads_tables_in_manifest(stage_dir):
    transform.write_outputs({"stage_company": pd.DataFrame({"company_id": ["2330"]})})
    pd.DataFrame({"x": [1]}).to_parquet(stage_dir / "stage_old.parquet")   # 不在 manifest：不讀
    assert list(load.load_tables()) == ["stage_company"]


def test_l_without_manifest_stops(stage_dir):
    with pytest.raises(SystemExit):
        load.load_tables()
