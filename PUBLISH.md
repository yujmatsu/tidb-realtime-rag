# 公開・Zenn投稿の手順

このリポジトリは Zenn 記事「日本語RAGの『鮮度』を測る ── TiDBで踏んだ実装の落とし穴と測定方法」の
再現コード・実測データ・図一式です。記事本文は [`docs/ARTICLE.md`](./docs/ARTICLE.md)。

## Zenn 公開手順
1. 概念図2枚を生成（[`docs/NANOBANANA-PROMPTS.md`](./docs/NANOBANANA-PROMPTS.md) のプロンプト）
   → `diagram-01-timeline.png` / `diagram-02-architecture.png`。
2. Zenn の `images/realtime-rag-tidb/` に、`docs/figures/*.png`（データ図）＋ 上記概念図2枚 を配置
   （記事本文は `/images/realtime-rag-tidb/...` を参照）。
3. `docs/ARTICLE.md` の「（リポジトリURL）」を、公開した GitHub リポジトリのURLに差し替え。
4. `docs/ARTICLE.md` 本文を Zenn 記事にコピー → `published: true` → コンテストに応募。

## 含まれるもの
- `src/expagent/`：db / embed / rt / mem9（realtime-rag に必要な最小構成）
- `scripts/rt_*.py`：鮮度計測・実害・鮮度境界・HTAP集計・干渉耐性・NLデモ・mem9連携・グラフ
- `sql/schema_rt.sql` / `docs/results/`（実測の裏付け）/ `docs/figures/`（生成グラフ）
- `docs/ARTICLE.md`（記事）/ `docs/RESULTS.md`（結果まとめ）

## 秘匿情報
- コードはすべて環境変数経由（`db.py` / `embed.py` / `mem9.py`）。**ハードコードされた認証情報なし**。`.env` は `.gitignore` 済。
