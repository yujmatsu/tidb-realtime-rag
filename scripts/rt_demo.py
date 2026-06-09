#!/usr/bin/env python3
"""実NLデモ: ライブ業務データAIアシスタントの Before/After 会話ログ。

同じ質問を Before(同期型=古いスナップショット参照) と After(TiDBライブ参照) の
2エージェントに投げ、Geminiが生成する回答の違い（古い嘘 vs 最新の正答）を見せる。
"""
from __future__ import annotations
import os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db, rt  # noqa: E402
from expagent.embed import get_genai_client  # noqa: E402

MODEL = os.getenv("VERTEX_GEN_MODEL", "gemini-2.5-flash-lite")
COLS = "product_id,name,category,price,stock,description,emb"
LOG = []


def log(s=""):
    print(s); LOG.append(s)


def seed(cur, table, prods):
    cur.execute(f"TRUNCATE TABLE {table}")
    cur.executemany(
        f"INSERT INTO {table}({COLS}) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
          p["description"], rt.emb_literal(p["emb"])) for p in prods])


def retrieve(cur, table, question):
    """質問に応じて文脈を取得。商品N指定→点参照 / それ以外→在庫ありハイブリッド検索。"""
    m = re.search(r"商品(\d+)", question)
    if m:
        pid = int(m.group(1))
        cur.execute(f"SELECT name, stock FROM {table} WHERE product_id=%s", (pid,))
        r = cur.fetchone()
        return f"{r[0]} の現在在庫: {r[1]} 個" if r else "該当商品なし"
    # ハイブリッド: 在庫>0でフィルタ × 意味検索
    q = rt.emb_literal("wireless earbuds")
    cur.execute(f"SELECT name, stock FROM {table} WHERE stock>0 "
                f"ORDER BY VEC_COSINE_DISTANCE(emb,%s) ASC LIMIT 3", (q,))
    rows = cur.fetchall()
    return "在庫あり候補:\n" + "\n".join(f"- {n}（在庫{s}個）" for n, s in rows)


def answer(client, question, context):
    prompt = (f"あなたはEC運用アシスタント。以下の社内データ**だけ**を根拠に、日本語で簡潔に1-2文で答えて。\n\n"
              f"# 社内データ\n{context}\n\n# 質問\n{question}")
    from google.genai import types
    r = client.models.generate_content(model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=200, temperature=0.0))
    return (r.text or "").strip()


def ask_both(cur, client, question):
    log(f"\n👤 ユーザー: {question}")
    ctx_b = retrieve(cur, "products_snapshot", question)
    ctx_a = retrieve(cur, "products_live", question)
    log(f"  ❌ Before(同期型RAG・古いスナップショット): {answer(client, question, ctx_b)}")
    log(f"     ↑参照した文脈: {ctx_b.splitlines()[0]}")
    log(f"  ✅ After(TiDBライブRAG): {answer(client, question, ctx_a)}")
    log(f"     ↑参照した文脈: {ctx_a.splitlines()[0]}")


def main():
    conn = db.connect(); conn.autocommit(True)
    cur = conn.cursor()
    prods = rt.catalog(40)
    # 商品5を在庫十分・人気のwireless系にしておく
    for p in prods:
        if p["product_id"] == 5:
            p["stock"] = 12; p["description"] = "wireless earbuds premium"
    log("## シナリオ: 初期状態（在庫あり）。Before/Afterは同じ。")
    seed(cur, "products_live", prods)
    seed(cur, "products_snapshot", prods)
    import time; time.sleep(6)
    client = get_genai_client()
    ask_both(cur, client, "商品5は在庫ありますか？")

    log("\n## ⚡ イベント発生: 商品5が完売 → 在庫0に更新（ライブのみ反映、同期はまだ）")
    cur.execute("UPDATE products_live SET stock=0 WHERE product_id=5")
    log("（products_live: 商品5=0 / products_snapshot: 商品5=12 のまま＝同期遅延窓）")
    ask_both(cur, client, "商品5は在庫ありますか？")
    ask_both(cur, client, "ワイヤレスイヤホンで、今買えるもの（在庫あり）を教えて")

    log("\n## 🔄 ここで同期が走った後（CDC/バッチが追いついた）")
    cur.execute(f"REPLACE INTO products_snapshot({COLS}) SELECT {COLS} FROM products_live")
    ask_both(cur, client, "商品5は在庫ありますか？")

    log("\n> 同期遅延窓の間、Before(同期型)は『在庫あります』と古い嘘をつく。"
        "After(TiDBライブ)は更新の瞬間から正答。これがリアルタイムRAGの価値。")
    out = os.path.join(os.path.dirname(__file__), "..", "docs", "results", "rt_demo.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# 実NLデモ: ライブ業務データAIアシスタント Before/After\n\n```\n" + "\n".join(LOG) + "\n```\n")
    print(f"\nsaved {out}")
    conn.close()


if __name__ == "__main__":
    main()
