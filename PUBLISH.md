# 公開・Zenn投稿の手順

このリポジトリは Zenn 記事「RAGの『鮮度』を測る ── TiDBで踏んだ実装の落とし穴（日本語全文・鮮度境界）と測定方法」の
再現コード・実測データ・図一式です。記事本文は [`docs/ARTICLE.md`](./docs/ARTICLE.md)。

> 注：`docs/ARTICLE.md` は GitHub 表示用に画像を相対パス `figures/...` で参照しています。
> Zenn 公開時は画像パスを `/images/<記事slug>/...` に置き換えてください（下記手順）。

## Zenn 公開手順
1. 概念図4枚を生成（[`docs/NANOBANANA-PROMPTS.md`](./docs/NANOBANANA-PROMPTS.md) のプロンプト）
   → `diagram-01-timeline.png` / `diagram-02-experiment-flow.png` / `diagram-03-architecture.png` / `diagram-04-htap-stores.png`。
2. Zenn の `images/<記事slug>/`（例: `images/20260611_tidb_realtime_rag/`）に、`docs/figures/*.png`（データ図5枚・日本語）＋ 上記概念図4枚 を配置。
   記事本文の画像パスは `/images/<記事slug>/...` を参照。
3. `docs/ARTICLE.md` の冒頭 `title:` と本文（画像パス）を Zenn 記事にコピー → リポジトリURLを確認 → `published: true` → コンテストに応募。

## 含まれるもの
- `src/expagent/`：db / embed / rt / mem9（realtime-rag に必要な最小構成）
- `scripts/rt_*.py`：鮮度計測・実害・鮮度境界・HTAP集計・干渉耐性・NLデモ・mem9連携・グラフ
- `sql/schema_rt.sql` / `docs/results/`（実測の裏付け）/ `docs/figures/`（生成グラフ）
- `docs/ARTICLE.md`（記事）/ `docs/RESULTS.md`（結果まとめ）

## 秘匿情報
- コードはすべて環境変数経由（`db.py` / `embed.py` / `mem9.py`）。**ハードコードされた認証情報なし**。`.env` は `.gitignore` 済。
