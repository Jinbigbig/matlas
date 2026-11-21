-- matlas 实时数据初始化脚本；PostgreSQL 容器首次启动时自动执行。
CREATE TABLE IF NOT EXISTS live_data (
    key         TEXT PRIMARY KEY,
    payload     JSONB NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS live_data_updated_idx ON live_data (updated_at);
