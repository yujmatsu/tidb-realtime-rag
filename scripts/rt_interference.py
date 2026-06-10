#!/usr/bin/env python3
"""干渉耐性（HTAP）実験：在庫更新(OLTP書き込み)を流し続けながら、
   ライブRAG検索(WHERE stock>0 × ベクトル, OLAP/TiFlash読み)のレイテンシ p50/p95 が
   劣化しないかを実測する。本記事の主題「更新が流れ続ける中で常に最新を返す」と直結。

   別スレッドのwriterが在庫を更新し続け、メインで検索を連打して計測。
   write_rate = 0(無負荷)/5/20 更新/秒 で比較。
"""
from __future__ import annotations
import os, sys, time, threading, statistics, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db, rt  # noqa: E402

RES = os.path.join(os.path.dirname(__file__), "..", "docs", "results")
N_READ = 40
RATES = [0, 5, 20]


def main():
    conn = db.connect(); cur = conn.cursor()
    prods = rt.catalog(200)
    cur.execute("TRUNCATE TABLE products_live")
    cur.executemany("INSERT INTO products_live(product_id,name,category,price,stock,description,emb) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
                      p["description"], rt.emb_literal(p["emb"])) for p in prods])
    # TiFlash 同期待ち（列ストア＝ベクトル検索の経路）
    for _ in range(30):
        cur.execute("SELECT /*+ read_from_storage(tiflash[products_live]) */ COUNT(*) FROM products_live")
        if cur.fetchone()[0] == len(prods):
            break
        time.sleep(2)

    q = rt.emb_literal("wireless earbuds compact")
    ids = [p["product_id"] for p in prods]
    read_conn = db.connect(); rcur = read_conn.cursor()

    def read_once():
        rcur.execute("SELECT product_id FROM products_live WHERE stock>0 "
                     "ORDER BY VEC_COSINE_DISTANCE(emb,%s) ASC LIMIT 5", (q,))
        rcur.fetchall()

    results = []
    for rate in RATES:
        stop = threading.Event(); cnt = [0]

        def writer():
            wc = db.connect(); rng = random.Random(rate or 1)
            interval = (1.0 / rate) if rate > 0 else 0
            while not stop.is_set():
                pid = rng.choice(ids); ns = rng.choice([0, 5, 12])
                with wc.cursor() as c:
                    c.execute("UPDATE products_live SET stock=%s WHERE product_id=%s", (ns, pid))
                cnt[0] += 1
                if interval:
                    time.sleep(interval)
            wc.close()

        t = None
        if rate > 0:
            t = threading.Thread(target=writer, daemon=True); t.start()
            time.sleep(1)  # 負荷を立ち上げてから計測

        read_once()  # warmup
        lat = []
        for _ in range(N_READ):
            t0 = time.perf_counter(); read_once(); lat.append((time.perf_counter() - t0) * 1000)
        if t:
            stop.set(); t.join(timeout=5)
        lat.sort()
        p50 = statistics.median(lat)
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
        results.append((rate, p50, p95, cnt[0]))
        print(f"write_rate={rate:>2}/s : read p50={p50:6.0f}ms  p95={p95:6.0f}ms  (writes done={cnt[0]})")

    os.makedirs(RES, exist_ok=True)
    import csv
    with open(os.path.join(RES, "rt_interference.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["write_rate_per_s", "read_p50_ms", "read_p95_ms", "writes_done"])
        for r, p50, p95, n in results:
            w.writerow([r, f"{p50:.0f}", f"{p95:.0f}", n])
    print("wrote rt_interference.csv")
    conn.close(); read_conn.close()


if __name__ == "__main__":
    main()
