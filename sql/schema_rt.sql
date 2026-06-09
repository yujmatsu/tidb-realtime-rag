-- realtime-RAG: ライブ業務データ(products_live) と 同期型スナップショット(products_snapshot)
-- 同一スキーマ。違いは「ライブ直」か「N更新ごとに同期されたコピー」かだけ（公平比較）。
DROP TABLE IF EXISTS products_live;
DROP TABLE IF EXISTS products_snapshot;

CREATE TABLE products_live (
    product_id  BIGINT PRIMARY KEY,
    name        VARCHAR(128),
    category    VARCHAR(32),
    price       INT,
    stock       INT          COMMENT '可変な取引状態（在庫）',
    description TEXT,
    emb         VECTOR(64),
    FULLTEXT INDEX idx_desc_live (description) WITH PARSER MULTILINGUAL
);
CREATE TABLE products_snapshot (
    product_id  BIGINT PRIMARY KEY,
    name        VARCHAR(128),
    category    VARCHAR(32),
    price       INT,
    stock       INT,
    description TEXT,
    emb         VECTOR(64),
    FULLTEXT INDEX idx_desc_snap (description) WITH PARSER MULTILINGUAL
);

ALTER TABLE products_live     SET TIFLASH REPLICA 1;
ALTER TABLE products_snapshot SET TIFLASH REPLICA 1;
ALTER TABLE products_live     ADD VECTOR INDEX vi_live ((VEC_COSINE_DISTANCE(emb))) USING HNSW;
ALTER TABLE products_snapshot ADD VECTOR INDEX vi_snap ((VEC_COSINE_DISTANCE(emb))) USING HNSW;
