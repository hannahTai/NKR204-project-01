"""轉換用的共用工具：給 stage_data_transform 用，不屬於任何一種資料。"""
import datetime

import pandas as pd

CHINESE_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def strip_html(s: pd.Series) -> pd.Series:
    """去掉 HTML 標籤。"""
    return s.str.replace(r"<[^>]+>", "", regex=True).str.strip()


def to_number(s: pd.Series) -> pd.Series:
    """'1,450.00' → 1450.0；'-----' 或空字串 → NaN；其他看不懂的值直接報錯。"""
    s = s.str.replace(",", "").str.strip()
    s = s.mask(s.str.fullmatch(r"-*"))
    return pd.to_numeric(s)


def chinese_number(text: str) -> int:
    """一～九十九 → int。

    >>> chinese_number("十"), chinese_number("十三"), chinese_number("二十五")
    (10, 13, 25)
    """
    if "十" not in text:
        return CHINESE_DIGITS[text]
    tens, _, ones = text.partition("十")
    return CHINESE_DIGITS.get(tens, 1) * 10 + CHINESE_DIGITS.get(ones, 0)


def rows_to_frame(raws: list[dict], fields: list[str], name: str, extra: dict | None = None) -> pd.DataFrame:
    """把多份 raw 的 data 合成一個 DataFrame。

    fields：預期的官方欄位，不一致就報錯（上游改版）。
    extra：每份 raw 額外加的欄位，{欄名: 函式(raw)}。
    """
    extra = extra or {}
    rows = []
    for raw in raws:
        body = raw["body"]
        if not body.get("data"):
            continue
        if body.get("fields") != fields:
            raise ValueError(f"{name}欄位改變：{body.get('fields')}")
        added = [func(raw) for func in extra.values()]
        rows += [row + added for row in body["data"]]
    return pd.DataFrame(rows, columns=fields + list(extra))


def fetched_at(raw: dict) -> datetime.datetime:
    """raw 的抓取時間（帶時區，可直接比較先後）。"""
    return datetime.datetime.fromisoformat(raw["meta"]["fetched_at"])
