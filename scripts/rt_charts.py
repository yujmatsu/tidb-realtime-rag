#!/usr/bin/env python3
"""実測CSVから記事用グラフ(PNG)を生成。ラベルは英語（CJKフォント非依存）。"""
from __future__ import annotations
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(__file__)
RES = os.path.join(HERE, "..", "docs", "results")
FIG = os.path.join(HERE, "..", "docs", "figures")
os.makedirs(FIG, exist_ok=True)
plt.rcParams.update({"figure.dpi": 130, "font.size": 11})


def load_freshness():
    rows = {}
    with open(os.path.join(RES, "rt_freshness.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["qmode"], {})[r["condition"]] = float(r["freshness_error_rate"]) * 100
    return rows


def chart_freshness_lines(fr):
    Ks = [1, 5, 20, 60]
    x = list(range(len(Ks)))
    active = [fr["active"][f"sync@{k}"] for k in Ks]
    uniform = [fr["uniform"][f"sync@{k}"] for k in Ks]
    plt.figure(figsize=(6.4, 4))
    plt.plot(x, active, "o-", color="#d6336c", lw=2.5, ms=8,
             label="Before / active queries (ask about changing items)")
    plt.plot(x, uniform, "s--", color="#f08c00", lw=2, ms=7,
             label="Before / uniform queries")
    plt.axhline(0, color="#2b8a3e", lw=2.5, label="After (TiDB live) = 0%")
    plt.xticks(x, ["CDC(@1)", "@5", "@20", "@60"])
    plt.xlabel("Sync interval (updates between syncs)")
    plt.ylabel("Freshness error rate (%)")
    plt.title("Stale-RAG freshness error vs sync interval")
    plt.ylim(-3, 50)
    for xi, v in zip(x, active):
        plt.annotate(f"{v:.0f}%", (xi, v), textcoords="offset points", xytext=(0, 8), color="#d6336c")
    plt.legend(fontsize=9, loc="center right")
    plt.tight_layout()
    p = os.path.join(FIG, "fig2_freshness_error.png")
    plt.savefig(p); plt.close(); print("wrote", p)


def chart_htap():
    # 正直版: rt_htap_scale.csv の実測（TiDB Cloud Zero, GROUP BY集計, 50k-500k）
    rows = []
    with open(os.path.join(RES, "rt_htap_scale.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["rows"]), float(r["tikv_ms"]), float(r["tiflash_ms"])))
    labels = [f"{n//1000}k" for n, _, _ in rows]
    tikv = [a for _, a, _ in rows]
    tiflash = [b for _, _, b in rows]
    x = range(len(labels)); w = 0.38
    plt.figure(figsize=(6.6, 4))
    plt.bar([i - w/2 for i in x], tikv, w, label="TiKV (row)", color="#e8590c")
    plt.bar([i + w/2 for i in x], tiflash, w, label="TiFlash (columnar)", color="#1c7ed6")
    plt.xticks(list(x), labels)
    plt.xlabel("Rows (GROUP BY aggregation)")
    plt.ylabel("Latency (ms)")
    plt.title("Aggregation latency on TiDB Cloud Zero\n(no clear columnar advantage at this scale; network-bound)")
    plt.legend(fontsize=9)
    plt.tight_layout()
    p = os.path.join(FIG, "fig4_htap_latency.png")
    plt.savefig(p); plt.close(); print("wrote", p)


def chart_harm():
    # active利用100問の内訳: 正答57 / 危険な誤答(売切れを在庫ありと偽答)30 / その他誤答13
    labels = ["Correct\n57", "Wrong: sold-out shown\nas IN-STOCK (dangerous)\n30", "Other\nwrong\n13"]
    vals = [57, 30, 13]
    colors = ["#2b8a3e", "#d6336c", "#f08c00"]
    plt.figure(figsize=(6.4, 4))
    b = plt.bar(labels, vals, color=colors)
    plt.bar_label(b, padding=3)
    plt.ylabel("# of questions (out of 100)")
    plt.title("Stale-RAG harm (active queries, sync@20):\n43/100 wrong, 30 falsely claim a sold-out item is available")
    plt.ylim(0, 70)
    plt.tight_layout()
    p = os.path.join(FIG, "fig1b_harm.png")
    plt.savefig(p); plt.close(); print("wrote", p)


def chart_interference():
    # 干渉耐性: 書き込み負荷下でも検索p50/p95が劣化しないか。
    # 旧スキーマ(単一writer: 目標レート+実書き込み数) / 新スキーマ(並列writer: 実効レート) の両対応。
    with open(os.path.join(RES, "rt_interference.csv"), encoding="utf-8") as f:
        rd = list(csv.DictReader(f))
    if rd and "effective_writes_per_s" in rd[0]:
        rows = [(int(r["writer_threads"]), float(r["effective_writes_per_s"]),
                 float(r["read_p50_ms"]), float(r["read_p95_ms"])) for r in rd]
        labels = [f"{eff:.0f}/s\n({nw}w)" for nw, eff, _, _ in rows]
        p50 = [a for _, _, a, _ in rows]; p95 = [b for _, _, _, b in rows]
        xlabel = "Effective concurrent write load (updates/sec, #writer threads)"
        title = "HTAP interference resistance:\nread latency stays flat as effective write load rises"
    else:  # 旧: 単一writer。目標レートと計測窓中の実書き込み数を正直に表示。
        rows = [(r["write_rate_per_s"], float(r["read_p50_ms"]), float(r["read_p95_ms"]),
                 int(r.get("writes_done", 0))) for r in rd]
        labels = ["no writes" if r == "0" else f"target {r}/s\n({w} writes)" for r, _, _, w in rows]
        p50 = [a for _, a, _, _ in rows]; p95 = [b for _, _, b, _ in rows]
        xlabel = "Concurrent writes during read window (single writer; actual count shown)"
        title = ("HTAP interference: read latency flat under concurrent writes\n"
                 "(provisional: single-writer load modest; parallel-writer re-run recommended)")
    x = range(len(labels))
    plt.figure(figsize=(6.4, 4))
    plt.plot(x, p95, "s--", color="#e8590c", lw=2, ms=7, label="read p95")
    plt.plot(x, p50, "o-", color="#1c7ed6", lw=2.5, ms=8, label="read p50")
    plt.xticks(list(x), labels, fontsize=9)
    plt.xlabel(xlabel, fontsize=9)
    plt.ylabel("Live RAG read latency (ms)")
    plt.title(title, fontsize=10)
    plt.ylim(0, max(max(p95) * 1.15, 200))
    for xi, v in zip(x, p50):
        plt.annotate(f"{v:.0f}ms", (xi, v), textcoords="offset points", xytext=(0, -14), color="#1c7ed6")
    plt.legend(fontsize=9)
    plt.tight_layout()
    p = os.path.join(FIG, "fig6_interference.png")
    plt.savefig(p); plt.close(); print("wrote", p)


def chart_freshness_boundary():
    # 鮮度の境界: 点参照(TiKV)=即時 vs 分析/ベクトル(TiFlash)~142ms
    labels = ["Point read\n(TiKV row,\nread-your-writes)", "Analytics/vector\n(TiFlash columnar,\nsync)"]
    vals = [0, 142]
    plt.figure(figsize=(5.2, 3.8))
    b = plt.bar(labels, vals, color=["#2b8a3e", "#1c7ed6"])
    plt.bar_label(b, fmt="%d ms", padding=3)
    plt.ylabel("Reflection latency after an update (ms)")
    plt.title("Freshness boundary inside TiDB (measured)")
    plt.ylim(0, 180)
    plt.tight_layout()
    p = os.path.join(FIG, "fig5_freshness_boundary.png")
    plt.savefig(p); plt.close(); print("wrote", p)


if __name__ == "__main__":
    fr = load_freshness()
    chart_freshness_lines(fr)
    chart_harm()
    chart_htap()
    chart_interference()
    chart_freshness_boundary()
    print("done")
