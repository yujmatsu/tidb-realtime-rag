"""埋め込みプロバイダ（差し替え可能）。

EMBED_PROVIDER 環境変数で選択:
  - hashing : 依存なし・決定的（オフライン検証/スモークテスト用）
  - openai  : OpenAI text-embedding-3-small 等（OPENAI_API_KEY 必須）
  - vertex  : Vertex AI text-multilingual-embedding-002（GCP 認証必須）

次元は EMBED_DIM（既定 768、schema の VECTOR(n) と一致させること）。
本番実験では openai/vertex を使う。hashing は意味を持たないため学習効果の検証には使わない。
"""
from __future__ import annotations

import hashlib
import math
import os
import struct

EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class HashingEmbedder:
    """決定的な擬似埋め込み（オフライン用）。意味的近接は表現しない。"""

    dim = EMBED_DIM

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        # 単語ハッシュを次元に散らす（bag-of-words 風）
        for tok in text.split():
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            for i in range(0, len(h), 4):
                idx = struct.unpack("<I", h[i : i + 4])[0] % self.dim
                vec[idx] += 1.0
        return _l2_normalize(vec)


class OpenAIEmbedder:
    dim = EMBED_DIM

    def __init__(self, model: str | None = None):
        from openai import OpenAI

        self.client = OpenAI()
        self.model = model or os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    def embed(self, text: str) -> list[float]:
        # dimensions パラメータで EMBED_DIM に合わせる（3-small/3-large 対応）
        resp = self.client.embeddings.create(
            model=self.model, input=text, dimensions=self.dim
        )
        return _l2_normalize(resp.data[0].embedding)


_GENAI_CLIENT = None


def get_genai_client():
    """google-genai の Vertex クライアント（ADC 認証）を返す（プロセス内で再利用）。

    旧 vertexai.generative_models / language_models は 2026-06-24 に削除されるため
    新 SDK `google-genai` を使う。認証は `gcloud auth application-default login`。
    """
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        from google import genai
        from google.genai import types

        # リクエストタイムアウト(ms)を必ず設定。未設定だとハングした接続で無限待機する。
        timeout_ms = int(float(os.getenv("GENAI_TIMEOUT_SEC", "60")) * 1000)
        _GENAI_CLIENT = genai.Client(
            vertexai=True,
            project=os.getenv("GCP_PROJECT") or None,
            location=os.getenv("GCP_LOCATION", "us-central1"),
            http_options=types.HttpOptions(timeout=timeout_ms),
        )
    return _GENAI_CLIENT


class VertexEmbedder:
    dim = EMBED_DIM

    def __init__(self, model: str | None = None):
        self.client = get_genai_client()
        self.model = model or os.getenv("VERTEX_EMBED_MODEL", "text-multilingual-embedding-002")

    def embed(self, text: str) -> list[float]:
        from google.genai import types

        # multilingual-embedding-002 は既定768次元。EMBED_DIM と一致させること。
        r = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=self.dim),
        )
        return _l2_normalize(list(r.embeddings[0].values))


def get_embedder():
    provider = os.getenv("EMBED_PROVIDER", "hashing").lower()
    if provider == "openai":
        return OpenAIEmbedder()
    if provider == "vertex":
        return VertexEmbedder()
    return HashingEmbedder()


def to_vector_literal(vec: list[float]) -> str:
    """TiDB の VECTOR リテラル '[...]' 文字列に変換。"""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
