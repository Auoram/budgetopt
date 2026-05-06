import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import io
import streamlit as st
import pandas as pd

from core.auth import require_login
from core.auth_ui import show_user_sidebar

# ── Auth guard — must be first ────────────────────────────
require_login()

from core.data_model import CampaignInput
from core.startup import (
    ensure_model_exists,
    ensure_team_tables_exist,
    ensure_task_tables_exist,
    ensure_performance_tables_exist,
)
from core.feedback import init_db
from core.charts import channel_label
from core.pdf_export import generate_pdf
from core.langsmith_setup import setup_langsmith, get_langsmith_config
from agent.conversation import (
    ConversationState,
    BudgetAgent,
    get_welcome_message,
)
from core.campaign_store import init_campaign_store, save_campaign_run

# ─────────────────────────────────────────
# STARTUP
# setup_langsmith() must be called before
# any LangChain call so the env vars are
# set before ChatOllama is instantiated.
# ─────────────────────────────────────────

setup_langsmith()
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
    page_title            = "BudgetOpt — AI Chat",
    page_icon             = "🤖",
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
    margin-bottom: 1.5rem;
  }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────

def init_session_state():
    if "conv_state" not in st.session_state:
        st.session_state.conv_state = ConversationState()
    if "agent" not in st.session_state:
        st.session_state.agent = BudgetAgent()

init_session_state()


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def reset_conversation():
    st.session_state.conv_state = ConversationState()


def render_allocation_table(result, campaign):
    """Renders KPI metrics + allocation table + download buttons inline."""
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

    st.divider()

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

    dl_col1, dl_col2 = st.columns(2)

    with dl_col1:
        export_df = pd.DataFrame({
            "Channel":              sorted_chs,
            "Budget_MAD":           [int(result.budget_per_channel[ch]) for ch in sorted_chs],
            "Share_pct":            [result.pct_per_channel[ch]         for ch in sorted_chs],
            "Expected_leads":       [int(result.expected_leads[ch])     for ch in sorted_chs],
            "Expected_revenue_MAD": [int(result.expected_revenue[ch])   for ch in sorted_chs],
        })
        meta = pd.DataFrame({
            "Channel":              ["", "TOTAL"],
            "Budget_MAD":           ["", int(campaign.total_budget)],
            "Share_pct":            ["", 100],
            "Expected_leads":       ["", int(result.total_leads)],
            "Expected_revenue_MAD": ["", int(result.total_revenue)],
        })
        full_export = pd.concat([export_df, meta], ignore_index=True)
        csv_buf = io.StringIO()
        full_export.to_csv(csv_buf, index=False)
        st.download_button(
            label     = "⬇ Download CSV",
            data      = csv_buf.getvalue(),
            file_name = (
                f"budgetopt_"
                f"{campaign.company_name.replace(' ','_')}"
                f"_{campaign.sector}.csv"
            ),
            mime      = "text/csv",
            key       = f"csv_{id(result)}",
        )

    with dl_col2:
        try:
            pdf_bytes = generate_pdf(campaign, result)
            st.download_button(
                label     = "⬇ Download PDF",
                data      = pdf_bytes,
                file_name = (
                    f"budgetopt_"
                    f"{campaign.company_name.replace(' ','_')}"
                    f"_{campaign.sector}.pdf"
                ),
                mime      = "application/pdf",
                key       = f"pdf_{id(result)}",
            )
        except Exception as e:
            st.warning(f"PDF generation failed: {e}")

    # ── Post-campaign redirect notice ─────────────────────
    st.divider()
    st.info(
        "📋 **Campaign saved automatically.** "
        "To submit post-campaign feedback, go to "
        "**🗂️ Campaign History** in the sidebar. "
        "To track performance and re-optimize, go to "
        "**📈 Monitoring**."
    )


# ─────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────

col_title, col_reset = st.columns([5, 1])
with col_title:
    st.markdown(
        '<div class="main-title">🤖 BudgetOpt — AI Chat</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-title">Describe your campaign in plain language '
        '— the agent will extract all parameters and recommend the optimal '
        'budget allocation.</div>',
        unsafe_allow_html=True,
    )
with col_reset:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 New chat", use_container_width=True):
        reset_conversation()
        st.rerun()


# ─────────────────────────────────────────
# CHAT HISTORY
# ─────────────────────────────────────────

state = st.session_state.conv_state

if not state.messages:
    with st.chat_message("assistant"):
        st.markdown(get_welcome_message())

for i, msg in enumerate(state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if (
            msg["role"] == "assistant"
            and state.last_result is not None
            and state.last_campaign is not None
            and i == len(state.messages) - 1
        ):
            render_allocation_table(
                state.last_result,
                state.last_campaign,
            )


# ─────────────────────────────────────────
# CHAT INPUT
# ─────────────────────────────────────────

if state.waiting_for == "budget":
    placeholder = "Enter your budget (e.g. '500,000 MAD' or '$50,000')..."
elif state.waiting_for == "channels":
    placeholder = "Enter channels (e.g. 'Facebook and Instagram')..."
else:
    placeholder = "Describe your campaign (sector, country, budget, channels, goal)..."

user_input = st.chat_input(placeholder)

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response, updated_state = st.session_state.agent.process_message(
                user_input,
                st.session_state.conv_state,
            )
            st.session_state.conv_state = updated_state

        st.markdown(response)

        if (
            updated_state.last_result is not None
            and updated_state.last_campaign is not None
            and updated_state.waiting_for is None
        ):
            render_allocation_table(
                updated_state.last_result,
                updated_state.last_campaign,
            )

    st.rerun()


# ─────────────────────────────────────────
# SIDEBAR — debug + LangSmith status
# ─────────────────────────────────────────

with st.sidebar:
    show_user_sidebar()
    st.divider()
    st.markdown("### 🛠 Debug info")

    # ── LangSmith status ──────────────────
    ls_config = get_langsmith_config()
    if ls_config["tracing_enabled"] == "true" and ls_config["api_key_set"]:
        st.success("LangSmith tracing active")
        st.caption(f"Project: `{ls_config['project']}`")
        st.markdown(
            "[Open dashboard →](https://smith.langchain.com)",
            unsafe_allow_html=False,
        )
    else:
        st.warning("LangSmith tracing off")
        st.caption(
            "Set LANGCHAIN_TRACING_V2=true and "
            "LANGCHAIN_API_KEY in your .env to enable."
        )

    st.divider()

    # ── Conversation state ────────────────
    st.markdown(f"**Waiting for:** `{state.waiting_for}`")
    st.markdown(f"**Clarification count:** `{state.clarification_count}`")
    st.markdown(f"**Messages:** `{len(state.messages)}`")
    st.markdown(f"**Has result:** `{state.last_result is not None}`")

    if state.last_campaign is not None:
        st.markdown("**Last extracted campaign:**")
        camp = state.last_campaign
        st.json({
            "sector":           camp.sector,
            "countries":        camp.target_countries,
            "client_type":      camp.client_type,
            "goal":             camp.goal,
            "horizon_months":   camp.horizon_months,
            "priority":         camp.priority,
            "audience_type":    camp.audience_type,
            "total_budget":     camp.total_budget,
            "allowed_channels": camp.allowed_channels,
        })

    if state.last_extraction is not None:
        st.markdown("**Raw LLM extraction:**")
        st.json(state.last_extraction.get("raw_json", {}))

    st.divider()
    if st.button("Reset state", use_container_width=True):
        reset_conversation()
        st.rerun()