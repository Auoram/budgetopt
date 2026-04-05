import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List
from core.data_model import CampaignInput
from core.scoring import get_channel_scores


@dataclass
class AllocationResult:
    budget_per_channel: Dict[str, float]
    pct_per_channel:    Dict[str, float]
    expected_leads:     Dict[str, float]
    expected_revenue:   Dict[str, float]
    total_leads:        float
    total_revenue:      float
    explanations:       Dict[str, str]
    scored_df:          pd.DataFrame = field(default_factory=pd.DataFrame)


AVG_ORDER_VALUE = {
    "fintech":   800,
    "ecommerce": 350,
    "saas":      1200,
    "education": 600,
    "health":    500,
}


def _horizon_penalty(horizon_months: int, short_term_score: float) -> float:
    if short_term_score <= 3:
        if horizon_months == 1:
            return 0.05
        elif horizon_months == 2:
            return 0.20
    return 1.0


def optimize(campaign: CampaignInput) -> AllocationResult:

    # Step 1 — get scores
    scores = get_channel_scores(campaign)

    if scores.empty:
        raise ValueError(
            "No scoring data found for this sector/goal/client_type/countries. "
            "Add more rows to scoring_table.csv."
        )
    
    # Step 1b — improve scores with ML predictions (if model exists)
    try:
        from core.predictor import predict_all_channels
        scores = predict_all_channels(campaign, scores)
        print("  [ML] Using model predictions.")
    except FileNotFoundError:
        print("  [CSV] Model not found, using CSV scores.")
    except Exception as e:
        print(f"  [CSV] Predictor error: {e}. Using CSV scores.")

    # Step 2 — compute horizon penalty per channel
    scores["horizon_mult"] = scores["short_term_score"].apply(
        lambda s: _horizon_penalty(campaign.horizon_months, s)
    )

    # Step 3 — normalize metrics to 0-1 scale
    max_cpl  = scores["cpl_mad"].max()
    max_conv = scores["conversion_rate"].max()

    scores["cpl_score"]  = 1 - (scores["cpl_mad"] / max_cpl)
    scores["conv_score"] = scores["conversion_rate"] / max_conv
    scores["reach_norm"] = scores["reach_score"] / 10

    # Soft cap: email and SEO can't score above 0.4 on cpl_score
    # in high_volume mode because their low CPL is misleading —
    # they require an existing audience/list to work.
    if campaign.priority == "high_volume":
        low_reach = scores["reach_score"] <= 3
        scores.loc[low_reach, "cpl_score"] = scores.loc[
            low_reach, "cpl_score"
        ].clip(upper=0.35)

    # Step 4 — composite score weighted by priority
    w = campaign.priority_weights

    scores["composite"] = (
        w["cpl"]        * scores["cpl_score"]  +
        w["reach"]      * scores["reach_norm"] +
        w["conversion"] * scores["conv_score"]
    ) * scores["horizon_mult"]

    # Step 5 — raw budget share from composite
    scores["raw_pct"] = scores["composite"] / scores["composite"].sum()

    # Step 6 — enforce max % per channel with redistribution
    scores["final_pct"] = scores["raw_pct"].clip(
        upper=campaign.max_pct_per_channel
    )

    for _ in range(30):
        total  = scores["final_pct"].sum()
        excess = 1.0 - total
        if abs(excess) < 1e-9:
            break
        mask = scores["final_pct"] < campaign.max_pct_per_channel
        if not mask.any():
            break
        room = scores.loc[mask, "composite"]
        extra = (excess * room / room.sum()).clip(
            upper=campaign.max_pct_per_channel
        )
        scores.loc[mask, "final_pct"] += extra
        scores["final_pct"] = scores["final_pct"].clip(
            upper=campaign.max_pct_per_channel
        )

    # Normalize to exactly 1.0
    scores["final_pct"] = scores["final_pct"] / scores["final_pct"].sum()

    # Step 7 — MAD amounts
    scores["budget_mad"] = (
        scores["final_pct"] * campaign.total_budget
    ).round(0)

    # Step 8 — expected leads and revenue
    scores["expected_leads"] = (
        scores["budget_mad"] / scores["cpl_mad"]
    ).round(0)

    aov = AVG_ORDER_VALUE.get(campaign.sector, 500)
    scores["expected_revenue"] = (
        scores["expected_leads"] * scores["conversion_rate"] * aov
    ).round(0)

    # ── Step 9 — generate text explanations ──────────────
    explanations = {}

    # Context strings used in explanations
    goal_verb = {
        "generate_leads":  "generate leads",
        "increase_sales":  "drive sales",
        "brand_awareness": "build brand awareness",
    }
    priority_focus = {
        "low_cost":     "keeping cost per lead low",
        "high_volume":  "maximising audience reach",
        "high_quality": "maximising conversion rate",
    }

    for _, row in scores.iterrows():
        ch       = row["channel"]
        pct      = round(row["final_pct"] * 100, 1)
        budget   = int(row["budget_mad"])
        cpl      = round(row["cpl_mad"], 0)
        conv     = round(row["conversion_rate"] * 100, 1)
        reach    = round(row["reach_score"], 1)

        # Opening: what this channel does for this campaign
        if row["composite"] == scores["composite"].max():
            opening = (
                f"Top channel for this campaign — "
                f"best overall score when optimising for "
                f"{priority_focus[campaign.priority]}."
            )
        elif row["reach_norm"] == scores["reach_norm"].max():
            opening = (
                f"Highest reach among selected channels "
                f"(score {reach}/10) — strong for "
                f"{goal_verb.get(campaign.goal, campaign.goal)}."
            )
        elif row["conv_score"] == scores["conv_score"].max():
            opening = (
                f"Best conversion rate at {conv}% — "
                f"ideal for {priority_focus['high_quality']}."
            )
        elif row["cpl_score"] == scores["cpl_score"].max():
            opening = (
                f"Lowest estimated CPL at {int(cpl)} MAD — "
                f"most cost-efficient channel in this mix."
            )
        elif (campaign.horizon_months < 3
              and row["short_term_score"] <= 3):
            opening = (
                f"Limited allocation due to your "
                f"{campaign.horizon_months}-month horizon — "
                f"this channel takes 4–6 months to show results."
            )
        else:
            opening = (
                f"Supporting channel with a reach score of "
                f"{reach}/10 and {conv}% conversion rate."
            )

        # Middle: audience fit
        audience_fit = {
            "students": {
                "tiktok":    "Excellent fit for student audiences — "
                             "high engagement with short-form content.",
                "instagram": "Strong fit for students — "
                             "visual content drives awareness.",
                "facebook":  "Solid reach for students, "
                             "though TikTok and Instagram lead for this group.",
                "youtube":   "Good for students — "
                             "educational content performs well.",
                "google_ads":"Moderate fit for students — "
                             "works best for high-intent searches.",
                "email":     "Lower fit for students — "
                             "they tend to ignore promotional email.",
                "seo":       "Long-term fit for students "
                             "searching for courses or tools.",
                "linkedin":  "Poor fit for students — "
                             "LinkedIn skews older and professional.",
            },
            "professionals": {
                "linkedin":   "Strong fit — professionals actively "
                              "engage with LinkedIn content.",
                "google_ads": "Strong fit — professionals search "
                              "with high intent.",
                "email":      "Good fit — professionals check email "
                              "regularly and respond to relevant offers.",
                "facebook":   "Moderate fit — professionals use Facebook "
                              "but less for business discovery.",
                "instagram":  "Lower fit for professionals "
                              "unless product is visual.",
                "tiktok":     "Lower fit — professionals are "
                              "less active on TikTok.",
                "seo":        "Good long-term fit — "
                              "professionals search before buying.",
                "youtube":    "Good fit — tutorial and review "
                              "content reaches professionals.",
            },
            "business_owners": {
                "linkedin":   "Top fit — business owners are "
                              "LinkedIn's core audience.",
                "google_ads": "Strong fit — business owners "
                              "search for solutions actively.",
                "email":      "Strong fit — direct, personal, "
                              "and high conversion for B2B.",
                "facebook":   "Moderate fit — business owners "
                              "reachable but noisy targeting.",
                "seo":        "Good long-term fit — "
                              "B2B buyers research thoroughly.",
                "instagram":  "Lower fit unless product is visual.",
                "tiktok":     "Poor fit for business owners.",
                "youtube":    "Moderate fit — demo and case study "
                              "videos work for B2B.",
            },
        }

        audience = campaign.audience_type or "professionals"
        fit_text = (
            audience_fit
            .get(audience, {})
            .get(ch, f"Benchmark CPL for this segment: {int(cpl)} MAD.")
        )

        # Closing: numbers
        closing = (
            f"Allocated {pct}% ({budget:,} MAD) — "
            f"estimated CPL {int(cpl)} MAD · "
            f"conversion rate {conv}%."
        )

        explanations[ch] = f"{opening} {fit_text} {closing}"

    # Step 10 — build result
    return AllocationResult(
        budget_per_channel = dict(zip(scores["channel"], scores["budget_mad"])),
        pct_per_channel    = dict(zip(scores["channel"], (scores["final_pct"] * 100).round(1))),
        expected_leads     = dict(zip(scores["channel"], scores["expected_leads"])),
        expected_revenue   = dict(zip(scores["channel"], scores["expected_revenue"])),
        total_leads        = scores["expected_leads"].sum(),
        total_revenue      = scores["expected_revenue"].sum(),
        explanations       = explanations,
        scored_df          = scores,
    )