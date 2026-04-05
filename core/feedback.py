import sqlite3
import json
from pathlib import Path
from datetime import datetime
from core.data_model import CampaignInput
from core.optimizer import AllocationResult

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


# ─────────────────────────────────────────
# DATABASE SETUP
# Creates the table if it doesn't exist.
# Call this once at app startup.
# ─────────────────────────────────────────

def init_db():
    """Creates the feedback database and table if not present."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            submitted_at        TEXT NOT NULL,

            -- Campaign inputs (from the form)
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

            -- Recommended allocation (what the system suggested)
            recommended_allocation  TEXT,   -- JSON dict channel->MAD
            recommended_leads       TEXT,   -- JSON dict channel->leads
            recommended_revenue     REAL,

            -- Actual results (what the user reports after the campaign)
            actual_spend        TEXT,   -- JSON dict channel->MAD
            actual_leads        TEXT,   -- JSON dict channel->leads
            actual_revenue      REAL,
            comments            TEXT,

            -- Computed fields (for retraining)
            actual_cpl          TEXT,   -- JSON dict channel->CPL
            actual_conv_rate    TEXT    -- JSON dict channel->rate
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# SAVE FEEDBACK
# ─────────────────────────────────────────

def save_feedback(
    campaign:        CampaignInput,
    result:          AllocationResult,
    actual_spend:    dict,   # channel -> MAD actually spent
    actual_leads:    dict,   # channel -> actual leads received
    actual_revenue:  float,
    comments:        str = "",
) -> int:
    """
    Saves one feedback record to the database.
    Returns the new row ID.

    actual_spend and actual_leads are dicts:
        {"facebook": 45000, "instagram": 30000, ...}
    """
    # Compute actual CPL and conversion rate per channel
    actual_cpl       = {}
    actual_conv_rate = {}

    for ch in actual_spend:
        spend  = actual_spend.get(ch, 0)
        leads  = actual_leads.get(ch, 0)

        if leads > 0:
            actual_cpl[ch] = round(spend / leads, 2)
        else:
            actual_cpl[ch] = None

        # Rough conversion rate: leads / (spend / benchmark_cpl)
        # We don't have impressions so we use leads/budget as proxy
        if spend > 0:
            actual_conv_rate[ch] = round(leads / (spend / 100), 4)
        else:
            actual_conv_rate[ch] = None

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("""
        INSERT INTO feedback (
            submitted_at, company_name, sector,
            target_countries, client_type, age_min, age_max,
            audience_type, goal, horizon_months, priority,
            total_budget, allowed_channels, max_pct_per_channel,
            recommended_allocation, recommended_leads, recommended_revenue,
            actual_spend, actual_leads, actual_revenue, comments,
            actual_cpl, actual_conv_rate
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        datetime.now().isoformat(),
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
        json.dumps(result.budget_per_channel),
        json.dumps({k: int(v) for k, v in result.expected_leads.items()}),
        float(result.total_revenue),
        json.dumps(actual_spend),
        json.dumps(actual_leads),
        float(actual_revenue),
        comments,
        json.dumps(actual_cpl),
        json.dumps(actual_conv_rate),
    ))

    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


# ─────────────────────────────────────────
# READ FEEDBACK
# ─────────────────────────────────────────

def get_all_feedback() -> list[dict]:
    """Returns all feedback records as a list of dicts."""
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()
    cur.execute("SELECT * FROM feedback ORDER BY submitted_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_feedback_count() -> int:
    """Returns total number of feedback submissions."""
    if not DB_PATH.exists():
        return 0
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM feedback")
    count = cur.fetchone()[0]
    conn.close()
    return count


# ─────────────────────────────────────────
# EXPORT FOR RETRAINING
# Converts feedback records into the same
# format as synthetic_campaigns.csv so
# predictor.train() can use them directly.
# ─────────────────────────────────────────

def export_for_retraining() -> list[dict]:
    """
    Converts feedback records into training rows.
    Each channel in each feedback record becomes
    one row in the training data.

    Returns a list of dicts compatible with
    synthetic_campaigns.csv columns.
    """
    from core.data_model import get_clusters

    records = get_all_feedback()
    rows    = []

    for rec in records:
        try:
            countries  = json.loads(rec["target_countries"])
            clusters   = get_clusters(countries)
            cluster    = clusters[0] if clusters else "maghreb"

            actual_spend = json.loads(rec["actual_spend"])
            actual_leads = json.loads(rec["actual_leads"])
            actual_cpl   = json.loads(rec["actual_cpl"])
            actual_conv  = json.loads(rec["actual_conv_rate"])

            for ch in actual_spend:
                spend = actual_spend.get(ch, 0)
                leads = actual_leads.get(ch, 0)
                cpl   = actual_cpl.get(ch)
                conv  = actual_conv.get(ch)

                if cpl is None or conv is None or leads == 0:
                    continue

                rows.append({
                    "sector":         rec["sector"],
                    "cluster":        cluster,
                    "channel":        ch,
                    "client_type":    rec["client_type"],
                    "goal":           rec["goal"],
                    "audience_type":  rec["audience_type"] or "professionals",
                    "priority":       rec["priority"],
                    "horizon_months": rec["horizon_months"],
                    "age_min":        rec["age_min"],
                    "age_max":        rec["age_max"],
                    "budget_mad":     spend,
                    "actual_leads":   int(leads),
                    "actual_revenue": int(
                        rec["actual_revenue"] / max(len(actual_spend), 1)
                    ),
                    "actual_cpl":     float(cpl),
                    "conv_rate":      float(conv),
                })
        except Exception:
            continue

    return rows


def retrain_with_feedback():
    """
    Appends real feedback to synthetic_campaigns.csv
    and retrains the ML model.
    Returns training metrics dict.
    """
    import pandas as pd
    from core.predictor import train

    new_rows = export_for_retraining()
    if not new_rows:
        return {"error": "No feedback records to retrain with."}

    csv_path = Path(__file__).parent.parent / "data" / "synthetic_campaigns.csv"
    existing = pd.read_csv(csv_path)
    new_df   = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.to_csv(csv_path, index=False)

    metrics = train()
    return metrics