"""
LangSmith tracing setup.

Import and call setup_langsmith() once at app startup.
After that, every LangChain call (ChatOllama.invoke, chains, etc.)
is automatically traced — no other code changes needed.

How to enable:
  Local:          Copy .env.example → .env and fill in your API key.
  Streamlit Cloud: Add the four LANGCHAIN_* vars in the app's Secrets panel.

How to disable:
  Set LANGCHAIN_TRACING_V2=false (or remove the variable entirely).
  The rest of the app keeps working — tracing is fully optional.
"""

import os
from pathlib import Path


def setup_langsmith() -> bool:
    """
    Loads .env if present, then checks whether LangSmith tracing
    is configured. Prints a clear status line at startup.

    Returns True if tracing is active, False if disabled or not configured.
    """
    # ── Load .env file if it exists (local dev only) ──────────
    # On Streamlit Cloud the vars are set via the Secrets panel,
    # so .env won't exist — that's fine, we just skip it.
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        _load_dotenv(env_path)

    # ── Check tracing flag ─────────────────────────────────────
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower()
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    project = os.getenv("LANGCHAIN_PROJECT", "budgetopt")

    if tracing != "true":
        print("[LangSmith] Tracing disabled (LANGCHAIN_TRACING_V2 != true)")
        return False

    if not api_key or api_key == "your_langsmith_api_key_here":
        print("[LangSmith] Tracing enabled but no API key set — tracing skipped.")
        return False

    print(f"[LangSmith] Tracing active → project: '{project}'")
    print(f"[LangSmith] Dashboard: https://smith.langchain.com")
    return True


def _load_dotenv(path: Path):
    """
    Minimal .env loader — no python-dotenv dependency needed.
    Reads KEY=VALUE lines, skips comments and blanks,
    does NOT override vars already set in the environment.
    """
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            # Never overwrite vars already set (e.g. by Streamlit Secrets)
            if key not in os.environ:
                os.environ[key] = value


def get_langsmith_config() -> dict:
    """
    Returns a dict of the current LangSmith config.
    Useful for the debug sidebar in app_agent.py.
    """
    return {
        "tracing_enabled": os.getenv("LANGCHAIN_TRACING_V2", "false"),
        "project":         os.getenv("LANGCHAIN_PROJECT", "budgetopt"),
        "endpoint":        os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"),
        "api_key_set":     bool(os.getenv("LANGCHAIN_API_KEY", "")),
    }