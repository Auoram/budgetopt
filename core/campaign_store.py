"""
Campaign store — saves every optimizer run automatically.

Separate from feedback.py which only saves when the user
explicitly submits post-campaign results.

Two tables:
  campaigns  — one row per optimizer run (saved automatically)
  feedback   — one row per user submission (saved manually, unchanged)

The history page reads from campaigns.
Feedback is linked to a campaign via campaign_id.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from core.data_model import CampaignInput
from core.optimizer import AllocationResult

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


# ─────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────

def init_campaign_store():
    """
    Creates the campaigns table if it doesn't exist.
    Safe to call multiple times — uses CREATE IF NOT EXISTS.
    Call this at app startup alongside init_db().
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at              TEXT NOT NULL,
            source              TEXT NOT NULL DEFAULT 'form',

            -- Campaign inputs
            company_name        TEXT,
            sector              TEXT,
            target_countries    TEXT,   -- JSON list
            client_type         TEXT,
            age_min             INTEGER,
            age_max             INTEGER,
            audience_type       TEXT,
            goal                TEXT,
            horizon_months      INTEGER,
            priority            TEXT,
            total_budget        REAL,
            allowed_channels    TEXT,   -- JSON list
            max_pct_per_channel REAL,

            -- Allocation result
            budget_per_channel  TEXT,   -- JSON dict channel->MAD
            pct_per_channel     TEXT,   -- JSON dict channel->pct
            expected_leads      TEXT,   -- JSON dict channel->leads
            expected_revenue    TEXT,   -- JSON dict channel->MAD
            total_leads         REAL,
            total_revenue       REAL,

            -- Feedback (filled in later from history page)
            feedback_submitted  INTEGER DEFAULT 0,
            actual_spend        TEXT,   -- JSON dict channel->MAD
            actual_leads        TEXT,   -- JSON dict channel->leads
            actual_revenue      REAL,
            comments            TEXT,
            feedback_at         TEXT
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────

def save_campaign_run(
    campaign: CampaignInput,
    result:   AllocationResult,
    source:   str = "form",   # "form" or "chat"
) -> int:
    """
    Saves one optimizer run to the campaigns table.
    Called automatically after every successful pipeline() call.
    Returns the new campaign ID.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO campaigns (
            run_at, source,
            company_name, sector, target_countries, client_type,
            age_min, age_max, audience_type, goal, horizon_months,
            priority, total_budget, allowed_channels, max_pct_per_channel,
            budget_per_channel, pct_per_channel, expected_leads,
            expected_revenue, total_leads, total_revenue
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
    """, (
        datetime.now().isoformat(),
        source,
        campaign.company_name,
        campaign.sector,
        json.dumps(campaign.target_countries),
        campaign.client_type,
        campaign.age_min,
        campaign.age_max,
        campaign.audience_type,
        campaign.goal,
        campaign.horizon_months,
        campaign.priority,
        campaign.total_budget,
        json.dumps(campaign.allowed_channels),
        campaign.max_pct_per_channel,
        json.dumps({k: float(v) for k, v in result.budget_per_channel.items()}),
        json.dumps({k: float(v) for k, v in result.pct_per_channel.items()}),
        json.dumps({k: int(v)   for k, v in result.expected_leads.items()}),
        json.dumps({k: int(v)   for k, v in result.expected_revenue.items()}),
        float(result.total_leads),
        float(result.total_revenue),
    ))
    campaign_id = cur.lastrowid
    conn.commit()
    conn.close()
    return campaign_id


# ─────────────────────────────────────────
# READ
# ─────────────────────────────────────────

def get_all_campaigns() -> list[dict]:
    """Returns all campaigns ordered by most recent first."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()
    cur.execute("""
        SELECT * FROM campaigns
        ORDER BY run_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_campaign_by_id(campaign_id: int) -> dict | None:
    """Returns one campaign row by ID, or None if not found."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()
    cur.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def search_campaigns(query: str) -> list[dict]:
    """
    Simple search across company_name, sector, and target_countries.
    Case-insensitive substring match.
    """
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()
    q    = f"%{query.lower()}%"
    cur.execute("""
        SELECT * FROM campaigns
        WHERE  LOWER(company_name)     LIKE ?
            OR LOWER(sector)           LIKE ?
            OR LOWER(target_countries) LIKE ?
            OR LOWER(source)           LIKE ?
        ORDER BY run_at DESC
    """, (q, q, q, q))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ─────────────────────────────────────────
# SAVE FEEDBACK ON EXISTING CAMPAIGN
# ─────────────────────────────────────────

def save_feedback_on_campaign(
    campaign_id:    int,
    actual_spend:   dict,   # channel -> MAD
    actual_leads:   dict,   # channel -> int
    actual_revenue: float,
    comments:       str = "",
) -> bool:
    """
    Saves post-campaign feedback directly on an existing campaign row.
    Returns True on success, False if campaign_id not found.
    """
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Compute actual CPL per channel
    actual_cpl = {}
    for ch in actual_spend:
        spend = actual_spend.get(ch, 0)
        leads = actual_leads.get(ch, 0)
        actual_cpl[ch] = round(spend / leads, 2) if leads > 0 else None

    cur.execute("""
        UPDATE campaigns SET
            feedback_submitted = 1,
            actual_spend       = ?,
            actual_leads       = ?,
            actual_revenue     = ?,
            comments           = ?,
            feedback_at        = ?
        WHERE id = ?
    """, (
        json.dumps(actual_spend),
        json.dumps(actual_leads),
        float(actual_revenue),
        comments,
        datetime.now().isoformat(),
        campaign_id,
    ))
    updated = cur.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def get_campaign_count() -> int:
    """Returns total number of saved campaigns."""
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM campaigns")
    count = cur.fetchone()[0]
    conn.close()
    return count