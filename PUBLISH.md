# 公開手順メモ

このリポジトリは `tidb-experiential-agent/`（探索の過程で別テーマ＝経験記憶も含む作業ディレクトリ）から、
**リアルタイムRAGの記事に必要なファイルだけを抽出したクリーン版**です。

## 含めたもの（記事と1:1）
- `src/expagent/`：db / embed / rt / __init__（realtime-rag に必要な最小構成）
- `scripts/rt_*.py`：鮮度計測・実害・鮮度境界・HTAPスケール・NLデモ・グラフ
- `sql/schema_rt.sql`
- `docs/results/`：記事の数値を裏付ける実測（rt_freshness.csv/md, rt_htap_scale.csv, rt_harm.txt, rt_demo.md）
- `docs/figures/`：実測から生成したグラフPNG
- `docs/ARTICLE.md`（記事本体）/ `docs/RESULTS.md`（結果まとめ）

## 意図的に除外したもの（記事に無関係・混乱の元）
- 放棄した別テーマ「エージェント経験記憶」の一式：`agent.py` `experience.py` `eval/` `normalize.py` `llm.py`、
  `scripts/00〜05`、`sql/schema_episodes.sql` `schema_business.sql`、`datasets/`（business_seed, nl2sql_qa, stub_answers）
- 生ログ（`*.log`）と経験記憶プロジェクトの結果（`learning_curve*`, `runs_*`, `summary_flash25/pro25`, `accumulation_*`, `pgvector_compare.md` 等）

## 秘匿情報
- コードはすべて環境変数経由（`db.py`）。**ハードコードされた認証情報なし**。`.env` は `.gitignore` 済。

## Zenn 公開手順
1. 概念図2枚を Nano Banana で生成（`docs/ARTICLE.md` 末尾のプロンプト）→ `diagram-01-timeline.png` / `diagram-02-architecture.png`。
2. Zenn の `images/realtime-rag-tidb/` に、`docs/figures/*.png`（データ図）＋ 上記概念図2枚 を配置
   （記事本文は `/images/realtime-rag-tidb/...` を参照）。
3. `docs/ARTICLE.md` の「（リポジトリURL）」を、公開したGitHubリポジトリのURLに差し替え。
4. リポジトリ名は `tidb-realtime-rag` 等を推奨（旧名 `tidb-experiential-agent` は別テーマ由来）。

## 再現
`README.md` の「実行（再現手順）」を参照。鮮度・HTAP計測は埋め込みAPI不要（hashing 64次元）。
NLデモ（`rt_demo.py`）のみ Vertex(Gemini) 認証が必要。
