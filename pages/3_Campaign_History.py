import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json
import streamlit as st
import pandas as pd

from core.campaign_store import (
    init_campaign_store,
    get_all_campaigns,
    search_campaigns,
    get_campaign_by_id,
    save_feedback_on_campaign,
    get_campaign_count,
)
from core.charts import channel_label, pie_budget_split, bar_expected_leads
from core.optimizer import AllocationResult
from core.pdf_export import generate_pdf
from core.data_model import CampaignInput
import io

# ─────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────

init_campaign_store()

st.set_page_config(
    page_title = "BudgetOpt — Campaign History",
    page_icon  = "🗂️",
    layout     = "wide",
)

st.markdown("""
<style>
  .main-title { font-size:2rem; font-weight:600; margin-bottom:0.2rem; }
  .sub-title  { font-size:1rem; color:#666; margin-bottom:1.5rem; }
  .badge-form { background:#dbeafe; color:#1e40af;
                border-radius:20px; padding:2px 10px;
                font-size:0.75rem; font-weight:500; }
  .badge-chat { background:#dcfce7; color:#166534;
                border-radius:20px; padding:2px 10px;
                font-size:0.75rem; font-weight:500; }
  .badge-done { background:#fef9c3; color:#854d0e;
                border-radius:20px; padding:2px 10px;
                font-size:0.75rem; font-weight:500; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────

if "selected_id" not in st.session_state:
    st.session_state.selected_id = None
if "feedback_saved" not in st.session_state:
    st.session_state.feedback_saved = False


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def parse_json(val, default):
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default


def row_to_result(row: dict) -> AllocationResult:
    """Reconstructs an AllocationResult from a DB row."""
    return AllocationResult(
        budget_per_channel = parse_json(row["budget_per_channel"], {}),
        pct_per_channel    = parse_json(row["pct_per_channel"],    {}),
        expected_leads     = parse_json(row["expected_leads"],     {}),
        expected_revenue   = parse_json(row["expected_revenue"],   {}),
        total_leads        = row["total_leads"]   or 0,
        total_revenue      = row["total_revenue"] or 0,
        explanations       = {},
    )


def row_to_campaign(row: dict) -> CampaignInput:
    """Reconstructs a CampaignInput from a DB row."""
    return CampaignInput(
        company_name        = row["company_name"]     or "Unknown",
        sector              = row["sector"]           or "ecommerce",
        target_countries    = parse_json(row["target_countries"], ["Morocco"]),
        client_type         = row["client_type"]      or "b2c",
        age_min             = row["age_min"]          or 18,
        age_max             = row["age_max"]          or 45,
        audience_type       = row["audience_type"]    or "professionals",
        goal                = row["goal"]             or "generate_leads",
        horizon_months      = row["horizon_months"]   or 3,
        priority            = row["priority"]         or "high_quality",
        total_budget        = row["total_budget"]     or 0,
        allowed_channels    = parse_json(row["allowed_channels"], []),
        max_pct_per_channel = row["max_pct_per_channel"] or 0.5,
    )


def format_date(iso: str) -> str:
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d %b %Y, %H:%M")
    except Exception:
        return iso


def source_badge(source: str) -> str:
    if source == "chat":
        return '<span class="badge-chat">🤖 Chat</span>'
    return '<span class="badge-form">📋 Form</span>'


def feedback_badge(submitted: int) -> str:
    if submitted:
        return '<span class="badge-done">✓ Feedback submitted</span>'
    return ""


# ─────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────

st.markdown(
    '<div class="main-title">🗂️ Campaign History</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">Browse all past campaign runs, '
    'view their allocations, and submit post-campaign feedback.</div>',
    unsafe_allow_html=True,
)

total = get_campaign_count()
if total == 0:
    st.info(
        "No campaigns saved yet. Run a campaign from the "
        "**Classic Form** or **AI Chat** pages first."
    )
    st.stop()

st.caption(f"{total} campaign{'s' if total != 1 else ''} saved.")

# ─────────────────────────────────────────
# LAYOUT — list on left, detail on right
# ─────────────────────────────────────────

col_list, col_detail = st.columns([1, 2], gap="large")

# ═════════════════════════════════════════
# LEFT — SEARCH + CAMPAIGN LIST
# ═════════════════════════════════════════

with col_list:

    search = st.text_input(
        label       = "🔍 Search",
        placeholder = "Company name, sector, country...",
        label_visibility = "collapsed",
    )

    # Filter buttons
    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        show_form = st.toggle("📋 Form", value=True)
    with f_col2:
        show_chat = st.toggle("🤖 Chat", value=True)
    with f_col3:
        show_pending = st.toggle("⏳ No feedback", value=False)

    st.divider()

    # Load campaigns
    if search.strip():
        campaigns = search_campaigns(search.strip())
    else:
        campaigns = get_all_campaigns()

    # Apply source filter
    filtered = [
        c for c in campaigns
        if (show_form and c["source"] == "form")
        or (show_chat and c["source"] == "chat")
    ]

    # Apply feedback filter
    if show_pending:
        filtered = [c for c in filtered if not c["feedback_submitted"]]

    if not filtered:
        st.warning("No campaigns match your filters.")
    else:
        for c in filtered:
            countries = parse_json(c["target_countries"], [])
            label = (
                f"**{c['company_name']}** · {c['sector'].title()} · "
                f"{', '.join(countries)}"
            )
            date_str = format_date(c["run_at"])
            budget   = f"{int(c['total_budget']):,} MAD"

            is_selected = st.session_state.selected_id == c["id"]

            if st.button(
                f"{label}\n{date_str} · {budget}",
                key              = f"camp_{c['id']}",
                use_container_width = True,
                type             = "primary" if is_selected else "secondary",
            ):
                st.session_state.selected_id  = c["id"]
                st.session_state.feedback_saved = False
                st.rerun()


# ═════════════════════════════════════════
# RIGHT — CAMPAIGN DETAIL
# ═════════════════════════════════════════

with col_detail:

    if st.session_state.selected_id is None:
        st.markdown(
            "← Select a campaign from the list to view its details."
        )
        st.stop()

    row = get_campaign_by_id(st.session_state.selected_id)
    if row is None:
        st.error("Campaign not found.")
        st.stop()

    campaign = row_to_campaign(row)
    result   = row_to_result(row)

    # ── Campaign header ──────────────────────────────────
    countries = parse_json(row["target_countries"], [])
    src_badge = source_badge(row["source"])
    fb_badge  = feedback_badge(row["feedback_submitted"])

    st.markdown(
        f"## {row['company_name']}\n"
        f"{src_badge} {fb_badge}",
        unsafe_allow_html=True,
    )
    st.caption(f"Run on {format_date(row['run_at'])}")

    # ── Campaign details ─────────────────────────────────
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.metric("Sector",   row["sector"].title())
    with d2:
        st.metric("Budget",   f"{int(row['total_budget']):,} MAD")
    with d3:
        st.metric("Horizon",  f"{row['horizon_months']} months")
    with d4:
        st.metric("Priority", row["priority"].replace("_"," ").title())

    st.caption(
        f"**Countries:** {', '.join(countries)} · "
        f"**Client:** {row['client_type'].upper()} · "
        f"**Goal:** {row['goal'].replace('_',' ').title()} · "
        f"**Audience:** {(row['audience_type'] or 'N/A').replace('_',' ').title()}"
    )

    st.divider()

    # ── KPI metrics ──────────────────────────────────────
    roi = round(
        result.total_revenue / campaign.total_budget * 100
        if campaign.total_budget > 0 else 0, 1,
    )
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Total leads",   f"{int(result.total_leads):,}")
    with m2:
        st.metric("Total revenue", f"{int(result.total_revenue):,} MAD")
    with m3:
        st.metric("Estimated ROI", f"{roi:.0f}%")

    # ── Tabs: table / charts / downloads ────────────────
    tab_table, tab_charts, tab_dl = st.tabs([
        "Allocation table", "Charts", "Downloads"
    ])

    with tab_table:
        sorted_chs = sorted(
            result.pct_per_channel,
            key=lambda x: -result.pct_per_channel[x],
        )
        table_data = []
        for ch in sorted_chs:
            leads  = result.expected_leads.get(ch, 0)
            budget = result.budget_per_channel.get(ch, 0)
            cpl    = round(budget / leads, 0) if leads > 0 else 0
            table_data.append({
                "Channel":       channel_label(ch),
                "Budget (MAD)":  f"{int(budget):,}",
                "Share":         f"{result.pct_per_channel[ch]:.1f}%",
                "Est. Leads":    f"{int(leads):,}",
                "CPL (MAD)":     f"{int(cpl):,}",
                "Revenue (MAD)": f"{int(result.expected_revenue.get(ch,0)):,}",
            })
        st.dataframe(
            pd.DataFrame(table_data),
            hide_index          = True,
            use_container_width = True,
        )

    with tab_charts:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                pie_budget_split(result),
                use_container_width=True,
            )
        with c2:
            st.plotly_chart(
                bar_expected_leads(result),
                use_container_width=True,
            )

    with tab_dl:
        dl1, dl2 = st.columns(2)
        with dl1:
            export_df = pd.DataFrame({
                "Channel":              sorted_chs,
                "Budget_MAD":           [int(result.budget_per_channel[ch]) for ch in sorted_chs],
                "Share_pct":            [result.pct_per_channel[ch]         for ch in sorted_chs],
                "Expected_leads":       [int(result.expected_leads[ch])     for ch in sorted_chs],
                "Expected_revenue_MAD": [int(result.expected_revenue[ch])   for ch in sorted_chs],
            })
            csv_buf = io.StringIO()
            export_df.to_csv(csv_buf, index=False)
            st.download_button(
                label     = "⬇ Download CSV",
                data      = csv_buf.getvalue(),
                file_name = (
                    f"budgetopt_{campaign.company_name.replace(' ','_')}"
                    f"_{campaign.sector}.csv"
                ),
                mime      = "text/csv",
                key       = f"csv_hist_{row['id']}",
            )
        with dl2:
            try:
                pdf_bytes = generate_pdf(campaign, result)
                st.download_button(
                    label     = "⬇ Download PDF",
                    data      = pdf_bytes,
                    file_name = (
                        f"budgetopt_{campaign.company_name.replace(' ','_')}"
                        f"_{campaign.sector}.pdf"
                    ),
                    mime      = "application/pdf",
                    key       = f"pdf_hist_{row['id']}",
                )
            except Exception as e:
                st.warning(f"PDF generation failed: {e}")

    st.divider()

    # ── Feedback section ─────────────────────────────────
    st.markdown("### 📋 Post-campaign feedback")

    if row["feedback_submitted"]:
        # Show existing feedback
        st.success("Feedback already submitted for this campaign.")

        actual_spend  = parse_json(row["actual_spend"],  {})
        actual_leads  = parse_json(row["actual_leads"],  {})
        actual_rev    = row["actual_revenue"] or 0
        comments      = row["comments"] or ""
        feedback_date = format_date(row["feedback_at"]) if row["feedback_at"] else "—"

        st.caption(f"Submitted on {feedback_date}")

        # Comparison table: recommended vs actual
        allowed_chs = parse_json(row["allowed_channels"], [])
        comp_rows   = []
        for ch in allowed_chs:
            rec_spend = int(result.budget_per_channel.get(ch, 0))
            rec_leads = int(result.expected_leads.get(ch, 0))
            act_spend = int(actual_spend.get(ch, 0))
            act_leads = actual_leads.get(ch, 0)
            diff      = act_leads - rec_leads
            comp_rows.append({
                "Channel":    channel_label(ch),
                "Rec. spend": f"{rec_spend:,}",
                "Act. spend": f"{act_spend:,}",
                "Rec. leads": f"{rec_leads:,}",
                "Act. leads": f"{act_leads:,}",
                "Leads diff": f"+{diff}" if diff >= 0 else str(diff),
            })

        st.dataframe(
            pd.DataFrame(comp_rows),
            hide_index          = True,
            use_container_width = True,
        )

        r1, r2 = st.columns(2)
        with r1:
            st.metric("Actual revenue", f"{int(actual_rev):,} MAD")
        with r2:
            actual_roi = round(
                actual_rev / campaign.total_budget * 100
                if campaign.total_budget > 0 else 0, 1,
            )
            st.metric("Actual ROI", f"{actual_roi:.0f}%")

        if comments:
            st.markdown(f"**Comments:** {comments}")

    elif st.session_state.feedback_saved:
        st.success(
            "Thank you — your feedback has been saved successfully."
        )

    else:
        # Feedback form
        st.markdown(
            "After your campaign ends, enter your actual results below. "
            "This helps improve future predictions."
        )

        allowed_chs = parse_json(row["allowed_channels"], [])

        with st.form(key=f"feedback_form_{row['id']}"):

            st.markdown("**Actual spend per channel (MAD)**")
            actual_spend = {}
            spend_cols   = st.columns(min(len(allowed_chs), 3))
            for i, ch in enumerate(allowed_chs):
                rec = int(result.budget_per_channel.get(ch, 0))
                with spend_cols[i % 3]:
                    actual_spend[ch] = st.number_input(
                        label     = f"{channel_label(ch)}\n(rec: {rec:,})",
                        min_value = 0.0,
                        max_value = float(campaign.total_budget * 2),
                        value     = float(rec),
                        step      = 1_000.0,
                        format    = "%0.0f",
                        key       = f"spend_{row['id']}_{ch}",
                    )

            st.divider()
            st.markdown("**Actual leads per channel**")
            actual_leads = {}
            lead_cols    = st.columns(min(len(allowed_chs), 3))
            for i, ch in enumerate(allowed_chs):
                rec_leads = int(result.expected_leads.get(ch, 0))
                with lead_cols[i % 3]:
                    actual_leads[ch] = int(st.number_input(
                        label     = f"{channel_label(ch)}\n(exp: {rec_leads:,})",
                        min_value = 0,
                        max_value = 10_000_000,
                        value     = rec_leads,
                        step      = 10,
                        key       = f"leads_{row['id']}_{ch}",
                    ))

            st.divider()
            actual_revenue = st.number_input(
                label     = "Total actual revenue (MAD)",
                min_value = 0.0,
                value     = float(int(result.total_revenue)),
                step      = 1_000.0,
                format    = "%0.0f",
                key       = f"rev_{row['id']}",
            )
            comments = st.text_area(
                label       = "Comments (optional)",
                placeholder = (
                    "e.g. Facebook underperformed due to Ramadan. "
                    "TikTok exceeded expectations for 18-25 segment."
                ),
                height = 80,
                key    = f"comments_{row['id']}",
            )

            submitted = st.form_submit_button(
                "Submit feedback →",
                type               = "primary",
                use_container_width= True,
            )

        if submitted:
            ok = save_feedback_on_campaign(
                campaign_id    = row["id"],
                actual_spend   = actual_spend,
                actual_leads   = actual_leads,
                actual_revenue = actual_revenue,
                comments       = comments,
            )
            if ok:
                st.session_state.feedback_saved = True
                st.rerun()
            else:
                st.error("Failed to save feedback — campaign not found.")