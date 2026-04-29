"""
core/team_db.py
───────────────
All database operations for the two HR tables:
  • freelancers
  • campaign_team

Kept separate from team_builder.py so the UI
can import DB ops without pulling in matching logic.
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

DB_PATH  = Path(__file__).parent.parent / "data" / "feedback.db"
CSV_PATH = Path(__file__).parent.parent / "data" / "freelancers.csv"


# ─────────────────────────────────────────
# INIT
# ─────────────────────────────────────────

def init_team_tables():
    """
    Creates freelancers + campaign_team tables if they don't exist.
    Seeds freelancers from CSV on first run.
    Safe to call multiple times (idempotent).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS freelancers (
            id               INTEGER PRIMARY KEY,
            name             TEXT    NOT NULL,
            role             TEXT    NOT NULL,
            specialties      TEXT,
            availability     TEXT    DEFAULT 'available',
            hourly_rate_mad  REAL    NOT NULL,
            experience_level TEXT    DEFAULT 'mid',
            email            TEXT,
            portfolio_url    TEXT,
            languages        TEXT
        )
    """)

    # Seed from CSV only if table is empty
    cur.execute("SELECT COUNT(*) FROM freelancers")
    if cur.fetchone()[0] == 0 and CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
        df.to_sql("freelancers", conn, if_exists="append", index=False)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS campaign_team (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id   INTEGER NOT NULL,
            freelancer_id INTEGER,
            role          TEXT    NOT NULL,
            hours         REAL    DEFAULT 0,
            budget_mad    REAL    DEFAULT 0,
            status        TEXT    DEFAULT 'proposed',
            rating        INTEGER,
            notes         TEXT,
            assigned_at   TEXT,
            FOREIGN KEY (freelancer_id) REFERENCES freelancers(id)
        )
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# FREELANCERS — READ
# ─────────────────────────────────────────

def get_all_freelancers() -> pd.DataFrame:
    """Returns every freelancer row."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM freelancers ORDER BY role, experience_level DESC", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_freelancers_by_role(role: str) -> pd.DataFrame:
    """Returns freelancers whose role matches exactly."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(
            "SELECT * FROM freelancers WHERE role = ? ORDER BY availability, hourly_rate_mad",
            conn, params=(role,)
        )
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_freelancer(freelancer_id: int) -> dict:
    """Returns one freelancer as a dict, or empty dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM freelancers WHERE id = ?", (freelancer_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


# ─────────────────────────────────────────
# FREELANCERS — WRITE
# ─────────────────────────────────────────

def add_freelancer(data: dict) -> int:
    """
    Inserts a new freelancer. data keys must match column names.
    Returns the new row id.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        INSERT INTO freelancers
          (name, role, specialties, availability,
           hourly_rate_mad, experience_level, email, portfolio_url, languages)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("name", ""),
        data.get("role", ""),
        data.get("specialties", ""),
        data.get("availability", "available"),
        float(data.get("hourly_rate_mad", 0)),
        data.get("experience_level", "mid"),
        data.get("email", ""),
        data.get("portfolio_url", ""),
        data.get("languages", ""),
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_freelancer_availability(freelancer_id: int, availability: str):
    """Sets a freelancer's availability to 'available' or 'busy'."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE freelancers SET availability = ? WHERE id = ?",
        (availability, freelancer_id)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# CAMPAIGN TEAM — READ
# ─────────────────────────────────────────

def get_campaign_team(campaign_id: int) -> pd.DataFrame:
    """
    Returns the full team for a campaign,
    joined with freelancer details.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT
                ct.id,
                ct.campaign_id,
                ct.freelancer_id,
                f.name,
                ct.role,
                f.hourly_rate_mad,
                ct.hours,
                ct.budget_mad,
                ct.status,
                ct.rating,
                ct.notes,
                ct.assigned_at,
                f.email,
                f.experience_level,
                f.availability
            FROM campaign_team ct
            LEFT JOIN freelancers f ON ct.freelancer_id = f.id
            WHERE ct.campaign_id = ?
            ORDER BY ct.role, f.name
        """, conn, params=(campaign_id,))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_all_campaign_teams() -> pd.DataFrame:
    """Returns every team row across all campaigns."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT ct.*, f.name, f.hourly_rate_mad, f.email
            FROM campaign_team ct
            LEFT JOIN freelancers f ON ct.freelancer_id = f.id
            ORDER BY ct.campaign_id, ct.role
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


# ─────────────────────────────────────────
# CAMPAIGN TEAM — WRITE
# ─────────────────────────────────────────

def save_team_assignments(campaign_id: int, assignments: list[dict]) -> int:
    """
    Saves confirmed freelancer assignments for a campaign.

    assignments is a list of dicts:
        {
            "freelancer_id": int,
            "role":          str,
            "hours":         float,
            "budget_mad":    float,
            "notes":         str  (optional)
        }

    Existing 'proposed' rows for this campaign are replaced.
    Returns number of rows inserted.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Remove old proposals for this campaign
    cur.execute(
        "DELETE FROM campaign_team WHERE campaign_id = ? AND status = 'proposed'",
        (campaign_id,)
    )

    now = datetime.now().isoformat()
    for a in assignments:
        cur.execute("""
            INSERT INTO campaign_team
              (campaign_id, freelancer_id, role, hours, budget_mad, status, notes, assigned_at)
            VALUES (?, ?, ?, ?, ?, 'confirmed', ?, ?)
        """, (
            campaign_id,
            a.get("freelancer_id"),
            a["role"],
            float(a.get("hours", 0)),
            float(a.get("budget_mad", 0)),
            a.get("notes", ""),
            now,
        ))

    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def update_team_member_status(row_id: int, status: str):
    """Updates a single campaign_team row's status."""
    valid = {"proposed", "confirmed", "active", "done", "cancelled"}
    if status not in valid:
        raise ValueError(f"status must be one of {valid}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE campaign_team SET status = ? WHERE id = ?",
        (status, row_id)
    )
    conn.commit()
    conn.close()


def rate_team_member(row_id: int, rating: int, notes: str = ""):
    """
    Saves a post-campaign rating (1–5) for a freelancer.
    Called from the feedback / history page.
    """
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be 1–5")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE campaign_team SET rating = ?, notes = ? WHERE id = ?",
        (rating, notes, row_id)
    )
    conn.commit()
    conn.close()


def remove_team_member(row_id: int):
    """Deletes a single campaign_team row (hard delete)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM campaign_team WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def team_cost_summary(campaign_id: int) -> dict:
    """
    Returns a quick cost summary for the team:
        total_budget_mad, total_hours, n_members
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)          AS n_members,
            SUM(hours)        AS total_hours,
            SUM(budget_mad)   AS total_budget_mad
        FROM campaign_team
        WHERE campaign_id = ? AND status != 'cancelled'
    """, (campaign_id,))
    row = cur.fetchone()
    conn.close()
    return {
        "n_members":       row[0] or 0,
        "total_hours":     row[1] or 0.0,
        "total_budget_mad": row[2] or 0.0,
    }