"""
pages/7_Learning.py
────────────────────
Streamlit page — Phase 5: Learning.

Three tabs:
  1. Model Performance  — accuracy card + confidence intervals
  2. ML Retraining      — retrain with real performance data
  3. Freelancer performance — leaderboard + ratings analytics
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from core.auth import require_login
from core.auth_ui import show_user_sidebar

require_login()

from core.learner import (
    export_performance_for_retraining,
    count_retraining_rows,
    retrain_from_performance,
    get_last_retrain_info,
    preview_retraining_data,
    get_freelancer_scores,
    get_top_freelancers,
    get_underperforming_freelancers,
    get_performance_summary_by_role,
    get_model_metrics,
    get_channel_uncertainty,
)
from core.startup import (
    ensure_model_exists,
    ensure_team_tables_exist,
    ensure_task_tables_exist,
    ensure_performance_tables_exist,
)
from core.feedback import init_db
from core.campaign_store import init_campaign_store, get_all_campaigns
from core.auth import COMPANY_NAME, LOGO_PATH

ensure_model_exists()
ensure_team_tables_exist()
ensure_task_tables_exist()
ensure_performance_tables_exist()
init_db()
init_campaign_store()

st.set_page_config(
    page_title            = f"{COMPANY_NAME} — Learning",
    page_icon             = str(LOGO_PATH) if LOGO_PATH.exists() else "🧠",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)

st.markdown("""
<style>
.main-title   { font-size:2rem; font-weight:600; margin-bottom:0.2rem; }
.sub-title    { font-size:1rem; color:#666; margin-bottom:1.5rem; }
.section-hdr  { font-size:1.05rem; font-weight:600; border-bottom:2px solid #f0f0f0;
                padding-bottom:0.4rem; margin-bottom:0.8rem; }
.stat-box     { background:#f8f9fa; border-radius:8px; padding:0.8rem 1rem;
                border-left:4px solid #6366f1; margin-bottom:0.5rem; }
.rating-star  { color:#f59e0b; font-size:1.1rem; }
.green        { color:#16a34a; font-weight:600; }
.red          { color:#dc2626; font-weight:600; }
.gray         { color:#6b7280; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🧠 Learning</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Improve the system over time — track model accuracy, '
    'retrain with real campaign data, and monitor freelancer performance.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    show_user_sidebar()

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────

tab_perf, tab_ml, tab_freelancers = st.tabs([
    "📊 Model Performance",
    "🔁 ML Retraining",
    "⭐ Freelancer Performance",
])


# ═══════════════════════════════════════════════════════════
# TAB 1 — MODEL PERFORMANCE CARD
# ═══════════════════════════════════════════════════════════

with tab_perf:

    model_info = get_last_retrain_info()
    metrics    = get_model_metrics()

    if not model_info["trained"]:
        st.error("No model found. Run the main app once to generate the initial model.")
        st.stop()

    # ── Header info ───────────────────────────────────────
    st.markdown('<div class="section-hdr">Model overview</div>', unsafe_allow_html=True)

    ov1, ov2, ov3, ov4 = st.columns(4)
    ov1.metric("Last trained",       model_info["trained_at"])
    ov2.metric("Training rows",      f"{model_info['total_rows']:,}")
    ov3.metric("Real data rows",     f"{model_info['n_real']:,}")
    ov4.metric("Synthetic rows",     f"{model_info['n_synthetic']:,}")

    st.divider()

    # ── Accuracy metrics ──────────────────────────────────
    st.markdown('<div class="section-hdr">Accuracy metrics</div>', unsafe_allow_html=True)
    st.caption(
        "Evaluated on a held-out test set (20% of training data, never seen during training)."
    )

    if not metrics:
        st.warning(
            "Detailed metrics not available — model was trained before this version. "
            "Click **Retrain model** in the ML Retraining tab to refresh metrics."
        )
    else:
        # ── CPL model ─────────────────────────────────────
        st.markdown("**CPL prediction model** (cost per lead, in MAD)")
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "MAE",
            f"{metrics['cpl_mae']} MAD",
            help="Mean Absolute Error — average gap between predicted and actual CPL on test set.",
        )
        c2.metric(
            "±1σ uncertainty",
            f"± {metrics['cpl_std']} MAD",
            help=(
                "Average standard deviation across 200 trees. "
                "68% of predictions fall within this range of the estimate."
            ),
        )
        c3.metric(
            "R²",
            f"{metrics['cpl_r2']}",
            help="Coefficient of determination. 1.0 = perfect. >0.7 is good for marketing data.",
        )

        st.caption(
            f"Interpretation: when the model predicts a CPL of 80 MAD, "
            f"the actual value is typically within "
            f"**{metrics['cpl_mae']} MAD** of that estimate (MAE), "
            f"and the prediction uncertainty is **± {metrics['cpl_std']} MAD** (1σ)."
        )

        st.divider()

        # ── Conversion rate model ─────────────────────────
        st.markdown("**Conversion rate prediction model**")
        d1, d2, d3 = st.columns(3)
        d1.metric(
            "MAE",
            f"{metrics['conv_mae']:.4f}",
            help="Mean Absolute Error on conversion rate (0–1 scale).",
        )
        d2.metric(
            "±1σ uncertainty",
            f"± {metrics['conv_std']:.4f}",
            help="Average std across 200 trees on the test set.",
        )
        d3.metric(
            "R²",
            f"{metrics['conv_r2']}",
        )
        st.caption(
            f"Interpretation: a predicted conversion rate of 3.0% is typically "
            f"within **{metrics['conv_mae']*100:.2f} percentage points** of actual, "
            f"with ± {metrics['conv_std']*100:.2f}pp uncertainty (1σ)."
        )

        st.divider()

        # ── Confidence interval chart ─────────────────────
        st.markdown('<div class="section-hdr">Per-channel CPL uncertainty (current model)</div>', unsafe_allow_html=True)
        st.markdown(
            "Select a campaign to see how confident the model is about its CPL "
            "prediction for each channel. Wider bars = higher uncertainty = "
            "the model has less training data for that combination."
        )

        # Let user pick a campaign to compute uncertainty for
        all_camps = get_all_campaigns()
        if not all_camps:
            st.info("No campaigns saved yet. Run a campaign first to see per-channel uncertainty.")
        else:
            camp_options = {
                f"#{c['id']} — {c['company_name']} · {c['sector']} · "
                f"{c['run_at'][:10]}": c
                for c in all_camps[:20]   # show last 20
            }
            selected_label = st.selectbox(
                "Select campaign",
                options=list(camp_options.keys()),
                key="uncertainty_camp_select",
            )
            selected_row = camp_options[selected_label]

            # Reconstruct CampaignInput
            import json as _json
            from core.data_model import CampaignInput
            try:
                camp_obj = CampaignInput(
                    company_name        = selected_row["company_name"] or "Unknown",
                    sector              = selected_row["sector"]       or "fintech",
                    target_countries    = _json.loads(selected_row["target_countries"] or '["Morocco"]'),
                    client_type         = selected_row["client_type"]  or "b2c",
                    age_min             = selected_row["age_min"]      or 18,
                    age_max             = selected_row["age_max"]      or 45,
                    audience_type       = selected_row["audience_type"] or "professionals",
                    goal                = selected_row["goal"]         or "generate_leads",
                    horizon_months      = selected_row["horizon_months"] or 3,
                    priority            = selected_row["priority"]     or "high_quality",
                    total_budget        = selected_row["total_budget"] or 100_000,
                    allowed_channels    = _json.loads(selected_row["allowed_channels"] or '[]'),
                    max_pct_per_channel = selected_row["max_pct_per_channel"] or 0.5,
                )

                with st.spinner("Computing per-tree predictions…"):
                    unc_df = get_channel_uncertainty(camp_obj)

                if not unc_df.empty and unc_df["cpl_std"].notna().any():

                    from core.charts import channel_label, get_color

                    unc_df = unc_df.sort_values("cpl_est")
                    labels = [channel_label(ch) for ch in unc_df["channel"]]
                    colors = [get_color(ch)     for ch in unc_df["channel"]]

                    fig = go.Figure()

                    # Error bars = ± 1 std
                    fig.add_trace(go.Bar(
                        x            = labels,
                        y            = unc_df["cpl_est"],
                        error_y      = dict(
                            type      = "data",
                            array     = unc_df["cpl_std"].tolist(),
                            visible   = True,
                            color     = "#6b7280",
                            thickness = 2,
                            width     = 6,
                        ),
                        marker_color = colors,
                        text         = [
                            f"{int(v)} ± {int(s)} MAD"
                            for v, s in zip(unc_df["cpl_est"], unc_df["cpl_std"])
                        ],
                        textposition = "outside",
                        hovertemplate = (
                            "<b>%{x}</b><br>"
                            "CPL estimate: %{y:.0f} MAD<br>"
                            "Uncertainty: ± %{error_y.array:.0f} MAD (1σ)<br>"
                            "<extra></extra>"
                        ),
                    ))

                    fig.update_layout(
                        title  = dict(
                            text    = "Estimated CPL per channel with uncertainty (± 1σ)",
                            x       = 0.5,
                            xanchor = "center",
                            font    = dict(size=14),
                        ),
                        xaxis_title  = "",
                        yaxis_title  = "Estimated CPL (MAD)",
                        yaxis        = dict(rangemode="tozero"),
                        margin       = dict(t=70, b=40, l=60, r=20),
                        height       = 400,
                        paper_bgcolor= "rgba(0,0,0,0)",
                        plot_bgcolor = "rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # ── Uncertainty table ──────────────────
                    st.markdown("**Detail table**")
                    tbl = pd.DataFrame({
                        "Channel":        [channel_label(ch) for ch in unc_df["channel"]],
                        "CPL estimate":   [f"{int(v):,} MAD" for v in unc_df["cpl_est"]],
                        "Lower bound":    [f"{int(v):,} MAD" for v in unc_df["cpl_low"]],
                        "Upper bound":    [f"{int(v):,} MAD" for v in unc_df["cpl_high"]],
                        "Uncertainty ±":  [f"{int(v):,} MAD" for v in unc_df["cpl_std"]],
                        "Conv. estimate": [f"{v*100:.2f}%" for v in unc_df["conv_est"]],
                    })
                    st.dataframe(tbl, hide_index=True, use_container_width=True)

                    st.caption(
                        "**How to read this:** A CPL of 80 ± 15 MAD means the model "
                        "predicts between 65 and 95 MAD with 68% confidence (1σ). "
                        "Channels with wider bars are less certain — consider "
                        "allocating a smaller test budget there first."
                    )
                else:
                    st.info(
                        "Uncertainty data not available for this campaign. "
                        "Retrain the model first using the ML Retraining tab."
                    )

            except Exception as e:
                st.warning(f"Could not compute uncertainty: {e}")

        st.divider()

        # ── What these numbers mean ───────────────────────
        st.markdown('<div class="section-hdr">How to interpret these metrics</div>', unsafe_allow_html=True)
        st.markdown(f"""
        | Metric | Value | Meaning |
        |---|---|---|
        | CPL MAE | **{metrics.get('cpl_mae', '—')} MAD** | Average prediction error on cost per lead |
        | CPL ±1σ | **± {metrics.get('cpl_std', '—')} MAD** | 68% of predictions fall within this range |
        | CPL R² | **{metrics.get('cpl_r2', '—')}** | % of CPL variance explained by the model |
        | Conv MAE | **{metrics.get('conv_mae', '—')}** | Average error on conversion rate (0–1) |
        | Conv ±1σ | **± {metrics.get('conv_std', '—')}** | Conversion rate uncertainty (1σ) |
        | Conv R² | **{metrics.get('conv_r2', '—')}** | % of conversion variance explained |

        **Why these numbers are acceptable for marketing data:**
        Marketing performance has high natural variance — the same channel,
        sector, and budget will produce different results every month due to
        seasonality, competition, and audience fatigue. A CPL MAE of ~10–30 MAD
        on a 30–200 MAD range is competitive with industry forecasting tools.
        The uncertainty bars make this variance explicit rather than hiding it
        behind a false point estimate.

        **What improves accuracy over time:**
        Every real campaign you log in the Monitoring page and retrain with
        replaces generic MENA benchmarks with your actual performance data.
        After 20–30 real rows, the model adapts to your specific market context.
        """)


# ═══════════════════════════════════════════════════════════
# TAB 2 — ML RETRAINING
# ═══════════════════════════════════════════════════════════

with tab_ml:

    st.markdown('<div class="section-hdr">Current model status</div>', unsafe_allow_html=True)

    model_info = get_last_retrain_info()

    if not model_info["trained"]:
        st.error("No model found. Run the main app once to generate the initial model.")
    else:
        mi1, mi2, mi3, mi4 = st.columns(4)
        mi1.metric("Last trained",        model_info["trained_at"])
        mi2.metric("Total training rows", f"{model_info['total_rows']:,}")
        mi3.metric("Real data rows",      f"{model_info['n_real']:,}")
        mi4.metric("Synthetic rows",      f"{model_info['n_synthetic']:,}")

        if model_info["n_real"] > 0:
            pct_real = model_info["n_real"] / model_info["total_rows"] * 100
            st.success(
                f"✅ Model includes **{model_info['n_real']} real performance rows** "
                f"({pct_real:.1f}% of training data)."
            )
        else:
            st.info(
                "Model is currently trained on **synthetic data only**. "
                "Log performance data in the Monitoring page, then retrain here."
            )

    st.divider()

    st.markdown('<div class="section-hdr">Real performance data available</div>', unsafe_allow_html=True)

    n_available = count_retraining_rows()

    ra1, ra2 = st.columns(2)
    ra1.metric(
        "Rows ready to add",
        str(n_available),
        delta="minimum 5 required" if n_available < 5 else "ready to retrain",
        delta_color="off" if n_available < 5 else "normal",
    )
    ra2.metric("Status", "✅ Ready" if n_available >= 5 else "⏳ Need more data")

    if n_available == 0:
        st.warning(
            "No performance data found. "
            "Go to **page 6 (Monitoring)** → Log performance tab first."
        )
    elif n_available < 5:
        st.warning(
            f"Only {n_available} row(s). Need at least 5 before retraining."
        )
    else:
        st.success(f"{n_available} real rows available — ready to retrain.")

    if n_available > 0:
        with st.expander(f"Preview {n_available} rows"):
            preview_df = preview_retraining_data()
            if not preview_df.empty:
                show_cols = [
                    "sector", "cluster", "channel", "client_type",
                    "budget_mad", "actual_leads", "actual_cpl", "conv_rate",
                ]
                avail = [c for c in show_cols if c in preview_df.columns]
                disp  = preview_df[avail].copy()
                disp.columns = [c.replace("_", " ").title() for c in avail]
                st.dataframe(disp, hide_index=True, use_container_width=True)

    st.divider()

    st.markdown('<div class="section-hdr">Retrain model</div>', unsafe_allow_html=True)
    st.markdown(
        "Retraining appends your real performance data to the training dataset "
        "and re-fits both models. Takes about 10–20 seconds."
    )

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        retrain_clicked = st.button(
            "🔁 Retrain model now",
            type                = "primary",
            use_container_width = True,
            disabled            = (n_available < 5),
            key                 = "retrain_btn",
        )
    with col_info:
        if n_available < 5:
            st.info(f"Need {5 - n_available} more row(s) to enable retraining.")

    if retrain_clicked:
        with st.spinner("Retraining… ~15 seconds…"):
            result = retrain_from_performance(min_rows=5)

        if "error" in result:
            st.error(result["error"])
        else:
            st.success("✅ Model retrained successfully!")
            st.balloons()

            rm1, rm2, rm3, rm4, rm5, rm6 = st.columns(6)
            rm1.metric("New rows added",  result["n_new_rows"])
            rm2.metric("Total rows now",  result["n_after"])
            rm3.metric("CPL MAE",         f"{result['cpl_mae']} MAD")
            rm4.metric("CPL ±1σ",         f"± {result.get('cpl_std', '—')} MAD")
            rm5.metric("Conv MAE",        f"{result['conv_mae']:.4f}")
            rm6.metric("CPL R²",          f"{result.get('cpl_r2', '—')}")

            st.caption(
                f"Train: {result['n_train']:,} rows · "
                f"Test: {result['n_test']:,} rows · "
                f"Retrained at {result['retrained_at'][:19]}"
            )
            st.info(
                "The model card in the **Model Performance** tab has been updated. "
                "New campaigns will use the retrained model."
            )

    st.divider()

    st.markdown('<div class="section-hdr">What improves after retraining</div>', unsafe_allow_html=True)
    st.markdown("""
    The ML model predicts two things per channel: **CPL** and **conversion rate**.
    After retraining with real data:

    - If your Facebook CPL in Morocco was consistently **120 MAD** (vs the 80 MAD benchmark),
      the model will start predicting ~120 MAD for similar future campaigns.
    - If Google Ads is performing at **600+ MAD CPL** for your sector,
      the optimizer will automatically allocate less budget to it in future runs.
    - Confidence intervals will narrow as more real data is added —
      the model becomes more certain about its predictions.

    Retrain every time you finish a campaign cycle (monthly or quarterly).
    """)


# ═══════════════════════════════════════════════════════════
# TAB 3 — FREELANCER PERFORMANCE
# ═══════════════════════════════════════════════════════════

with tab_freelancers:

    scores_df = get_freelancer_scores()

    st.markdown('<div class="section-hdr">Overview</div>', unsafe_allow_html=True)

    if scores_df.empty:
        st.info(
            "No freelancer ratings yet. "
            "Go to **page 4 (Team Builder)** → Past assignments tab "
            "and rate freelancers after each campaign."
        )
    else:
        n_rated    = len(scores_df[scores_df["n_rated"] > 0])
        avg_global = scores_df["avg_rating"].mean()
        top_score  = scores_df["score"].max()

        ov1, ov2, ov3 = st.columns(3)
        ov1.metric("Freelancers rated",   str(n_rated))
        ov2.metric("Global avg rating",   f"{avg_global:.1f} / 5")
        ov3.metric("Top performer score", f"{top_score:.2f} / 1.0")

        st.divider()

        st.markdown('<div class="section-hdr">⭐ Leaderboard</div>', unsafe_allow_html=True)

        def stars(rating):
            if pd.isna(rating) or rating == 0:
                return "—"
            full  = int(rating)
            half  = 1 if (rating - full) >= 0.5 else 0
            empty = 5 - full - half
            return "★" * full + "½" * half + "☆" * empty

        display_df = scores_df.copy()
        display_df["Rating"] = display_df["avg_rating"].apply(stars)

        show = display_df[[
            "name", "role", "avg_rating", "Rating",
            "n_rated", "n_campaigns", "score",
        ]].copy()
        show.columns = [
            "Name", "Role", "Avg Rating (num)",
            "Rating", "Times rated", "Campaigns", "Score",
        ]
        show["Avg Rating (num)"] = show["Avg Rating (num)"].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else "—"
        )
        show["Score"] = show["Score"].apply(lambda x: f"{x:.2f}")
        show["Role"]  = show["Role"].apply(lambda x: x.replace("_", " ").title())

        st.dataframe(show, hide_index=True, use_container_width=True)

        st.divider()

        st.markdown('<div class="section-hdr">Rating distribution</div>', unsafe_allow_html=True)

        rated_only = scores_df[scores_df["n_rated"] > 0].copy()
        if not rated_only.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x             = rated_only["name"],
                y             = rated_only["avg_rating"],
                marker_color  = rated_only["avg_rating"].apply(
                    lambda r: "#16a34a" if r >= 4
                    else "#f59e0b" if r >= 3
                    else "#dc2626"
                ),
                text          = rated_only["avg_rating"].apply(lambda r: f"{r:.1f}"),
                textposition  = "outside",
                hovertemplate = (
                    "<b>%{x}</b><br>Avg rating: %{y:.1f}<br><extra></extra>"
                ),
            ))
            fig.add_hline(
                y                   = 3.0,
                line_dash           = "dash",
                line_color          = "#6b7280",
                annotation_text     = "Threshold (3.0)",
                annotation_position = "top right",
            )
            fig.update_layout(
                title        = dict(text="Average rating per freelancer",
                                    x=0.5, xanchor="center"),
                xaxis_title  = "",
                yaxis_title  = "Avg rating",
                yaxis        = dict(range=[0, 5.5]),
                margin       = dict(t=60, b=60, l=40, r=20),
                height       = 380,
                paper_bgcolor= "rgba(0,0,0,0)",
                plot_bgcolor = "rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()

        st.markdown('<div class="section-hdr">Performance by role</div>', unsafe_allow_html=True)
        role_summary = get_performance_summary_by_role()
        if not role_summary.empty:
            role_summary["role"] = role_summary["role"].apply(
                lambda x: x.replace("_", " ").title()
            )
            role_summary.columns = ["Role", "Freelancers", "Avg Rating", "Total Campaigns"]
            role_summary["Avg Rating"] = role_summary["Avg Rating"].apply(
                lambda x: f"{x:.2f}"
            )
            st.dataframe(role_summary, hide_index=True, use_container_width=True)

        st.divider()

        st.markdown('<div class="section-hdr">⚠️ Freelancers to review</div>', unsafe_allow_html=True)
        underperf = get_underperforming_freelancers(min_campaigns=2)
        if underperf.empty:
            st.success("No underperforming freelancers (avg rating < 3 with 2+ campaigns). ✅")
        else:
            st.warning(
                f"{len(underperf)} freelancer(s) with avg rating below 3.0 "
                f"across 2+ campaigns."
            )
            up_disp = underperf[["name", "role", "avg_rating", "n_rated"]].copy()
            up_disp.columns = ["Name", "Role", "Avg Rating", "Times Rated"]
            up_disp["Role"]       = up_disp["Role"].apply(lambda x: x.replace("_", " ").title())
            up_disp["Avg Rating"] = up_disp["Avg Rating"].apply(lambda x: f"{x:.1f}")
            st.dataframe(up_disp, hide_index=True, use_container_width=True)

        st.divider()

        st.markdown('<div class="section-hdr">How ratings affect future matching</div>', unsafe_allow_html=True)
        st.markdown("""
        When the **Team Builder** suggests freelancers for a new campaign,
        it ranks candidates using this priority order:

        1. **Availability** — available freelancers always appear before busy ones
        2. **Rating score** — composite of avg rating (75%) + number of rated campaigns (25%)
        3. **Sector/channel affinity** — specialties matching your campaign
        4. **Experience level** — senior > mid > junior
        5. **Hourly rate** — cheaper wins on tie

        Rate every freelancer after each campaign to make matching smarter over time.
        """)