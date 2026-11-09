"""各來源共用的清洗工具：輸入、輸出都是 pandas Series（整欄一次處理），不碰檔案、不碰資料庫。

為什麼整欄處理：pandas 的 .str 方法與 to_numeric 在底層一次處理整欄，
比 for 迴圈或 .map(python 函式) 逐筆呼叫快得多，資料越多差越多。

日期相關的（民國轉西元等）在 crawler/utils/dates.py，這裡不重複。
"""
import pandas as pd

_CN_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}


def strip_html(s: pd.Series) -> pd.Series:
    """去掉 HTML 標籤，只留文字。

    >>> strip_html(pd.Series(["漲幅<font color='#FF0000'>﹝第十款﹞</font>。"])).tolist()
    ['漲幅﹝第十款﹞。']
    """
    return s.str.replace(r"<[^>]+>", "", regex=True).str.strip()


def to_number(s: pd.Series) -> pd.Series:
    """數字字串 → 數字；去千分位逗號；全是減號（'-----'）或空字串 → NaN。

    其他看不懂的值會直接報錯（不用 errors="coerce"），免得上游格式改了卻默默變成 NaN。

    >>> to_number(pd.Series(["1,450.00", "-----", "69.94"])).tolist()
    [1450.0, nan, 69.94]
    """
    cleaned = s.str.replace(",", "", regex=False).str.strip()
    cleaned = cleaned.mask(cleaned.str.fullmatch(r"-*"))   # '-----' 或 '' → NaN
    return pd.to_numeric(cleaned)


def cn_number(text: str) -> int:
    """中文數字（一～九十九）→ int。單一值用；整欄請先取 unique 再對照，見 notice.py。

    >>> cn_number("三"), cn_number("十"), cn_number("十三"), cn_number("二十一")
    (3, 10, 13, 21)
    """
    if "十" not in text:
        return _CN_DIGIT[text]
    tens, _, ones = text.partition("十")
    return (_CN_DIGIT[tens] if tens else 1) * 10 + (_CN_DIGIT[ones] if ones else 0)
