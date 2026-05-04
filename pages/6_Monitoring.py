"""
pages/6_Monitoring.py
──────────────────────
Streamlit page — Phase 4: Monitoring & Re-optimization.

Tabs:
  1. Log performance   — enter this week's numbers per channel
  2. Dashboard         — actual vs planned + trend charts
  3. Re-optimize       — re-run optimizer with real data, compare old vs new
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta

from core.data_model import CampaignInput
from core.campaign_store import get_all_campaigns, get_campaign_by_id
from core.performance_db import (
    init_performance_tables,
    log_performance_batch,
    get_performance,
    get_totals_by_channel,
    get_cpl_trend,
    campaign_performance_summary,
    has_performance_data,
    delete_performance_entry,
)
from core.reoptimizer import (
    reoptimize,
    build_original_result_from_db,
)
from core.startup import (
    ensure_model_exists,
    ensure_team_tables_exist,
    ensure_task_tables_exist,
    ensure_performance_tables_exist,
)
from core.feedback import init_db
from core.campaign_store import init_campaign_store

# ── Startup ────────────────────────────────────────────────
ensure_model_exists()
ensure_team_tables_exist()
ensure_task_tables_exist()
ensure_performance_tables_exist()
init_db()
init_campaign_store()

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title            = "BudgetOpt — Monitoring",
    page_icon             = "📈",
    layout                = "wide",
    initial_sidebar_state = "collapsed",
)

st.markdown("""
<style>
.main-title  { font-size:2rem; font-weight:600; margin-bottom:0.2rem; }
.sub-title   { font-size:1rem; color:#666; margin-bottom:1.5rem; }
.section-hdr { font-size:1.05rem; font-weight:600; border-bottom:2px solid #f0f0f0;
               padding-bottom:0.4rem; margin-bottom:0.8rem; }
.up          { color:#16a34a; font-weight:700; }
.down        { color:#dc2626; font-weight:700; }
.neutral     { color:#6b7280; }
.kpi-label   { font-size:0.8rem; color:#6b7280; text-transform:uppercase;
               letter-spacing:0.05em; }
.kpi-value   { font-size:1.6rem; font-weight:700; color:#111; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📈 Monitoring</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Track real campaign performance, compare against plan, '
    'and re-optimize remaining budget based on actual data.</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────

CHANNEL_COLORS = {
    "facebook":   "#1877F2",
    "instagram":  "#E1306C",
    "google_ads": "#FBBC05",
    "email":      "#34A853",
    "seo":        "#6B7280",
    "tiktok":     "#010101",
    "linkedin":   "#0A66C2",
}

def ch_color(ch: str) -> str:
    return CHANNEL_COLORS.get(ch.lower(), "#94A3B8")

def ch_label(ch: str) -> str:
    return ch.replace("_", " ").title()

def delta_arrow(val: float, inverse: bool = False) -> str:
    """Returns colored arrow string for a numeric delta."""
    if val > 0:
        color = "down" if inverse else "up"
        return f'<span class="{color}">▲ +{val:,.0f}</span>'
    elif val < 0:
        color = "up" if inverse else "down"
        return f'<span class="{color}">▼ {val:,.0f}</span>'
    return '<span class="neutral">— 0</span>'


@st.cache_data(ttl=60)
def load_campaigns():
    records = get_all_campaigns()
    if not records:
        return []
    return [
        {
            "label": (
                f"#{r['id']} · {r['company_name']} · "
                f"{r['sector'].title()} · "
                f"{float(r['total_budget']):,.0f} MAD · "
                f"{r['run_at'][:10]}"
            ),
            "id":                  r["id"],
            "company_name":        r["company_name"],
            "sector":              r["sector"],
            "client_type":         r["client_type"],
            "target_countries":    r["target_countries"],
            "goal":                r["goal"],
            "horizon_months":      r["horizon_months"],
            "priority":            r["priority"],
            "total_budget":        float(r["total_budget"]),
            "allowed_channels":    r["allowed_channels"],
            "age_min":             r.get("age_min", 18),
            "age_max":             r.get("age_max", 45),
            "audience_type":       r.get("audience_type", "professionals"),
            "max_pct_per_channel": r.get("max_pct_per_channel", 0.5),
            # Original allocation stored in DB
            "budget_per_channel":  r.get("budget_per_channel", "{}"),
            "pct_per_channel":     r.get("pct_per_channel", "{}"),
            "expected_leads":      r.get("expected_leads", "{}"),
            "expected_revenue":    r.get("expected_revenue", "{}"),
            "total_leads":         r.get("total_leads", 0),
            "total_revenue":       r.get("total_revenue", 0),
        }
        for r in records
    ]


def rec_to_campaign(rec: dict) -> CampaignInput:
    return CampaignInput(
        company_name        = rec["company_name"],
        sector              = rec["sector"],
        target_countries    = json.loads(rec["target_countries"]),
        client_type         = rec["client_type"],
        age_min             = int(rec["age_min"]),
        age_max             = int(rec["age_max"]),
        audience_type       = rec.get("audience_type", "professionals"),
        goal                = rec["goal"],
        horizon_months      = int(rec["horizon_months"]),
        priority            = rec["priority"],
        total_budget        = float(rec["total_budget"]),
        allowed_channels    = json.loads(rec["allowed_channels"]),
        max_pct_per_channel = float(rec.get("max_pct_per_channel", 0.5)),
    )


def rec_to_original_result(rec: dict):
    """Rebuilds AllocationResult from the stored campaign record."""
    return build_original_result_from_db(rec)


# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────
tab_log, tab_dash, tab_reopt = st.tabs([
    "📝 Log performance",
    "📊 Dashboard",
    "🔄 Re-optimize",
])


# ═══════════════════════════════════════════════════════════
# TAB 1 — LOG PERFORMANCE
# ═══════════════════════════════════════════════════════════
with tab_log:

    campaigns = load_campaigns()
    if not campaigns:
        st.info("No campaigns found. Run one in the main app first.")
        st.stop()

    st.markdown('<div class="section-hdr">1 · Select campaign</div>', unsafe_allow_html=True)

    labels  = [c["label"] for c in campaigns]
    chosen  = st.selectbox("Campaign", labels, key="log_pick")
    rec     = next(c for c in campaigns if c["label"] == chosen)
    cid     = rec["id"]
    campaign = rec_to_campaign(rec)
    channels = campaign.allowed_channels

    c1, c2, c3 = st.columns(3)
    c1.metric("Budget",   f"{int(campaign.total_budget):,} MAD")
    c2.metric("Channels", str(len(channels)))
    c3.metric("Horizon",  f"{campaign.horizon_months} months")

    st.divider()
    st.markdown('<div class="section-hdr">2 · Log this period\'s performance</div>', unsafe_allow_html=True)

    lc1, lc2 = st.columns(2)
    with lc1:
        entry_date = st.date_input(
            "Entry date",
            value=date.today(),
            key="log_date",
        )
    with lc2:
        period_label = st.text_input(
            "Period label (optional)",
            placeholder="e.g. Week 1, Day 5, Month 2",
            key="log_period",
        )

    st.caption(
        "Enter actual numbers for each channel. "
        "Channels with zero spend and zero leads will be skipped automatically."
    )
    st.divider()

    # ── Per-channel inputs ────────────────────────────────
    entries = []
    for ch in channels:
        orig_budget = json.loads(rec["budget_per_channel"]).get(ch, 0)
        st.markdown(f"**{ch_label(ch)}** — planned budget: {int(orig_budget):,} MAD")

        cc1, cc2, cc3, cc4, cc5 = st.columns(5)
        with cc1:
            impressions = st.number_input(
                "Impressions", min_value=0, value=0, step=100,
                key=f"log_imp_{ch}",
            )
        with cc2:
            clicks = st.number_input(
                "Clicks", min_value=0, value=0, step=10,
                key=f"log_clk_{ch}",
            )
        with cc3:
            spend = st.number_input(
                "Spend (MAD)", min_value=0.0, value=0.0, step=100.0,
                format="%0.0f", key=f"log_spend_{ch}",
            )
        with cc4:
            leads = st.number_input(
                "Leads", min_value=0, value=0, step=1,
                key=f"log_leads_{ch}",
            )
        with cc5:
            revenue = st.number_input(
                "Revenue (MAD)", min_value=0.0, value=0.0, step=100.0,
                format="%0.0f", key=f"log_rev_{ch}",
            )

        # Show quick derived metrics inline
        if spend > 0 and leads > 0:
            cpl_live = spend / leads
            st.caption(
                f"CPL: **{cpl_live:,.0f} MAD** · "
                f"CTR: **{clicks/impressions*100:.2f}%**"
                if impressions > 0
                else f"CPL: **{cpl_live:,.0f} MAD**"
            )

        entries.append({
            "channel":       ch,
            "impressions":   impressions,
            "clicks":        clicks,
            "spend_actual":  spend,
            "leads_actual":  leads,
            "revenue_actual":revenue,
            "notes":         "",
        })
        st.divider()

    # ── Save button ───────────────────────────────────────
    if st.button(
        "💾 Save performance log",
        type="primary",
        use_container_width=True,
        key="log_save",
    ):
        n = log_performance_batch(
            campaign_id  = cid,
            entries      = entries,
            entry_date   = entry_date,
            period_label = period_label.strip(),
        )
        if n > 0:
            st.success(
                f"✅ Saved {n} channel entries for "
                f"{entry_date.strftime('%d %b %Y')}"
                f"{f' ({period_label})' if period_label else ''}."
            )
            st.cache_data.clear()
        else:
            st.warning(
                "Nothing was saved — all channels had zero spend and zero leads. "
                "Enter at least one non-zero value."
            )

    st.divider()

    # ── Past entries ──────────────────────────────────────
    st.markdown('<div class="section-hdr">Past performance entries</div>', unsafe_allow_html=True)

    hist_df = get_performance(cid)
    if hist_df.empty:
        st.info("No entries logged yet for this campaign.")
    else:
        show_cols = ["entry_date", "period_label", "channel",
                     "spend_actual", "leads_actual", "cpl",
                     "impressions", "clicks", "ctr", "roas"]
        avail = [c for c in show_cols if c in hist_df.columns]
        disp  = hist_df[avail].copy()
        disp.columns = [c.replace("_", " ").title() for c in avail]
        st.dataframe(disp, hide_index=True, use_container_width=True)

        # Delete entry
        st.divider()
        del_id = st.number_input(
            "Delete entry by ID (use with caution)",
            min_value=1, step=1, key="del_entry_id"
        )
        if st.button("Delete entry", key="del_entry_btn"):
            delete_performance_entry(int(del_id))
            st.success(f"Entry #{del_id} deleted.")
            st.cache_data.clear()
            st.rerun()


# ═══════════════════════════════════════════════════════════
# TAB 2 — DASHBOARD
# ═══════════════════════════════════════════════════════════
with tab_dash:

    campaigns_d = load_campaigns()
    if not campaigns_d:
        st.info("No campaigns found.")
        st.stop()

    st.markdown('<div class="section-hdr">Select campaign</div>', unsafe_allow_html=True)
    labels_d  = [c["label"] for c in campaigns_d]
    chosen_d  = st.selectbox("Campaign", labels_d, key="dash_pick")
    rec_d     = next(c for c in campaigns_d if c["label"] == chosen_d)
    cid_d     = rec_d["id"]
    campaign_d = rec_to_campaign(rec_d)

    if not has_performance_data(cid_d):
        st.info(
            "No performance data logged yet for this campaign. "
            "Go to the **Log performance** tab to add entries."
        )
        st.stop()

    # ── Top KPIs ──────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-hdr">Overall performance</div>', unsafe_allow_html=True)

    summary = campaign_performance_summary(cid_d)

    km1, km2, km3, km4, km5 = st.columns(5)
    km1.metric(
        "Total spent",
        f"{int(summary['total_spent']):,} MAD",
        delta=f"{summary['total_spent'] / campaign_d.total_budget * 100:.1f}% of budget",
    )
    km2.metric("Total leads",    f"{int(summary['total_leads']):,}")
    km3.metric("Total revenue",  f"{int(summary['total_revenue']):,} MAD")
    km4.metric(
        "Blended CPL",
        f"{int(summary['blended_cpl']):,} MAD" if summary['blended_cpl'] else "—",
    )
    km5.metric(
        "Blended ROAS",
        f"{summary['blended_roas']:.2f}×" if summary['blended_roas'] else "—",
    )

    # Budget pacing
    pct_spent  = summary['total_spent'] / campaign_d.total_budget * 100 \
                 if campaign_d.total_budget > 0 else 0
    remaining  = campaign_d.total_budget - summary['total_spent']
    st.divider()
    st.markdown(f"**Budget pacing — {pct_spent:.1f}% spent**")
    st.progress(min(pct_spent / 100, 1.0))
    st.caption(f"Spent: {int(summary['total_spent']):,} MAD · Remaining: {int(remaining):,} MAD")

    st.divider()

    # ── Actual vs planned table ───────────────────────────
    st.markdown('<div class="section-hdr">Actual vs planned — by channel</div>', unsafe_allow_html=True)

    totals_df = get_totals_by_channel(cid_d)
    orig_budget = json.loads(rec_d["budget_per_channel"])
    orig_leads  = json.loads(rec_d["expected_leads"])

    table_rows = []
    for ch in campaign_d.allowed_channels:
        plan_budget  = float(orig_budget.get(ch, 0))
        plan_leads   = int(orig_leads.get(ch, 0))

        if not totals_df.empty and ch in totals_df["channel"].values:
            row = totals_df[totals_df["channel"] == ch].iloc[0]
            act_spend  = float(row.get("total_spend", 0) or 0)
            act_leads  = int(row.get("total_leads", 0) or 0)
            real_cpl   = row.get("real_cpl")
            real_cpl_s = f"{int(real_cpl):,}" if real_cpl else "—"
        else:
            act_spend = 0.0
            act_leads = 0
            real_cpl_s = "—"

        spend_diff = act_spend - plan_budget
        leads_diff = act_leads - plan_leads

        table_rows.append({
            "Channel":        ch_label(ch),
            "Plan budget":    f"{int(plan_budget):,}",
            "Actual spend":   f"{int(act_spend):,}",
            "Spend vs plan":  f"+{int(spend_diff):,}" if spend_diff >= 0 else f"{int(spend_diff):,}",
            "Plan leads":     f"{plan_leads:,}",
            "Actual leads":   f"{act_leads:,}",
            "Leads vs plan":  f"+{leads_diff:,}" if leads_diff >= 0 else f"{leads_diff:,}",
            "Real CPL (MAD)": real_cpl_s,
        })

    st.dataframe(
        pd.DataFrame(table_rows),
        hide_index=True,
        use_container_width=True,
    )

    st.divider()

    # ── Charts ────────────────────────────────────────────
    st.markdown('<div class="section-hdr">Charts</div>', unsafe_allow_html=True)

    chart1, chart2, chart3 = st.tabs([
        "Leads: actual vs planned",
        "Spend: actual vs planned",
        "CPL trend over time",
    ])

    with chart1:
        if totals_df.empty:
            st.info("No data yet.")
        else:
            channels_with_data = totals_df["channel"].tolist()
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name  = "Planned leads",
                x     = [ch_label(ch) for ch in channels_with_data],
                y     = [int(orig_leads.get(ch, 0)) for ch in channels_with_data],
                marker_color = "#e5e7eb",
                text  = [f"{int(orig_leads.get(ch,0)):,}" for ch in channels_with_data],
                textposition = "outside",
            ))
            fig.add_trace(go.Bar(
                name  = "Actual leads",
                x     = [ch_label(ch) for ch in channels_with_data],
                y     = [int(totals_df[totals_df["channel"]==ch]["total_leads"].values[0] or 0)
                         for ch in channels_with_data],
                marker_color = [ch_color(ch) for ch in channels_with_data],
                text  = [f"{int(totals_df[totals_df['channel']==ch]['total_leads'].values[0] or 0):,}"
                         for ch in channels_with_data],
                textposition = "outside",
            ))
            fig.update_layout(
                barmode = "group",
                title   = dict(text="Planned vs actual leads per channel",
                               x=0.5, xanchor="center"),
                xaxis_title = "",
                yaxis_title = "Leads",
                legend = dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
                margin = dict(t=60, b=80, l=40, r=20),
                height = 380,
                paper_bgcolor = "rgba(0,0,0,0)",
                plot_bgcolor  = "rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

    with chart2:
        if totals_df.empty:
            st.info("No data yet.")
        else:
            channels_with_data = totals_df["channel"].tolist()
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                name  = "Planned budget",
                x     = [ch_label(ch) for ch in channels_with_data],
                y     = [float(orig_budget.get(ch, 0)) for ch in channels_with_data],
                marker_color = "#e5e7eb",
                text  = [f"{int(orig_budget.get(ch,0)):,}" for ch in channels_with_data],
                textposition = "outside",
            ))
            fig2.add_trace(go.Bar(
                name  = "Actual spend",
                x     = [ch_label(ch) for ch in channels_with_data],
                y     = [float(totals_df[totals_df["channel"]==ch]["total_spend"].values[0] or 0)
                         for ch in channels_with_data],
                marker_color = [ch_color(ch) for ch in channels_with_data],
                text  = [f"{int(totals_df[totals_df['channel']==ch]['total_spend'].values[0] or 0):,}"
                         for ch in channels_with_data],
                textposition = "outside",
            ))
            fig2.update_layout(
                barmode = "group",
                title   = dict(text="Planned vs actual spend per channel (MAD)",
                               x=0.5, xanchor="center"),
                xaxis_title = "",
                yaxis_title = "MAD",
                legend = dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
                margin = dict(t=60, b=80, l=40, r=20),
                height = 380,
                paper_bgcolor = "rgba(0,0,0,0)",
                plot_bgcolor  = "rgba(0,0,0,0)",
            )
            st.plotly_chart(fig2, use_container_width=True)

    with chart3:
        trend_df = get_cpl_trend(cid_d)
        if trend_df.empty:
            st.info("Not enough data for CPL trend yet (need at least 2 entries).")
        else:
            fig3 = go.Figure()
            for ch in trend_df["channel"].unique():
                ch_df = trend_df[trend_df["channel"] == ch].copy()
                fig3.add_trace(go.Scatter(
                    x    = ch_df["entry_date"],
                    y    = ch_df["cpl"],
                    mode = "lines+markers",
                    name = ch_label(ch),
                    line = dict(color=ch_color(ch), width=2.5),
                    marker = dict(size=8, color=ch_color(ch)),
                    hovertemplate = (
                        f"<b>{ch_label(ch)}</b><br>"
                        "Date: %{x}<br>"
                        "CPL: %{y:,.0f} MAD<br>"
                        "<extra></extra>"
                    ),
                ))
            fig3.update_layout(
                title  = dict(text="CPL trend per channel over time",
                              x=0.5, xanchor="center"),
                xaxis_title = "Date",
                yaxis_title = "CPL (MAD)",
                legend = dict(orientation="h", y=-0.3, x=0.5, xanchor="center"),
                margin = dict(t=60, b=100, l=60, r=20),
                height = 400,
                hovermode = "x unified",
                paper_bgcolor = "rgba(0,0,0,0)",
                plot_bgcolor  = "rgba(0,0,0,0)",
            )
            st.plotly_chart(fig3, use_container_width=True)


# ═══════════════════════════════════════════════════════════
# TAB 3 — RE-OPTIMIZE
# ═══════════════════════════════════════════════════════════
with tab_reopt:

    campaigns_r = load_campaigns()
    if not campaigns_r:
        st.info("No campaigns found.")
        st.stop()

    st.markdown('<div class="section-hdr">Select campaign</div>', unsafe_allow_html=True)
    labels_r  = [c["label"] for c in campaigns_r]
    chosen_r  = st.selectbox("Campaign", labels_r, key="reopt_pick")
    rec_r     = next(c for c in campaigns_r if c["label"] == chosen_r)
    cid_r     = rec_r["id"]
    campaign_r = rec_to_campaign(rec_r)

    if not has_performance_data(cid_r):
        st.warning(
            "No performance data found for this campaign. "
            "Log at least one week of actual data in the **Log performance** tab first."
        )
        st.stop()

    # Show current state
    totals_r  = get_totals_by_channel(cid_r)
    summary_r = campaign_performance_summary(cid_r)

    st.divider()

    rm1, rm2, rm3 = st.columns(3)
    rm1.metric("Total spent so far",  f"{int(summary_r['total_spent']):,} MAD")
    rm2.metric("Remaining budget",
               f"{int(max(0, campaign_r.total_budget - summary_r['total_spent'])):,} MAD")
    rm3.metric("Leads so far",        f"{int(summary_r['total_leads']):,}")

    st.divider()

    # ── Original allocation ───────────────────────────────
    st.markdown('<div class="section-hdr">Current allocation (original plan)</div>', unsafe_allow_html=True)

    orig_budget_r = json.loads(rec_r["budget_per_channel"])
    orig_pct_r    = json.loads(rec_r["pct_per_channel"])
    orig_leads_r  = json.loads(rec_r["expected_leads"])

    orig_rows = []
    for ch in campaign_r.allowed_channels:
        orig_rows.append({
            "Channel":       ch_label(ch),
            "Budget (MAD)":  f"{int(float(orig_budget_r.get(ch, 0))):,}",
            "Share":         f"{float(orig_pct_r.get(ch, 0)):.1f}%",
            "Planned leads": f"{int(float(orig_leads_r.get(ch, 0))):,}",
        })
    st.dataframe(pd.DataFrame(orig_rows), hide_index=True, use_container_width=True)

    st.divider()

    # ── Re-optimize button ────────────────────────────────
    st.markdown('<div class="section-hdr">Re-optimize remaining budget</div>', unsafe_allow_html=True)
    st.markdown(
        "The optimizer will use your **actual CPL and conversion rate** "
        "data to reallocate the remaining budget. "
        "Channels that outperformed their benchmark will receive more; "
        "underperformers will be scaled back."
    )

    reopt_clicked = st.button(
        "🔄 Re-optimize budget now →",
        type="primary",
        use_container_width=True,
        key="reopt_btn",
    )

    if reopt_clicked or st.session_state.get("reopt_result_r") is not None:

        if reopt_clicked:
            with st.spinner("Re-running optimizer with actual performance data…"):
                original_result = rec_to_original_result(rec_r)
                reopt_result = reoptimize(
                    campaign        = campaign_r,
                    original_result = original_result,
                    performance_df  = totals_r,
                )
            st.session_state["reopt_result_r"]    = reopt_result
            st.session_state["reopt_campaign_id"] = cid_r

        # Only show results if they belong to this campaign
        if st.session_state.get("reopt_campaign_id") != cid_r:
            st.info("Click Re-optimize to generate a new allocation for this campaign.")
            st.stop()

        reopt_result = st.session_state["reopt_result_r"]

        st.divider()

        # ── Summary explanation ───────────────────────────
        st.info(reopt_result.summary_explanation)

        st.divider()

        # ── Side-by-side comparison ───────────────────────
        st.markdown('<div class="section-hdr">Old vs new allocation</div>', unsafe_allow_html=True)

        comparison = reopt_result.comparison
        new_result = reopt_result.new_result

        comp_rows = []
        for ch in campaign_r.allowed_channels:
            c = comparison.get(ch)
            if not c:
                continue

            delta_str = (
                f"+{c.delta_pct:.1f}pp" if c.delta_pct > 0
                else f"{c.delta_pct:.1f}pp" if c.delta_pct < 0
                else "—"
            )
            real_cpl_str = f"{int(c.real_cpl):,} MAD" if c.real_cpl else "no data"
            bench_str    = f"{int(c.benchmark_cpl):,} MAD"

            comp_rows.append({
                "Channel":          ch_label(ch),
                "Old share":        f"{c.old_pct:.1f}%",
                "New share":        f"{c.new_pct:.1f}%",
                "Change":           delta_str,
                "Old budget (MAD)": f"{int(c.old_budget):,}",
                "New budget (MAD)": f"{int(c.new_budget):,}",
                "Benchmark CPL":    bench_str,
                "Real CPL":         real_cpl_str,
            })

        st.dataframe(
            pd.DataFrame(comp_rows),
            hide_index=True,
            use_container_width=True,
        )

        st.divider()

        # ── Visual comparison chart ───────────────────────
        channels_list = campaign_r.allowed_channels
        fig_comp = go.Figure()

        fig_comp.add_trace(go.Bar(
            name         = "Original allocation %",
            x            = [ch_label(ch) for ch in channels_list],
            y            = [comparison[ch].old_pct if ch in comparison else 0
                            for ch in channels_list],
            marker_color = "#e5e7eb",
            text         = [f"{comparison[ch].old_pct:.1f}%" if ch in comparison else "0%"
                            for ch in channels_list],
            textposition = "outside",
        ))

        fig_comp.add_trace(go.Bar(
            name         = "New allocation %",
            x            = [ch_label(ch) for ch in channels_list],
            y            = [comparison[ch].new_pct if ch in comparison else 0
                            for ch in channels_list],
            marker_color = [ch_color(ch) for ch in channels_list],
            text         = [f"{comparison[ch].new_pct:.1f}%" if ch in comparison else "0%"
                            for ch in channels_list],
            textposition = "outside",
        ))

        fig_comp.update_layout(
            barmode     = "group",
            title       = dict(text="Original vs re-optimized allocation",
                               x=0.5, xanchor="center"),
            xaxis_title = "",
            yaxis_title = "Share (%)",
            legend      = dict(orientation="h", y=-0.2, x=0.5, xanchor="center"),
            margin      = dict(t=60, b=80, l=40, r=20),
            height      = 380,
            paper_bgcolor = "rgba(0,0,0,0)",
            plot_bgcolor  = "rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_comp, use_container_width=True)

        st.divider()

        # ── Per-channel explanations ──────────────────────
        st.markdown('<div class="section-hdr">Why each channel changed</div>', unsafe_allow_html=True)
        for ch in campaign_r.allowed_channels:
            c = comparison.get(ch)
            if not c:
                continue
            with st.expander(
                f"{ch_label(ch)} — "
                f"{c.old_pct:.1f}% → {c.new_pct:.1f}% "
                f"({'↑' if c.delta_pct > 0 else '↓' if c.delta_pct < 0 else '→'} "
                f"{abs(c.delta_pct):.1f}pp)"
            ):
                st.markdown(c.explanation)

        st.divider()

        # ── Download new allocation ───────────────────────
        import io as _io
        import pandas as _pd

        export_rows = []
        for ch in campaign_r.allowed_channels:
            c = comparison.get(ch)
            if not c:
                continue
            export_rows.append({
                "Channel":              ch,
                "Original_budget_MAD":  int(c.old_budget),
                "Original_share_pct":   c.old_pct,
                "New_budget_MAD":       int(c.new_budget),
                "New_share_pct":        c.new_pct,
                "Delta_pp":             c.delta_pct,
                "Benchmark_CPL_MAD":    int(c.benchmark_cpl),
                "Real_CPL_MAD":         int(c.real_cpl) if c.real_cpl else "",
                "New_expected_leads":   int(new_result.expected_leads.get(ch, 0)),
            })

        export_df  = _pd.DataFrame(export_rows)
        csv_buffer = _io.StringIO()
        export_df.to_csv(csv_buffer, index=False)

        st.download_button(
            label     = "⬇ Download new allocation as CSV",
            data      = csv_buffer.getvalue(),
            file_name = (
                f"reoptimized_{rec_r['company_name'].replace(' ','_')}"
                f"_{rec_r['sector']}.csv"
            ),
            mime = "text/csv",
        )