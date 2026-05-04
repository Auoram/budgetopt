"""
core/performance_db.py
──────────────────────
All database operations for the campaign_performance table.

One row = one logging session for one channel on one date.
The user comes back weekly (or daily) and enters actual numbers.
Derived metrics (CTR, CPC, CPL, ROAS) are computed on insert.

Schema
──────
campaign_performance (
    id             INTEGER PK AUTOINCREMENT,
    campaign_id    INTEGER NOT NULL,
    channel        TEXT    NOT NULL,
    entry_date     TEXT    NOT NULL,   -- ISO date YYYY-MM-DD
    period_label   TEXT,               -- e.g. "Week 1", "Day 5"
    impressions    INTEGER DEFAULT 0,
    clicks         INTEGER DEFAULT 0,
    spend_actual   REAL    DEFAULT 0,  -- MAD
    leads_actual   INTEGER DEFAULT 0,
    revenue_actual REAL    DEFAULT 0,  -- MAD
    ctr            REAL,               -- clicks / impressions
    cpc            REAL,               -- spend / clicks
    cpl            REAL,               -- spend / leads
    roas           REAL,               -- revenue / spend
    notes          TEXT    DEFAULT '',
    created_at     TEXT
)
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, date
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


# ─────────────────────────────────────────
# INIT
# ─────────────────────────────────────────

def init_performance_tables():
    """
    Creates campaign_performance table if it doesn't exist.
    Safe to call multiple times (idempotent).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS campaign_performance (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id    INTEGER NOT NULL,
            channel        TEXT    NOT NULL,
            entry_date     TEXT    NOT NULL,
            period_label   TEXT    DEFAULT '',
            impressions    INTEGER DEFAULT 0,
            clicks         INTEGER DEFAULT 0,
            spend_actual   REAL    DEFAULT 0,
            leads_actual   INTEGER DEFAULT 0,
            revenue_actual REAL    DEFAULT 0,
            ctr            REAL,
            cpc            REAL,
            cpl            REAL,
            roas           REAL,
            notes          TEXT    DEFAULT '',
            created_at     TEXT
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# WRITE
# ─────────────────────────────────────────

def log_performance(
    campaign_id:    int,
    channel:        str,
    entry_date:     date,
    period_label:   str   = "",
    impressions:    int   = 0,
    clicks:         int   = 0,
    spend_actual:   float = 0.0,
    leads_actual:   int   = 0,
    revenue_actual: float = 0.0,
    notes:          str   = "",
) -> int:
    """
    Saves one performance entry for one channel.
    Auto-computes CTR, CPC, CPL, ROAS.
    Returns the new row id.
    """
    # Derived metrics — safe division
    ctr  = round(clicks / impressions, 4)       if impressions > 0 else None
    cpc  = round(spend_actual / clicks, 2)       if clicks > 0      else None
    cpl  = round(spend_actual / leads_actual, 2) if leads_actual > 0 else None
    roas = round(revenue_actual / spend_actual, 3) if spend_actual > 0 else None

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO campaign_performance (
            campaign_id, channel, entry_date, period_label,
            impressions, clicks, spend_actual, leads_actual, revenue_actual,
            ctr, cpc, cpl, roas, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        campaign_id,
        channel,
        entry_date.isoformat(),
        period_label,
        int(impressions),
        int(clicks),
        float(spend_actual),
        int(leads_actual),
        float(revenue_actual),
        ctr, cpc, cpl, roas,
        notes,
        datetime.now().isoformat(),
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def log_performance_batch(
    campaign_id:  int,
    entries:      list[dict],
    entry_date:   date,
    period_label: str = "",
) -> int:
    """
    Saves multiple channel entries at once.
    entries = [
        {"channel": "facebook", "impressions": 10000, "clicks": 300,
         "spend_actual": 5000, "leads_actual": 45, "revenue_actual": 0, "notes": ""},
        ...
    ]
    Returns number of rows inserted.
    """
    count = 0
    for e in entries:
        # Skip channels with zero spend AND zero leads
        if e.get("spend_actual", 0) == 0 and e.get("leads_actual", 0) == 0:
            continue
        log_performance(
            campaign_id    = campaign_id,
            channel        = e["channel"],
            entry_date     = entry_date,
            period_label   = period_label,
            impressions    = int(e.get("impressions", 0)),
            clicks         = int(e.get("clicks", 0)),
            spend_actual   = float(e.get("spend_actual", 0)),
            leads_actual   = int(e.get("leads_actual", 0)),
            revenue_actual = float(e.get("revenue_actual", 0)),
            notes          = e.get("notes", ""),
        )
        count += 1
    return count


def delete_performance_entry(entry_id: int):
    """Hard-deletes one performance row."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM campaign_performance WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# READ — RAW
# ─────────────────────────────────────────

def get_performance(
    campaign_id: int,
    channel:     Optional[str] = None,
) -> pd.DataFrame:
    """
    Returns all performance rows for a campaign,
    optionally filtered by channel.
    Sorted by entry_date ASC, channel ASC.
    """
    query  = "SELECT * FROM campaign_performance WHERE campaign_id = ?"
    params = [campaign_id]
    if channel:
        query  += " AND channel = ?"
        params.append(channel)
    query += " ORDER BY entry_date ASC, channel ASC"

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_latest_entry_date(campaign_id: int) -> Optional[str]:
    """Returns the most recent entry_date for a campaign, or None."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT MAX(entry_date) FROM campaign_performance
        WHERE campaign_id = ?
    """, (campaign_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None


def has_performance_data(campaign_id: int) -> bool:
    """Returns True if any performance rows exist for this campaign."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM campaign_performance WHERE campaign_id = ?",
        (campaign_id,)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


# ─────────────────────────────────────────
# READ — AGGREGATED
# ─────────────────────────────────────────

def get_totals_by_channel(campaign_id: int) -> pd.DataFrame:
    """
    Returns cumulative totals per channel across all entries:
        channel, total_spend, total_leads, total_impressions,
        total_clicks, total_revenue, avg_cpl, avg_ctr, avg_roas
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT
                channel,
                SUM(spend_actual)   AS total_spend,
                SUM(leads_actual)   AS total_leads,
                SUM(impressions)    AS total_impressions,
                SUM(clicks)         AS total_clicks,
                SUM(revenue_actual) AS total_revenue,
                CASE WHEN SUM(leads_actual) > 0
                     THEN ROUND(SUM(spend_actual) / SUM(leads_actual), 2)
                     ELSE NULL END  AS real_cpl,
                CASE WHEN SUM(impressions) > 0
                     THEN ROUND(SUM(clicks) * 1.0 / SUM(impressions), 4)
                     ELSE NULL END  AS real_ctr,
                CASE WHEN SUM(spend_actual) > 0
                     THEN ROUND(SUM(revenue_actual) / SUM(spend_actual), 3)
                     ELSE NULL END  AS real_roas
            FROM campaign_performance
            WHERE campaign_id = ?
            GROUP BY channel
            ORDER BY total_spend DESC
        """, conn, params=(campaign_id,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_cpl_trend(campaign_id: int) -> pd.DataFrame:
    """
    Returns CPL per channel per entry_date — used for the trend line chart.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT
                entry_date,
                channel,
                cpl,
                period_label
            FROM campaign_performance
            WHERE campaign_id = ?
              AND cpl IS NOT NULL
            ORDER BY entry_date ASC, channel ASC
        """, conn, params=(campaign_id,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_spend_trend(campaign_id: int) -> pd.DataFrame:
    """
    Returns cumulative spend per channel over time — used for pacing chart.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT
                entry_date,
                channel,
                SUM(spend_actual) OVER (
                    PARTITION BY channel
                    ORDER BY entry_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_spend
            FROM campaign_performance
            WHERE campaign_id = ?
            ORDER BY entry_date ASC, channel ASC
        """, conn, params=(campaign_id,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


# ─────────────────────────────────────────
# SUMMARY STATS
# ─────────────────────────────────────────

def campaign_performance_summary(campaign_id: int) -> dict:
    """
    Returns top-level KPIs across all channels and all entries:
        total_spent, total_leads, total_revenue, total_impressions,
        total_clicks, blended_cpl, blended_roas, n_entries
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)            AS n_entries,
            SUM(spend_actual)   AS total_spent,
            SUM(leads_actual)   AS total_leads,
            SUM(revenue_actual) AS total_revenue,
            SUM(impressions)    AS total_impressions,
            SUM(clicks)         AS total_clicks
        FROM campaign_performance
        WHERE campaign_id = ?
    """, (campaign_id,))
    row = cur.fetchone()
    conn.close()

    n_entries        = row[0] or 0
    total_spent      = row[1] or 0.0
    total_leads      = row[2] or 0
    total_revenue    = row[3] or 0.0
    total_impressions= row[4] or 0
    total_clicks     = row[5] or 0

    blended_cpl  = round(total_spent / total_leads, 2)    if total_leads > 0   else None
    blended_roas = round(total_revenue / total_spent, 3)  if total_spent > 0   else None

    return {
        "n_entries":         n_entries,
        "total_spent":       total_spent,
        "total_leads":       total_leads,
        "total_revenue":     total_revenue,
        "total_impressions": total_impressions,
        "total_clicks":      total_clicks,
        "blended_cpl":       blended_cpl,
        "blended_roas":      blended_roas,
    }