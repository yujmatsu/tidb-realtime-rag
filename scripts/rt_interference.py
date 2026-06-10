#!/usr/bin/env python3
"""干渉耐性（HTAP）実験：在庫更新(OLTP書き込み)を流し続けながら、
   ライブRAG検索(WHERE stock>0 × ベクトル, OLAP/TiFlash読み)のレイテンシ p50/p95 が
   劣化しないかを実測する。

   ※ 単一接続のwriterはネットワークRTT律速で毎秒数件しか出ない。実効負荷を本当に上げるため
      writerを「並列接続(スレッド)」にし、読み計測窓での【実効書き込みレート】を計測して併記する。
"""
from __future__ import annotations
import os, sys, time, threading, statistics, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db, rt  # noqa: E402

RES = os.path.join(os.path.dirname(__file__), "..", "docs", "results")
N_READ = 40
WORKER_SETS = [0, 4, 12]   # 並列writerスレッド数（=同時書き込み接続数）


def main():
    conn = db.connect(); cur = conn.cursor()
    prods = rt.catalog(200)
    cur.execute("TRUNCATE TABLE products_live")
    cur.executemany("INSERT INTO products_live(product_id,name,category,price,stock,description,emb) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
                      p["description"], rt.emb_literal(p["emb"])) for p in prods])
    for _ in range(30):  # TiFlash 同期待ち
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
    for nw in WORKER_SETS:
        stop = threading.Event()
        counts = [0] * max(nw, 1)   # 各writerの書き込み数（別スロット＝ロック不要）

        def writer(idx):
            wc = db.connect(); rng = random.Random(1000 + idx)
            while not stop.is_set():
                pid = rng.choice(ids); ns = rng.choice([0, 5, 12])
                try:
                    with wc.cursor() as c:
                        c.execute("UPDATE products_live SET stock=%s WHERE product_id=%s", (ns, pid))
                    counts[idx] += 1
                except Exception:
                    break
            wc.close()

        threads = [threading.Thread(target=writer, args=(i,), daemon=True) for i in range(nw)]
        for t in threads:
            t.start()
        if nw:
            time.sleep(1.0)  # 負荷を立ち上げる

        read_once()  # warmup
        before = sum(counts); t0 = time.perf_counter()
        lat = []
        for _ in range(N_READ):
            s = time.perf_counter(); read_once(); lat.append((time.perf_counter() - s) * 1000)
        window = time.perf_counter() - t0
        eff = (sum(counts) - before) / window if window > 0 else 0.0
        stop.set()
        for t in threads:
            t.join(timeout=5)

        lat.sort()
        p50 = statistics.median(lat)
        p95 = lat[min(len(lat) - 1, int(round(len(lat) * 0.95)) - 1)]
        results.append((nw, eff, p50, p95))
        print(f"writers={nw:>2} eff={eff:6.1f} updates/s : read p50={p50:6.0f}ms p95={p95:6.0f}ms (n={N_READ})")

    os.makedirs(RES, exist_ok=True)
    import csv
    with open(os.path.join(RES, "rt_interference.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["writer_threads", "effective_writes_per_s", "read_p50_ms", "read_p95_ms", "reads_n"])
        for nw, eff, p50, p95 in results:
            w.writerow([nw, f"{eff:.1f}", f"{p50:.0f}", f"{p95:.0f}", N_READ])
    print("wrote rt_interference.csv")
    conn.close(); read_conn.close()


if __name__ == "__main__":
    main()
