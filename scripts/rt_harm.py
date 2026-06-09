#!/usr/bin/env python3
"""フック用「実害」計測:
  (A) Q-STOCK の誤答の"向き": 古いRAGが「在庫あり」と偽った件数（危険な方向）。
  (B) ハイブリッド推薦の実害: 古いRAGが「在庫あり」として推薦した商品のうち、実際は売り切れの割合。
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db, rt  # noqa: E402

COLS = "product_id,name,category,price,stock,description,emb"


def seed(cur, table, prods):
    cur.execute(f"TRUNCATE TABLE {table}")
    cur.executemany(f"INSERT INTO {table}({COLS}) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
          p["description"], rt.emb_literal(p["emb"])) for p in prods])


def main():
    conn = db.connect(); cur = conn.cursor()
    prods = rt.catalog(80)
    events = rt.event_log(prods, 100)
    questions = rt.question_log(prods, 100)
    truth = rt.truth_timeline(prods, events)
    seq = rt.interleave(events, questions, qmode="active")

    # (A) active・sync@20 を再生し、Q-STOCK誤答の向きを集計
    K = 20
    seed(cur, "products_live", prods); seed(cur, "products_snapshot", prods)
    applied = 0
    false_instock = false_outofstock = total = wrong = 0
    for kind, payload, _ in seq:
        if kind == "event":
            _, pid, ns = payload
            cur.execute("UPDATE products_live SET stock=%s WHERE product_id=%s", (ns, pid))
            applied += 1
            if applied % K == 0:
                cur.execute(f"REPLACE INTO products_snapshot({COLS}) SELECT {COLS} FROM products_live")
        else:
            _, pid = payload
            cur.execute("SELECT stock FROM products_snapshot WHERE product_id=%s", (pid,))
            snap = cur.fetchone()[0]
            true_stock = truth[applied][pid]
            total += 1
            if (snap > 0) != (true_stock > 0):
                wrong += 1
                if snap > 0 and true_stock == 0:
                    false_instock += 1   # 危険: 売り切れを「在庫あり」と偽る
                else:
                    false_outofstock += 1
    print(f"(A) Q-STOCK active sync@{K}: 総質問{total} / 誤答{wrong} "
          f"/ うち『売り切れを在庫ありと偽る』{false_instock} / 逆{false_outofstock}")

    # (B) ハイブリッド推薦の実害: 売り切れ直後、stale が在庫ありとして推す上位kに含まれる実売り切れ数
    seed(cur, "products_live", prods); seed(cur, "products_snapshot", prods)
    # 人気帯(wireless)を作って売り切れさせる
    cur.execute("UPDATE products_live SET description='wireless earbuds compact', stock=10 "
                "WHERE product_id IN (5,7,9,11,13)")
    cur.execute(f"REPLACE INTO products_snapshot({COLS}) SELECT {COLS} FROM products_live")  # 同期(ここまで最新)
    cur.execute("UPDATE products_live SET stock=0 WHERE product_id IN (5,7,9,11,13)")  # 完売(snapshotは古い)
    import time; time.sleep(3)
    q = rt.emb_literal("wireless earbuds compact")
    recommended = sold_out_recommended = 0
    for tbl, tag in [("products_snapshot", "stale"), ("products_live", "live")]:
        cur.execute(f"SELECT product_id FROM {tbl} WHERE stock>0 "
                    f"ORDER BY VEC_COSINE_DISTANCE(emb,%s) ASC LIMIT 5", (q,))
        rec = [r[0] for r in cur.fetchall()]
        # 実際の在庫(live)で売り切れている推薦数
        bad = 0
        for pid in rec:
            cur.execute("SELECT stock FROM products_live WHERE product_id=%s", (pid,))
            if cur.fetchone()[0] == 0:
                bad += 1
        print(f"(B) {tag}: 推薦{rec} / 実際は売り切れ {bad}/{len(rec)}")
        if tag == "stale":
            recommended, sold_out_recommended = len(rec), bad
    print(f"\n>> フック用: active利用でstale-RAGは在庫質問の {wrong}/{total} を誤答、"
          f"うち {false_instock} 件は『売り切れを在庫あり』と偽答。"
          f"在庫あり推薦{recommended}件中{sold_out_recommended}件が実際は売り切れ。")
    conn.close()


if __name__ == "__main__":
    main()
