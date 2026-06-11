#!/usr/bin/env python3
"""実測CSVから記事用グラフ(PNG)を生成。ラベルは日本語。

日本語フォントは環境にインストール済みのものを自動選択する
（Noto Sans CJK JP / IPAexGothic 等）。無い場合は次でインストール可:
    Debian/Ubuntu: sudo apt-get install -y fonts-noto-cjk
フォントが見つからない場合は警告を出し、日本語が豆腐(□)になる。
"""
from __future__ import annotations
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

# 環境にある日本語フォントを優先順で探して設定（japanize-matplotlib不要）
_JP_CANDIDATES = ("Noto Sans CJK JP", "IPAexGothic", "IPAGothic", "TakaoGothic", "VL Gothic")
_installed = {f.name for f in fm.fontManager.ttflist}
for _name in _JP_CANDIDATES:
    if _name in _installed:
        plt.rcParams["font.family"] = _name
        break
else:
    print("WARN: 日本語フォントが見つかりません。ラベルが豆腐(□)になる可能性があります。"
          " `sudo apt-get install -y fonts-noto-cjk` 等でインストールしてください。")
plt.rcParams["axes.unicode_minus"] = False

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
    plt.figure(figsize=(6.6, 4))
    plt.plot(x, active, "o-", color="#d6336c", lw=2.5, ms=8,
             label="同期型・active（更新直後を質問＝上限）")
    plt.plot(x, uniform, "s--", color="#f08c00", lw=2, ms=7,
             label="同期型・uniform（一様に質問）")
    plt.axhline(0, color="#2b8a3e", lw=2.5, label="ライブ参照（TiDB）＝0%")
    plt.xticks(x, ["CDC(@1)", "@5", "@20", "@60"])
    plt.xlabel("同期間隔（何更新ごとに同期するか）")
    plt.ylabel("鮮度誤答率（％）")
    plt.title("同期遅延による鮮度誤答率 vs 同期間隔")
    plt.ylim(-3, 50)
    for xi, v in zip(x, active):
        plt.annotate(f"{v:.0f}%", (xi, v), textcoords="offset points", xytext=(0, 8), color="#d6336c")
    plt.legend(fontsize=9, loc="center right")
    plt.tight_layout()
    p = os.path.join(FIG, "fig2_freshness_error.png")
    plt.savefig(p); plt.close(); print("wrote", p)


def chart_htap():
    # rt_htap_scale.csv の実測（TiDB Cloud Zero, GROUP BY集計, 50k-500k）
    rows = []
    with open(os.path.join(RES, "rt_htap_scale.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((int(r["rows"]), float(r["tikv_ms"]), float(r["tiflash_ms"])))
    labels = [f"{n//1000}k" for n, _, _ in rows]
    tikv = [a for _, a, _ in rows]
    tiflash = [b for _, _, b in rows]
    x = range(len(labels)); w = 0.38
    plt.figure(figsize=(6.6, 4))
    plt.bar([i - w/2 for i in x], tikv, w, label="TiKV（行ストア）", color="#e8590c")
    plt.bar([i + w/2 for i in x], tiflash, w, label="TiFlash（列ストア）", color="#1c7ed6")
    plt.xticks(list(x), labels)
    plt.xlabel("行数（GROUP BY 集計）")
    plt.ylabel("レイテンシ（ms）")
    plt.title("集計レイテンシ（TiDB Cloud Zero）\nこの規模では列ストアの明確な優位なし（ネットワーク律速）")
    plt.legend(fontsize=9)
    plt.tight_layout()
    p = os.path.join(FIG, "fig5_htap_latency.png")
    plt.savefig(p); plt.close(); print("wrote", p)


def chart_harm():
    # active利用100問の内訳: 正答57 / 危険な誤答(売切れを在庫ありと偽答)30 / その他誤答13
    labels = ["正答\n57", "誤答：売り切れを\n在庫ありと回答（危険）\n30", "その他の\n誤答\n13"]
    vals = [57, 30, 13]
    colors = ["#2b8a3e", "#d6336c", "#f08c00"]
    plt.figure(figsize=(6.6, 4))
    b = plt.bar(labels, vals, color=colors)
    plt.bar_label(b, padding=3)
    plt.ylabel("質問数（100問中）")
    plt.title("同期遅延RAGの実害（active・同期@20）：\n100問中43問が誤答、うち30問は売り切れを在庫ありと回答")
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
        labels = [f"{eff:.0f}/秒\n(writer{nw})" for nw, eff, _, _ in rows]
        p50 = [a for _, _, a, _ in rows]; p95 = [b for _, _, _, b in rows]
        xlabel = "並行書き込み負荷（実効 更新/秒・writer数）"
        title = "HTAP干渉耐性：\n実効書き込み負荷を上げても検索レイテンシは横ばい"
    else:  # 旧: 単一writer。目標レートと計測窓中の実書き込み数を正直に表示。
        rows = [(r["write_rate_per_s"], float(r["read_p50_ms"]), float(r["read_p95_ms"]),
                 int(r.get("writes_done", 0))) for r in rd]
        labels = ["書き込みなし" if r == "0" else f"目標{r}/秒\n({w}件)" for r, _, _, w in rows]
        p50 = [a for _, a, _, _ in rows]; p95 = [b for _, _, b, _ in rows]
        xlabel = "計測窓中の並行書き込み（単一writer・実書き込み数）"
        title = ("HTAP干渉耐性：並行書き込み下でも検索レイテンシは横ばい\n"
                 "（暫定：単一writerで負荷は控えめ。並列writerでの再計測を推奨）")
    x = range(len(labels))
    plt.figure(figsize=(6.6, 4))
    plt.plot(x, p95, "s--", color="#e8590c", lw=2, ms=7, label="検索 p95")
    plt.plot(x, p50, "o-", color="#1c7ed6", lw=2.5, ms=8, label="検索 p50")
    plt.xticks(list(x), labels, fontsize=9)
    plt.xlabel(xlabel, fontsize=9)
    plt.ylabel("ライブRAG検索レイテンシ（ms）")
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
    labels = ["点参照\n(TiKV行ストア・\nread-your-writes)", "分析/ベクトル\n(TiFlash列ストア・\n同期)"]
    vals = [0, 142]
    plt.figure(figsize=(5.4, 3.8))
    b = plt.bar(labels, vals, color=["#2b8a3e", "#1c7ed6"])
    plt.bar_label(b, fmt="%d ms", padding=3)
    plt.ylabel("更新後に反映されるまでの時間（ms）")
    plt.title("TiDB内部の鮮度境界（実測）")
    plt.ylim(0, 180)
    plt.tight_layout()
    p = os.path.join(FIG, "fig4_freshness_boundary.png")
    plt.savefig(p); plt.close(); print("wrote", p)


if __name__ == "__main__":
    fr = load_freshness()
    chart_freshness_lines(fr)
    chart_harm()
    chart_htap()
    chart_interference()
    chart_freshness_boundary()
    print("done")
