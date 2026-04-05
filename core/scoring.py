import pandas as pd
from pathlib import Path
from core.data_model import CampaignInput

SCORING_PATH = Path(__file__).parent.parent / "data" / "scoring_table.csv"


def load_scoring_table() -> pd.DataFrame:
    """Loads the CSV once and returns a DataFrame."""
    return pd.read_csv(SCORING_PATH)


def get_channel_scores(campaign: CampaignInput) -> pd.DataFrame:
    """
    Given a CampaignInput, returns a DataFrame with one row
    per allowed channel, showing the scores the optimizer will use.

    Steps:
      1. Filter rows matching sector + goal + client_type + clusters
      2. Average scores across clusters (if multiple countries selected)
      3. Apply audience affinity multipliers
      4. Return only the allowed channels
    """
    df = load_scoring_table()

    # ── Step 1: filter matching rows ──────────────────────
    filtered = df[
        (df["sector"]      == campaign.sector)     &
        (df["goal"]        == campaign.goal)        &
        (df["client_type"] == campaign.client_type) &
        (df["cluster"].isin(campaign.clusters))
    ].copy()

    # Fallback: if no exact match, relax client_type filter
    if filtered.empty:
        filtered = df[
            (df["sector"]  == campaign.sector) &
            (df["goal"]    == campaign.goal)   &
            (df["cluster"].isin(campaign.clusters))
        ].copy()

    # ── Step 2: average across clusters ───────────────────
    # If the user picked Morocco + France, we average
    # the scores for maghreb and europe per channel.
    scores = (
        filtered.groupby("channel")
        .agg(
            cpl_mad          = ("cpl_mad",          "mean"),
            conversion_rate  = ("conversion_rate",  "mean"),
            reach_score      = ("reach_score",      "mean"),
            short_term_score = ("short_term_score", "mean"),
        )
        .reset_index()
    )

    # ── Step 3: apply audience affinity multipliers ───────
    affinity = campaign.audience_affinity
    scores["reach_score"] = scores["channel"].map(
        lambda ch: scores.loc[
            scores["channel"] == ch, "reach_score"
        ].values[0] * affinity.get(ch, 1.0)
    )
    scores["reach_score"] = scores["reach_score"].clip(upper=10)

    # ── Step 4: keep only allowed channels ────────────────
    scores = scores[
        scores["channel"].isin(campaign.allowed_channels)
    ].copy()

    return scores.reset_index(drop=True)