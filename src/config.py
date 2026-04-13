from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _from_streamlit_secrets() -> tuple[str, str] | None:
    try:
        import streamlit as st  # type: ignore

        if hasattr(st, "secrets"):
            u = st.secrets.get("ORDINO_ADMIN_USER", os.environ.get("ORDINO_ADMIN_USER"))
            p = st.secrets.get("ORDINO_ADMIN_PASSWORD", os.environ.get("ORDINO_ADMIN_PASSWORD"))
            if u and p:
                return str(u), str(p)
    except Exception:
        pass
    return None


def get_admin_credentials() -> tuple[str, str]:
    sp = _from_streamlit_secrets()
    if sp:
        return sp
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    u = os.environ.get("ORDINO_ADMIN_USER", "admin")
    p = os.environ.get("ORDINO_ADMIN_PASSWORD", "7283")
    return u, p


def db_path() -> Path:
    # Production deploys should provide a persistent absolute path
    # (e.g. /var/data/ordino.sqlite3 on Render persistent disk).
    env_path = os.environ.get("ORDINO_DB_PATH", "").strip()
    if not env_path:
        try:
            import streamlit as st  # type: ignore

            env_path = str(st.secrets.get("ORDINO_DB_PATH", "")).strip()
        except Exception:
            env_path = ""
    if env_path:
        p = Path(env_path).expanduser()
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    d = ROOT / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "ordino.sqlite3"
