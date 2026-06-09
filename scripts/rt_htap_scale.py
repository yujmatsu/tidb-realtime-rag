#!/usr/bin/env python3
"""HTAPスケール実験: 集計(GROUP BY)レイテンシ TiKV(行) vs TiFlash(列) を規模を上げて実測。
   分析集計はベクトル不要＝軽量行で大規模投入できる。同一クラスタ・同一ネットワークで
   ストレージエンジンだけ切り替え（hint）て公平比較。行ストアのみ(=素のPostgres相当)が
   スケールで詰まり、列ストア(HTAP)が横ばいに保つことを示す。"""
from __future__ import annotations
import csv, os, statistics, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db  # noqa: E402

RES = os.path.join(os.path.dirname(__file__), "..", "docs", "results")
CATS = ["A", "B", "C", "D", "E"]
SCALES = [50_000, 100_000, 200_000, 500_000]
ITERS = 7


def median_ms(cur, sql):
    cur.execute(sql); cur.fetchall()  # warmup
    ts = []
    for _ in range(ITERS):
        t0 = time.perf_counter(); cur.execute(sql); cur.fetchall()
        ts.append((time.perf_counter() - t0) * 1000)
    return statistics.median(ts)


def main():
    conn = db.connect(); cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS htap_bench")
    cur.execute("CREATE TABLE htap_bench(id BIGINT PRIMARY KEY AUTO_RANDOM, category VARCHAR(8), val INT)")
    cur.execute("ALTER TABLE htap_bench SET TIFLASH REPLICA 1")
    for _ in range(24):
        cur.execute("SELECT AVAILABLE FROM information_schema.tiflash_replica "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='htap_bench'")
        r = cur.fetchone()
        if r and r[0] == 1:
            break
        time.sleep(5)

    agg = ("category, COUNT(*) n, SUM(val) s FROM htap_bench GROUP BY category")
    q_tikv = f"SELECT /*+ read_from_storage(tikv[htap_bench]) */ {agg}"
    q_tiflash = f"SELECT /*+ read_from_storage(tiflash[htap_bench]) */ {agg}"

    results = []
    current = 0
    B = 5000
    for target in SCALES:
        # 追加投入
        rng_i = current
        while rng_i < target:
            batch = [(CATS[i % 5], (i * 7) % 1000) for i in range(rng_i, min(rng_i + B, target))]
            cur.executemany("INSERT INTO htap_bench(category, val) VALUES(%s,%s)", batch)
            rng_i += B
        current = target
        # TiFlash 同期待ち（列ストアが全行反映するまで）
        for _ in range(60):
            cur.execute(f"SELECT /*+ read_from_storage(tiflash[htap_bench]) */ COUNT(*) FROM htap_bench")
            if cur.fetchone()[0] == current:
                break
            time.sleep(2)
        tikv = median_ms(cur, q_tikv)
        tiflash = median_ms(cur, q_tiflash)
        results.append((target, tikv, tiflash))
        print(f"n={target:>7}: TiKV(row)={tikv:.1f}ms  TiFlash(col)={tiflash:.1f}ms  speedup={tikv/tiflash:.1f}x")

    os.makedirs(RES, exist_ok=True)
    with open(os.path.join(RES, "rt_htap_scale.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["rows", "tikv_ms", "tiflash_ms", "speedup"])
        for n, a, b in results:
            w.writerow([n, f"{a:.1f}", f"{b:.1f}", f"{a/b:.2f}"])
    print("wrote rt_htap_scale.csv")
    conn.close()


if __name__ == "__main__":
    main()
