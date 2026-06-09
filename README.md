# 日本語リアルタイムRAG on TiDB ── 実装と「鮮度」の測定

業務データ（在庫・ステータス等）に答えるRAGで、**データが更新された直後に古い答えを返す（stale RAG）問題**を
定量的に計測し、データと埋め込みを**単一エンジン（TiDB）**に置いて鮮度ゼロ遅延にする検証コードです。

> 解説記事：[`doc/ARTICLE.md`](./doc/ARTICLE.md)（Zenn投稿コンテスト「TiDBで作るAI時代のデータ基盤」応募作）
> 実測結果まとめ：[`doc/RESULTS.md`](./doc/RESULTS.md)

## この検証で分かること（3つ）

1. **RAGの鮮度を"測る"方法論**：「鮮度誤答率」＝ 同一質問を同時刻に「同期型」「ライブ」へ投げ、
   ライブ正答 ∧ 同期型誤答 の割合。質問分布(uniform/active) × 同期間隔の関数として計測。
   - 実測：**上限ケース(active)で同期型RAGは35〜43%誤答、ライブ(TiDB)は0%**。
2. **日本語全文検索の限界と設計レシピ**：`PARSER MULTILINGUAL` は形態素解析ではなく、日本語は漏れ・誤ヒット。
   → 日本語自然文はベクトル、英数字(SKU/型番)は全文、に役割分担。
3. **TiDBの鮮度境界**：点参照(TiKV行)は即時(read-your-writes)、分析/大規模ベクトル(TiFlash列)は ≈142ms の同期遅延。

> 正直な前提：鮮度の解消は「単一エンジン化」の効果で **TiDB固有ではありません**（Postgres+pgvector でも可）。
> また HTAP の性能優位は本検証規模（〜500k行・無料クラスタ）では確認できませんでした（記事§5に正直に記載）。

## セットアップ

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[vertex,eval]"        # pymysql + google-genai(Vertex) + matplotlib
cp .env.example .env
gcloud auth application-default login  # Vertex(Gemini)埋め込み/生成を使う場合（ADC）
```

### 使い捨てクラスタ（TiDB Cloud Zero・サインアップ不要）

```bash
curl -s -X POST https://zero.tidbapi.com/v1beta1/instances \
  -H "Content-Type: application/json" -d '{"tag":"realtime-rag"}'
# → host/port/user/password が即返る。.env に転記し、DB(例: rtdb)を作成。
```

`.env` 例：
```dotenv
TIDB_HOST=gatewayXX.us-west-2.prod.aws.tidbcloud.com
TIDB_PORT=4000
TIDB_USER=xxxx.root
TIDB_PASSWORD=xxxx
TIDB_DATABASE=rtdb
EMBED_PROVIDER=hashing          # 鮮度計測は意味埋め込み不要のため hashing(64次元) で十分・無料
GCP_PROJECT=your-project        # rt_demo.py(Gemini回答生成)を使う場合のみ
GCP_LOCATION=us-central1
VERTEX_GEN_MODEL=gemini-2.5-flash-lite
```

## 実行（再現手順）

```bash
# 鮮度誤答率（uniform/active × 同期間隔）→ docs/results/rt_freshness.{csv,md}
python scripts/rt_freshness.py --products 80 --events 100 --questions 100 --syncs 1,5,20,60

# 実害の内訳（誤答の向き：売り切れを在庫ありと偽答した数）
python scripts/rt_harm.py

# 鮮度境界（read-your-writes 即時 / TiFlash 同期遅延）＋ キラークエリ
python scripts/rt_primary.py

# HTAPスケール（TiKV行 vs TiFlash列の集計レイテンシ、50k-500k）
python scripts/rt_htap_scale.py

# 実NLデモ（Gemini回答で Before/After の会話ログ。要 Vertex 認証）
python scripts/rt_demo.py

# 実測CSVから記事用グラフ(PNG)を生成
python scripts/rt_charts.py
```

## 構成

```
sql/schema_rt.sql          products_live / products_snapshot（VECTOR+FULLTEXT+TiFlash）
src/expagent/
  db.py                    TiDB接続（env、TLS、ping再接続）
  embed.py                 埋め込み（hashing / vertex / openai）＋ google-genai クライアント
  rt.py                    決定的な商品カタログ・更新イベント・質問・truth_timeline
scripts/rt_*.py            鮮度計測 / 実害 / 鮮度境界 / HTAPスケール / NLデモ / グラフ
docs/results/              実測CSV・md（記事の数値の裏付け）
docs/figures/              生成グラフ(PNG)
doc/ARTICLE.md, RESULTS.md 記事・結果まとめ
```

## 注意（実機検証で判明した運用知見）
- ベクトル/全文インデックスは **TiFlash レプリカ前提**。INSERT直後は列ストア反映に遅延あり。
- 長時間実行ではDB接続のアイドル切断が起きる → ping再接続＋リトライ実装済（`db.py`）。
- 全文一致は `fts_match_word('語', カラム)`（小文字・WHERE内で単独使用）。日本語は不安定（→英数字に限定）。
- 数値は無料クラスタ・小規模デモの「傾向」。絶対値は環境依存（記事に正直に明記）。

## ライセンス
MIT
