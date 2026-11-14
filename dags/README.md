# dags（第 4 週）

Airflow 的 DAG 放這裡，只負責編排：依序執行各步驟的入口，取代 `scripts/run_daily.bat`。

```
extract_twse → extract_mops → transform → load_mysql → engine
```

| 任務 | 指令 |
|---|---|
| extract_twse | `python -m pipeline.extract.producer daily --source twse` |
| extract_mops | `python -m pipeline.extract.producer daily --source mops` |
| transform | `python -m pipeline.transform.stage` |
| load_mysql | `python -m pipeline.load.mysql` |
| engine | `python -m engine.run` |
