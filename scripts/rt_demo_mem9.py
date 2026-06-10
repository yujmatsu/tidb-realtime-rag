#!/usr/bin/env python3
"""mem9 連携デモ（任意・コンテスト加点用）:
   ユーザーの関心・過去の問い合わせ文脈を mem9 に記憶し、ライブ在庫(TiDB)の回答に反映して
   パーソナル化する最小例。

   ⚠️ 実行には MEM9_API_KEY（mem9.ai ホスト版 or セルフホスト）が必要。
      未設定の場合は mem9 を無効化し、「mem9なしの回答」のみ出して構造を示す（著者環境では未実行）。
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db, rt  # noqa: E402
from expagent.embed import get_genai_client  # noqa: E402
from expagent.mem9 import Mem9  # noqa: E402

MODEL = os.getenv("VERTEX_GEN_MODEL", "gemini-2.5-flash-lite")


def answer(client, question, stock_ctx, user_ctx):
    from google.genai import types
    prompt = (f"あなたはEC運用アシスタント。社内データとユーザー文脈を踏まえ日本語で簡潔に答えて。\n\n"
              f"# 在庫(最新)\n{stock_ctx}\n\n# ユーザー文脈(mem9の記憶)\n{user_ctx or '（なし）'}\n\n# 質問\n{question}")
    r = client.models.generate_content(model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=200, temperature=0.0))
    return (r.text or "").strip()


def main():
    conn = db.connect(); conn.autocommit(True); cur = conn.cursor()
    prods = rt.catalog(20)
    cur.execute("TRUNCATE TABLE products_live")
    cur.executemany("INSERT INTO products_live(product_id,name,category,price,stock,description,emb) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
                      p["description"], rt.emb_literal(p["emb"])) for p in prods])

    mem = Mem9()
    print(f"mem9 enabled: {mem.enabled}  (MEM9_API_KEY {'設定済' if mem.enabled else '未設定→無効化'})")

    # 過去セッションのユーザー文脈を記憶（mem9）
    if mem.enabled:
        mem.store("ユーザーは渋谷区在住で、防災と子育ての情報に関心がある。"
                  "以前ワイヤレスイヤホンの在庫を問い合わせた。", labels=["user-profile"])

    question = "今おすすめの在庫あり商品を1つ教えて"
    # ライブ在庫(最新)を取得
    cur.execute("SELECT name, stock, category FROM products_live WHERE stock>0 ORDER BY product_id LIMIT 5")
    stock_ctx = "\n".join(f"- {n}（在庫{s}・{c}）" for n, s, c in cur.fetchall())
    # mem9 からユーザー文脈を想起
    recalled = mem.search(question) if mem.enabled else []
    user_ctx = "\n".join(str(m.get("content", m)) for m in recalled) if recalled else None

    client = get_genai_client()
    print("\n👤", question)
    print("【mem9なし（在庫のみ）】", answer(client, question, stock_ctx, None))
    if mem.enabled:
        print("【mem9あり（在庫＋ユーザー文脈）】", answer(client, question, stock_ctx, user_ctx))
    else:
        print("（MEM9_API_KEY を設定すると、ユーザー文脈を反映したパーソナル回答が出ます）")
    conn.close()


if __name__ == "__main__":
    main()
