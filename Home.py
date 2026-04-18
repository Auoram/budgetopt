import streamlit as st

st.set_page_config(
    page_title = "BudgetOpt",
    page_icon  = "📊",
    layout     = "centered",
)

st.markdown("""
<style>
  .title {
    font-size: 2.6rem;
    font-weight: 700;
    text-align: center;
    margin-bottom: 0.3rem;
  }
  .subtitle {
    font-size: 1.1rem;
    color: #888;
    text-align: center;
    margin-bottom: 2.5rem;
  }
  .card {
    border: 1.5px solid #e0e0e0;
    border-radius: 14px;
    padding: 2rem 1.8rem;
    text-align: center;
    cursor: pointer;
    transition: box-shadow 0.2s;
    background: #fff;
    height: 100%;
  }
  .card:hover {
    box-shadow: 0 4px 20px rgba(0,0,0,0.09);
    border-color: #bbb;
  }
  .card-icon {
    font-size: 2.8rem;
    margin-bottom: 0.7rem;
  }
  .card-title {
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  .card-desc {
    font-size: 0.9rem;
    color: #777;
    line-height: 1.5;
  }
  .card-tag {
    display: inline-block;
    margin-top: 1rem;
    font-size: 0.75rem;
    background: #f0f0f0;
    color: #555;
    border-radius: 20px;
    padding: 0.2rem 0.8rem;
  }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────

st.markdown('<div class="title">📊 BudgetOpt</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">'
    'AI-powered marketing budget allocation for MENA campaigns.<br>'
    'Choose how you want to get started.'
    '</div>',
    unsafe_allow_html=True,
)

# ── Cards ───────────────────────────────────────────────────

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("""
    <div class="card">
      <div class="card-icon">📋</div>
      <div class="card-title">Classic Form</div>
      <div class="card-desc">
        Fill in a structured form with your campaign details —
        sector, budget, channels, goals — and get an instant
        allocation with charts and a PDF report.
      </div>
      <div class="card-tag">Best for first-time users</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(
        "Open form →",
        key                = "btn_form",
        type               = "primary",
        use_container_width= True,
    ):
        st.switch_page("pages/1_Classic_Form.py")

with col2:
    st.markdown("""
    <div class="card">
      <div class="card-icon">🤖</div>
      <div class="card-title">AI Chat</div>
      <div class="card-desc">
        Describe your campaign in plain language — English or French.
        The agent extracts all parameters automatically and recommends
        the optimal budget split.
      </div>
      <div class="card-tag">Best for quick exploration</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(
        "Open chat →",
        key                = "btn_chat",
        use_container_width= True,
    ):
        st.switch_page("pages/2_AI_Chat.py")

# ── Footer ──────────────────────────────────────────────────

st.divider()
st.caption(
    "Built with Streamlit · Scikit-learn · LangChain · Ollama · "
    "Real MENA benchmark data"
)