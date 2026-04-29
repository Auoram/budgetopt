"""
core/team_builder.py
────────────────────
Determines which roles a campaign needs,
matches freelancers from the database,
and manages the campaign_team table.
"""
import sqlite3
import json
import pandas as pd
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from core.data_model import CampaignInput

DB_PATH   = Path(__file__).parent.parent / "data" / "feedback.db"
CSV_PATH  = Path(__file__).parent.parent / "data" / "freelancers.csv"

# ─────────────────────────────────────────
# ROLE REQUIREMENTS PER CHANNEL
# ─────────────────────────────────────────

CHANNEL_ROLES: Dict[str, List[dict]] = {
    "facebook": [
        {"role": "media_buyer",       "hours": 20, "reason": "Campaign setup, audience targeting, daily optimisation"},
        {"role": "copywriter",        "hours": 10, "reason": "Ad copy — headline, primary text, CTA"},
        {"role": "graphic_designer",  "hours": 8,  "reason": "Static creatives and carousel images"},
        {"role": "community_manager", "hours": 8,  "reason": "Comment moderation and engagement"},
    ],
    "instagram": [
        {"role": "media_buyer",      "hours": 16, "reason": "Stories, Reels, feed ad management"},
        {"role": "graphic_designer", "hours": 12, "reason": "Visual creatives optimised for Instagram format"},
        {"role": "video_editor",     "hours": 10, "reason": "Reels and short-form video production"},
        {"role": "copywriter",       "hours": 6,  "reason": "Caption and CTA writing"},
    ],
    "google_ads": [
        {"role": "media_buyer",    "hours": 20, "reason": "Search/display campaign setup, bid management"},
        {"role": "copywriter",     "hours": 8,  "reason": "Ad headlines, descriptions (RSA format)"},
        {"role": "web_developer",  "hours": 6,  "reason": "Conversion tracking, tag setup"},
        {"role": "data_analyst",   "hours": 6,  "reason": "Search term report, quality score analysis"},
    ],
    "tiktok": [
        {"role": "video_editor",      "hours": 20, "reason": "Short-form video production and editing"},
        {"role": "media_buyer",       "hours": 12, "reason": "TikTok Ads Manager setup and optimisation"},
        {"role": "copywriter",        "hours": 6,  "reason": "Hook writing, on-screen text, captions"},
        {"role": "community_manager", "hours": 6,  "reason": "Comment engagement and trend monitoring"},
    ],
    "email": [
        {"role": "copywriter",    "hours": 12, "reason": "Email sequences, subject lines, body copy"},
        {"role": "graphic_designer", "hours": 8, "reason": "Email template design"},
        {"role": "web_developer", "hours": 4,  "reason": "Template coding, list integration, tracking"},
        {"role": "data_analyst",  "hours": 4,  "reason": "Open rate, CTR, unsubscribe analysis"},
    ],
    "seo": [
        {"role": "seo_specialist", "hours": 30, "reason": "Keyword research, on-page, technical SEO"},
        {"role": "copywriter",     "hours": 20, "reason": "Blog articles, landing-page content"},
        {"role": "web_developer",  "hours": 8,  "reason": "Technical fixes, schema markup, page speed"},
        {"role": "data_analyst",   "hours": 6,  "reason": "Rank tracking, organic traffic reporting"},
    ],
    "linkedin": [
        {"role": "media_buyer",      "hours": 16, "reason": "LinkedIn Campaign Manager, sponsored content"},
        {"role": "copywriter",       "hours": 10, "reason": "Thought-leadership copy, lead gen forms"},
        {"role": "graphic_designer", "hours": 8,  "reason": "Sponsored content visuals"},
        {"role": "data_analyst",     "hours": 4,  "reason": "Lead quality and conversion analysis"},
    ],
}

# Roles always needed regardless of channels
ALWAYS_NEEDED = [
    {"role": "data_analyst", "hours": 8,
     "reason": "Overall campaign performance dashboard and weekly reporting"},
]

# Extra roles triggered by complexity
def _extra_roles(campaign: CampaignInput) -> List[dict]:
    extras = []
    # Big budget → dedicated project manager
    if campaign.total_budget >= 500_000:
        extras.append({
            "role": "project_manager",
            "hours": 20,
            "reason": "Campaign coordination across multiple channels and vendors",
        })
    # Multi-country → translator
    if len(campaign.target_countries) >= 3:
        extras.append({
            "role": "translator",
            "hours": 10,
            "reason": "Content localisation for multiple markets",
        })
    return extras


# ─────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────

@dataclass
class RoleRequirement:
    role: str
    hours: int
    reason: str
    estimated_cost_mad: float = 0.0  # computed from hourly rate


@dataclass
class FreelancerMatch:
    freelancer_id: int
    name: str
    role: str
    specialties: str
    hourly_rate_mad: float
    experience_level: str
    availability: str
    email: str
    estimated_hours: int
    estimated_cost_mad: float


@dataclass
class TeamPlan:
    campaign_id: Optional[int]
    required_roles: List[RoleRequirement]
    matches: Dict[str, List[FreelancerMatch]]  # role → candidates
    total_estimated_cost_mad: float


# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────

def init_team_tables():
    """
    Creates the freelancers and campaign_team tables
    in feedback.db if they don't already exist.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Load CSV into freelancers table on first run
    cur.execute("""
        CREATE TABLE IF NOT EXISTS freelancers (
            id                INTEGER PRIMARY KEY,
            name              TEXT NOT NULL,
            role              TEXT NOT NULL,
            specialties       TEXT,
            availability      TEXT DEFAULT 'available',
            hourly_rate_mad   REAL NOT NULL,
            experience_level  TEXT DEFAULT 'mid',
            email             TEXT,
            portfolio_url     TEXT,
            languages         TEXT
        )
    """)

    cur.execute("SELECT COUNT(*) FROM freelancers")
    if cur.fetchone()[0] == 0 and CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
        df.to_sql("freelancers", conn, if_exists="append", index=False)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_team (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id    INTEGER,
            freelancer_id  INTEGER,
            role           TEXT NOT NULL,
            hours          REAL DEFAULT 0,
            budget_mad     REAL DEFAULT 0,
            status         TEXT DEFAULT 'proposed',   -- proposed|confirmed|active|done
            rating         INTEGER,                   -- 1-5 post-campaign
            notes          TEXT,
            assigned_at    TEXT,
            FOREIGN KEY(freelancer_id) REFERENCES freelancers(id)
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────

def get_required_roles(campaign: CampaignInput) -> List[RoleRequirement]:
    """
    Returns the list of roles needed for this campaign,
    based on the selected channels and campaign properties.
    Deduplicates — if two channels both need a media_buyer,
    we return one entry with summed hours.
    """
    role_map: Dict[str, RoleRequirement] = {}

    for ch in campaign.allowed_channels:
        for r in CHANNEL_ROLES.get(ch, []):
            key = r["role"]
            if key in role_map:
                role_map[key].hours += r["hours"]
            else:
                role_map[key] = RoleRequirement(
                    role=key, hours=r["hours"], reason=r["reason"]
                )

    # Always-needed
    for r in ALWAYS_NEEDED:
        key = r["role"]
        if key in role_map:
            role_map[key].hours += r["hours"]
        else:
            role_map[key] = RoleRequirement(
                role=key, hours=r["hours"], reason=r["reason"]
            )

    # Extras
    for r in _extra_roles(campaign):
        key = r["role"]
        if key not in role_map:
            role_map[key] = RoleRequirement(
                role=key, hours=r["hours"], reason=r["reason"]
            )

    # Cap hours to campaign horizon
    max_hours = campaign.horizon_months * 160  # full-time cap
    for req in role_map.values():
        req.hours = min(req.hours, max_hours // 4)  # reasonable cap

    return list(role_map.values())


def load_freelancers() -> pd.DataFrame:
    """Loads all freelancers from DB (or CSV fallback)."""
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        try:
            df = pd.read_sql("SELECT * FROM freelancers", conn)
            conn.close()
            return df
        except Exception:
            conn.close()
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH)
    return pd.DataFrame()


def find_matches(
    role: str,
    campaign: CampaignInput,
    top_n: int = 3,
) -> List[FreelancerMatch]:
    """
    Returns up to top_n freelancers that match the given role,
    filtered by:
    - availability (prefer 'available')
    - sector / channel specialty affinity (keyword match)
    Sorted by: available first, then experience desc, then rate asc.
    """
    df = load_freelancers()
    if df.empty:
        return []

    matches = df[df["role"] == role].copy()

    if matches.empty:
        # Fallback: broader match on specialties
        matches = df[
            df["specialties"].fillna("").str.contains(role, case=False)
        ].copy()

    if matches.empty:
        return []

    # Score for sector / channel affinity
    sector_kw = campaign.sector.lower()
    channel_kw = "|".join(campaign.allowed_channels)
    matches["affinity"] = matches["specialties"].fillna("").apply(
        lambda s: (sector_kw in s.lower()) + bool(
            any(c in s.lower() for c in campaign.allowed_channels)
        )
    )

    # Sort
    exp_order = {"senior": 0, "mid": 1, "junior": 2}
    avail_order = {"available": 0, "busy": 1}
    matches["_exp_ord"]   = matches["experience_level"].map(exp_order).fillna(9)
    matches["_avail_ord"] = matches["availability"].map(avail_order).fillna(9)
    matches = matches.sort_values(
        ["_avail_ord", "affinity", "_exp_ord", "hourly_rate_mad"],
        ascending=[True, False, True, True]
    ).head(top_n)

    results = []
    for _, row in matches.iterrows():
        results.append(FreelancerMatch(
            freelancer_id   = int(row["id"]),
            name            = row["name"],
            role            = row["role"],
            specialties     = row.get("specialties", ""),
            hourly_rate_mad = float(row["hourly_rate_mad"]),
            experience_level= row.get("experience_level", "mid"),
            availability    = row.get("availability", "available"),
            email           = row.get("email", ""),
            estimated_hours = 0,  # filled in by caller
            estimated_cost_mad = 0.0,
        ))
    return results


def build_team_plan(campaign: CampaignInput, campaign_id: Optional[int] = None) -> TeamPlan:
    """
    Main entry point.
    Returns a TeamPlan with required roles + candidate freelancers per role.
    """
    roles = get_required_roles(campaign)
    matches: Dict[str, List[FreelancerMatch]] = {}
    total_cost = 0.0

    for req in roles:
        candidates = find_matches(req.role, campaign)
        for c in candidates:
            c.estimated_hours     = req.hours
            c.estimated_cost_mad  = req.hours * c.hourly_rate_mad
        if candidates:
            total_cost += candidates[0].estimated_cost_mad  # use top candidate
        req.estimated_cost_mad = (
            candidates[0].estimated_cost_mad if candidates else 0.0
        )
        matches[req.role] = candidates

    return TeamPlan(
        campaign_id=campaign_id,
        required_roles=roles,
        matches=matches,
        total_estimated_cost_mad=total_cost,
    )


def save_team_assignment(
    campaign_id: int,
    assignments: List[dict],  # [{"freelancer_id": x, "role": ..., "hours": ..., "budget": ...}]
) -> int:
    """Saves the chosen freelancers to campaign_team. Returns count inserted."""
    from datetime import datetime
    init_team_tables()
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Remove any previous proposals for this campaign
    cur.execute("DELETE FROM campaign_team WHERE campaign_id=? AND status='proposed'", (campaign_id,))

    for a in assignments:
        cur.execute("""
            INSERT INTO campaign_team
              (campaign_id, freelancer_id, role, hours, budget_mad, status, assigned_at)
            VALUES (?, ?, ?, ?, ?, 'confirmed', ?)
        """, (
            campaign_id,
            a["freelancer_id"],
            a["role"],
            a.get("hours", 0),
            a.get("budget_mad", 0),
            datetime.now().isoformat(),
        ))

    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def get_campaign_team(campaign_id: int) -> pd.DataFrame:
    """Returns the confirmed team for a campaign as a DataFrame."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT ct.*, f.name, f.hourly_rate_mad, f.email, f.experience_level
            FROM campaign_team ct
            JOIN freelancers f ON ct.freelancer_id = f.id
            WHERE ct.campaign_id = ?
            ORDER BY ct.role
        """, conn, params=(campaign_id,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


ROLE_LABELS = {
    "media_buyer":        "📣 Media Buyer",
    "copywriter":         "✍️ Copywriter",
    "graphic_designer":   "🎨 Graphic Designer",
    "video_editor":       "🎬 Video Editor",
    "web_developer":      "💻 Web Developer",
    "data_analyst":       "📊 Data Analyst",
    "seo_specialist":     "🌱 SEO Specialist",
    "community_manager":  "💬 Community Manager",
    "project_manager":    "📋 Project Manager",
    "translator":         "🌍 Translator",
}