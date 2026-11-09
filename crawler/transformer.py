"""資料整理層（transformer）：只負責「把 raw 整理成要存的樣子」（raw → stage）。

這個檔案的邊界：
    知道 API 回傳哪些欄位、stage 表要哪些欄位、型別要怎麼轉。
    不知道資料是怎麼抓來的，也不知道整理完會被存到哪裡。

改欄位、改型別、改去重規則時，只有這個檔案要改。
所有函式都是純函式：不碰檔案、不碰資料庫，回傳新的 DataFrame，不修改傳進來的資料。

stage 層只做清洗，不做業務判斷（例如「第 9 款不累計」「要不要排除權證」是規則引擎的事）。

效能做法：
  1. 所有日子的 raw 先合成一個 DataFrame，整批轉換一次（不是一天轉一次）
  2. 每個欄位都用整欄運算（.str、to_numeric、extractall），不用 for 迴圈
  3. 中文款次只有十幾種寫法：先取 unique 換算，再整欄對照
"""
import pandas as pd

from crawler.date_utils import roc_to_dates

# ==================== 共用的清洗工具（整欄處理） ====================
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
    """中文數字（一～九十九）→ int。單一值用；整欄請先取 unique 再對照。

    >>> cn_number("三"), cn_number("十"), cn_number("十三"), cn_number("二十一")
    (3, 10, 13, 21)
    """
    if "十" not in text:
        return _CN_DIGIT[text]
    tens, _, ones = text.partition("十")
    return (_CN_DIGIT[tens] if tens else 1) * 10 + (_CN_DIGIT[ones] if ones else 0)


# ==================== 注意股 ====================
# stage_notice         一檔股票一天一列   唯一鍵：trade_date + stock_id
# stage_notice_clause  一檔股票一天可能觸發好幾款   唯一鍵：trade_date + stock_id + clause
#
# 刻意丟掉的欄位（11/09 確認不可靠）：
#   編號      全部是 1
#   累計次數  不是個股累計，而是該次查詢回傳的筆數
#
# 觀察到但不使用的線索：第 9～14 款在原文裡被 <font color='#FF0000'> 包起來（紅字），
# 剛好就是「不累計」的那幾款。但顏色是排版，不是資料，規則引擎一律以款次數字判斷。

NOTICE_FIELDS = ["編號", "證券代號", "證券名稱", "累計次數", "注意交易資訊", "日期", "收盤價", "本益比"]
NOTICE_COLUMNS = ["trade_date", "stock_id", "stock_name", "info", "close", "pe"]
NOTICE_CLAUSE_COLUMNS = ["trade_date", "stock_id", "clause"]


def notice_to_frame(envelopes: list[dict]) -> pd.DataFrame:
    """把多份注意股 raw（信封）合成一個 DataFrame，欄位照官方原名。

    先把所有資料列收進一個 list，最後只建一次 DataFrame，
    比每天各建一個再 concat 快（concat 每次都要複製資料）。
    上游改了欄位就直接報錯，不要默默解析出錯的資料。
    """
    rows = []
    for env in envelopes:
        body = env["body"]
        data = body.get("data") or []
        if not data:
            continue                       # 沒開市：stat 還是 OK，但 data 是空的
        if body.get("fields") != NOTICE_FIELDS:
            raise ValueError(f"注意股欄位和預期不同，上游可能改版了：{body.get('fields')}")
        rows.extend(data)
    return pd.DataFrame(rows, columns=NOTICE_FIELDS)


def transform_notice(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """注意股官方原始欄位 → (stage_notice, stage_notice_clause)。"""
    if df.empty:
        return pd.DataFrame(columns=NOTICE_COLUMNS), pd.DataFrame(columns=NOTICE_CLAUSE_COLUMNS)

    notices = pd.DataFrame({
        "trade_date": roc_to_dates(df["日期"]),
        "stock_id": df["證券代號"].str.strip(),
        "stock_name": df["證券名稱"].str.strip(),
        "info": strip_html(df["注意交易資訊"]),
        "close": to_number(df["收盤價"]),
        "pe": to_number(df["本益比"]),
    })

    # 款次：extractall 一次抓出每一列所有的「第X款」，結果一個符合一列（index 第 0 層 = 原本的列號）
    matches = notices["info"].str.extractall(r"第(?P<cn>[一二三四五六七八九十]+)款")["cn"]

    missing = notices.index.difference(matches.index.get_level_values(0))
    if len(missing):
        bad = notices.loc[missing, ["trade_date", "stock_id", "info"]].head(3).to_dict("records")
        raise ValueError(f"有 {len(missing)} 列找不到款次，格式可能改了：{bad}")

    lookup = {cn: cn_number(cn) for cn in matches.unique()}   # 十幾種寫法，各換算一次
    clauses = (
        notices.loc[matches.index.get_level_values(0), ["trade_date", "stock_id"]]
        .assign(clause=matches.map(lookup).to_numpy())
        .drop_duplicates()                 # 同一列提到同一款兩次只算一次
        .sort_values(NOTICE_CLAUSE_COLUMNS)
        .reset_index(drop=True)
    )
    return notices[NOTICE_COLUMNS], clauses[NOTICE_CLAUSE_COLUMNS]
