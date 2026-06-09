#!/usr/bin/env python3
"""鮮度 Before/After 計測（realtime-RAG の主役）。

TiDB上で在庫更新イベントを再生し、各質問時刻で
  - After(live)   : products_live を直接参照（read-your-writes・常に最新）
  - Before(sync@K): products_snapshot（K更新ごとにしか同期されない）を参照
の在庫回答が「その時点の真の在庫」と一致するかを実測。
鮮度誤答率 = 各条件で誤答した質問の割合（差分: After=0 基準）。
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from expagent import db, rt  # noqa: E402

HERE = os.path.dirname(__file__)
SCHEMA = os.path.join(HERE, "..", "sql", "schema_rt.sql")
OUT = os.path.join(HERE, "..", "docs", "results")

COLS = "product_id,name,category,price,stock,description,emb"


def seed(conn, table, prods):
    with db.cursor(conn) as cur:
        cur.execute(f"TRUNCATE TABLE {table}")
        cur.executemany(
            f"INSERT INTO {table}({COLS}) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            [(p["product_id"], p["name"], p["category"], p["price"], p["stock"],
              p["description"], rt.emb_literal(p["emb"])) for p in prods])


def run_condition(conn, prods, seq, truth, *, live: bool, K: int = 0):
    seed(conn, "products_live", prods)
    if not live:
        seed(conn, "products_snapshot", prods)
    applied = 0
    wrong = total = 0
    refreshes = 0
    with db.cursor(conn) as cur:
        for kind, payload, _ in seq:
            if kind == "event":
                _, pid, ns = payload
                cur.execute("UPDATE products_live SET stock=%s WHERE product_id=%s", (ns, pid))
                applied += 1
                if not live and applied % K == 0:
                    cur.execute(f"REPLACE INTO products_snapshot({COLS}) "
                                f"SELECT {COLS} FROM products_live")
                    refreshes += 1
            else:
                _, pid = payload
                tbl = "products_live" if live else "products_snapshot"
                cur.execute(f"SELECT stock FROM {tbl} WHERE product_id=%s", (pid,))
                got = cur.fetchone()[0]
                true_stock = truth[applied][pid]
                total += 1
                if (got > 0) != (true_stock > 0):
                    wrong += 1
    return {"wrong": wrong, "total": total, "rate": wrong / total if total else 0,
            "refreshes": refreshes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", type=int, default=80)
    ap.add_argument("--events", type=int, default=100)
    ap.add_argument("--questions", type=int, default=100)
    ap.add_argument("--syncs", default="1,5,20", help="Before の同期間隔(更新数)。1=CDC理想")
    args = ap.parse_args()

    conn = db.connect()
    with open(SCHEMA, encoding="utf-8") as f:
        db.execute_script(conn, f.read())
    # TiFlash available 待ち（vector index 用）
    import time
    for _ in range(24):
        with db.cursor(conn) as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.tiflash_replica "
                        "WHERE TABLE_SCHEMA=DATABASE() AND AVAILABLE=1")
            if cur.fetchone()[0] >= 2:
                break
        time.sleep(5)

    prods = rt.catalog(args.products)
    events = rt.event_log(prods, args.events)
    questions = rt.question_log(prods, args.questions)
    truth = rt.truth_timeline(prods, events)
    Ks = [int(x) for x in args.syncs.split(",")]
    conditions = ["live"] + [f"sync@{K}" for K in Ks]

    # uniform(無相関) と active(直近更新を聞く=実利用) の両モードで計測
    results = {"uniform": {}, "active": {}}
    for qmode in ("uniform", "active"):
        seq = rt.interleave(events, questions, qmode=qmode)
        print(f"##### qmode={qmode} #####")
        results[qmode]["live"] = run_condition(conn, prods, seq, truth, live=True)
        print(f"  [{qmode}] live:", results[qmode]["live"]["rate"])
        for K in Ks:
            results[qmode][f"sync@{K}"] = run_condition(conn, prods, seq, truth, live=False, K=K)
            print(f"  [{qmode}] sync@{K}:", results[qmode][f"sync@{K}"]["rate"])

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "rt_freshness.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["qmode", "condition", "freshness_error_rate", "wrong", "total", "refreshes"])
        for qm in ("uniform", "active"):
            for c in conditions:
                r = results[qm][c]
                w.writerow([qm, c, f"{r['rate']:.4f}", r["wrong"], r["total"], r["refreshes"]])

    def lbl(c):
        return "After(TiDB live)" if c == "live" else f"Before(同期@{c.split('@')[1]}更新)"

    lines = ["# 鮮度 Before/After 計測結果", "",
             f"products={args.products}, events={args.events}, questions={args.questions}", "",
             "鮮度誤答率（質問が在庫変化と無相関 / 直近更新を聞く=実利用）", "",
             "| 条件 | uniform(無相関) | active(実利用:直近更新を聞く) |", "|---|---|---|"]
    for c in conditions:
        lines.append(f"| {lbl(c)} | {results['uniform'][c]['rate']:.1%} | {results['active'][c]['rate']:.1%} |")
    lines += ["",
              "> After(live)=read-your-writesで常に最新→両モードで誤答0。",
              "> Beforeは同期間隔が広いほど誤答増。**特にactive(実利用=今変化している項目を聞く)で顕著**。",
              "> uniform(大カタログを一様に聞く)では鮮度が問われにくく希薄＝鮮度誤答は"
              "「同期間隔 × 質問が更新と相関するか」の関数（正直に提示）。",
              "> sync@1=CDC理想(毎更新同期)≈live。CDCで縮むが運用複雑性/コストが増す一方、TiDBは構造的にlive。"]
    with open(os.path.join(OUT, "rt_freshness.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    conn.close()


if __name__ == "__main__":
    main()
