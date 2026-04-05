import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from core.optimizer import AllocationResult
from core.data_model import CampaignInput

# ─────────────────────────────────────────
# CHANNEL COLOR MAP
# Same color for each channel across
# all charts. Consistent visual identity.
# ─────────────────────────────────────────

CHANNEL_COLORS = {
    "facebook":   "#1877F2",   # Facebook blue
    "instagram":  "#E1306C",   # Instagram pink
    "google_ads": "#FBBC05",   # Google yellow
    "email":      "#34A853",   # Google green (email)
    "seo":        "#6B7280",   # neutral gray
    "tiktok":     "#010101",   # TikTok black
    "linkedin":   "#0A66C2",   # LinkedIn blue
}

def get_color(channel: str) -> str:
    return CHANNEL_COLORS.get(channel.lower(), "#94A3B8")

def channel_label(channel: str) -> str:
    return channel.replace("_", " ").title()


# ─────────────────────────────────────────
# CHART 1 — PIE: budget split
# ─────────────────────────────────────────

def pie_budget_split(result: AllocationResult) -> go.Figure:
    """
    Donut chart showing % of budget per channel.
    """
    channels = list(result.pct_per_channel.keys())
    values   = list(result.pct_per_channel.values())
    labels   = [channel_label(ch) for ch in channels]
    colors   = [get_color(ch) for ch in channels]

    fig = go.Figure(go.Pie(
        labels       = labels,
        values       = values,
        hole         = 0.45,
        marker_colors = colors,
        textinfo     = "label+percent",
        textposition = "outside",
        hovertemplate = (
            "<b>%{label}</b><br>"
            "Share: %{value:.1f}%<br>"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        title       = dict(
            text    = "Budget split by channel",
            x       = 0.5,
            xanchor = "center",
            font    = dict(size=15),
        ),
        showlegend  = False,
        margin      = dict(t=60, b=20, l=20, r=20),
        height      = 380,
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
    )

    return fig


# ─────────────────────────────────────────
# CHART 2 — BAR: expected leads per channel
# ─────────────────────────────────────────

def bar_expected_leads(result: AllocationResult) -> go.Figure:
    """
    Horizontal bar chart showing expected leads per channel,
    sorted highest to lowest.
    """
    # Sort by leads descending
    sorted_channels = sorted(
        result.expected_leads.keys(),
        key=lambda ch: result.expected_leads[ch],
        reverse=True,
    )

    channels = sorted_channels
    leads    = [int(result.expected_leads[ch]) for ch in channels]
    labels   = [channel_label(ch) for ch in channels]
    colors   = [get_color(ch) for ch in channels]
    budgets  = [int(result.budget_per_channel[ch]) for ch in channels]
    cpls     = [
        round(result.budget_per_channel[ch] /
              result.expected_leads[ch], 1)
        if result.expected_leads[ch] > 0 else 0
        for ch in channels
    ]

    fig = go.Figure(go.Bar(
        x             = leads,
        y             = labels,
        orientation   = "h",
        marker_color  = colors,
        text          = [f"{l:,}" for l in leads],
        textposition  = "outside",
        hovertemplate = (
            "<b>%{y}</b><br>"
            "Expected leads: %{x:,}<br>"
            "Budget: %{customdata[0]:,} MAD<br>"
            "CPL: %{customdata[1]} MAD<br>"
            "<extra></extra>"
        ),
        customdata = list(zip(budgets, cpls)),
    ))

    fig.update_layout(
        title = dict(
            text    = "Expected leads per channel",
            x       = 0.5,
            xanchor = "center",
            font    = dict(size=15),
        ),
        xaxis = dict(
            title     = "Expected leads",
            showgrid  = True,
            gridcolor = "#F0F0F0",
        ),
        yaxis = dict(
            title     = "",
            autorange = "reversed",
        ),
        margin           = dict(t=60, b=40, l=120, r=80),
        height           = 360,
        paper_bgcolor    = "rgba(0,0,0,0)",
        plot_bgcolor     = "rgba(0,0,0,0)",
        bargap           = 0.3,
    )

    return fig


# ─────────────────────────────────────────
# CHART 3 — LINE: budget sensitivity
# How allocation changes at 3 budget levels
# ─────────────────────────────────────────

def line_budget_sensitivity(
    campaign: CampaignInput,
) -> go.Figure:
    """
    Runs the pipeline at 3 budget levels:
    half budget, current budget, double budget.
    Shows how channel % allocation shifts.
    """
    from core.pipeline import pipeline

    base    = campaign.total_budget
    budgets = {
        f"{int(base*0.5):,} MAD (0.5×)": base * 0.5,
        f"{int(base):,} MAD (current)":  base,
        f"{int(base*2):,} MAD (2×)":     base * 2.0,
    }

    # Run pipeline for each budget level
    results = {}
    for label, budget in budgets.items():
        c = CampaignInput(
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
            total_budget        = budget,
            allowed_channels    = campaign.allowed_channels,
            max_pct_per_channel = campaign.max_pct_per_channel,
        )
        results[label] = pipeline(c)

    # Build one line per channel
    budget_labels = list(budgets.keys())
    channels      = campaign.allowed_channels

    fig = go.Figure()

    for ch in channels:
        pcts = [
            results[label].pct_per_channel.get(ch, 0)
            for label in budget_labels
        ]
        fig.add_trace(go.Scatter(
            x          = budget_labels,
            y          = pcts,
            mode       = "lines+markers",
            name       = channel_label(ch),
            line       = dict(color=get_color(ch), width=2.5),
            marker     = dict(size=8, color=get_color(ch)),
            hovertemplate = (
                f"<b>{channel_label(ch)}</b><br>"
                "Budget: %{x}<br>"
                "Share: %{y:.1f}%<br>"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        title = dict(
            text    = "How allocation shifts with budget",
            x       = 0.5,
            xanchor = "center",
            font    = dict(size=15),
        ),
        xaxis = dict(
            title    = "Budget level",
            tickfont = dict(size=11),
        ),
        yaxis = dict(
            title    = "Channel share (%)",
            range    = [0, 60],
            ticksuffix = "%",
        ),
        legend = dict(
            orientation = "h",
            yanchor     = "bottom",
            y           = -0.35,
            xanchor     = "center",
            x           = 0.5,
        ),
        margin        = dict(t=60, b=100, l=60, r=20),
        height        = 420,
        paper_bgcolor = "rgba(0,0,0,0)",
        plot_bgcolor  = "rgba(0,0,0,0)",
        hovermode     = "x unified",
    )

    # Add horizontal reference line at max_pct_per_channel
    max_pct = campaign.max_pct_per_channel * 100
    if max_pct < 100:
        fig.add_hline(
            y          = max_pct,
            line_dash  = "dash",
            line_color = "#EF4444",
            annotation_text = f"Max {int(max_pct)}% constraint",
            annotation_position = "top right",
        )

    return fig