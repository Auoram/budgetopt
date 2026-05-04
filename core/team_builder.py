"""
core/team_builder.py
────────────────────
Determines which roles a campaign needs,
matches freelancers from the database,
and manages the campaign_team table.

Phase 5 update: find_matches() now boosts freelancers
with high past ratings and demotes those with low ratings.
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
        {"role": "copywriter",       "hours": 12, "reason": "Email sequences, subject lines, body copy"},
        {"role": "graphic_designer", "hours": 8,  "reason": "Email template design"},
        {"role": "web_developer",    "hours": 4,  "reason": "Template coding, list integration, tracking"},
        {"role": "data_analyst",     "hours": 4,  "reason": "Open rate, CTR, unsubscribe analysis"},
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
    if campaign.total_budget >= 500_000:
        extras.append({
            "role":   "project_manager",
            "hours":  20,
            "reason": "Campaign coordination across multiple channels and vendors",
        })
    if len(campaign.target_countries) >= 3:
        extras.append({
            "role":   "translator",
            "hours":  10,
            "reason": "Content localisation for multiple markets",
        })
    return extras


# ─────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────

@dataclass
class RoleRequirement:
    role:                str
    hours:               int
    reason:              str
    estimated_cost_mad:  float = 0.0


@dataclass
class FreelancerMatch:
    freelancer_id:     int
    name:              str
    role:              str
    specialties:       str
    hourly_rate_mad:   float
    experience_level:  str
    availability:      str
    email:             str
    estimated_hours:   int
    estimated_cost_mad:float
    avg_rating:        Optional[float] = None   # ← Phase 5: from past campaigns
    n_rated:           int             = 0      # ← Phase 5: number of rated campaigns
    rating_score:      float           = 0.5    # ← Phase 5: composite score 0–1


@dataclass
class TeamPlan:
    campaign_id:              Optional[int]
    required_roles:           List[RoleRequirement]
    matches:                  Dict[str, List[FreelancerMatch]]
    total_estimated_cost_mad: float


# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────

def init_team_tables():
    """
    Creates the freelancers and campaign_team tables
    in feedback.db if they don't already exist.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

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
            status         TEXT DEFAULT 'proposed',
            rating         INTEGER,
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
    Returns the list of roles needed for this campaign.
    Deduplicates across channels — if two channels both need
    a media_buyer, returns one entry with summed hours.
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

    for r in ALWAYS_NEEDED:
        key = r["role"]
        if key in role_map:
            role_map[key].hours += r["hours"]
        else:
            role_map[key] = RoleRequirement(
                role=key, hours=r["hours"], reason=r["reason"]
            )

    for r in _extra_roles(campaign):
        key = r["role"]
        if key not in role_map:
            role_map[key] = RoleRequirement(
                role=key, hours=r["hours"], reason=r["reason"]
            )

    max_hours = campaign.horizon_months * 160
    for req in role_map.values():
        req.hours = min(req.hours, max_hours // 4)

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


def _load_rating_scores() -> Dict[int, dict]:
    """
    Loads avg_rating, n_rated, and composite score
    for every freelancer that has been rated.
    Returns dict keyed by freelancer_id.
    """
    try:
        from core.learner import get_freelancer_scores
        scores_df = get_freelancer_scores()
        if scores_df.empty:
            return {}
        result = {}
        for _, row in scores_df.iterrows():
            fid = int(row["freelancer_id"])
            result[fid] = {
                "avg_rating": float(row["avg_rating"]) if row["avg_rating"] else None,
                "n_rated":    int(row["n_rated"]),
                "score":      float(row["score"]),
            }
        return result
    except Exception:
        return {}


def find_matches(
    role:     str,
    campaign: CampaignInput,
    top_n:    int = 3,
) -> List[FreelancerMatch]:
    """
    Returns up to top_n freelancers matching the given role.

    Sorting priority (Phase 5 updated):
    1. Availability (available first)
    2. Rating score (composite from past campaigns, 0–1)
       — freelancers with no ratings get a neutral score of 0.5
    3. Sector / channel affinity (keyword match)
    4. Experience level (senior > mid > junior)
    5. Hourly rate (ascending — cheaper wins on tie)
    """
    df = load_freelancers()
    if df.empty:
        return []

    # Load rating scores once
    rating_scores = _load_rating_scores()

    matches = df[df["role"] == role].copy()
    if matches.empty:
        matches = df[
            df["specialties"].fillna("").str.contains(role, case=False)
        ].copy()
    if matches.empty:
        return []

    # Sector / channel affinity score
    matches["affinity"] = matches["specialties"].fillna("").apply(
        lambda s: (campaign.sector.lower() in s.lower()) + bool(
            any(c in s.lower() for c in campaign.allowed_channels)
        )
    )

    # Rating score — neutral 0.5 for unrated freelancers
    matches["_rating_score"] = matches["id"].apply(
        lambda fid: rating_scores.get(int(fid), {}).get("score", 0.5)
    )

    # Sort orders
    exp_order   = {"senior": 0, "mid": 1, "junior": 2}
    avail_order = {"available": 0, "busy": 1}

    matches["_exp_ord"]   = matches["experience_level"].map(exp_order).fillna(9)
    matches["_avail_ord"] = matches["availability"].map(avail_order).fillna(9)

    matches = matches.sort_values(
        ["_avail_ord", "_rating_score", "affinity", "_exp_ord", "hourly_rate_mad"],
        ascending=[True, False, False, True, True],
    ).head(top_n)

    results = []
    for _, row in matches.iterrows():
        fid          = int(row["id"])
        rating_info  = rating_scores.get(fid, {})
        avg_rating   = rating_info.get("avg_rating")
        n_rated      = rating_info.get("n_rated", 0)
        r_score      = rating_info.get("score", 0.5)

        results.append(FreelancerMatch(
            freelancer_id     = fid,
            name              = row["name"],
            role              = row["role"],
            specialties       = row.get("specialties", ""),
            hourly_rate_mad   = float(row["hourly_rate_mad"]),
            experience_level  = row.get("experience_level", "mid"),
            availability      = row.get("availability", "available"),
            email             = row.get("email", ""),
            estimated_hours   = 0,
            estimated_cost_mad= 0.0,
            avg_rating        = avg_rating,
            n_rated           = n_rated,
            rating_score      = r_score,
        ))
    return results


def build_team_plan(
    campaign:    CampaignInput,
    campaign_id: Optional[int] = None,
) -> TeamPlan:
    """
    Main entry point.
    Returns a TeamPlan with required roles + candidate freelancers per role.
    """
    roles   = get_required_roles(campaign)
    matches: Dict[str, List[FreelancerMatch]] = {}
    total_cost = 0.0

    for req in roles:
        candidates = find_matches(req.role, campaign)
        for c in candidates:
            c.estimated_hours      = req.hours
            c.estimated_cost_mad   = req.hours * c.hourly_rate_mad
        if candidates:
            total_cost += candidates[0].estimated_cost_mad
        req.estimated_cost_mad = (
            candidates[0].estimated_cost_mad if candidates else 0.0
        )
        matches[req.role] = candidates

    return TeamPlan(
        campaign_id              = campaign_id,
        required_roles           = roles,
        matches                  = matches,
        total_estimated_cost_mad = total_cost,
    )


def save_team_assignment(
    campaign_id: int,
    assignments: List[dict],
) -> int:
    """Saves chosen freelancers to campaign_team. Returns count inserted."""
    from datetime import datetime
    init_team_tables()
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute(
        "DELETE FROM campaign_team WHERE campaign_id=? AND status='proposed'",
        (campaign_id,)
    )

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
    "media_buyer":       "📣 Media Buyer",
    "copywriter":        "✍️ Copywriter",
    "graphic_designer":  "🎨 Graphic Designer",
    "video_editor":      "🎬 Video Editor",
    "web_developer":     "💻 Web Developer",
    "data_analyst":      "📊 Data Analyst",
    "seo_specialist":    "🌱 SEO Specialist",
    "community_manager": "💬 Community Manager",
    "project_manager":   "📋 Project Manager",
    "translator":        "🌍 Translator",
}