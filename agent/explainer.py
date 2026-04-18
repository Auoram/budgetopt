import json
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langsmith import traceable
from core.data_model import CampaignInput
from core.optimizer import AllocationResult
from core.charts import channel_label


# ─────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────

EXPLAINER_SYSTEM_PROMPT = """You are a senior digital marketing strategist.
You will receive a JSON object describing a campaign allocation result.
Your job is to write a clear, professional explanation of WHY this
budget allocation was recommended for this specific campaign.

RULES:
1. Write in plain English. No bullet points. 2-4 short paragraphs.
2. Reference the specific sector, region, and goal in your explanation.
3. Mention the top 2 channels by name and explain why they were prioritized.
4. Reference the CPL (cost per lead) and conversion rate where relevant.
5. If SEO received a small allocation, briefly explain why (time horizon).
6. End with one sentence about expected results.
7. Do NOT repeat the numbers table — just explain the reasoning.
8. Keep the total response under 200 words.
9. Return ONLY the explanation text. No JSON, no markdown headers.
"""


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _build_explainer_prompt(
    campaign: CampaignInput,
    result: AllocationResult,
) -> str:
    """
    Serialises the campaign inputs and allocation result
    into a JSON string the LLM can read and reason about.
    """
    channels_detail = []
    for ch in sorted(
        result.pct_per_channel,
        key=lambda x: -result.pct_per_channel[x],
    ):
        leads  = result.expected_leads.get(ch, 0)
        budget = result.budget_per_channel.get(ch, 0)
        cpl    = round(budget / leads, 0) if leads > 0 else 0
        channels_detail.append({
            "channel":        channel_label(ch),
            "budget_mad":     int(budget),
            "share_pct":      round(result.pct_per_channel[ch], 1),
            "expected_leads": int(leads),
            "cpl_mad":        int(cpl),
        })

    roi = round(
        result.total_revenue / campaign.total_budget * 100
        if campaign.total_budget > 0 else 0,
        1,
    )

    payload = {
        "campaign": {
            "sector":           campaign.sector,
            "countries":        campaign.target_countries,
            "client_type":      campaign.client_type,
            "goal":             campaign.goal,
            "horizon_months":   campaign.horizon_months,
            "priority":         campaign.priority,
            "audience_type":    campaign.audience_type,
            "age_range":        f"{campaign.age_min}-{campaign.age_max}",
            "total_budget_mad": int(campaign.total_budget),
        },
        "allocation": channels_detail,
        "summary": {
            "total_expected_leads":   int(result.total_leads),
            "total_expected_revenue": int(result.total_revenue),
            "estimated_roi_pct":      roi,
        },
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _get_aov(sector: str) -> int:
    return {
        "fintech":   800,
        "ecommerce": 350,
        "saas":      1200,
        "education": 600,
        "health":    500,
    }.get(sector, 500)


def _fallback_explanation(
    campaign: CampaignInput,
    result: AllocationResult,
) -> str:
    """Template fallback used when the LLM call fails."""
    sorted_channels = sorted(
        result.pct_per_channel,
        key=lambda x: -result.pct_per_channel[x],
    )
    top_ch     = sorted_channels[0]
    top_pct    = result.pct_per_channel[top_ch]
    top_budget = int(result.budget_per_channel[top_ch])

    cheapest_ch = min(
        result.budget_per_channel,
        key=lambda ch: (
            result.budget_per_channel[ch] / result.expected_leads[ch]
            if result.expected_leads[ch] > 0
            else 999_999
        ),
    )
    cheapest_cpl = round(
        result.budget_per_channel[cheapest_ch] /
        result.expected_leads[cheapest_ch], 0
    ) if result.expected_leads[cheapest_ch] > 0 else 0

    return (
        f"{channel_label(top_ch)} takes the lead at {top_pct:.0f}% "
        f"({top_budget:,} MAD) as the strongest channel for a "
        f"{campaign.sector} campaign targeting "
        f"{campaign.client_type.upper()} customers in "
        f"{', '.join(campaign.target_countries)}. "
        f"{channel_label(cheapest_ch)} offers the lowest estimated "
        f"cost per lead at {int(cheapest_cpl)} MAD. "
        f"This mix is optimised for "
        f"{campaign.priority.replace('_', ' ')} over "
        f"{campaign.horizon_months} month"
        f"{'s' if campaign.horizon_months > 1 else ''}."
    )


# ─────────────────────────────────────────
# MAIN FUNCTION — second LLM call
# ─────────────────────────────────────────

@traceable(name="generate_explanation", run_type="chain")
def generate_explanation(
    campaign: CampaignInput,
    result: AllocationResult,
    model: str = "llama3.1",
) -> str:
    """
    Second LLM call: generates a natural language explanation
    of the budget allocation.

    LangSmith logs:
      - input:  campaign sector/goal/priority + allocation summary
      - output: the explanation string
      - child:  the ChatOllama LLM call (auto-traced)

    Falls back to template if the LLM fails.
    """
    try:
        llm = ChatOllama(
            model       = model,
            temperature = 0.3,
            format      = "",
        )

        prompt = _build_explainer_prompt(campaign, result)

        messages = [
            SystemMessage(content=EXPLAINER_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        response    = llm.invoke(messages)
        explanation = response.content.strip()

        if len(explanation) < 80 or explanation.startswith("{"):
            return _fallback_explanation(campaign, result)

        return explanation

    except Exception:
        return _fallback_explanation(campaign, result)


# ─────────────────────────────────────────
# STANDALONE TEST
# python -m agent.explainer
# ─────────────────────────────────────────

if __name__ == "__main__":
    from core.data_model import CampaignInput
    from core.pipeline import pipeline
    from core.langsmith_setup import setup_langsmith

    setup_langsmith()

    print("Testing explainer with LangSmith tracing...\n")

    campaign = CampaignInput(
        company_name        = "TestCo",
        sector              = "ecommerce",
        target_countries    = ["Morocco"],
        client_type         = "b2c",
        age_min             = 25,
        age_max             = 40,
        audience_type       = "professionals",
        goal                = "increase_sales",
        horizon_months      = 3,
        priority            = "high_quality",
        total_budget        = 200_000.0,
        allowed_channels    = ["facebook", "instagram"],
        max_pct_per_channel = 0.5,
    )

    result = pipeline(campaign)

    print("── Allocation ──")
    for ch, pct in sorted(
        result.pct_per_channel.items(), key=lambda x: -x[1]
    ):
        print(f"  {ch}: {pct:.1f}% — {int(result.budget_per_channel[ch]):,} MAD")

    print("\n── LLM Explanation (check LangSmith dashboard) ──")
    explanation = generate_explanation(campaign, result)
    print(explanation)