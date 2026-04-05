import numpy as np
import pandas as pd


def generate_campaign_data(n_samples: int = 2000) -> pd.DataFrame:
    """
    Generates synthetic campaign performance data.
    Same logic as notebook 03 — moved here so it can be
    imported by startup.py on Streamlit Cloud.
    """
    np.random.seed(42)

    sectors      = ["fintech", "ecommerce", "saas", "education", "health"]
    clusters     = ["maghreb", "levant", "gulf", "europe",
                    "north_america", "west_africa"]
    channels     = ["facebook", "instagram", "google_ads",
                    "email", "tiktok", "seo"]
    client_types = ["b2c", "b2b"]
    goals        = ["generate_leads", "increase_sales", "brand_awareness"]
    audiences    = ["students", "professionals", "business_owners"]
    priorities   = ["low_cost", "high_volume", "high_quality"]

    base_cpl = {
        "facebook":   80,
        "instagram":  95,
        "google_ads": 180,
        "email":      25,
        "tiktok":     55,
        "seo":        80,
    }
    cluster_cpl_mult = {
        "maghreb":       0.4,
        "levant":        0.35,
        "gulf":          1.4,
        "europe":        1.6,
        "north_america": 2.2,
        "west_africa":   0.2,
    }
    sector_conv_mult = {
        "fintech":   1.0,
        "ecommerce": 1.3,
        "saas":      0.8,
        "education": 1.1,
        "health":    0.9,
    }
    aov = {
        "fintech":   800,
        "ecommerce": 350,
        "saas":      1200,
        "education": 600,
        "health":    500,
    }

    rows = []
    for _ in range(n_samples):
        sector      = np.random.choice(sectors)
        cluster     = np.random.choice(clusters)
        channel     = np.random.choice(channels)
        client_type = np.random.choice(client_types)
        goal        = np.random.choice(goals)
        audience    = np.random.choice(audiences)
        priority    = np.random.choice(priorities)
        horizon     = np.random.choice([1, 2, 3, 6, 12])
        age_min     = np.random.choice([18, 20, 25, 30])
        age_max     = age_min + np.random.choice([10, 15, 20, 25, 30])
        budget      = np.random.choice([
            10_000, 25_000, 50_000, 100_000,
            250_000, 500_000, 1_000_000, 2_000_000,
        ])

        cpl = (
            base_cpl[channel]
            * cluster_cpl_mult[cluster]
            * np.random.uniform(0.7, 1.4)
        )

        if channel == "seo" and horizon <= 2:
            cpl *= 3.0

        actual_leads = max(
            0, int(budget / cpl * np.random.uniform(0.8, 1.2))
        )

        base_conv  = 0.03 * sector_conv_mult[sector]
        conv_rate  = max(
            0.005, base_conv * np.random.uniform(0.5, 1.8)
        )
        actual_revenue = int(
            actual_leads * conv_rate * aov[sector]
            * np.random.uniform(0.85, 1.15)
        )
        actual_cpl = (
            round(budget / actual_leads, 2)
            if actual_leads > 0 else cpl
        )

        rows.append({
            "sector":         sector,
            "cluster":        cluster,
            "channel":        channel,
            "client_type":    client_type,
            "goal":           goal,
            "audience_type":  audience,
            "priority":       priority,
            "horizon_months": horizon,
            "age_min":        age_min,
            "age_max":        age_max,
            "budget_mad":     budget,
            "actual_leads":   actual_leads,
            "actual_revenue": actual_revenue,
            "actual_cpl":     actual_cpl,
            "conv_rate":      round(conv_rate, 4),
        })

    return pd.DataFrame(rows)