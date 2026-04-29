"""
pages/2_Team_Builder.py
───────────────────────
Streamlit page — Phase 2: Human Resources.

Flow:
  1. User picks a past campaign from history (or enters a new campaign_id).
  2. System shows which roles are required based on that campaign's channels.
  3. System shows matched freelancers per role (filtered, ranked).
  4. User selects freelancers, sets hours / budget per person.
  5. User saves the team → stored in campaign_team table.
  6. Summary card shows total team cost vs campaign budget.

Also includes a tab to manage the freelancer roster (view / add).
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime

from core.data_model import CampaignInput, CHANNELS, SECTORS
from core.team_builder import (
    build_team_plan,
    get_required_roles,
    find_matches,
    ROLE_LABELS,
)
from core.team_db import (
    init_team_tables,
    get_all_freelancers,
    get_freelancers_by_role,
    get_campaign_team,
    save_team_assignments,
    team_cost_summary,
    add_freelancer,
    update_freelancer_availability,
    rate_team_member,
    remove_team_member,
)
from core.feedback import init_db, get_all_feedback
from core.startup import ensure_model_exists

# ── Startup ───────────────────────────────────────────────
ensure_model_exists()
init_db()
init_team_tables()

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────
st.set_page_config(
    page_title  = "BudgetOpt — Team Builder",
    page_icon   = "👥",
    layout      = "wide",
    initial_sidebar_state = "collapsed",
)

st.markdown("""
<style>
.main-title   { font-size:2rem; font-weight:600; margin-bottom:0.2rem; }
.sub-title    { font-size:1rem; color:#666; margin-bottom:1.5rem; }
.section-hdr  { font-size:1.05rem; font-weight:600; border-bottom:2px solid #f0f0f0;
                padding-bottom:0.4rem; margin-bottom:0.8rem; }
.role-card    { background:#f8f9fa; border-radius:8px; padding:0.8rem 1rem;
                margin-bottom:0.6rem; border-left:4px solid #6366f1; }
.avail-yes    { color:#16a34a; font-weight:600; }
.avail-no     { color:#dc2626; font-weight:600; }
.cost-pill    { background:#ede9fe; color:#4f46e5; border-radius:20px;
                padding:2px 10px; font-size:0.8rem; font-weight:600; display:inline-block; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">👥 Team Builder</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Auto-generate a team for any campaign — '
    'match freelancers by role, assign hours, and track budget.</div>',
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────
# TABS
# ─────────────────────────────────────────
tab_assign, tab_roster, tab_history = st.tabs([
    "🎯 Assign team to campaign",
    "📋 Freelancer roster",
    "🕑 Past assignments",
])


# ═══════════════════════════════════════════════════════════
# TAB 1 — ASSIGN TEAM TO CAMPAIGN
# ═══════════════════════════════════════════════════════════
with tab_assign:

    # ── Helper: load past campaigns from feedback.db ──────
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
                    f"{r['total_budget']:,.0f} MAD · "
                    f"{r['submitted_at'][:10]}"
                ),
                "id":            r["id"],
                "company_name":  r["company_name"],
                "sector":        r["sector"],
                "client_type":   r["client_type"],
                "target_countries": r["target_countries"],  # JSON string
                "goal":          r["goal"],
                "horizon_months":r["horizon_months"],
                "priority":      r["priority"],
                "total_budget":  r["total_budget"],
                "allowed_channels": r["allowed_channels"],  # JSON string
                "age_min":       r.get("age_min", 18),
                "age_max":       r.get("age_max", 45),
                "audience_type": r.get("audience_type", "professionals"),
                "max_pct_per_channel": r.get("max_pct_per_channel", 0.5),
            }
            for r in records
        ]

    past = load_past_campaigns()

    # ── Source selection ──────────────────────────────────
    st.markdown('<div class="section-hdr">1 · Select campaign</div>', unsafe_allow_html=True)

    source = st.radio(
        "Campaign source",
        ["Pick from past campaigns", "Enter manually"],
        horizontal=True,
    )

    campaign: CampaignInput | None = None
    campaign_id: int | None = None

    if source == "Pick from past campaigns":
        if not past:
            st.warning(
                "No past campaigns found. Run a campaign in the main app first, "
                "then come back here to assign a team."
            )
        else:
            labels  = [p["label"] for p in past]
            chosen  = st.selectbox("Campaign", labels)
            rec     = next(p for p in past if p["label"] == chosen)
            campaign_id = rec["id"]

            import json
            campaign = CampaignInput(
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

            # Show campaign summary
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sector",   campaign.sector.title())
            c2.metric("Budget",   f"{int(campaign.total_budget):,} MAD")
            c3.metric("Horizon",  f"{campaign.horizon_months} months")
            c4.metric("Channels", str(len(campaign.allowed_channels)))

    else:  # Enter manually
        st.markdown("**Define a campaign to generate a team for:**")
        mc1, mc2 = st.columns(2)
        with mc1:
            m_company   = st.text_input("Company name", value="My Campaign")
            m_sector    = st.selectbox("Sector", SECTORS)
            m_budget    = st.number_input("Total budget (MAD)", min_value=10_000.0,
                                          value=200_000.0, step=10_000.0)
            m_horizon   = st.slider("Horizon (months)", 1, 12, 3)
        with mc2:
            m_channels  = st.multiselect("Channels", CHANNELS, default=["facebook", "instagram", "google_ads"])
            m_client    = st.radio("Client type", ["b2c", "b2b"], horizontal=True)
            m_goal      = st.selectbox("Goal", ["generate_leads", "increase_sales", "brand_awareness"])

        if m_channels:
            campaign = CampaignInput(
                company_name        = m_company,
                sector              = m_sector,
                target_countries    = ["Morocco"],
                client_type         = m_client,
                goal                = m_goal,
                horizon_months      = m_horizon,
                priority            = "high_quality",
                total_budget        = m_budget,
                allowed_channels    = m_channels,
            )
            campaign_id = None  # no DB record to link to

    st.divider()

    if campaign is None:
        st.info("Select or define a campaign above to generate team requirements.")
        st.stop()

    # ── Build team plan ───────────────────────────────────
    st.markdown('<div class="section-hdr">2 · Required roles & freelancer matches</div>', unsafe_allow_html=True)

    with st.spinner("Finding best freelancer matches…"):
        plan = build_team_plan(campaign, campaign_id)

    n_roles = len(plan.required_roles)
    est_cost = plan.total_estimated_cost_mad
    budget_pct = (est_cost / campaign.total_budget * 100) if campaign.total_budget > 0 else 0

    # Summary metrics
    sm1, sm2, sm3 = st.columns(3)
    sm1.metric("Roles needed",       str(n_roles))
    sm2.metric("Est. team cost",     f"{int(est_cost):,} MAD")
    sm3.metric("% of campaign budget", f"{budget_pct:.1f}%",
               delta="within budget" if budget_pct < 15 else "high — consider reducing scope",
               delta_color="normal" if budget_pct < 15 else "inverse")

    st.divider()

    # ── Per-role expanders ────────────────────────────────
    st.markdown('<div class="section-hdr">3 · Select & configure freelancers</div>', unsafe_allow_html=True)
    st.caption(
        "Expand each role to pick a freelancer and set hours. "
        "The system pre-fills hours from channel benchmarks — adjust as needed."
    )

    # Session state to hold selections
    if "team_selections" not in st.session_state:
        st.session_state["team_selections"] = {}

    for req in sorted(plan.required_roles, key=lambda r: -r.hours):
        role_label = ROLE_LABELS.get(req.role, req.role.replace("_", " ").title())
        candidates = plan.matches.get(req.role, [])

        with st.expander(
            f"{role_label} — {req.hours}h · est. "
            f"{int(req.estimated_cost_mad):,} MAD",
            expanded=(len(plan.required_roles) <= 4),
        ):
            st.caption(f"**Why needed:** {req.reason}")

            if not candidates:
                st.warning(
                    f"No freelancers found for **{role_label}** in the database. "
                    "Add one in the Freelancer Roster tab."
                )
                continue

            # Candidate cards
            cand_options = {}
            for c in candidates:
                avail_badge = (
                    '<span class="avail-yes">● available</span>'
                    if c.availability == "available"
                    else '<span class="avail-no">● busy</span>'
                )
                label = (
                    f"{c.name}  ·  {c.experience_level.title()}  ·  "
                    f"{int(c.hourly_rate_mad)} MAD/h"
                )
                cand_options[label] = c

            chosen_label = st.radio(
                "Choose freelancer",
                list(cand_options.keys()) + ["None — skip this role"],
                key=f"radio_{req.role}",
            )

            if chosen_label != "None — skip this role":
                chosen_c = cand_options[chosen_label]

                col_h, col_b = st.columns(2)
                with col_h:
                    hours = st.number_input(
                        "Hours",
                        min_value=1,
                        max_value=500,
                        value=int(req.hours),
                        step=1,
                        key=f"hours_{req.role}",
                    )
                with col_b:
                    computed_budget = hours * chosen_c.hourly_rate_mad
                    budget = st.number_input(
                        "Budget (MAD)",
                        min_value=0.0,
                        value=float(computed_budget),
                        step=500.0,
                        key=f"budget_{req.role}",
                    )

                st.caption(
                    f"Specialties: {chosen_c.specialties}  ·  "
                    f"Email: {chosen_c.email}"
                )

                st.session_state["team_selections"][req.role] = {
                    "freelancer_id": chosen_c.freelancer_id,
                    "name":          chosen_c.name,
                    "role":          req.role,
                    "hours":         hours,
                    "budget_mad":    budget,
                }
            else:
                # Remove from selections if deselected
                st.session_state["team_selections"].pop(req.role, None)

    st.divider()

    # ── Save button ───────────────────────────────────────
    st.markdown('<div class="section-hdr">4 · Confirm & save team</div>', unsafe_allow_html=True)

    selections = st.session_state.get("team_selections", {})

    if not selections:
        st.info("Select at least one freelancer above to enable saving.")
    else:
        # Preview table
        preview_rows = []
        total_team_budget = 0.0
        for role, sel in selections.items():
            preview_rows.append({
                "Role":          ROLE_LABELS.get(role, role),
                "Freelancer":    sel["name"],
                "Hours":         sel["hours"],
                "Budget (MAD)":  f"{int(sel['budget_mad']):,}",
            })
            total_team_budget += sel["budget_mad"]

        st.dataframe(pd.DataFrame(preview_rows), hide_index=True, use_container_width=True)

        tc1, tc2 = st.columns(2)
        tc1.metric("Total team budget", f"{int(total_team_budget):,} MAD")
        tc2.metric(
            "% of campaign budget",
            f"{total_team_budget / campaign.total_budget * 100:.1f}%"
            if campaign.total_budget > 0 else "—",
        )

        save_label = (
            f"Save team for campaign #{campaign_id}"
            if campaign_id
            else "Save team plan (no campaign ID — for preview only)"
        )

        if st.button(save_label, type="primary", use_container_width=True):
            if campaign_id:
                assignment_list = list(selections.values())
                n = save_team_assignments(campaign_id, assignment_list)
                st.success(
                    f"✅ Team saved — {n} freelancer(s) confirmed for campaign #{campaign_id}."
                )
                st.session_state["team_selections"] = {}
                st.cache_data.clear()
            else:
                st.info(
                    "This campaign has no database ID (manual entry). "
                    "Run it through the main app first to link a team to it."
                )

    # ── Existing team (if campaign_id known) ──────────────
    if campaign_id:
        existing = get_campaign_team(campaign_id)
        if not existing.empty:
            st.divider()
            st.markdown('<div class="section-hdr">Current confirmed team</div>', unsafe_allow_html=True)
            disp = existing[[
                "name", "role", "hours", "budget_mad", "status", "experience_level"
            ]].copy()
            disp.columns = ["Freelancer", "Role", "Hours", "Budget (MAD)", "Status", "Level"]
            disp["Budget (MAD)"] = disp["Budget (MAD)"].apply(lambda x: f"{int(x):,}")
            st.dataframe(disp, hide_index=True, use_container_width=True)

            summary = team_cost_summary(campaign_id)
            st.caption(
                f"Team: {summary['n_members']} members · "
                f"{int(summary['total_hours'])} hours · "
                f"{int(summary['total_budget_mad']):,} MAD"
            )


# ═══════════════════════════════════════════════════════════
# TAB 2 — FREELANCER ROSTER
# ═══════════════════════════════════════════════════════════
with tab_roster:
    st.markdown('<div class="section-hdr">Freelancer database</div>', unsafe_allow_html=True)

    all_fl = get_all_freelancers()

    if all_fl.empty:
        st.warning("No freelancers found. Add one below.")
    else:
        # Filters
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            role_filter = st.selectbox(
                "Filter by role",
                ["All"] + sorted(all_fl["role"].unique().tolist()),
            )
        with fc2:
            avail_filter = st.selectbox(
                "Availability",
                ["All", "available", "busy"],
            )
        with fc3:
            exp_filter = st.selectbox(
                "Experience",
                ["All", "senior", "mid", "junior"],
            )

        filtered = all_fl.copy()
        if role_filter != "All":
            filtered = filtered[filtered["role"] == role_filter]
        if avail_filter != "All":
            filtered = filtered[filtered["availability"] == avail_filter]
        if exp_filter != "All":
            filtered = filtered[filtered["experience_level"] == exp_filter]

        # Display
        display_cols = ["id", "name", "role", "specialties",
                        "availability", "hourly_rate_mad", "experience_level", "email"]
        disp = filtered[display_cols].copy()
        disp.columns = ["ID", "Name", "Role", "Specialties",
                        "Availability", "Rate (MAD/h)", "Level", "Email"]
        st.dataframe(disp, hide_index=True, use_container_width=True)
        st.caption(f"{len(filtered)} freelancer(s) shown.")

        # Toggle availability
        st.divider()
        st.markdown("**Update availability**")
        ua1, ua2, ua3 = st.columns([2, 2, 1])
        with ua1:
            toggle_id = st.number_input("Freelancer ID", min_value=1, step=1, value=1)
        with ua2:
            new_avail = st.selectbox("New status", ["available", "busy"])
        with ua3:
            st.write("")
            st.write("")
            if st.button("Update", key="update_avail"):
                update_freelancer_availability(int(toggle_id), new_avail)
                st.success(f"Freelancer #{toggle_id} set to **{new_avail}**.")
                st.cache_data.clear()
                st.rerun()

    # ── Add new freelancer ────────────────────────────────
    st.divider()
    st.markdown('<div class="section-hdr">Add new freelancer</div>', unsafe_allow_html=True)

    with st.expander("+ Add freelancer"):
        ROLES = [
            "media_buyer", "copywriter", "graphic_designer",
            "video_editor", "web_developer", "data_analyst",
            "seo_specialist", "community_manager",
            "project_manager", "translator",
        ]
        na1, na2 = st.columns(2)
        with na1:
            new_name    = st.text_input("Full name")
            new_role    = st.selectbox("Role", ROLES)
            new_specs   = st.text_input(
                "Specialties (comma-separated)",
                placeholder="facebook,instagram,ecommerce",
            )
            new_avail2  = st.selectbox("Availability", ["available", "busy"])
        with na2:
            new_rate    = st.number_input("Hourly rate (MAD)", min_value=50.0, value=200.0, step=10.0)
            new_level   = st.selectbox("Experience level", ["junior", "mid", "senior"])
            new_email   = st.text_input("Email")
            new_langs   = st.text_input("Languages (;-separated)", placeholder="fr;ar;en")

        if st.button("Add to roster", type="primary"):
            if not new_name.strip():
                st.error("Name is required.")
            else:
                fid = add_freelancer({
                    "name":             new_name.strip(),
                    "role":             new_role,
                    "specialties":      new_specs.strip(),
                    "availability":     new_avail2,
                    "hourly_rate_mad":  new_rate,
                    "experience_level": new_level,
                    "email":            new_email.strip(),
                    "languages":        new_langs.strip(),
                })
                st.success(f"✅ Freelancer '{new_name}' added (ID #{fid}).")
                st.cache_data.clear()
                st.rerun()


# ═══════════════════════════════════════════════════════════
# TAB 3 — PAST ASSIGNMENTS & RATINGS
# ═══════════════════════════════════════════════════════════
with tab_history:
    st.markdown('<div class="section-hdr">All campaign team assignments</div>', unsafe_allow_html=True)

    from core.team_db import get_all_campaign_teams
    all_teams = get_all_campaign_teams()

    if all_teams.empty:
        st.info("No team assignments saved yet.")
    else:
        disp_cols = [
            "campaign_id", "name", "role",
            "hours", "budget_mad", "status", "rating",
        ]
        available_cols = [c for c in disp_cols if c in all_teams.columns]
        disp = all_teams[available_cols].copy()
        disp.columns = [c.replace("_", " ").title() for c in available_cols]
        if "Budget Mad" in disp.columns:
            disp["Budget Mad"] = disp["Budget Mad"].apply(
                lambda x: f"{int(x):,}" if pd.notna(x) else "—"
            )
        st.dataframe(disp, hide_index=True, use_container_width=True)

        # ── Rate a freelancer ─────────────────────────────
        st.divider()
        st.markdown("**Rate a freelancer post-campaign**")
        rc1, rc2, rc3, rc4 = st.columns([2, 2, 1, 2])
        with rc1:
            rate_row_id = st.number_input("Assignment row ID", min_value=1, step=1)
        with rc2:
            rate_stars  = st.slider("Rating (1–5 ⭐)", 1, 5, 4)
        with rc3:
            st.write("")
            st.write("")
        with rc4:
            rate_notes  = st.text_input("Notes (optional)", placeholder="Great work on Reels!")

        if st.button("Submit rating", type="primary"):
            try:
                rate_team_member(int(rate_row_id), int(rate_stars), rate_notes)
                st.success(f"✅ Rating saved for assignment #{rate_row_id}.")
                st.cache_data.clear()
                st.rerun()
            except ValueError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Error: {e}")