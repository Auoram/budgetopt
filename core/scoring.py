import pandas as pd
from pathlib import Path
from core.data_model import CampaignInput

SCORING_PATH = Path(__file__).parent.parent / "data" / "scoring_table.csv"

# ─────────────────────────────────────────
# CHANNEL / CLIENT-TYPE EXCLUSIONS
# ─────────────────────────────────────────
# These channels only make sense for one
# client type. They must never appear in
# campaigns of the opposite type — even
# through the fallback chain.

B2B_ONLY_CHANNELS = {"linkedin"}   # never shown for b2c campaigns
B2C_ONLY_CHANNELS = {"tiktok"}     # never shown for b2b campaigns


def load_scoring_table() -> pd.DataFrame:
    """Loads the CSV once and returns a DataFrame."""
    return pd.read_csv(SCORING_PATH)


def get_channel_scores(campaign: CampaignInput) -> pd.DataFrame:
    """
    Given a CampaignInput, returns a DataFrame with one row
    per allowed channel, showing the scores the optimizer will use.

    Fallback chain (most specific → least specific):
      1. sector + goal + client_type + clusters          (exact match)
      2. sector + goal + clusters          (relax client_type)
      3. sector + client_type + clusters   (relax goal)
      4. sector + clusters                 (relax both)

    For channels that are in allowed_channels but have no scoring
    row at all, we synthesise a row using the average of all other
    channels in the same sector so the channel is never silently dropped.

    LinkedIn is always excluded for B2C campaigns.
    TikTok is always excluded for B2B campaigns.
    """
    df = load_scoring_table()

    # ── Step 1: progressively relax filters ──────────────

    filtered = _filter(df, campaign.sector, campaign.goal,
                       campaign.client_type, campaign.clusters)

    if filtered.empty:
        # relax client_type
        filtered = _filter(df, campaign.sector, campaign.goal,
                           None, campaign.clusters)

    if filtered.empty:
        # relax goal
        filtered = _filter(df, campaign.sector, "generate_leads",
                           campaign.client_type, campaign.clusters)

    if filtered.empty:
        # relax both
        filtered = _filter(df, campaign.sector, "generate_leads",
                           None, campaign.clusters)

    if filtered.empty:
        # last resort: just match sector
        filtered = df[df["sector"] == campaign.sector].copy()

    if filtered.empty:
        raise ValueError(
            f"No scoring data found for sector='{campaign.sector}'. "
            "Add rows to scoring_table.csv."
        )

    # ── Step 1b: enforce B2B/B2C channel exclusions ──────
    # Applied immediately after filtering so excluded channels
    # never influence averages or synthesis.

    if campaign.client_type == "b2c":
        filtered = filtered[
            ~filtered["channel"].isin(B2B_ONLY_CHANNELS)
        ].copy()
    elif campaign.client_type == "b2b":
        filtered = filtered[
            ~filtered["channel"].isin(B2C_ONLY_CHANNELS)
        ].copy()

    if filtered.empty:
        raise ValueError(
            f"No scoring data left after client_type exclusions "
            f"for sector='{campaign.sector}', "
            f"client_type='{campaign.client_type}'. "
            "Add rows to scoring_table.csv."
        )

    # ── Step 2: average across clusters ──────────────────

    scores = (
        filtered.groupby("channel")
        .agg(
            cpl_mad          = ("cpl_mad",          "mean"),
            conversion_rate  = ("conversion_rate",   "mean"),
            reach_score      = ("reach_score",       "mean"),
            short_term_score = ("short_term_score",  "mean"),
        )
        .reset_index()
    )

    # ── Step 3: synthesise missing channels ──────────────
    # If a channel is in allowed_channels but has no scoring row,
    # give it the sector average so it participates in optimisation
    # at a neutral score rather than being silently dropped.
    # Respect B2B/B2C exclusions — never synthesise excluded channels.

    if campaign.client_type == "b2c":
        eligible_missing = [
            ch for ch in campaign.allowed_channels
            if ch not in scores["channel"].values
            and ch not in B2B_ONLY_CHANNELS
        ]
    elif campaign.client_type == "b2b":
        eligible_missing = [
            ch for ch in campaign.allowed_channels
            if ch not in scores["channel"].values
            and ch not in B2C_ONLY_CHANNELS
        ]
    else:
        eligible_missing = [
            ch for ch in campaign.allowed_channels
            if ch not in scores["channel"].values
        ]

    if eligible_missing:
        avg_cpl   = scores["cpl_mad"].mean()
        avg_conv  = scores["conversion_rate"].mean()
        avg_reach = scores["reach_score"].mean()
        avg_st    = scores["short_term_score"].mean()

        synthetic = pd.DataFrame([
            {
                "channel":          ch,
                "cpl_mad":          avg_cpl,
                "conversion_rate":  avg_conv,
                "reach_score":      avg_reach,
                "short_term_score": avg_st,
            }
            for ch in eligible_missing
        ])
        scores = pd.concat([scores, synthetic], ignore_index=True)
        print(
            f" [scoring] Synthesised rows for missing channels: "
            f"{eligible_missing}"
        )

    # ── Step 4: apply audience affinity multipliers ───────

    affinity = campaign.audience_affinity
    scores["reach_score"] = scores["channel"].map(
        lambda ch: scores.loc[
            scores["channel"] == ch, "reach_score"
        ].values[0] * affinity.get(ch, 1.0)
    )
    scores["reach_score"] = scores["reach_score"].clip(upper=10)

    # ── Step 5: keep only allowed channels ────────────────

    scores = scores[
        scores["channel"].isin(campaign.allowed_channels)
    ].copy()

    return scores.reset_index(drop=True)


def _filter(
    df:          pd.DataFrame,
    sector:      str,
    goal:        str,
    client_type: str | None,
    clusters:    list[str],
) -> pd.DataFrame:
    """Helper: filter scoring table with optional client_type."""
    mask = (
        (df["sector"]  == sector) &
        (df["goal"]    == goal)   &
        (df["cluster"].isin(clusters))
    )
    if client_type:
        mask = mask & (df["client_type"] == client_type)
    return df[mask].copy()