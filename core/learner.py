"""
core/learner.py
───────────────
Phase 5 — Learning.

Two responsibilities:

1. ML RETRAINING
   Converts real campaign_performance rows into the same
   format as synthetic_campaigns.csv, appends them, and
   retrains the ML model (CPL + conversion rate predictors).

2. FREELANCER SCORING
   Reads post-campaign ratings from campaign_team and
   computes a score per freelancer used to boost or
   demote them in find_matches() ranking.
"""

import sqlite3
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH    = Path(__file__).parent.parent / "data" / "feedback.db"
CSV_PATH   = Path(__file__).parent.parent / "data" / "synthetic_campaigns.csv"
MODEL_PATH = Path(__file__).parent.parent / "data" / "model.joblib"


# ═══════════════════════════════════════════════════════════
# PART 1 — ML RETRAINING
# ═══════════════════════════════════════════════════════════

def export_performance_for_retraining() -> list[dict]:
    """
    Converts campaign_performance rows into training rows
    compatible with synthetic_campaigns.csv.
    """
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT
                p.channel,
                p.spend_actual,
                p.leads_actual,
                p.revenue_actual,
                p.cpl,
                p.entry_date,
                c.sector,
                c.target_countries,
                c.client_type,
                c.goal,
                c.audience_type,
                c.priority,
                c.horizon_months,
                c.age_min,
                c.age_max
            FROM campaign_performance p
            JOIN campaigns c ON p.campaign_id = c.id
            WHERE p.spend_actual > 0
              AND p.leads_actual > 0
              AND p.cpl IS NOT NULL
        """).fetchall()
    except Exception:
        conn.close()
        return []

    conn.close()

    from core.data_model import COUNTRIES

    training_rows = []
    for r in rows:
        try:
            countries = json.loads(r["target_countries"])
            cluster   = COUNTRIES.get(countries[0], "maghreb") \
                        if countries else "maghreb"
        except Exception:
            cluster = "maghreb"

        spend     = float(r["spend_actual"])
        leads     = int(r["leads_actual"])
        cpl       = float(r["cpl"])
        conv_rate = round(leads / (spend / cpl), 4) if spend > 0 else 0.03
        conv_rate = max(0.005, min(conv_rate, 0.30))

        training_rows.append({
            "sector":         r["sector"]        or "fintech",
            "cluster":        cluster,
            "channel":        r["channel"],
            "client_type":    r["client_type"]   or "b2c",
            "goal":           r["goal"]           or "generate_leads",
            "audience_type":  r["audience_type"] or "professionals",
            "priority":       r["priority"]       or "high_quality",
            "horizon_months": int(r["horizon_months"] or 3),
            "age_min":        int(r["age_min"]    or 18),
            "age_max":        int(r["age_max"]    or 45),
            "budget_mad":     spend,
            "actual_leads":   leads,
            "actual_revenue": float(r["revenue_actual"] or 0),
            "actual_cpl":     cpl,
            "conv_rate":      conv_rate,
        })

    return training_rows


def count_retraining_rows() -> int:
    return len(export_performance_for_retraining())


def retrain_from_performance(min_rows: int = 5) -> dict:
    """
    Appends real performance data to training CSV and retrains.
    Returns metrics dict including MAE + std confidence intervals.
    """
    new_rows = export_performance_for_retraining()

    if len(new_rows) < min_rows:
        return {
            "error": (
                f"Only {len(new_rows)} real performance row(s) available. "
                f"Need at least {min_rows} before retraining. "
                f"Log more performance data in the Monitoring page."
            ),
            "n_new_rows": len(new_rows),
        }

    if not CSV_PATH.exists():
        return {"error": "synthetic_campaigns.csv not found. Run startup first."}

    existing_df = pd.read_csv(CSV_PATH)
    new_df      = pd.DataFrame(new_rows)

    new_df["source"] = "real_performance"
    if "source" not in existing_df.columns:
        existing_df["source"] = "synthetic"

    combined = pd.concat([existing_df, new_df], ignore_index=True)
    combined.to_csv(CSV_PATH, index=False)

    n_before = len(existing_df)
    n_after  = len(combined)

    from core.predictor import train
    metrics = train()

    return {
        "success":      True,
        "n_new_rows":   len(new_rows),
        "n_before":     n_before,
        "n_after":      n_after,
        "cpl_mae":      metrics.get("cpl_mae"),
        "cpl_std":      metrics.get("cpl_std"),
        "cpl_r2":       metrics.get("cpl_r2"),
        "conv_mae":     metrics.get("conv_mae"),
        "conv_std":     metrics.get("conv_std"),
        "conv_r2":      metrics.get("conv_r2"),
        "n_train":      metrics.get("n_train"),
        "n_test":       metrics.get("n_test"),
        "retrained_at": datetime.now().isoformat(),
    }


def get_last_retrain_info() -> dict:
    """Returns metadata about the current model file."""
    if not MODEL_PATH.exists():
        return {"trained": False}

    import joblib
    mtime = datetime.fromtimestamp(MODEL_PATH.stat().st_mtime)

    n_rows      = 0
    n_real      = 0
    n_synthetic = 0
    if CSV_PATH.exists():
        try:
            df = pd.read_csv(CSV_PATH)
            n_rows = len(df)
            if "source" in df.columns:
                n_real      = int((df["source"] == "real_performance").sum())
                n_synthetic = int((df["source"] == "synthetic").sum())
            else:
                n_synthetic = n_rows
        except Exception:
            pass

    return {
        "trained":      True,
        "trained_at":   mtime.strftime("%Y-%m-%d %H:%M"),
        "total_rows":   n_rows,
        "n_real":       n_real,
        "n_synthetic":  n_synthetic,
    }


def get_model_metrics() -> dict:
    """
    Returns the metrics stored inside model.joblib:
    MAE, std (confidence interval), R² for both models.
    Used by the page 7 model performance card.
    Returns empty dict if model not found or not yet upgraded.
    """
    from core.predictor import get_stored_metrics
    return get_stored_metrics()


def get_channel_uncertainty(campaign) -> pd.DataFrame:
    """
    Runs predict_channel_with_std() for every allowed channel
    in the campaign and returns a DataFrame with CPL estimates
    and their ± uncertainty.

    Columns:
        channel, cpl_est, cpl_low, cpl_high, cpl_std,
        conv_est, conv_std, source
    """
    from core.predictor import predict_channel_with_std
    from core.data_model import COUNTRIES

    cluster = campaign.clusters[0] if campaign.clusters else "maghreb"

    rows = []
    for ch in campaign.allowed_channels:
        r = predict_channel_with_std(
            sector         = campaign.sector,
            cluster        = cluster,
            channel        = ch,
            client_type    = campaign.client_type,
            goal           = campaign.goal,
            audience_type  = campaign.audience_type or "professionals",
            priority       = campaign.priority,
            horizon_months = campaign.horizon_months,
            age_min        = campaign.age_min,
            age_max        = campaign.age_max,
            budget_mad     = campaign.total_budget,
        )
        rows.append({
            "channel":   ch,
            "cpl_est":   r.get("predicted_cpl"),
            "cpl_low":   r.get("cpl_low"),
            "cpl_high":  r.get("cpl_high"),
            "cpl_std":   r.get("cpl_std"),
            "conv_est":  r.get("predicted_conv"),
            "conv_std":  r.get("conv_std"),
            "source":    r.get("source"),
        })

    return pd.DataFrame(rows)


def preview_retraining_data() -> pd.DataFrame:
    rows = export_performance_for_retraining()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════
# PART 2 — FREELANCER SCORING
# ═══════════════════════════════════════════════════════════

def get_freelancer_scores() -> pd.DataFrame:
    """
    Returns one row per freelancer with composite score.
    score = 0.75 * (avg_rating/5) + 0.25 * min(n_rated/5, 1)
    """
    if not DB_PATH.exists():
        return pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT
                ct.freelancer_id,
                f.name,
                f.role,
                f.hourly_rate_mad,
                f.experience_level,
                COUNT(ct.id)             AS n_campaigns,
                COUNT(ct.rating)         AS n_rated,
                ROUND(AVG(ct.rating), 2) AS avg_rating,
                MIN(ct.rating)           AS min_rating,
                MAX(ct.rating)           AS max_rating
            FROM campaign_team ct
            JOIN freelancers f ON ct.freelancer_id = f.id
            WHERE ct.status != 'proposed'
            GROUP BY ct.freelancer_id, f.name, f.role
            ORDER BY avg_rating DESC NULLS LAST, n_rated DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()

    if df.empty:
        return df

    df["avg_rating"] = pd.to_numeric(df["avg_rating"], errors="coerce").fillna(0)
    df["n_rated"]    = pd.to_numeric(df["n_rated"],    errors="coerce").fillna(0)

    base        = df["avg_rating"] / 5.0
    volume      = (df["n_rated"] / 5.0).clip(upper=1.0)
    df["score"] = (0.75 * base + 0.25 * volume).round(3)

    return df


def get_freelancer_score(freelancer_id: int) -> Optional[float]:
    scores_df = get_freelancer_scores()
    if scores_df.empty:
        return None
    row = scores_df[scores_df["freelancer_id"] == freelancer_id]
    if row.empty:
        return None
    n_rated = int(row["n_rated"].values[0])
    if n_rated == 0:
        return None
    return float(row["score"].values[0])


def get_top_freelancers(role: Optional[str] = None, top_n: int = 10) -> pd.DataFrame:
    df = get_freelancer_scores()
    if df.empty:
        return df
    if role:
        df = df[df["role"] == role]
    return df.head(top_n)


def get_underperforming_freelancers(min_campaigns: int = 2) -> pd.DataFrame:
    df = get_freelancer_scores()
    if df.empty:
        return df
    return df[
        (df["avg_rating"] < 3.0) &
        (df["n_rated"] >= min_campaigns)
    ].sort_values("avg_rating")


def get_performance_summary_by_role() -> pd.DataFrame:
    df = get_freelancer_scores()
    if df.empty:
        return df
    summary = (
        df.groupby("role")
        .agg(
            n_freelancers     = ("freelancer_id", "count"),
            avg_rating        = ("avg_rating",    "mean"),
            n_total_campaigns = ("n_campaigns",   "sum"),
        )
        .round(2)
        .reset_index()
        .sort_values("avg_rating", ascending=False)
    )
    return summary