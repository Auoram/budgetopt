import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
import io

import streamlit as st
import pandas as pd

from core.data_model import (
    SECTORS, COUNTRIES, CHANNELS, GOALS,
    PRIORITIES, AUDIENCE_TYPES,
    CampaignInput, get_clusters,
    AUDIENCE_CHANNEL_AFFINITY,
)
from core.pipeline import pipeline
from core.charts import (
    pie_budget_split,
    bar_expected_leads,
    line_budget_sensitivity,
    channel_label,
)
from core.pdf_export import generate_pdf
from core.feedback import (
    init_db, save_feedback,
    get_feedback_count, retrain_with_feedback,
)
from core.startup import (
    ensure_model_exists,
    ensure_team_tables_exist,
    ensure_task_tables_exist,
    ensure_performance_tables_exist,
)
from core.feedback import init_db, save_feedback, get_feedback_count
from core.campaign_store import init_campaign_store, save_campaign_run

# ── Startup checks ────────────────────────────────────────
ensure_model_exists()               # generates ML model if missing
ensure_team_tables_exist()          # creates freelancers + campaign_team tables
ensure_task_tables_exist()          # creates campaign_tasks table
ensure_performance_tables_exist()   # creates campaign_performance table
init_db()                           # creates feedback table
init_campaign_store()               # creates campaigns table

st.set_page_config(
    page_title            = "BudgetOpt — Campaign Allocator",
    page_icon             = "📊",
    layout                = "wide",
    initial_sidebar_state = "collapsed",
)

st.markdown("""
<style>
  .main-title {
      font-size: 2rem;
      font-weight: 600;
      margin-bottom: 0.2rem;
  }
  .sub-title {
      font-size: 1rem;
      color: #666;
      margin-bottom: 2rem;
  }
  .section-header {
      font-size: 1.1rem;
      font-weight: 600;
      padding: 0.5rem 0;
      border-bottom: 2px solid #f0f0f0;
      margin-bottom: 1rem;
  }
  .section-hint {
      font-size: 0.85rem;
      color: #888;
      margin-bottom: 1rem;
  }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────

def init_session_state():
    defaults = {
        "company_name":        "",
        "sector":              SECTORS[0],
        "target_countries":    ["Morocco"],
        "client_type":         "b2c",
        "age_min":             18,
        "age_max":             45,
        "audience_type":       AUDIENCE_TYPES[1],
        "goal":                GOALS[0],
        "horizon_months":      3,
        "priority":            PRIORITIES[2],
        "total_budget":        100_000.0,
        "allowed_channels":    list(CHANNELS),
        "max_pct_pct":         50,
        "result":              None,
        "campaign":            None,
        "form_submitted":      False,
        # Feedback form state
        "feedback_submitted":      False,
        "feedback_actual_spend":   {},
        "feedback_actual_leads":   {},
        "feedback_actual_revenue": 0.0,
        "feedback_comments":       "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_session_state()


# ─────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────

st.markdown('<div class="main-title">📊 BudgetOpt</div>',
            unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">AI-powered marketing budget allocation — '
    'fill in your campaign details to get the optimal channel split.</div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────
# LAYOUT
# ─────────────────────────────────────────

col_form, col_results = st.columns([1, 1], gap="large")


# ═════════════════════════════════════════
# FORM COLUMN
# ═════════════════════════════════════════

with col_form:

    # ── Section 1 — Client & business info ──
    st.markdown(
        '<div class="section-header">1 · Client & Business Info</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-hint">Gives context — affects which channels '
        'perform best for your sector and region.</div>',
        unsafe_allow_html=True,
    )

    st.text_input(
        label       = "Company name",
        placeholder = "e.g. CashFlow Morocco",
        key         = "company_name",
    )

    st.selectbox(
        label       = "Sector",
        options     = SECTORS,
        format_func = lambda x: {
            "fintech":   "Fintech",
            "ecommerce": "E-commerce",
            "saas":      "SaaS",
            "education": "Education",
            "health":    "Health",
        }.get(x, x),
        key = "sector",
    )

    st.multiselect(
        label   = "Target countries",
        options = list(COUNTRIES.keys()),
        key     = "target_countries",
        help    = "Benchmarks are averaged across selected regions.",
    )
    if st.session_state["target_countries"]:
        clusters = get_clusters(st.session_state["target_countries"])
        st.caption(f"Regions detected: {', '.join(clusters)}")
    else:
        st.warning("Please select at least one country.")

    st.radio(
        label       = "Client type",
        options     = ["b2c", "b2b"],
        format_func = lambda x: (
            "B2C — selling to consumers"
            if x == "b2c"
            else "B2B — selling to businesses"
        ),
        horizontal = True,
        key        = "client_type",
    )

    st.divider()

    # ── Section 2 — Target audience ──
    st.markdown(
        '<div class="section-header">2 · Target Audience</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-hint">Influences which channels work best — '
        'TikTok for students, LinkedIn for business owners.</div>',
        unsafe_allow_html=True,
    )

    age_range = st.slider(
        label     = "Age range",
        min_value = 18,
        max_value = 60,
        value     = (st.session_state["age_min"],
                     st.session_state["age_max"]),
        step      = 1,
    )
    st.session_state["age_min"] = age_range[0]
    st.session_state["age_max"] = age_range[1]

    mid = (age_range[0] + age_range[1]) / 2
    if mid <= 25:
        st.caption("Gen Z — TikTok and Instagram perform best.")
    elif mid <= 35:
        st.caption("Young adults — Facebook and Instagram perform best.")
    elif mid <= 50:
        st.caption("Professionals — Google Ads and LinkedIn perform best.")
    else:
        st.caption("Senior audience — Facebook and Email perform best.")

    st.selectbox(
        label       = "Audience type",
        options     = AUDIENCE_TYPES,
        format_func = lambda x: {
            "students":        "Students — price-sensitive, high social media use",
            "professionals":   "Professionals — LinkedIn and Google receptive",
            "business_owners": "Business owners — decision-makers, B2B focus",
        }.get(x, x),
        key = "audience_type",
    )

    affinity = AUDIENCE_CHANNEL_AFFINITY[st.session_state["audience_type"]]
    top_chs  = sorted(affinity.items(), key=lambda x: -x[1])[:3]
    boosted  = ", ".join(
        f"{ch} (+{int((v - 1) * 100)}%)"
        for ch, v in top_chs if v > 1.0
    )
    if boosted:
        st.caption(f"Channels boosted for this audience: {boosted}")

    st.divider()

    # ── Section 3 — Campaign goals ──
    st.markdown(
        '<div class="section-header">3 · Campaign Goals</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-hint">Defines the optimization objective — '
        'the optimizer weights channels differently per goal.</div>',
        unsafe_allow_html=True,
    )

    st.selectbox(
        label       = "Main goal",
        options     = GOALS,
        format_func = lambda x: {
            "generate_leads":  "Generate leads — capture contact info",
            "increase_sales":  "Increase sales — direct revenue",
            "brand_awareness": "Brand awareness — reach and visibility",
        }.get(x, x),
        key = "goal",
    )

    st.slider(
        label     = "Time horizon (months)",
        min_value = 1,
        max_value = 12,
        step      = 1,
        key       = "horizon_months",
    )
    if st.session_state["horizon_months"] < 3:
        st.warning(
            f"Short horizon "
            f"({st.session_state['horizon_months']} month"
            f"{'s' if st.session_state['horizon_months'] > 1 else ''}) — "
            "SEO will receive minimal allocation."
        )
    elif st.session_state["horizon_months"] >= 6:
        st.success(
            f"Good horizon ({st.session_state['horizon_months']} months) — "
            "SEO and content channels can contribute meaningfully."
        )

    st.radio(
        label       = "Priority",
        options     = PRIORITIES,
        format_func = lambda x: {
            "low_cost":     "Low cost — minimize cost per lead",
            "high_volume":  "High volume — maximize number of leads",
            "high_quality": "High quality — maximize conversion rate",
        }.get(x, x),
        key = "priority",
    )
    st.caption({
        "low_cost":     "Weights: CPL 60% · Reach 20% · Conversion 20%",
        "high_volume":  "Weights: CPL 20% · Reach 60% · Conversion 20%",
        "high_quality": "Weights: CPL 20% · Reach 20% · Conversion 60%",
    }[st.session_state["priority"]])

    st.divider()

    # ── Section 4 — Budget & channels ──
    st.markdown(
        '<div class="section-header">4 · Budget & Channels</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-hint">Core of the system — define your total '
        'spend and which channels to consider.</div>',
        unsafe_allow_html=True,
    )

    st.number_input(
        label     = "Total budget (MAD)",
        min_value = 1_000.0,
        max_value = 100_000_000.0,
        step      = 1_000.0,
        format    = "%0.0f",
        help      = "1 USD ≈ 10 MAD.",
        key       = "total_budget",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(
            f"≈ ${st.session_state['total_budget'] / 10:,.0f} USD"
        )
    with col_b:
        st.caption(
            f"≈ €{st.session_state['total_budget'] / 11:,.0f} EUR"
        )

    st.multiselect(
        label       = "Allowed channels",
        options     = CHANNELS,
        format_func = lambda x: {
            "facebook":   "📘 Facebook Ads",
            "instagram":  "📷 Instagram Ads",
            "google_ads": "🔍 Google Ads",
            "email":      "📧 Email Marketing",
            "seo":        "🌱 SEO / Content",
            "tiktok":     "🎵 TikTok Ads",
        }.get(x, x),
        help = "Only selected channels will receive budget.",
        key  = "allowed_channels",
    )

    if not st.session_state["allowed_channels"]:
        st.error("Please select at least one channel.")
    else:
        n_ch        = len(st.session_state["allowed_channels"])
        equal_split = st.session_state["total_budget"] / n_ch
        st.caption(
            f"{n_ch} channel{'s' if n_ch > 1 else ''} selected — "
            f"equal split would be {equal_split:,.0f} MAD each."
        )

    st.divider()

    # ── Section 5 — Constraints ──
    st.markdown(
        '<div class="section-header">5 · Constraints</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="section-hint">Prevents over-reliance on '
        'one platform.</div>',
        unsafe_allow_html=True,
    )

    st.slider(
        label     = "Max % per channel",
        min_value = 10,
        max_value = 100,
        step      = 5,
        format    = "%d%%",
        key       = "max_pct_pct",
    )

    max_mad = (
        st.session_state["total_budget"] *
        st.session_state["max_pct_pct"] / 100
    )
    st.caption(
        f"Maximum {st.session_state['max_pct_pct']}% = "
        f"{max_mad:,.0f} MAD per channel."
    )

    if st.session_state["max_pct_pct"] == 100:
        st.info("No constraint — one channel could get the full budget.")
    elif st.session_state["allowed_channels"]:
        n_ch = len(st.session_state["allowed_channels"])
        if (st.session_state["max_pct_pct"] / 100) * n_ch < 1.0:
            st.warning(
                f"{n_ch} channels × {st.session_state['max_pct_pct']}% = "
                f"{st.session_state['max_pct_pct'] * n_ch}% — "
                "increase max % or add more channels."
            )

    st.divider()

    # ── Validation + Calculate button ──
    can_submit = (
        bool(st.session_state["company_name"].strip()) and
        bool(st.session_state["target_countries"])     and
        bool(st.session_state["allowed_channels"])     and
        st.session_state["total_budget"] > 0
    )

    if not can_submit:
        missing = []
        if not st.session_state["company_name"].strip():
            missing.append("company name")
        if not st.session_state["target_countries"]:
            missing.append("at least one country")
        if not st.session_state["allowed_channels"]:
            missing.append("at least one channel")
        st.warning(f"Please fill in: {', '.join(missing)}.")

    calculate_clicked = st.button(
        label               = "Calculate optimal allocation →",
        type                = "primary",
        disabled            = not can_submit,
        use_container_width = True,
    )


# ═════════════════════════════════════════
# PIPELINE CALL
# ═════════════════════════════════════════

if calculate_clicked:
    try:
        campaign = CampaignInput(
            company_name        = st.session_state["company_name"].strip(),
            sector              = st.session_state["sector"],
            target_countries    = st.session_state["target_countries"],
            client_type         = st.session_state["client_type"],
            age_min             = st.session_state["age_min"],
            age_max             = st.session_state["age_max"],
            audience_type       = st.session_state["audience_type"],
            goal                = st.session_state["goal"],
            horizon_months      = st.session_state["horizon_months"],
            priority            = st.session_state["priority"],
            total_budget        = st.session_state["total_budget"],
            allowed_channels    = st.session_state["allowed_channels"],
            max_pct_per_channel = st.session_state["max_pct_pct"] / 100,
        )

        with st.spinner("Running optimization..."):
            result = pipeline(campaign)
            save_campaign_run(campaign, result, source="form")

        st.session_state["result"]         = result
        st.session_state["campaign"]       = campaign
        st.session_state["form_submitted"] = True

    except Exception as e:
        st.error(f"Something went wrong: {e}")
        import traceback
        st.code(traceback.format_exc())
        st.session_state["result"] = None


# ═════════════════════════════════════════
# RESULTS COLUMN
# ═════════════════════════════════════════

with col_results:
    st.markdown(
        '<div class="section-header">Results</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state["form_submitted"] or \
       st.session_state["result"] is None:

        st.markdown("""
        **How it works:**
        1. Fill in your campaign details on the left
        2. Click **Calculate optimal allocation**
        3. See the recommended budget split with expected leads and revenue

        The optimizer uses:
        - Real MENA benchmark data for your sector and region
        - A machine learning model trained on 2,000+ campaign scenarios
        - Your priority to weight channels accordingly
        """)

    else:
        result   = st.session_state["result"]
        campaign = st.session_state["campaign"]

        # ── Campaign label ──
        st.markdown(
            f"**{campaign.company_name}** · "
            f"{campaign.sector.title()} · "
            f"{campaign.client_type.upper()} · "
            f"{', '.join(campaign.target_countries)}"
        )

        # ── Summary paragraph ──
        top_channel = max(
            result.pct_per_channel,
            key=result.pct_per_channel.get,
        )
        top_pct    = result.pct_per_channel[top_channel]
        top_budget = int(result.budget_per_channel[top_channel])

        cheapest_ch = min(
            result.budget_per_channel,
            key=lambda ch: (
                result.budget_per_channel[ch] /
                result.expected_leads[ch]
                if result.expected_leads[ch] > 0
                else 999999
            ),
        )
        cheapest_cpl = round(
            result.budget_per_channel[cheapest_ch] /
            result.expected_leads[cheapest_ch], 0
        ) if result.expected_leads[cheapest_ch] > 0 else 0

        st.info(
            f"For a **{campaign.sector}** campaign targeting "
            f"**{campaign.client_type.upper()}** customers in "
            f"**{', '.join(campaign.target_countries)}**, "
            f"the optimizer recommends leading with "
            f"**{channel_label(top_channel)}** "
            f"({top_pct:.0f}% · {top_budget:,} MAD) "
            f"as your primary channel. "
            f"The most cost-efficient channel is "
            f"**{channel_label(cheapest_ch)}** "
            f"at an estimated **{int(cheapest_cpl)} MAD per lead**. "
            f"Total expected output: "
            f"**{int(result.total_leads):,} leads** and "
            f"**{int(result.total_revenue):,} MAD** in revenue "
            f"over {campaign.horizon_months} month"
            f"{'s' if campaign.horizon_months > 1 else ''}."
        )

        # ── KPI metrics ──
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(
                label = "Total leads",
                value = f"{int(result.total_leads):,}",
            )
        with m2:
            st.metric(
                label = "Total revenue",
                value = f"{int(result.total_revenue):,} MAD",
            )
        with m3:
            roi = (
                result.total_revenue / campaign.total_budget * 100
                if campaign.total_budget > 0 else 0
            )
            st.metric(
                label = "Estimated ROI",
                value = f"{roi:.0f}%",
                help  = "Total expected revenue ÷ total budget × 100",
            )

        st.divider()

        # ── Tabs: table / charts ──
        tab_table, tab_charts = st.tabs([
            "Allocation table",
            "Charts",
        ])

        with tab_table:

            table_data = []
            for ch in sorted(
                result.pct_per_channel,
                key=lambda x: -result.pct_per_channel[x],
            ):
                table_data.append({
                    "Channel":       channel_label(ch),
                    "Budget (MAD)":  f"{int(result.budget_per_channel[ch]):,}",
                    "Share":         f"{result.pct_per_channel[ch]:.1f}%",
                    "Leads":         f"{int(result.expected_leads[ch]):,}",
                    "Revenue (MAD)": f"{int(result.expected_revenue[ch]):,}",
                })

            st.dataframe(
                pd.DataFrame(table_data),
                hide_index          = True,
                use_container_width = True,
            )

            # ── Export buttons ──
            exp_col1, exp_col2 = st.columns(2)

            with exp_col1:
                sorted_chs = sorted(
                    result.pct_per_channel,
                    key=lambda x: -result.pct_per_channel[x],
                )
                export_df = pd.DataFrame({
                    "Channel": sorted_chs,
                    "Budget_MAD": [
                        int(result.budget_per_channel[ch])
                        for ch in sorted_chs
                    ],
                    "Share_pct": [
                        result.pct_per_channel[ch]
                        for ch in sorted_chs
                    ],
                    "Expected_leads": [
                        int(result.expected_leads[ch])
                        for ch in sorted_chs
                    ],
                    "Expected_revenue_MAD": [
                        int(result.expected_revenue[ch])
                        for ch in sorted_chs
                    ],
                })
                meta = pd.DataFrame({
                    "Channel":             ["", "TOTAL"],
                    "Budget_MAD":          ["", int(campaign.total_budget)],
                    "Share_pct":           ["", 100],
                    "Expected_leads":      ["", int(result.total_leads)],
                    "Expected_revenue_MAD":["", int(result.total_revenue)],
                })
                full_export = pd.concat(
                    [export_df, meta], ignore_index=True
                )
                csv_buffer = io.StringIO()
                full_export.to_csv(csv_buffer, index=False)
                st.download_button(
                    label     = "⬇ Download CSV",
                    data      = csv_buffer.getvalue(),
                    file_name = (
                        f"budgetopt_"
                        f"{campaign.company_name.replace(' ','_')}"
                        f"_{campaign.sector}.csv"
                    ),
                    mime = "text/csv",
                )

            with exp_col2:
                try:
                    pdf_bytes = generate_pdf(campaign, result)
                    st.download_button(
                        label     = "⬇ Download PDF report",
                        data      = pdf_bytes,
                        file_name = (
                            f"budgetopt_"
                            f"{campaign.company_name.replace(' ','_')}"
                            f"_{campaign.sector}.pdf"
                        ),
                        mime = "application/pdf",
                    )
                except Exception as e:
                    st.warning(f"PDF generation failed: {e}")

            st.divider()

            # ── Explanations ──
            st.markdown("**Why this allocation?**")
            for ch in sorted(
                result.explanations,
                key=lambda x: -result.pct_per_channel[x],
            ):
                expl   = result.explanations[ch]
                pct    = result.pct_per_channel[ch]
                budget = int(result.budget_per_channel[ch])
                with st.expander(
                    f"{channel_label(ch)} — "
                    f"{pct:.1f}% · {budget:,} MAD"
                ):
                    st.markdown(expl)

        with tab_charts:

            ct1, ct2, ct3 = st.tabs([
                "Budget split",
                "Expected leads",
                "Budget sensitivity",
            ])

            with ct1:
                st.plotly_chart(
                    pie_budget_split(result),
                    use_container_width = True,
                )
            with ct2:
                st.plotly_chart(
                    bar_expected_leads(result),
                    use_container_width = True,
                )
            with ct3:
                with st.spinner("Computing budget sensitivity..."):
                    fig_line = line_budget_sensitivity(campaign)
                st.plotly_chart(
                    fig_line,
                    use_container_width = True,
                )

        st.divider()

        # ── Summary caption ──
        st.caption(
            f"Budget: {int(campaign.total_budget):,} MAD · "
            f"Horizon: {campaign.horizon_months} months · "
            f"Priority: {campaign.priority.replace('_', ' ').title()} · "
            f"Max per channel: {int(campaign.max_pct_per_channel * 100)}%"
        )

        st.divider()

        # ── Feedback form ─────────────────────────────────
        st.markdown(
            '<div class="section-header">'
            'Campaign Feedback (optional)</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "After your campaign ends, submit your actual results here. "
            "This improves the model's predictions for future campaigns."
        )

        if st.session_state["feedback_submitted"]:
            st.success(
                "Thank you — your feedback has been saved and will be "
                "used to improve future recommendations."
            )
            n = get_feedback_count()
            st.caption(f"Total feedback records in database: {n}")

        else:
            with st.expander("Submit post-campaign results"):

                st.markdown("**Actual spend per channel (MAD)**")
                st.caption(
                    "Enter how much you actually spent on each channel. "
                    "Leave at 0 if you did not use that channel."
                )

                actual_spend = {}
                for ch in campaign.allowed_channels:
                    recommended = int(
                        result.budget_per_channel.get(ch, 0)
                    )
                    actual_spend[ch] = st.number_input(
                        label     = (
                            f"{ch.replace('_',' ').title()} "
                            f"(recommended: {recommended:,} MAD)"
                        ),
                        min_value = 0.0,
                        max_value = float(campaign.total_budget),
                        value     = float(recommended),
                        step      = 1_000.0,
                        format    = "%0.0f",
                        key       = f"spend_{ch}",
                    )

                st.divider()

                st.markdown("**Actual leads received per channel**")
                actual_leads = {}
                for ch in campaign.allowed_channels:
                    recommended_leads = int(
                        result.expected_leads.get(ch, 0)
                    )
                    actual_leads[ch] = int(st.number_input(
                        label     = (
                            f"{ch.replace('_',' ').title()} "
                            f"(expected: {recommended_leads:,})"
                        ),
                        min_value = 0,
                        max_value = 10_000_000,
                        value     = recommended_leads,
                        step      = 10,
                        key       = f"leads_{ch}",
                    ))

                st.divider()

                actual_revenue = st.number_input(
                    label     = "Total actual revenue (MAD)",
                    min_value = 0.0,
                    value     = float(int(result.total_revenue)),
                    step      = 1_000.0,
                    format    = "%0.0f",
                    help      = "Total revenue generated by this campaign.",
                    key       = "feedback_revenue",
                )

                comments = st.text_area(
                    label       = "Comments (optional)",
                    placeholder = (
                        "e.g. Facebook underperformed due to Ramadan period. "
                        "TikTok exceeded expectations for the 18-25 segment."
                    ),
                    height = 100,
                    key    = "feedback_comments_input",
                )

                st.divider()

                st.markdown("**Recommended vs actual (preview)**")
                comparison_rows = []
                for ch in campaign.allowed_channels:
                    rec_spend  = int(result.budget_per_channel.get(ch, 0))
                    rec_leads  = int(result.expected_leads.get(ch, 0))
                    act_spend  = int(actual_spend.get(ch, 0))
                    act_leads  = actual_leads.get(ch, 0)
                    lead_diff  = act_leads - rec_leads
                    diff_str   = (
                        f"+{lead_diff}" if lead_diff >= 0
                        else str(lead_diff)
                    )
                    comparison_rows.append({
                        "Channel":    ch.replace("_"," ").title(),
                        "Rec. spend": f"{rec_spend:,}",
                        "Act. spend": f"{act_spend:,}",
                        "Rec. leads": f"{rec_leads:,}",
                        "Act. leads": f"{act_leads:,}",
                        "Leads diff": diff_str,
                    })

                st.dataframe(
                    pd.DataFrame(comparison_rows),
                    hide_index          = True,
                    use_container_width = True,
                )

                st.divider()

                submit_feedback = st.button(
                    label               = "Submit feedback →",
                    type                = "primary",
                    use_container_width = True,
                    key                 = "submit_feedback_btn",
                )

                if submit_feedback:
                    try:
                        save_feedback(
                            campaign       = campaign,
                            result         = result,
                            actual_spend   = actual_spend,
                            actual_leads   = actual_leads,
                            actual_revenue = actual_revenue,
                            comments       = comments,
                        )
                        st.session_state["feedback_submitted"] = True
                        st.rerun()

                    except Exception as e:
                        st.error(f"Failed to save feedback: {e}")
                        import traceback
                        st.code(traceback.format_exc())