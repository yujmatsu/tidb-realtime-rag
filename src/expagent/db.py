"""TiDB 接続ユーティリティ。

接続情報は環境変数から読む（.env も読み込む）。
  TIDB_HOST / TIDB_PORT / TIDB_USER / TIDB_PASSWORD / TIDB_DATABASE
TiDB Cloud は TLS 必須。CA は環境変数 TIDB_SSL_CA かシステムCAを使う。
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pymysql

# .env を簡易ロード（python-dotenv があれば使う）
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # 依存が無くても動く
    pass

_DEFAULT_CA_CANDIDATES = [
    "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL
    "/etc/ssl/cert.pem",  # macOS/BSD
]


def _ca_path() -> str | None:
    ca = os.getenv("TIDB_SSL_CA")
    if ca and os.path.exists(ca):
        return ca
    for c in _DEFAULT_CA_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


def connect(database: str | None = None) -> pymysql.connections.Connection:
    """新しい接続を返す。database 未指定なら TIDB_DATABASE。"""
    ca = _ca_path()
    return pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.getenv("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USER"],
        password=os.environ["TIDB_PASSWORD"],
        database=database or os.getenv("TIDB_DATABASE") or None,
        ssl={"ca": ca} if ca else {"ssl": {}},
        connect_timeout=30,
        charset="utf8mb4",
        autocommit=True,
    )


@contextmanager
def cursor(conn: pymysql.connections.Connection):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def execute_script(conn: pymysql.connections.Connection, sql_text: str) -> None:
    """`;` 区切りの複数ステートメントを順に実行する（簡易）。"""
    for stmt in _split_statements(sql_text):
        if stmt.strip():
            with cursor(conn) as cur:
                cur.execute(stmt)


def _split_statements(sql_text: str) -> list[str]:
    """素朴な `;` 分割。コメント行（-- で始まる）と空行は除去。"""
    lines = []
    for line in sql_text.splitlines():
        s = line.strip()
        if s.startswith("--") or not s:
            continue
        lines.append(line)
    joined = "\n".join(lines)
    return [s for s in joined.split(";") if s.strip()]
