"""realtime-RAG: 決定的な商品カタログ・更新イベント・質問・鮮度評価。

鮮度の核は「在庫(可変な取引状態)」。Before(同期型スナップショット)はN更新ごとにしか
更新されないため、更新直後の質問で古い在庫を返す→誤答。After(ライブ)は常に最新。
"""
from __future__ import annotations

import hashlib
import random
import struct

DIM = 64
CATS = ["家電", "食品", "衣料", "書籍", "日用品"]
_ADJ = ["wireless", "compact", "premium", "eco", "smart", "classic", "lightweight", "pro"]
_NOUN = ["earbuds", "speaker", "kettle", "jacket", "notebook", "bottle", "lamp", "charger"]


def _emb(text: str) -> list[float]:
    v = [0.0] * DIM
    for tok in text.split():
        h = hashlib.sha256(tok.encode()).digest()
        for i in range(0, len(h), 4):
            v[struct.unpack("<I", h[i:i+4])[0] % DIM] += 1.0
    n = sum(x*x for x in v) ** 0.5 or 1.0
    return [x/n for x in v]


def emb_literal(text: str) -> str:
    return "[" + ",".join(f"{x:.5f}" for x in _emb(text)) + "]"


def catalog(n: int = 100, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        desc = f"{rng.choice(_ADJ)} {rng.choice(_NOUN)} {rng.choice(_ADJ)}"
        rows.append({
            "product_id": i, "name": f"商品{i}", "category": rng.choice(CATS),
            "price": rng.randint(300, 120000), "stock": rng.choice([0, 3, 5, 10, 20]),
            "description": desc, "emb": desc,
        })
    return rows


def event_log(prods: list[dict], n_events: int = 120, seed: int = 11) -> list[tuple]:
    """(event_idx, product_id, new_stock) の決定的な在庫更新列。"""
    rng = random.Random(seed)
    ids = [p["product_id"] for p in prods]
    ev = []
    for k in range(n_events):
        pid = rng.choice(ids)
        new_stock = rng.choice([0, 0, 1, 5, 12])  # 0(在庫切れ)を多めに
        ev.append((k, pid, new_stock))
    return ev


def question_log(prods: list[dict], n_q: int = 120, seed: int = 13) -> list[tuple]:
    """(question_idx, product_id) Q-STOCK: 「商品Xは在庫ある？」。
    更新が起きやすい商品を狙い、鮮度が問われるようにする。"""
    rng = random.Random(seed)
    ids = [p["product_id"] for p in prods]
    return [(k, rng.choice(ids)) for k in range(n_q)]


def truth_timeline(prods: list[dict], events: list[tuple]):
    """各 event_idx 適用後の在庫状態(dict pid->stock)のスナップショット列を返す。
    index e の状態 = 初期 + events[0..e] 適用後。"""
    state = {p["product_id"]: p["stock"] for p in prods}
    timeline = [dict(state)]  # before any event (e=-1)
    for (_, pid, ns) in events:
        state[pid] = ns
        timeline.append(dict(state))
    return timeline  # len = n_events+1; timeline[e+1] = state after event e


def interleave(events: list[tuple], questions: list[tuple], qmode: str = "uniform"):
    """イベントと質問を時間軸(tick)に交互配置。tick順に (kind, payload, applied_events) を返す。

    qmode:
      - "uniform": 質問はカタログ全体から一様（在庫変化と無相関）。鮮度がほぼ問われない希薄ケース。
      - "active" : 質問は「直前に更新された商品」を聞く。＝実際のライブ業務利用
                   （"今変化している在庫/注文/チケットを聞く"）に即した相関ケース。
    """
    seq = []
    ei = qi = 0
    applied = 0
    last_pid = None
    while ei < len(events) or qi < len(questions):
        if ei < len(events):
            ev = events[ei]
            seq.append(("event", ev, applied))
            last_pid = ev[1]
            applied += 1
            ei += 1
        if qi < len(questions):
            qk, qpid = questions[qi]
            if qmode == "active" and last_pid is not None:
                qpid = last_pid  # 直近更新された商品を聞く
            seq.append(("question", (qk, qpid), applied))
            qi += 1
    return seq
