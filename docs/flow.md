# 執行流程

```
E 抓資料  extract_raw.py           API ──→ data/raw/<來源>/<key>.json
T 轉換    transform_stage.py       raw ──→ data/stage/<表名>.parquet ＋ manifest.json
L 載入    load_stage_to_mysql.py   parquet ──→ MySQL stage_* 表
```

- T 只讀 raw、不連網路也不連資料庫；整理規則改了只要重跑 T、L。
- 每一步都能單獨重跑，成功或失敗看結束代碼，之後可以直接對應成 Airflow 的任務。
- 每日排程 `scripts/run_daily.bat`（週一～週五 21:00）依序執行 E（`daily`）→ T → L，輸出寫進 `data/daily.log`。

## E 抓資料

先抓證交所（間隔 1 秒），再依當天的注意股、處置股查重大訊息（間隔 0.6 秒）。

| 資料 | API | 查詢參數 | 一份涵蓋 | 檔名 |
|---|---|---|---|---|
| 開休市日期 | `holidaySchedule/holidaySchedule` | `queryYear=115`（民國年） | 一年 | `2026.json` |
| 每日市場成交 | `afterTrading/FMTQIK` | `date=20261101`（回傳整個月） | 一個月 | `202611.json` |
| 注意股 | `announcement/notice` | `startDate`＝`endDate`＝當天 | 一天 | `20261113.json` |
| 處置股 | `announcement/punish` | `startDate`＝當天，`endDate`＝當天＋14 天 | 一天 | `20261113.json` |
| 上市公司清單 | OpenAPI `opendata/t187ap03_L` | 無 | 當下快照 | 抓取日期 |
| 注意累計名單 | `announcement/notetrans` | 無（只有最新一份，只在抓今天時執行） | 一天 | 標題上的資料日期 |
| 重大訊息 | 觀測站 `t05st01`（POST） | `companyId`、`year`（民國年）、`month`、`firstDay`、`lastDay` | 一家公司一個月 | `1303_202611.json` |

- 處置股多帶 14 天：API 篩的是處置期間，今天公布的處置下一個交易日才開始，連假時可能隔 10 天左右。
- 重大訊息：股票被列注意或處置時，查這家公司這個月和上個月的公告（股價異常的起因可能是上個月底的消息）。
  - 這個月：每天都抓，因為每天可能有新公告。
  - 上個月：已經過完，抓到完整的一次就不再抓。
  - 例：11/13 台積電被列注意 → 抓 11 月；10 月還沒有完整的才抓。
  - 上個月被列過、這個月沒再被列的，上個月也會補完整一次。`--refetch` 則全部重抓。
- 開休市日期：過去的年份有檔就不再抓。
- 單一任務失敗不中斷，最後列出失敗清單。
- raw 檔 = `meta`（抓取紀錄）+ `body`（API 原始回應）；同 key 直接覆蓋，失敗另存 `<key>.error.json`。

## T 轉換

讀全部 raw，用 `stage_data_transform.py` 整理成各表，每張表存成一個 parquet（完整內容），最後寫 `manifest.json` 代表寫完了。加 `--csv` 另外輸出 CSV，方便用 Excel 檢查。

## L 載入

照 `manifest.json` 讀 parquet，在同一個交易裡每張表「清空 → 寫入」：重跑不會重複，失敗就整批不變。轉換規則改了，重跑 T、L 就會套用到所有日期。

`db/init/*.sql` 的欄位改了，L 要加 `--recreate`（先刪表再重建）。

## 常用指令

在專案根目錄執行：

```
uv run python -m crawler.extract_raw                               # 抓今天（daily ＝ 只有今天的 init）
uv run python -m crawler.extract_raw init --start 20261001         # 回補到今天（可加 --end、--refetch）
uv run python -m crawler.transform_stage                           # T：raw → parquet
uv run python -m crawler.load_stage_to_mysql                       # L：parquet → MySQL（欄位改了加 --recreate）
uv run pytest                                                      # 跑測試
```

漏跑：跑 `init --start <漏跑那天>`。注意累計名單只有最新一份，下一個交易日收盤前要補。

## 排程設定

用 Windows 工作排程器（`Win+R` → `taskschd.msc`），工作名稱 `G2-attention_stock_tracker-daily`。之後改用 Airflow 時取代。

- 觸發：每週一～週五 21:00
- 動作：`conhost.exe --headless` 執行 `scripts\run_daily.bat`（背景執行，避免視窗被關掉而中斷）
- 錯過時：電腦開機後盡快執行
- 限制：只在使用者登入時執行；電腦關機或睡眠時不會跑

在專案根目錄用 PowerShell 建立（重灌或換電腦時用）：

```powershell
$action   = New-ScheduledTaskAction -Execute conhost.exe -Argument "--headless cmd.exe /c `"$(Resolve-Path scripts\run_daily.bat)`""
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 21:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName G2-attention_stock_tracker-daily -Action $action -Trigger $trigger -Settings $settings
```

```powershell
Start-ScheduledTask G2-attention_stock_tracker-daily      # 立刻手動執行一次
Get-ScheduledTaskInfo G2-attention_stock_tracker-daily    # 上次執行時間、結果（0 = 成功）、下次執行時間
```
