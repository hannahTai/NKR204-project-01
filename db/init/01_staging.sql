-- staging 層：raw 解析後的乾淨資料，一列 = 官方公告的一個事實，不做業務判斷
-- 由 crawler.storage.db.init_db() 執行；之後搬到 Docker 時，也可以掛到 /docker-entrypoint-initdb.d/

CREATE TABLE IF NOT EXISTS stg_notice (
    trade_date  DATE           NOT NULL COMMENT '交易日',
    stock_id    VARCHAR(10)    NOT NULL COMMENT '證券代號（含權證、ETF、DR）',
    stock_name  VARCHAR(50)    NOT NULL COMMENT '證券名稱',
    info        TEXT           NOT NULL COMMENT '注意交易資訊全文（已去 HTML）',
    close       DECIMAL(12, 4)          COMMENT '收盤價',
    pe          DECIMAL(12, 4)          COMMENT '本益比；無本益比為 NULL',
    loaded_at   TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '寫入時間',
    PRIMARY KEY (trade_date, stock_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='注意股（每日）';

CREATE TABLE IF NOT EXISTS stg_notice_clause (
    trade_date  DATE           NOT NULL,
    stock_id    VARCHAR(10)    NOT NULL,
    clause      TINYINT        NOT NULL COMMENT '款次 1～14',
    loaded_at   TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, stock_id, clause)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='注意股觸發的款次';
