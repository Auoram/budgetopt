"""
pages/7_Learning.py
────────────────────
Streamlit page — Phase 5: Learning.

Two tabs:
  1. ML Retraining   — retrain the model with real performance data
  2. Freelancer performance — leaderboard + ratings analytics
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.auth import require_login
from core.auth_ui import show_user_sidebar

# ── Auth guard — must be first ────────────────────────────
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
    page_title            = "BudgetOpt — Learning",
    page_icon             = "🧠",
    layout                = "wide",
    initial_sidebar_state = "collapsed",
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
    '<div class="sub-title">Improve the system over time — retrain the ML model '
    'with real campaign data and track freelancer performance across campaigns.</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────
tab_ml, tab_freelancers = st.tabs([
    "🤖 ML Retraining",
    "⭐ Freelancer Performance",
])


# ═══════════════════════════════════════════════════════════
# TAB 1 — ML RETRAINING
# ═══════════════════════════════════════════════════════════
with tab_ml:

    # ── Current model info ────────────────────────────────
    st.markdown('<div class="section-hdr">Current model status</div>', unsafe_allow_html=True)

    model_info = get_last_retrain_info()

    if not model_info["trained"]:
        st.error(
            "No model found. Run the main app once to generate the initial model."
        )
    else:
        mi1, mi2, mi3, mi4 = st.columns(4)
        mi1.metric("Last trained",      model_info["trained_at"])
        mi2.metric("Total training rows", f"{model_info['total_rows']:,}")
        mi3.metric("Real data rows",    f"{model_info['n_real']:,}")
        mi4.metric("Synthetic rows",    f"{model_info['n_synthetic']:,}")

        if model_info["n_real"] > 0:
            pct_real = model_info["n_real"] / model_info["total_rows"] * 100
            st.success(
                f"✅ Model includes **{model_info['n_real']} real performance rows** "
                f"({pct_real:.1f}% of training data). "
                f"The more real data, the more accurate predictions become."
            )
        else:
            st.info(
                "Model is currently trained on **synthetic data only**. "
                "Log performance data in the Monitoring page, then retrain here "
                "to improve accuracy for your specific campaigns."
            )

    st.divider()

    # ── Available real data ───────────────────────────────
    st.markdown('<div class="section-hdr">Real performance data available for retraining</div>', unsafe_allow_html=True)

    n_available = count_retraining_rows()

    ra1, ra2 = st.columns(2)
    ra1.metric(
        "Rows ready to add",
        str(n_available),
        delta="minimum 5 required" if n_available < 5 else "ready to retrain",
        delta_color="off" if n_available < 5 else "normal",
    )
    ra2.metric(
        "Status",
        "✅ Ready" if n_available >= 5 else "⏳ Need more data",
    )

    if n_available == 0:
        st.warning(
            "No performance data found. "
            "Go to **page 6 (Monitoring)** → Log performance tab "
            "and enter actual channel metrics first."
        )
    elif n_available < 5:
        st.warning(
            f"Only {n_available} performance row(s) logged. "
            f"Need at least 5 before retraining — "
            f"log more performance data in the Monitoring page."
        )
    else:
        st.success(
            f"{n_available} real performance rows available. "
            f"Click **Retrain model** below to incorporate them."
        )

    # ── Preview data ──────────────────────────────────────
    if n_available > 0:
        with st.expander(f"Preview {n_available} rows that will be added"):
            preview_df = preview_retraining_data()
            if not preview_df.empty:
                show_cols = [
                    "sector", "cluster", "channel", "client_type",
                    "budget_mad", "actual_leads", "actual_cpl", "conv_rate",
                ]
                avail = [c for c in show_cols if c in preview_df.columns]
                disp  = preview_df[avail].copy()
                disp.columns = [c.replace("_", " ").title() for c in avail]
                if "Actual Cpl" in disp.columns:
                    disp["Actual Cpl"] = disp["Actual Cpl"].apply(
                        lambda x: f"{x:,.0f} MAD" if pd.notna(x) else "—"
                    )
                if "Budget Mad" in disp.columns:
                    disp["Budget Mad"] = disp["Budget Mad"].apply(
                        lambda x: f"{int(x):,}" if pd.notna(x) else "—"
                    )
                st.dataframe(disp, hide_index=True, use_container_width=True)
                st.caption(
                    "These rows are derived from your campaign_performance table. "
                    "Each row represents one channel's real performance in one session."
                )

    st.divider()

    # ── Retrain button ────────────────────────────────────
    st.markdown('<div class="section-hdr">Retrain model</div>', unsafe_allow_html=True)
    st.markdown(
        "Retraining appends your real performance data to the training dataset "
        "and re-fits both the CPL and conversion rate prediction models. "
        "The process takes about 10–20 seconds."
    )

    col_btn, col_info = st.columns([1, 2])

    with col_btn:
        retrain_clicked = st.button(
            "🔁 Retrain model now",
            type            = "primary",
            use_container_width = True,
            disabled        = (n_available < 5),
            key             = "retrain_btn",
        )

    with col_info:
        if n_available < 5:
            st.info(f"Need {5 - n_available} more performance row(s) to enable retraining.")

    if retrain_clicked:
        with st.spinner("Retraining… this takes about 15 seconds…"):
            result = retrain_from_performance(min_rows=5)

        if "error" in result:
            st.error(result["error"])
        else:
            st.success("✅ Model retrained successfully!")
            st.balloons()

            rm1, rm2, rm3, rm4 = st.columns(4)
            rm1.metric("New rows added",   result["n_new_rows"])
            rm2.metric("Total rows now",   result["n_after"])
            rm3.metric("CPL model MAE",    f"{result['cpl_mae']} MAD")
            rm4.metric("Conv rate MAE",    f"{result['conv_mae']:.4f}")

            st.caption(
                f"Training set: {result['n_train']:,} rows · "
                f"Test set: {result['n_test']:,} rows · "
                f"Retrained at {result['retrained_at'][:19]}"
            )

            st.info(
                "The model is now live. The next time you run a campaign allocation "
                "on page 1 or 2, predictions will use your real performance data."
            )

    st.divider()

    # ── What improves after retraining ───────────────────
    st.markdown('<div class="section-hdr">What improves after retraining</div>', unsafe_allow_html=True)
    st.markdown("""
    The ML model predicts two things per channel: **CPL** and **conversion rate**.
    After retraining with real data:

    - If your Facebook CPL in Morocco was consistently **120 MAD** (vs the 80 MAD benchmark),
      the model will start predicting ~120 MAD for similar future campaigns — giving you
      a more realistic lead estimate.

    - If Google Ads is performing at **600+ MAD CPL** for your sector,
      the optimizer will automatically allocate less budget to it in future runs.

    - The more campaigns you log, the more the model reflects **your** market reality
      rather than generic MENA benchmarks.

    Retrain every time you finish a campaign cycle (monthly or quarterly).
    """)


# ═══════════════════════════════════════════════════════════
# TAB 2 — FREELANCER PERFORMANCE
# ═══════════════════════════════════════════════════════════
with tab_freelancers:

    scores_df = get_freelancer_scores()

    # ── Overview ──────────────────────────────────────────
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

        # ── Leaderboard ───────────────────────────────────
        st.markdown('<div class="section-hdr">⭐ Leaderboard — all rated freelancers</div>', unsafe_allow_html=True)

        display_df = scores_df.copy()

        # Star rating display
        def stars(rating):
            if pd.isna(rating) or rating == 0:
                return "—"
            full  = int(rating)
            half  = 1 if (rating - full) >= 0.5 else 0
            empty = 5 - full - half
            return "★" * full + "½" * half + "☆" * empty

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
        show["Role"]  = show["Role"].apply(
            lambda x: x.replace("_", " ").title()
        )

        st.dataframe(show, hide_index=True, use_container_width=True)

        st.divider()

        # ── Rating distribution chart ─────────────────────
        st.markdown('<div class="section-hdr">Rating distribution</div>', unsafe_allow_html=True)

        rated_only = scores_df[scores_df["n_rated"] > 0].copy()
        if not rated_only.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x            = rated_only["name"],
                y            = rated_only["avg_rating"],
                marker_color = rated_only["avg_rating"].apply(
                    lambda r: "#16a34a" if r >= 4
                    else "#f59e0b" if r >= 3
                    else "#dc2626"
                ),
                text         = rated_only["avg_rating"].apply(lambda r: f"{r:.1f}"),
                textposition = "outside",
                hovertemplate = (
                    "<b>%{x}</b><br>"
                    "Avg rating: %{y:.1f}<br>"
                    "<extra></extra>"
                ),
            ))
            fig.add_hline(
                y                  = 3.0,
                line_dash          = "dash",
                line_color         = "#6b7280",
                annotation_text    = "Threshold (3.0)",
                annotation_position= "top right",
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

        # ── By role ───────────────────────────────────────
        st.markdown('<div class="section-hdr">Performance by role</div>', unsafe_allow_html=True)

        role_summary = get_performance_summary_by_role()
        if not role_summary.empty:
            role_summary["role"] = role_summary["role"].apply(
                lambda x: x.replace("_", " ").title()
            )
            role_summary.columns = [
                "Role", "Freelancers", "Avg Rating", "Total Campaigns"
            ]
            role_summary["Avg Rating"] = role_summary["Avg Rating"].apply(
                lambda x: f"{x:.2f}"
            )
            st.dataframe(role_summary, hide_index=True, use_container_width=True)

        st.divider()

        # ── Underperformers ───────────────────────────────
        st.markdown('<div class="section-hdr">⚠️ Freelancers to review</div>', unsafe_allow_html=True)

        underperf = get_underperforming_freelancers(min_campaigns=2)
        if underperf.empty:
            st.success("No underperforming freelancers (avg rating < 3 with 2+ campaigns). ✅")
        else:
            st.warning(
                f"{len(underperf)} freelancer(s) with avg rating below 3.0 "
                f"across 2+ campaigns. Consider replacing them in future team assignments."
            )
            up_disp = underperf[[
                "name", "role", "avg_rating", "n_rated"
            ]].copy()
            up_disp.columns = ["Name", "Role", "Avg Rating", "Times Rated"]
            up_disp["Role"] = up_disp["Role"].apply(
                lambda x: x.replace("_", " ").title()
            )
            up_disp["Avg Rating"] = up_disp["Avg Rating"].apply(
                lambda x: f"{x:.1f}"
            )
            st.dataframe(up_disp, hide_index=True, use_container_width=True)

        st.divider()

        # ── How ratings affect matching ───────────────────
        st.markdown('<div class="section-hdr">How ratings affect future matching</div>', unsafe_allow_html=True)
        st.markdown("""
        When the **Team Builder** suggests freelancers for a new campaign,
        it now ranks candidates using this priority order:

        1. **Availability** — available freelancers always appear before busy ones
        2. **Rating score** — composite of avg rating (75%) + number of rated campaigns (25%)
           - A freelancer with avg **4.5 ★** across 3 campaigns scores **0.72**
           - An unrated freelancer gets a neutral score of **0.50**
           - A freelancer with avg **2.0 ★** scores **0.30** and appears last
        3. **Sector/channel affinity** — specialties matching your campaign
        4. **Experience level** — senior > mid > junior
        5. **Hourly rate** — cheaper wins on tie

        This means your best-performing freelancers will automatically
        rise to the top of suggestions for future campaigns.
        Rate every freelancer after each campaign to make matching smarter over time.
        """)