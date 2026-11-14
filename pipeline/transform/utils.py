"""轉換用的共用工具：給 rules.py 用，不屬於任何一種資料。"""
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


def require_columns(df: pd.DataFrame, needed: list[str], name: str) -> pd.DataFrame:
    """只留 needed 這幾欄；少了任何一欄就報錯（上游改版，不能默默變成空值）。

    官方多加欄位、調整順序都不影響，因為是用欄名取，不是用位置。
    """
    missing = [col for col in needed if col not in df.columns]
    if missing:
        raise ValueError(f"{name}少了欄位：{missing}（回傳的欄位：{list(df.columns)}）")
    return df[needed]


def rows_to_frame(raws: list[dict], fields: list[str], name: str, extra: dict | None = None) -> pd.DataFrame:
    """把多份 raw 的 data 合成一個 DataFrame，只留用得到的欄位。

    fields：用得到的官方欄位。每份 raw 依它自己的 fields 對應欄名，再取出這幾欄。
    extra：每份 raw 額外加的欄位，{欄名: 函式(raw)}。
    """
    extra = extra or {}
    frames = []
    for raw in raws:
        body = raw["body"]
        if not body.get("data"):
            continue
        df = pd.DataFrame(body["data"], columns=body.get("fields"))   # 證交所的資料列是陣列，欄名在 fields
        df = require_columns(df, fields, name)
        for col, func in extra.items():
            df[col] = func(raw)
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=fields + list(extra))
    return pd.concat(frames, ignore_index=True)


def fetched_at(raw: dict) -> datetime.datetime:
    """raw 的抓取時間（帶時區，可直接比較先後）。"""
    return datetime.datetime.fromisoformat(raw["meta"]["fetched_at"])
