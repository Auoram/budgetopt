import base64
import streamlit as st
from pathlib import Path

LOGO_PATH    = Path(__file__).parent / "assets" / "logo.png"
# ── Edit these two lines ──────────────────────────────────
COMPANY_NAME = "V12Trading"   # ← replace with real name
TAGLINE      = "AI-powered marketing budget allocation for MENA campaigns."

st.set_page_config(
    page_title = COMPANY_NAME,
    page_icon  = str(LOGO_PATH) if LOGO_PATH.exists() else "📊",
    layout     = "centered",
)


# ─────────────────────────────────────────
# LOGO HELPER
# ─────────────────────────────────────────

def _logo_b64() -> str | None:
    try:
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return None


# ─────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────

st.markdown("""
<style>
  /* Company header block */
  .co-logo  { max-height:80px; max-width:220px;
              object-fit:contain; margin-bottom:0.6rem; }
  .co-name  { font-size:2.2rem; font-weight:800;
              letter-spacing:-0.5px; color:var(--text-color);
              margin-bottom:0.1rem; }
  .co-tag   { font-size:0.95rem; color:#888;
              margin-bottom:0.25rem; }
  .co-divider { border:none; border-top:1.5px solid rgba(128,128,128,0.18);
                margin:1.2rem 0 1.6rem; }
  /* Tool cards */
  .card     { border:1.5px solid rgba(128,128,128,0.2);
              border-radius:14px; padding:2rem 1.8rem;
              text-align:center; cursor:pointer;
              transition:box-shadow 0.2s, border-color 0.2s;
              background:rgba(128,128,128,0.04); height:100%; }
  .card:hover { box-shadow:0 4px 20px rgba(0,0,0,0.09);
                border-color:rgba(128,128,128,0.4); }
  .card-icon  { font-size:2.8rem; margin-bottom:0.7rem; }
  .card-title { font-size:1.25rem; font-weight:600;
                margin-bottom:0.5rem; color:var(--text-color); }
  .card-desc  { font-size:0.9rem; color:#777; line-height:1.5; }
  .card-tag   { display:inline-block; margin-top:1rem;
                font-size:0.75rem; background:rgba(128,128,128,0.12);
                color:#888; border-radius:20px; padding:0.2rem 0.8rem; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────
# HEADER — logo + company name + tagline
# ─────────────────────────────────────────

logo_b64 = _logo_b64()

if logo_b64:
    st.markdown(
        f"<div style='text-align:center; margin-top:2rem;'>"
        f"<img src='data:image/png;base64,{logo_b64}' class='co-logo'>"
        f"</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        "<div style='text-align:center; font-size:3rem; margin-top:2rem;'>📊</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    f"<div style='text-align:center;'>"
    f"<div class='co-name'>{COMPANY_NAME}</div>"
    f"<div class='co-tag'>{TAGLINE}</div>"
    f"</div>"
    f"<hr class='co-divider'>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div style='text-align:center; font-size:1rem; color:#888; "
    "margin-bottom:1.8rem;'>Choose how you want to get started.</div>",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────
# TOOL CARDS
# ─────────────────────────────────────────

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
        key                 = "btn_form",
        type                = "primary",
        use_container_width = True,
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
        key                 = "btn_chat",
        use_container_width = True,
    ):
        st.switch_page("pages/2_AI_Chat.py")


# ─────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────

st.divider()
st.caption(
    "Built with Streamlit · Scikit-learn · LangChain · Ollama · "
    "Real MENA benchmark data"
)