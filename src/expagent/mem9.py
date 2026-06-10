"""mem9（TiDB上のエージェント向け長期記憶）への薄いクライアント。

mem9 はホスト型API（https://api.mem9.ai、内部は TiDB Cloud）またはセルフホスト（mnemo-server）。
本記事のデモでは「ユーザーの関心・過去の問い合わせ文脈」を mem9 に記憶し、在庫質問の回答に反映する。

認証: X-API-Key（MEM9_API_KEY）。任意で X-Mnemo-Agent-Id でエージェント識別。
- 環境変数 MEM9_API_KEY 未設定なら無効化（no-op）し、デモは mem9 なしでも動く。

⚠️ 本リポジトリ著者の検証環境では mem9 APIキー未取得のため**未実行**。
   MEM9_API_KEY を設定すれば動作する想定（API仕様は mem9 公式の v1alpha2 に準拠）。
   レスポンスの正確なスキーマは実行時に確認のこと（search の取り出しは防御的に実装）。
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class Mem9:
    def __init__(self):
        self.base = os.getenv("MEM9_API_URL", "https://api.mem9.ai").rstrip("/")
        self.key = os.getenv("MEM9_API_KEY")
        self.agent = os.getenv("MEM9_AGENT_ID", "realtime-rag-demo")
        self.enabled = bool(self.key)

    def _req(self, method: str, path: str, body=None, params=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-API-Key", self.key or "")
        req.add_header("X-Mnemo-Agent-Id", self.agent)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    def store(self, content: str, labels: list[str] | None = None):
        """記憶を保存（v1alpha2: POST /v1alpha2/mem9s/memories）。"""
        if not self.enabled:
            return None
        return self._req("POST", "/v1alpha2/mem9s/memories",
                         body={"content": content, "labels": labels or []})

    def search(self, query: str, k: int = 3) -> list:
        """記憶を検索（v1alpha2: GET /v1alpha2/mem9s/memories?query=...）。"""
        if not self.enabled:
            return []
        r = self._req("GET", "/v1alpha2/mem9s/memories", params={"query": query})
        # レスポンス形は実行時に要確認。防御的に list を取り出す。
        if isinstance(r, list):
            items = r
        else:
            items = r.get("memories") or r.get("results") or r.get("data") or []
        return items[:k]
