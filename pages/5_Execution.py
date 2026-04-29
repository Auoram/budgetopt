"""
pages/3_Execution.py
─────────────────────
Streamlit page — Phase 3: Execution.

Tabs:
  1. Generate tasks   — pick a campaign → auto-generate task list → save
  2. Task board       — kanban-style view with status updates per task
  3. Progress         — summary metrics + overdue alerts + category breakdown
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from datetime import date, timedelta
import json

from core.data_model import CampaignInput, CHANNELS
from core.task_generator import (
    generate_tasks,
    CATEGORY_EMOJI,
    PRIORITY_COLOR,
)
from core.task_db import (
    init_task_tables,
    save_tasks,
    get_campaign_tasks,
    update_task,
    bulk_update_status,
    delete_task,
    task_exists_for_campaign,
    task_summary,
    tasks_by_category,
    overdue_tasks,
)
from core.feedback import init_db, get_all_feedback
from core.startup import ensure_model_exists, ensure_team_tables_exist

# ── Startup ────────────────────────────────────────────────
ensure_model_exists()
ensure_team_tables_exist()
init_db()
init_task_tables()

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title            = "BudgetOpt — Execution",
    page_icon             = "🚀",
    layout                = "wide",
    initial_sidebar_state = "collapsed",
)

st.markdown("""
<style>
.main-title  { font-size:2rem; font-weight:600; margin-bottom:0.2rem; }
.sub-title   { font-size:1rem; color:#666; margin-bottom:1.5rem; }
.section-hdr { font-size:1.05rem; font-weight:600; border-bottom:2px solid #f0f0f0;
               padding-bottom:0.4rem; margin-bottom:0.8rem; }
.task-card   { background:#f8f9fa; border-radius:8px; padding:0.75rem 1rem;
               margin-bottom:0.5rem; border-left:4px solid #6366f1; }
.tag-high    { background:#fee2e2; color:#991b1b; border-radius:4px;
               padding:1px 7px; font-size:0.75rem; font-weight:600; }
.tag-medium  { background:#fef9c3; color:#854d0e; border-radius:4px;
               padding:1px 7px; font-size:0.75rem; font-weight:600; }
.tag-low     { background:#dcfce7; color:#166534; border-radius:4px;
               padding:1px 7px; font-size:0.75rem; font-weight:600; }
.status-done { color:#16a34a; font-weight:600; }
.status-todo { color:#6b7280; }
.status-prog { color:#2563eb; font-weight:600; }
.status-blok { color:#dc2626; font-weight:600; }
.prog-bar-bg { background:#e5e7eb; border-radius:8px; height:12px; }
.prog-bar-fg { background:#6366f1; border-radius:8px; height:12px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🚀 Execution</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Generate a step-by-step task list for your campaign, '
    'assign tasks to team members, and track execution progress.</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────
# SHARED HELPER — load past campaigns
# ─────────────────────────────────────────
@st.cache_data(ttl=60)
def load_past_campaigns():
    records = get_all_feedback()
    if not records:
        return []
    return [
        {
            "label": (
                f"#{r['id']} · {r['company_name']} · "
                f"{r['sector'].title()} · "
                f"{r['total_budget']:,.0f} MAD"
            ),
            "id":                 r["id"],
            "company_name":       r["company_name"],
            "sector":             r["sector"],
            "client_type":        r["client_type"],
            "target_countries":   r["target_countries"],
            "goal":               r["goal"],
            "horizon_months":     r["horizon_months"],
            "priority":           r["priority"],
            "total_budget":       r["total_budget"],
            "allowed_channels":   r["allowed_channels"],
            "age_min":            r.get("age_min", 18),
            "age_max":            r.get("age_max", 45),
            "audience_type":      r.get("audience_type", "professionals"),
            "max_pct_per_channel":r.get("max_pct_per_channel", 0.5),
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


STATUS_OPTIONS  = ["todo", "in_progress", "done", "blocked"]
STATUS_LABELS   = {
    "todo":        "⬜ To do",
    "in_progress": "🔵 In progress",
    "done":        "✅ Done",
    "blocked":     "🔴 Blocked",
}
CATEGORY_ORDER  = ["Setup", "Creative", "Launch", "Monitoring", "Reporting"]

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────
tab_gen, tab_board, tab_progress = st.tabs([
    "⚙️ Generate tasks",
    "📋 Task board",
    "📊 Progress",
])


# ═══════════════════════════════════════════════════════════
# TAB 1 — GENERATE TASKS
# ═══════════════════════════════════════════════════════════
with tab_gen:

    st.markdown('<div class="section-hdr">1 · Select campaign</div>', unsafe_allow_html=True)

    past = load_past_campaigns()

    source = st.radio(
        "Campaign source",
        ["Pick from past campaigns", "Enter manually"],
        horizontal=True,
        key="gen_source",
    )

    campaign: CampaignInput | None = None
    campaign_id: int | None = None

    if source == "Pick from past campaigns":
        if not past:
            st.warning(
                "No past campaigns found. Run a campaign in the main app first, "
                "or use the manual entry option."
            )
            st.stop()

        labels = [p["label"] for p in past]
        chosen = st.selectbox("Campaign", labels, key="gen_pick")
        rec    = next(p for p in past if p["label"] == chosen)
        campaign_id = rec["id"]
        campaign    = rec_to_campaign(rec)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Sector",   campaign.sector.title())
        c2.metric("Budget",   f"{int(campaign.total_budget):,} MAD")
        c3.metric("Horizon",  f"{campaign.horizon_months} months")
        c4.metric("Channels", str(len(campaign.allowed_channels)))

    else:
        mc1, mc2 = st.columns(2)
        with mc1:
            m_company  = st.text_input("Company name", value="My Campaign", key="gen_company")
            m_sector   = st.selectbox("Sector",
                                      ["fintech","ecommerce","saas","education","health"],
                                      key="gen_sector")
            m_budget   = st.number_input("Total budget (MAD)", min_value=10_000.0,
                                         value=200_000.0, step=10_000.0, key="gen_budget")
            m_horizon  = st.slider("Horizon (months)", 1, 12, 3, key="gen_horizon")
        with mc2:
            m_channels = st.multiselect("Channels", CHANNELS,
                                        default=["facebook", "instagram", "google_ads"],
                                        key="gen_channels")
            m_client   = st.radio("Client type", ["b2c", "b2b"],
                                  horizontal=True, key="gen_client")
            m_goal     = st.selectbox("Goal",
                                      ["generate_leads","increase_sales","brand_awareness"],
                                      key="gen_goal")

        if m_channels:
            campaign    = CampaignInput(
                company_name     = m_company,
                sector           = m_sector,
                target_countries = ["Morocco"],
                client_type      = m_client,
                goal             = m_goal,
                horizon_months   = m_horizon,
                priority         = "high_quality",
                total_budget     = m_budget,
                allowed_channels = m_channels,
            )
            campaign_id = None

    if campaign is None:
        st.info("Select or define a campaign above.")
        st.stop()

    st.divider()

    # ── Start date ────────────────────────────────────────
    st.markdown('<div class="section-hdr">2 · Set campaign start date</div>', unsafe_allow_html=True)
    start_date = st.date_input(
        "Campaign start date",
        value=date.today(),
        key="gen_start_date",
    )
    st.caption(
        "Due dates for each task will be computed from this date. "
        "You can adjust individual due dates on the Task Board tab."
    )

    st.divider()

    # ── Preview tasks ─────────────────────────────────────
    st.markdown('<div class="section-hdr">3 · Preview generated tasks</div>', unsafe_allow_html=True)

    if campaign_id and task_exists_for_campaign(campaign_id):
        st.info(
            f"Tasks already exist for campaign #{campaign_id}. "
            "Generating a new list will **replace** the existing tasks."
        )

    with st.spinner("Generating task list…"):
        preview_tasks = generate_tasks(campaign)

    # Summary counts
    cats = {}
    for t in preview_tasks:
        cats[t.category] = cats.get(t.category, 0) + 1

    col_counts = st.columns(len(cats))
    for i, (cat, count) in enumerate(sorted(cats.items())):
        col_counts[i].metric(
            f"{CATEGORY_EMOJI.get(cat, '')} {cat}",
            f"{count} tasks",
        )

    st.caption(f"Total: **{len(preview_tasks)} tasks** across {len(campaign.allowed_channels)} channels.")

    # Expandable preview per category
    for cat in CATEGORY_ORDER:
        cat_tasks = [t for t in preview_tasks if t.category == cat]
        if not cat_tasks:
            continue
        with st.expander(
            f"{CATEGORY_EMOJI.get(cat, '')} {cat} — {len(cat_tasks)} tasks",
            expanded=(cat == "Setup"),
        ):
            for t in cat_tasks:
                ch_label = t.channel.replace("_", " ").title() if t.channel != "all" else "All channels"
                prio_tag = f"**{PRIORITY_COLOR.get(t.priority,'')} {t.priority.upper()}**"
                due_str  = (
                    (start_date + timedelta(days=t.due_day - 1)).strftime("%#d %b")
                    if t.due_day else "—"
                )
                st.markdown(
                    f"**{t.title}** &nbsp; {prio_tag} &nbsp; "
                    f"`{ch_label}` &nbsp; Due: **{due_str}**"
                )
                st.caption(t.description)
                st.divider()

    st.divider()

    # ── Save button ───────────────────────────────────────
    st.markdown('<div class="section-hdr">4 · Save task list</div>', unsafe_allow_html=True)

    if not campaign_id:
        st.warning(
            "Manual campaigns have no database ID. "
            "Save the campaign through the main app first, then return here to generate tasks."
        )
    else:
        if st.button(
            f"💾 Save {len(preview_tasks)} tasks for campaign #{campaign_id}",
            type="primary",
            use_container_width=True,
            key="btn_save_tasks",
        ):
            save_tasks(
                campaign_id = campaign_id,
                tasks       = preview_tasks,
                start_date  = start_date,
                replace     = True,
            )
            st.success(
                f"✅ {len(preview_tasks)} tasks saved for campaign #{campaign_id}. "
                "Go to the **Task Board** tab to manage them."
            )
            st.cache_data.clear()


# ═══════════════════════════════════════════════════════════
# TAB 2 — TASK BOARD
# ═══════════════════════════════════════════════════════════
with tab_board:

    st.markdown('<div class="section-hdr">Select campaign</div>', unsafe_allow_html=True)

    past_b = load_past_campaigns()
    if not past_b:
        st.info("No campaigns found. Run one in the main app first.")
        st.stop()

    labels_b = [p["label"] for p in past_b]
    chosen_b = st.selectbox("Campaign", labels_b, key="board_pick")
    rec_b    = next(p for p in past_b if p["label"] == chosen_b)
    cid_b    = rec_b["id"]

    if not task_exists_for_campaign(cid_b):
        st.warning(
            f"No tasks found for campaign #{cid_b}. "
            "Go to the **Generate tasks** tab first."
        )
        st.stop()

    # ── Filters ───────────────────────────────────────────
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        all_channels = ["All"] + [
            r for r in (
                get_campaign_tasks(cid_b)["channel"].unique().tolist()
                if not get_campaign_tasks(cid_b).empty else []
            )
        ]
        ch_filter = st.selectbox("Channel", all_channels, key="board_ch")
    with fc2:
        cat_filter = st.selectbox(
            "Category",
            ["All"] + CATEGORY_ORDER,
            key="board_cat",
        )
    with fc3:
        status_filter = st.selectbox(
            "Status",
            ["All"] + STATUS_OPTIONS,
            key="board_status",
        )

    df_tasks = get_campaign_tasks(
        cid_b,
        channel  = None if ch_filter  == "All" else ch_filter,
        category = None if cat_filter == "All" else cat_filter,
        status   = None if status_filter == "All" else status_filter,
    )

    if df_tasks.empty:
        st.info("No tasks match the current filters.")
        st.stop()

    st.caption(f"Showing {len(df_tasks)} task(s).")
    st.divider()

    # ── Per-task cards ────────────────────────────────────
    for _, row in df_tasks.iterrows():
        task_id  = int(row["id"])
        ch_label = row["channel"].replace("_", " ").title() if row["channel"] != "all" else "All channels"
        due_str  = row["due_date"] if pd.notna(row.get("due_date")) and row["due_date"] else f"Day {row['due_day']}"

        with st.expander(
            f"{CATEGORY_EMOJI.get(row['category'], '')} "
            f"**{row['title']}** — "
            f"{STATUS_LABELS.get(row['status'], row['status'])}",
            expanded=False,
        ):
            # Meta row
            meta_c1, meta_c2, meta_c3, meta_c4 = st.columns(4)
            meta_c1.markdown(f"**Channel:** `{ch_label}`")
            meta_c2.markdown(f"**Priority:** {PRIORITY_COLOR.get(row['priority'],'')} {row['priority'].upper()}")
            meta_c3.markdown(f"**Due:** {due_str}")
            meta_c4.markdown(f"**Role:** {row['assignee_role'].replace('_',' ').title()}")

            # Description
            st.markdown(f"> {row['description']}")

            # Edit controls
            ed1, ed2, ed3 = st.columns([2, 2, 3])

            with ed1:
                new_status = st.selectbox(
                    "Status",
                    STATUS_OPTIONS,
                    index=STATUS_OPTIONS.index(row["status"])
                          if row["status"] in STATUS_OPTIONS else 0,
                    key=f"status_{task_id}",
                    label_visibility="collapsed",
                )

            with ed2:
                new_assignee = st.text_input(
                    "Assigned to",
                    value=row.get("assigned_to") or "",
                    placeholder="Freelancer name",
                    key=f"assignee_{task_id}",
                    label_visibility="collapsed",
                )

            with ed3:
                new_notes = st.text_input(
                    "Notes",
                    value=row.get("notes") or "",
                    placeholder="Add a note…",
                    key=f"notes_{task_id}",
                    label_visibility="collapsed",
                )

            btn_c1, btn_c2 = st.columns([1, 4])
            with btn_c1:
                if st.button("Save", key=f"save_{task_id}", type="primary"):
                    update_task(
                        task_id     = task_id,
                        status      = new_status,
                        assigned_to = new_assignee.strip() or None,
                        notes       = new_notes.strip() or None,
                    )
                    st.success("Saved.")
                    st.cache_data.clear()
                    st.rerun()

    st.divider()

    # ── Bulk actions ──────────────────────────────────────
    st.markdown("**Bulk actions**")
    ba1, ba2 = st.columns([2, 3])
    with ba1:
        bulk_status = st.selectbox(
            "Set all filtered tasks to",
            STATUS_OPTIONS,
            key="bulk_status",
        )
    with ba2:
        st.write("")
        if st.button("Apply to all filtered tasks", key="bulk_apply"):
            ids = df_tasks["id"].tolist()
            bulk_update_status(ids, bulk_status)
            st.success(f"Updated {len(ids)} task(s) to **{bulk_status}**.")
            st.cache_data.clear()
            st.rerun()


# ═══════════════════════════════════════════════════════════
# TAB 3 — PROGRESS
# ═══════════════════════════════════════════════════════════
with tab_progress:

    st.markdown('<div class="section-hdr">Select campaign</div>', unsafe_allow_html=True)

    past_p = load_past_campaigns()
    if not past_p:
        st.info("No campaigns found.")
        st.stop()

    labels_p = [p["label"] for p in past_p]
    chosen_p = st.selectbox("Campaign", labels_p, key="prog_pick")
    rec_p    = next(p for p in past_p if p["label"] == chosen_p)
    cid_p    = rec_p["id"]

    if not task_exists_for_campaign(cid_p):
        st.warning(
            f"No tasks saved for campaign #{cid_p}. "
            "Generate them in the first tab."
        )
        st.stop()

    summary = task_summary(cid_p)
    st.divider()

    # ── Top metrics ───────────────────────────────────────
    st.markdown('<div class="section-hdr">Overall progress</div>', unsafe_allow_html=True)

    pm1, pm2, pm3, pm4, pm5 = st.columns(5)
    pm1.metric("Total tasks",    summary["total"])
    pm2.metric("✅ Done",         summary["done"])
    pm3.metric("🔵 In progress",  summary["in_progress"])
    pm4.metric("⬜ To do",        summary["todo"])
    pm5.metric("🔴 Blocked",      summary["blocked"])

    # Progress bar
    pct = summary["pct_done"]
    st.markdown(f"**{pct}% complete**")
    st.progress(pct / 100)

    st.divider()

    # ── By category ───────────────────────────────────────
    st.markdown('<div class="section-hdr">Progress by category</div>', unsafe_allow_html=True)

    cat_df = tasks_by_category(cid_p)
    if not cat_df.empty:
        for _, row in cat_df.iterrows():
            cat      = row["category"]
            total    = int(row["total"])
            done     = int(row["done"])
            pct_cat  = float(row["pct_done"])
            emoji    = CATEGORY_EMOJI.get(cat, "")
            c1, c2   = st.columns([3, 1])
            with c1:
                st.markdown(f"{emoji} **{cat}**")
                st.progress(pct_cat / 100)
            with c2:
                st.metric("", f"{done}/{total}", f"{pct_cat:.0f}%")

    st.divider()

    # ── Overdue tasks ─────────────────────────────────────
    st.markdown('<div class="section-hdr">Overdue tasks</div>', unsafe_allow_html=True)

    overdue_df = overdue_tasks(cid_p)
    if overdue_df.empty:
        st.success("No overdue tasks. 🎉")
    else:
        st.warning(f"⚠️ {len(overdue_df)} task(s) are past their due date and not done.")
        disp_cols = ["title", "channel", "category", "due_date", "status", "assigned_to"]
        available = [c for c in disp_cols if c in overdue_df.columns]
        disp = overdue_df[available].copy()
        disp.columns = [c.replace("_", " ").title() for c in available]
        st.dataframe(disp, hide_index=True, use_container_width=True)

    st.divider()

    # ── Full task table ───────────────────────────────────
    st.markdown('<div class="section-hdr">All tasks</div>', unsafe_allow_html=True)

    all_tasks_df = get_campaign_tasks(cid_p)
    if not all_tasks_df.empty:
        show_cols = ["title", "channel", "category", "priority",
                     "due_date", "assigned_to", "status"]
        available = [c for c in show_cols if c in all_tasks_df.columns]
        disp_all  = all_tasks_df[available].copy()
        disp_all.columns = [c.replace("_", " ").title() for c in available]
        st.dataframe(disp_all, hide_index=True, use_container_width=True)

        # Download
        csv_buf = all_tasks_df.to_csv(index=False)
        st.download_button(
            label     = "⬇ Download task list as CSV",
            data      = csv_buf,
            file_name = f"tasks_campaign_{cid_p}.csv",
            mime      = "text/csv",
        )