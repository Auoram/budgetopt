"""
core/reoptimizer.py
───────────────────
Re-runs the budget optimizer using actual campaign performance data.

Logic
─────
1. Load actual performance totals per channel from campaign_performance.
2. Compute real CPL and real conversion rate per channel.
3. Override the scoring table values with real data where available.
4. Compute remaining budget = total_budget - total_spent.
5. Run optimize() with remaining budget + real scores.
6. Build a comparison dict: original allocation vs new allocation.
7. Generate a plain-language explanation of why budget shifted.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
import pandas as pd

from core.data_model import CampaignInput
from core.optimizer import optimize, AllocationResult
from core.scoring import get_channel_scores


# ─────────────────────────────────────────
# DATA CLASS
# ─────────────────────────────────────────

@dataclass
class ChannelComparison:
    channel:        str
    old_pct:        float   # original allocation %
    new_pct:        float   # reoptimized allocation %
    old_budget:     float   # original MAD
    new_budget:     float   # reoptimized MAD
    delta_pct:      float   # new_pct - old_pct
    benchmark_cpl:  float   # CPL from scoring table
    real_cpl:       Optional[float]   # CPL from actual data (None if no data)
    real_leads:     int     # actual leads recorded so far
    real_spend:     float   # actual spend recorded so far
    explanation:    str     # plain-language reason for change


@dataclass
class ReoptimizationResult:
    original_result:     AllocationResult
    new_result:          AllocationResult
    comparison:          Dict[str, ChannelComparison]
    remaining_budget:    float
    total_spent:         float
    total_budget:        float
    pct_budget_used:     float
    summary_explanation: str   # 2-3 sentence overview


# ─────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────

def reoptimize(
    campaign:         CampaignInput,
    original_result:  AllocationResult,
    performance_df:   pd.DataFrame,   # from get_totals_by_channel()
) -> ReoptimizationResult:
    """
    Re-runs the optimizer with real performance data.

    campaign         — original CampaignInput (unchanged)
    original_result  — the AllocationResult from the first run
    performance_df   — DataFrame from performance_db.get_totals_by_channel()
                       columns: channel, total_spend, total_leads,
                                total_revenue, real_cpl, real_ctr, real_roas
    """

    # ── Step 1: index performance data by channel ─────────
    perf: Dict[str, dict] = {}
    if not performance_df.empty:
        for _, row in performance_df.iterrows():
            perf[row["channel"]] = {
                "total_spend":   float(row.get("total_spend", 0) or 0),
                "total_leads":   int(row.get("total_leads", 0) or 0),
                "total_revenue": float(row.get("total_revenue", 0) or 0),
                "real_cpl":      float(row["real_cpl"]) if row.get("real_cpl") else None,
                "real_roas":     float(row["real_roas"]) if row.get("real_roas") else None,
            }

    # ── Step 2: compute totals ────────────────────────────
    total_spent = sum(p["total_spend"] for p in perf.values())
    remaining   = max(0.0, campaign.total_budget - total_spent)
    pct_used    = round(total_spent / campaign.total_budget * 100, 1) \
                  if campaign.total_budget > 0 else 0.0

    # ── Step 3: get base scores from scoring table ────────
    base_scores = get_channel_scores(campaign)

    # ── Step 4: override CPL + conversion rate with real data ──
    adjusted_scores = base_scores.copy()

    for idx, row in adjusted_scores.iterrows():
        ch = row["channel"]
        if ch not in perf:
            continue

        p        = perf[ch]
        real_cpl = p["real_cpl"]

        if real_cpl and real_cpl > 0:
            # Blend real CPL with benchmark: 70% real, 30% benchmark
            # Avoids overreacting to small sample sizes
            benchmark_cpl = float(row["cpl_mad"])
            blended_cpl   = 0.70 * real_cpl + 0.30 * benchmark_cpl
            adjusted_scores.at[idx, "cpl_mad"] = round(blended_cpl, 2)

            # Derive adjusted conversion rate from real leads and spend
            real_leads = p["total_leads"]
            real_spend = p["total_spend"]
            if real_leads > 0 and real_spend > 0:
                # leads per MAD spent → scale to match scoring table units
                implied_conv = real_leads / (real_spend / real_cpl)
                implied_conv = max(0.005, min(implied_conv, 0.30))
                # Blend: 70% real, 30% benchmark
                benchmark_conv = float(row["conversion_rate"])
                blended_conv   = 0.70 * implied_conv + 0.30 * benchmark_conv
                adjusted_scores.at[idx, "conversion_rate"] = round(blended_conv, 4)

    # ── Step 5: build a temporary CampaignInput with remaining budget ──
    reopt_campaign = CampaignInput(
        company_name        = campaign.company_name,
        sector              = campaign.sector,
        target_countries    = campaign.target_countries,
        client_type         = campaign.client_type,
        age_min             = campaign.age_min,
        age_max             = campaign.age_max,
        audience_type       = campaign.audience_type,
        goal                = campaign.goal,
        horizon_months      = campaign.horizon_months,
        priority            = campaign.priority,
        total_budget        = remaining if remaining > 0 else campaign.total_budget,
        allowed_channels    = campaign.allowed_channels,
        max_pct_per_channel = campaign.max_pct_per_channel,
    )

    # ── Step 6: run optimizer with adjusted scores ────────
    # Monkey-patch get_channel_scores to return our adjusted scores
    # for this one call, then restore it.
    import core.optimizer as opt_module
    import core.scoring   as scoring_module

    _orig_get_scores = scoring_module.get_channel_scores

    def _patched_get_scores(camp):
        # Only patch for our reopt_campaign call
        if camp is reopt_campaign:
            filtered = adjusted_scores[
                adjusted_scores["channel"].isin(camp.allowed_channels)
            ].copy()
            # Re-apply audience affinity on adjusted scores
            affinity = camp.audience_affinity
            filtered["reach_score"] = filtered["channel"].map(
                lambda ch: filtered.loc[
                    filtered["channel"] == ch, "reach_score"
                ].values[0] * affinity.get(ch, 1.0)
            )
            filtered["reach_score"] = filtered["reach_score"].clip(upper=10)
            return filtered.reset_index(drop=True)
        return _orig_get_scores(camp)

    scoring_module.get_channel_scores = _patched_get_scores
    try:
        new_result = optimize(reopt_campaign)
    finally:
        scoring_module.get_channel_scores = _orig_get_scores

    # ── Step 7: build comparison ──────────────────────────
    comparison: Dict[str, ChannelComparison] = {}

    for ch in campaign.allowed_channels:
        old_pct    = original_result.pct_per_channel.get(ch, 0.0)
        new_pct    = new_result.pct_per_channel.get(ch, 0.0)
        old_budget = original_result.budget_per_channel.get(ch, 0.0)
        new_budget = new_result.budget_per_channel.get(ch, 0.0)
        delta      = round(new_pct - old_pct, 1)

        p_data        = perf.get(ch, {})
        real_cpl      = p_data.get("real_cpl")
        real_leads    = p_data.get("total_leads", 0)
        real_spend    = p_data.get("total_spend", 0.0)
        benchmark_cpl = float(
            base_scores.loc[base_scores["channel"] == ch, "cpl_mad"].values[0]
        ) if ch in base_scores["channel"].values else 0.0

        # Generate per-channel explanation
        expl = _channel_explanation(
            ch, delta, real_cpl, benchmark_cpl, real_leads, real_spend
        )

        comparison[ch] = ChannelComparison(
            channel       = ch,
            old_pct       = old_pct,
            new_pct       = new_pct,
            old_budget    = old_budget,
            new_budget    = new_budget,
            delta_pct     = delta,
            benchmark_cpl = benchmark_cpl,
            real_cpl      = real_cpl,
            real_leads    = real_leads,
            real_spend    = real_spend,
            explanation   = expl,
        )

    # ── Step 8: summary explanation ───────────────────────
    summary = _summary_explanation(comparison, total_spent, remaining, campaign)

    return ReoptimizationResult(
        original_result  = original_result,
        new_result       = new_result,
        comparison       = comparison,
        remaining_budget = remaining,
        total_spent      = total_spent,
        total_budget     = campaign.total_budget,
        pct_budget_used  = pct_used,
        summary_explanation = summary,
    )


# ─────────────────────────────────────────
# EXPLANATION GENERATORS
# ─────────────────────────────────────────

def _channel_explanation(
    channel:       str,
    delta_pct:     float,
    real_cpl:      Optional[float],
    benchmark_cpl: float,
    real_leads:    int,
    real_spend:    float,
) -> str:
    ch_label = channel.replace("_", " ").title()

    if real_cpl is None or real_leads == 0:
        return (
            f"No performance data logged yet for {ch_label}. "
            f"Allocation based on benchmark CPL of {int(benchmark_cpl)} MAD."
        )

    cpl_ratio = real_cpl / benchmark_cpl if benchmark_cpl > 0 else 1.0

    if delta_pct > 5:
        if cpl_ratio < 0.85:
            return (
                f"{ch_label} is outperforming — real CPL {int(real_cpl)} MAD "
                f"is {int((1 - cpl_ratio) * 100)}% below the {int(benchmark_cpl)} MAD benchmark. "
                f"Budget increased by {delta_pct:.1f}pp to capitalise on efficiency."
            )
        else:
            return (
                f"{ch_label} allocation increased by {delta_pct:.1f}pp "
                f"based on relative performance vs other channels."
            )
    elif delta_pct < -5:
        if cpl_ratio > 1.20:
            return (
                f"{ch_label} is underperforming — real CPL {int(real_cpl)} MAD "
                f"is {int((cpl_ratio - 1) * 100)}% above the {int(benchmark_cpl)} MAD benchmark. "
                f"Budget reduced by {abs(delta_pct):.1f}pp and shifted to better-performing channels."
            )
        else:
            return (
                f"{ch_label} allocation reduced by {abs(delta_pct):.1f}pp. "
                f"Real CPL {int(real_cpl)} MAD vs benchmark {int(benchmark_cpl)} MAD — "
                f"other channels are delivering better relative efficiency."
            )
    else:
        return (
            f"{ch_label} allocation stable (±{abs(delta_pct):.1f}pp). "
            f"Real CPL {int(real_cpl)} MAD vs benchmark {int(benchmark_cpl)} MAD — "
            f"performing within expected range."
        )


def _summary_explanation(
    comparison:   Dict[str, ChannelComparison],
    total_spent:  float,
    remaining:    float,
    campaign:     CampaignInput,
) -> str:
    if not comparison:
        return "No performance data available to generate explanation."

    # Find biggest winner and loser
    with_data = [c for c in comparison.values() if c.real_cpl is not None]

    if not with_data:
        return (
            f"Re-optimization complete. No real performance data has been logged yet — "
            f"allocation is based on benchmark data. "
            f"Log actual metrics in the performance tab to get data-driven recommendations."
        )

    best  = max(with_data, key=lambda c: c.delta_pct)
    worst = min(with_data, key=lambda c: c.delta_pct)

    lines = []
    lines.append(
        f"Re-optimization based on {int(total_spent):,} MAD spent so far "
        f"({campaign.total_budget / total_spent * 100 - 100:.0f}% of budget used). "
        f"Remaining budget to allocate: {int(remaining):,} MAD."
    )

    if best.delta_pct > 3:
        lines.append(
            f"**{best.channel.replace('_',' ').title()}** is the top performer "
            f"(real CPL {int(best.real_cpl)} MAD vs {int(best.benchmark_cpl)} MAD benchmark) "
            f"and receives a larger share of the remaining budget."
        )

    if worst.delta_pct < -3:
        lines.append(
            f"**{worst.channel.replace('_',' ').title()}** is underperforming "
            f"(real CPL {int(worst.real_cpl)} MAD vs {int(worst.benchmark_cpl)} MAD benchmark) "
            f"and has been scaled back."
        )

    return " ".join(lines)


# ─────────────────────────────────────────
# HELPER — reconstruct AllocationResult from DB
# ─────────────────────────────────────────

def build_original_result_from_db(campaign_record: dict) -> AllocationResult:
    """
    Reconstructs an AllocationResult from a campaigns table row
    (as returned by get_campaign_by_id).
    Used when the original result is no longer in session state.
    """
    import json
    from core.optimizer import AllocationResult

    budget_per_channel  = json.loads(campaign_record["budget_per_channel"])
    pct_per_channel     = json.loads(campaign_record["pct_per_channel"])
    expected_leads      = json.loads(campaign_record["expected_leads"])
    expected_revenue    = json.loads(campaign_record["expected_revenue"])

    # Rebuild simple explanations (originals not stored in DB)
    explanations = {
        ch: f"Original allocation: {pct_per_channel.get(ch, 0):.1f}%"
        for ch in budget_per_channel
    }

    return AllocationResult(
        budget_per_channel = {k: float(v) for k, v in budget_per_channel.items()},
        pct_per_channel    = {k: float(v) for k, v in pct_per_channel.items()},
        expected_leads     = {k: float(v) for k, v in expected_leads.items()},
        expected_revenue   = {k: float(v) for k, v in expected_revenue.items()},
        total_leads        = float(campaign_record["total_leads"]),
        total_revenue      = float(campaign_record["total_revenue"]),
        explanations       = explanations,
    )