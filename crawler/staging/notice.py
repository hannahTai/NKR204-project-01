"""注意股 raw → staging（pandas 版）。

產出兩張表：

stg_notice         一檔股票一天一列   唯一鍵：trade_date + stock_id
  trade_date   交易日（date）
  stock_id     證券代號（含權證、ETF、DR；要不要排除是規則引擎的事）
  stock_name   證券名稱
  info         注意交易資訊全文（已去掉 HTML 標籤）
  close        收盤價
  pe           本益比（'-----' → NaN，寫進資料庫是 NULL）

stg_notice_clause  一檔股票一天可能觸發好幾款   唯一鍵：trade_date + stock_id + clause
  trade_date, stock_id
  clause       款次（int，1～14）

刻意丟掉的欄位（11/09 確認不可靠）：
  編號      全部是 1
  累計次數  不是個股累計，而是該次查詢回傳的筆數

觀察到但不使用的線索：第 9～14 款在原文裡被 <font color='#FF0000'> 包起來（紅字），
剛好就是「不累計」的那幾款。但顏色是排版，不是資料，規則引擎一律以款次數字判斷。

效能做法：
  1. 所有日子的 raw 先合成一個 DataFrame，整批轉換一次（不是一天轉一次）
  2. 每個欄位都用整欄運算（.str、to_numeric、extractall），不用 for 迴圈
  3. 中文款次只有十幾種寫法：先取 unique 換算，再整欄對照
"""
import pandas as pd

from crawler.staging.clean import cn_number, strip_html, to_number
from crawler.utils.dates import roc_to_dates

EXPECTED_FIELDS = ["編號", "證券代號", "證券名稱", "累計次數", "注意交易資訊", "日期", "收盤價", "本益比"]
NOTICE_COLUMNS = ["trade_date", "stock_id", "stock_name", "info", "close", "pe"]
CLAUSE_COLUMNS = ["trade_date", "stock_id", "clause"]


def to_frame(envelopes: list[dict]) -> pd.DataFrame:
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
        if body.get("fields") != EXPECTED_FIELDS:
            raise ValueError(f"注意股欄位和預期不同，上游可能改版了：{body.get('fields')}")
        rows.extend(data)
    return pd.DataFrame(rows, columns=EXPECTED_FIELDS)


def transform(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """官方原始欄位 → (stg_notice, stg_notice_clause)，回傳新的 DataFrame，不修改傳進來的 df。"""
    if df.empty:
        return pd.DataFrame(columns=NOTICE_COLUMNS), pd.DataFrame(columns=CLAUSE_COLUMNS)

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
        .sort_values(CLAUSE_COLUMNS)
        .reset_index(drop=True)
    )
    return notices[NOTICE_COLUMNS], clauses[CLAUSE_COLUMNS]
