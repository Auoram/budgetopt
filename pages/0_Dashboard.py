"""
pages/0_Dashboard.py — dark-mode safe version
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import json
import sqlite3
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta

from core.auth import require_login, current_username
from core.auth_ui import show_user_sidebar

require_login()

from core.campaign_store import init_campaign_store, get_all_campaigns
from core.task_db        import init_task_tables, task_exists_for_campaign
from core.team_db        import init_team_tables, get_campaign_team
from core.startup import (
    ensure_model_exists,
    ensure_team_tables_exist,
    ensure_task_tables_exist,
    ensure_performance_tables_exist,
)
from core.feedback import init_db

ensure_model_exists()
ensure_team_tables_exist()
ensure_task_tables_exist()
ensure_performance_tables_exist()
init_db()
init_campaign_store()

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"

st.set_page_config(
    page_title            = "BudgetOpt — Dashboard",
    page_icon             = "📊",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)

with st.sidebar:
    show_user_sidebar()

st.markdown("""
<style>
.main-title   { font-size:2rem; font-weight:600; margin-bottom:0.2rem;
                color:var(--text-color); }
.sub-title    { font-size:1rem; color:#888; margin-bottom:1.5rem; }
.section-hdr  { font-size:1.05rem; font-weight:600;
                border-bottom:2px solid rgba(128,128,128,0.25);
                padding-bottom:0.4rem; margin-bottom:1rem;
                color:var(--text-color); }
.alert-row    { border-radius:8px; padding:0.7rem 1rem;
                margin-bottom:0.5rem; font-size:0.9rem;
                color:var(--text-color); }
.alert-red    { background:rgba(220,38,38,0.13);
                border-left:4px solid #dc2626; }
.alert-orange { background:rgba(249,115,22,0.13);
                border-left:4px solid #f97316; }
.alert-yellow { background:rgba(234,179,8,0.13);
                border-left:4px solid #eab308; }
.alert-blue   { background:rgba(59,130,246,0.13);
                border-left:4px solid #3b82f6; }
.alert-neutral{ background:rgba(128,128,128,0.08);
                border-left:4px solid rgba(128,128,128,0.3); }
.card-meta    { font-size:0.82rem; opacity:0.65; }
.alert-accent { color:#f87171; font-weight:600; }
.badge-form   { background:rgba(59,130,246,0.18); color:#3b82f6;
                border-radius:20px; padding:2px 8px;
                font-size:0.72rem; font-weight:600; }
.badge-chat   { background:rgba(16,185,129,0.18); color:#10b981;
                border-radius:20px; padding:2px 8px;
                font-size:0.72rem; font-weight:600; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────

def parse_json(val, default):
    if not val:
        return default
    try:
        return json.loads(val)
    except Exception:
        return default

def days_ago(iso: str) -> str:
    try:
        delta = datetime.now() - datetime.fromisoformat(iso)
        if delta.days == 0:  return "Today"
        if delta.days == 1:  return "Yesterday"
        return f"{delta.days}d ago"
    except Exception:
        return "—"

def days_until(iso_date: str) -> int:
    try:
        return (date.fromisoformat(iso_date) - date.today()).days
    except Exception:
        return 999

def get_overdue_tasks_all() -> list:
    today = date.today().isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT t.id, t.campaign_id, t.title, t.channel,
                   t.priority, t.due_date, t.status, t.assigned_to,
                   c.company_name
            FROM campaign_tasks t
            JOIN campaigns c ON t.campaign_id = c.id
            WHERE t.due_date < ? AND t.status != 'done'
            ORDER BY t.due_date ASC
        """, (today,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

def get_upcoming_tasks_all(days: int = 3) -> list:
    today = date.today().isoformat()
    soon  = (date.today() + timedelta(days=days)).isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT t.id, t.campaign_id, t.title, t.channel,
                   t.priority, t.due_date, t.status, t.assigned_to,
                   c.company_name
            FROM campaign_tasks t
            JOIN campaigns c ON t.campaign_id = c.id
            WHERE t.due_date BETWEEN ? AND ? AND t.status != 'done'
            ORDER BY t.due_date ASC
        """, (today, soon)).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

def get_blocked_tasks_all() -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT t.id, t.campaign_id, t.title, t.channel,
                   t.priority, t.due_date, t.assigned_to,
                   c.company_name
            FROM campaign_tasks t
            JOIN campaigns c ON t.campaign_id = c.id
            WHERE t.status = 'blocked'
            ORDER BY t.campaign_id
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []

def has_team(campaign_id: int) -> bool:
    return not get_campaign_team(campaign_id).empty


# ── Header ────────────────────────────────────────────────

hour     = datetime.now().hour
greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
username = current_username()

st.markdown(f'<div class="main-title">👋 {greeting}, {username}</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-title">{date.today().strftime("%A, %d %B %Y")} · '
    f"Here's what needs your attention today.</div>",
    unsafe_allow_html=True,
)

# ── Load data ─────────────────────────────────────────────

all_campaigns  = get_all_campaigns()
overdue_tasks  = get_overdue_tasks_all()
upcoming_tasks = get_upcoming_tasks_all(days=3)
blocked_tasks  = get_blocked_tasks_all()

no_team     = [c for c in all_campaigns if not has_team(c["id"])]
no_tasks    = [c for c in all_campaigns if not task_exists_for_campaign(c["id"])]
no_feedback = [c for c in all_campaigns if not c["feedback_submitted"]]

month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
this_month  = [c for c in all_campaigns if datetime.fromisoformat(c["run_at"]) >= month_start]

# ── KPI row ───────────────────────────────────────────────

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total campaigns",      len(all_campaigns))
k2.metric("This month",           len(this_month),
          delta=f"+{len(this_month)}" if this_month else None)
k3.metric("🔴 Overdue tasks",     len(overdue_tasks),
          delta="Need attention"  if overdue_tasks else "All on track",
          delta_color="inverse"   if overdue_tasks else "normal")
k4.metric("⏳ Awaiting feedback", len(no_feedback),
          delta_color="inverse"   if no_feedback else "normal")
k5.metric("🚧 Blocked tasks",     len(blocked_tasks),
          delta="Unblock needed"  if blocked_tasks else "None",
          delta_color="inverse"   if blocked_tasks else "normal")

st.divider()

col_alerts, col_activity = st.columns([3, 2], gap="large")

# ═══ LEFT — ALERTS ═══════════════════════════════════════

with col_alerts:

    # 1. Overdue
    st.markdown('<div class="section-hdr">🔴 Overdue tasks</div>', unsafe_allow_html=True)
    if not overdue_tasks:
        st.success("No overdue tasks — everything is on track. ✅")
    else:
        st.error(f"{len(overdue_tasks)} task(s) are past their due date and not done.")
        for t in overdue_tasks[:8]:
            days_late = -days_until(t["due_date"])
            ch    = t.get("channel", "").replace("_", " ").title()
            camp  = t.get("company_name", f"#{t['campaign_id']}")
            owner = t.get("assigned_to") or "Unassigned"
            st.markdown(
                f'<div class="alert-row alert-red">'
                f'<b>{t["title"]}</b> &nbsp;·&nbsp; {ch} &nbsp;·&nbsp; <i>{camp}</i><br>'
                f'<span class="card-meta">'
                f'<span class="alert-accent">⚠ {days_late} day(s) overdue</span>'
                f' &nbsp;·&nbsp; {owner}</span></div>',
                unsafe_allow_html=True,
            )
        if len(overdue_tasks) > 8:
            st.caption(f"… and {len(overdue_tasks) - 8} more.")
        if st.button("Go to Task Board →", key="btn_overdue"):
            st.switch_page("pages/5_Execution.py")

    st.divider()

    # 2. Upcoming
    st.markdown('<div class="section-hdr">🟡 Due in the next 3 days</div>', unsafe_allow_html=True)
    if not upcoming_tasks:
        st.info("No tasks due in the next 3 days.")
    else:
        for t in upcoming_tasks[:8]:
            d_left  = days_until(t["due_date"])
            ch      = t.get("channel", "").replace("_", " ").title()
            camp    = t.get("company_name", f"#{t['campaign_id']}")
            owner   = t.get("assigned_to") or "Unassigned"
            urgency = "alert-red" if d_left == 0 else "alert-orange" if d_left == 1 else "alert-yellow"
            due_str = "Today" if d_left == 0 else "Tomorrow" if d_left == 1 else f"In {d_left} days"
            st.markdown(
                f'<div class="alert-row {urgency}">'
                f'<b>{t["title"]}</b> &nbsp;·&nbsp; {ch} &nbsp;·&nbsp; <i>{camp}</i><br>'
                f'<span class="card-meta">📅 {due_str} ({t["due_date"]})'
                f' &nbsp;·&nbsp; {owner}</span></div>',
                unsafe_allow_html=True,
            )
        if len(upcoming_tasks) > 8:
            st.caption(f"… and {len(upcoming_tasks) - 8} more.")

    st.divider()

    # 3. Blocked
    st.markdown('<div class="section-hdr">🚧 Blocked tasks</div>', unsafe_allow_html=True)
    if not blocked_tasks:
        st.success("No blocked tasks. ✅")
    else:
        st.warning(f"{len(blocked_tasks)} task(s) are blocked and need attention.")
        for t in blocked_tasks[:6]:
            ch    = t.get("channel", "").replace("_", " ").title()
            camp  = t.get("company_name", f"#{t['campaign_id']}")
            owner = t.get("assigned_to") or "Unassigned"
            st.markdown(
                f'<div class="alert-row alert-orange">'
                f'<b>{t["title"]}</b> &nbsp;·&nbsp; {ch} &nbsp;·&nbsp; <i>{camp}</i><br>'
                f'<span class="card-meta">🚧 Blocked &nbsp;·&nbsp; {owner}</span></div>',
                unsafe_allow_html=True,
            )
        if st.button("Unblock tasks →", key="btn_blocked"):
            st.switch_page("pages/5_Execution.py")

    st.divider()

    # 4. No team
    st.markdown('<div class="section-hdr">👥 Campaigns without a team</div>', unsafe_allow_html=True)
    if not no_team:
        st.success("All campaigns have a team assigned. ✅")
    else:
        st.warning(f"{len(no_team)} campaign(s) have no freelancers assigned yet.")
        for c in no_team[:5]:
            countries = parse_json(c["target_countries"], [])
            st.markdown(
                f'<div class="alert-row alert-blue">'
                f'<b>{c["company_name"]}</b> &nbsp;·&nbsp; {c["sector"].title()} &nbsp;·&nbsp; {", ".join(countries)}<br>'
                f'<span class="card-meta">📅 {days_ago(c["run_at"])} &nbsp;·&nbsp; {int(c["total_budget"]):,} MAD</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if len(no_team) > 5:
            st.caption(f"… and {len(no_team) - 5} more.")
        if st.button("Assign teams →", key="btn_team"):
            st.switch_page("pages/4_Team_Builder.py")

    st.divider()

    # 5. No tasks
    st.markdown('<div class="section-hdr">🚀 Campaigns without tasks</div>', unsafe_allow_html=True)
    if not no_tasks:
        st.success("All campaigns have tasks generated. ✅")
    else:
        st.warning(f"{len(no_tasks)} campaign(s) have no tasks generated yet.")
        for c in no_tasks[:5]:
            countries = parse_json(c["target_countries"], [])
            st.markdown(
                f'<div class="alert-row alert-blue">'
                f'<b>{c["company_name"]}</b> &nbsp;·&nbsp; {c["sector"].title()} &nbsp;·&nbsp; {", ".join(countries)}<br>'
                f'<span class="card-meta">📅 {days_ago(c["run_at"])} &nbsp;·&nbsp; {int(c["total_budget"]):,} MAD</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if len(no_tasks) > 5:
            st.caption(f"… and {len(no_tasks) - 5} more.")
        if st.button("Generate tasks →", key="btn_tasks"):
            st.switch_page("pages/5_Execution.py")


# ═══ RIGHT — ACTIVITY ════════════════════════════════════

with col_activity:

    # Recent campaigns
    st.markdown('<div class="section-hdr">🕐 Recent campaigns</div>', unsafe_allow_html=True)
    if not all_campaigns:
        st.info("No campaigns yet. Use the Classic Form or AI Chat to start.")
    else:
        for c in all_campaigns[:6]:
            countries    = parse_json(c["target_countries"], [])
            source_badge = (
                '<span class="badge-chat">🤖 Chat</span>'
                if c["source"] == "chat"
                else '<span class="badge-form">📋 Form</span>'
            )
            feedback_icon = "✅" if c["feedback_submitted"] else "⏳"
            st.markdown(
                f'<div class="alert-row alert-neutral">'
                f'{source_badge} &nbsp; <b>{c["company_name"]}</b> &nbsp;·&nbsp; {c["sector"].title()}<br>'
                f'<span class="card-meta">'
                f'{", ".join(countries)} &nbsp;·&nbsp; {int(c["total_budget"]):,} MAD'
                f' &nbsp;·&nbsp; {days_ago(c["run_at"])} &nbsp;·&nbsp; Feedback: {feedback_icon}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        if st.button("View all campaigns →", key="btn_history"):
            st.switch_page("pages/3_Campaign_History.py")

    st.divider()

    # Feedback needed
    st.markdown('<div class="section-hdr">📋 Awaiting post-campaign feedback</div>', unsafe_allow_html=True)
    if not no_feedback:
        st.success("All campaigns have post-campaign feedback. ✅")
    else:
        st.warning(
            f"{len(no_feedback)} campaign(s) missing real results. "
            "Submitting feedback improves future ML predictions."
        )
        for c in no_feedback[:5]:
            countries = parse_json(c["target_countries"], [])
            st.markdown(
                f'<div class="alert-row alert-yellow">'
                f'<b>{c["company_name"]}</b> &nbsp;·&nbsp; {c["sector"].title()}<br>'
                f'<span class="card-meta">'
                f'{", ".join(countries)} &nbsp;·&nbsp; {int(c["total_budget"]):,} MAD'
                f' &nbsp;·&nbsp; {days_ago(c["run_at"])}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
        if len(no_feedback) > 5:
            st.caption(f"… and {len(no_feedback) - 5} more.")
        if st.button("Submit feedback →", key="btn_feedback"):
            st.switch_page("pages/3_Campaign_History.py")

    st.divider()

    # Quick stats
    st.markdown('<div class="section-hdr">📊 At a glance</div>', unsafe_allow_html=True)

    total_budget_all = sum(c["total_budget"] or 0 for c in all_campaigns)
    total_leads_all  = sum(c["total_leads"]  or 0 for c in all_campaigns)

    g1, g2 = st.columns(2)
    g1.metric(
        "Total budget allocated",
        f"{total_budget_all/1_000_000:.1f}M MAD"
        if total_budget_all >= 1_000_000
        else f"{total_budget_all/1_000:.0f}K MAD",
    )
    g2.metric("Total leads estimated", f"{int(total_leads_all):,}")

    if all_campaigns:
        sector_counts: dict = {}
        for c in all_campaigns:
            s = (c["sector"] or "unknown").title()
            sector_counts[s] = sector_counts.get(s, 0) + 1
        sector_df = pd.DataFrame(
            sorted(sector_counts.items(), key=lambda x: -x[1]),
            columns=["Sector", "Campaigns"],
        )
        st.markdown("**Campaigns by sector**")
        st.dataframe(sector_df, hide_index=True, use_container_width=True)