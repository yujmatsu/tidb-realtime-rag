#!/usr/bin/env python3
"""一次情報計測（"ここでしか読めない数字"）:
  (1) read-your-writes 遅延: 更新→ライブ(TiKV)クエリが反映するまで
  (2) TiFlash 列ストア同期遅延: 更新→TiFlash(列)が反映するまで（HTAPの鮮度境界）
  (3) キラークエリ: 現在在庫>0(最新) × ベクトル意味検索 × カテゴリ集計 を1クエリで
"""
from __future__ import annotations
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from expagent import db, rt  # noqa: E402


def main():
    conn = db.connect()
    cur = conn.cursor()
    # 小規模に products_live を既知状態へ
    prods = rt.catalog(60)
    cur.execute("TRUNCATE TABLE products_live")
    cur.executemany(
        "INSERT INTO products_live(product_id,name,category,price,stock,description,emb) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s)",
        [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
          p["description"], rt.emb_literal(p["emb"])) for p in prods])
    time.sleep(8)  # TiFlash 初期同期

    print("=== (1) read-your-writes 遅延 (TiKV行ストア) ===")
    lat = []
    for i, newv in enumerate([0, 7, 0, 12, 3]):
        pid = 1 + i
        t0 = time.perf_counter()
        cur.execute("UPDATE products_live SET stock=%s WHERE product_id=%s", (newv, pid))
        cur.execute("SELECT stock FROM products_live WHERE product_id=%s", (pid,))
        got = cur.fetchone()[0]
        dt = (time.perf_counter() - t0) * 1000
        lat.append(dt)
        print(f"  update→read pid={pid}: got={got} expect={newv} reflected={got==newv} {dt:.1f}ms")
    print(f"  read-your-writes: 即時反映, update+read往復 中央値 ~{sorted(lat)[len(lat)//2]:.0f}ms")

    print("\n=== (2) TiFlash 列ストア同期遅延 ===")
    syncs = []
    for i, newv in enumerate([99, 88, 77]):
        pid = 10 + i
        cur.execute("UPDATE products_live SET stock=%s WHERE product_id=%s", (newv, pid))
        t0 = time.perf_counter()
        reflected_ms = None
        for _ in range(200):  # 最大~20s ポーリング
            cur.execute("SELECT /*+ read_from_storage(tiflash[products_live]) */ stock "
                        "FROM products_live WHERE product_id=%s", (pid,))
            if cur.fetchone()[0] == newv:
                reflected_ms = (time.perf_counter() - t0) * 1000
                break
            time.sleep(0.1)
        syncs.append(reflected_ms)
        print(f"  pid={pid}: TiFlash反映まで {reflected_ms:.0f}ms" if reflected_ms else f"  pid={pid}: >20s未反映")
    ok = [s for s in syncs if s]
    if ok:
        print(f"  TiFlash同期遅延 中央値 ~{sorted(ok)[len(ok)//2]:.0f}ms （列ストアはOLTPに対し非同期）")

    print("\n=== (3) キラークエリ: 最新在庫>0 × ベクトル × カテゴリ集計 を1クエリ ===")
    q = rt.emb_literal("wireless earbuds")
    cur.execute("UPDATE products_live SET stock=0 WHERE product_id=3")  # 直前に在庫0化
    cur.execute(
        "SELECT product_id, name, stock, category, VEC_COSINE_DISTANCE(emb,%s) d "
        "FROM products_live WHERE stock > 0 ORDER BY d ASC LIMIT 3", (q,))
    print("  hybrid(最新在庫filter×vector):", cur.fetchall())
    cur.execute("SELECT category, COUNT(*) n, SUM(stock) total_stock "
                "FROM products_live WHERE stock>0 GROUP BY category ORDER BY n DESC LIMIT 3")
    print("  集計(現在庫>0のカテゴリ別):", cur.fetchall())
    print("  → 鮮度(最新OLTP) × ベクトル × 集計 が単一エンジン1クエリで成立")
    conn.close()
    print("\nDONE")


if __name__ == "__main__":
    main()
