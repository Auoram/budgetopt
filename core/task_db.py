"""
core/task_db.py
───────────────
All database operations for the campaign_tasks table.

Schema
──────
campaign_tasks (
    id             INTEGER PK AUTOINCREMENT,
    campaign_id    INTEGER NOT NULL,
    channel        TEXT,           -- channel slug or "all"
    category       TEXT,           -- Creative | Setup | Launch | Monitoring | Reporting
    title          TEXT NOT NULL,
    description    TEXT,
    due_day        INTEGER,        -- days from campaign start
    due_date       TEXT,           -- ISO date, set when campaign start date is known
    priority       TEXT,           -- high | medium | low
    assignee_role  TEXT,           -- role slug
    assigned_to    TEXT,           -- freelancer name (denormalised for display)
    status         TEXT DEFAULT 'todo',  -- todo | in_progress | done | blocked
    notes          TEXT,
    created_at     TEXT,
    updated_at     TEXT
)
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, List

from core.task_generator import Task

DB_PATH = Path(__file__).parent.parent / "data" / "feedback.db"


# ─────────────────────────────────────────
# INIT
# ─────────────────────────────────────────

def init_task_tables():
    """
    Creates campaign_tasks table if it doesn't exist.
    Safe to call multiple times (idempotent).
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS campaign_tasks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id    INTEGER NOT NULL,
            channel        TEXT    DEFAULT 'all',
            category       TEXT,
            title          TEXT    NOT NULL,
            description    TEXT,
            due_day        INTEGER DEFAULT 0,
            due_date       TEXT,
            priority       TEXT    DEFAULT 'medium',
            assignee_role  TEXT,
            assigned_to    TEXT,
            status         TEXT    DEFAULT 'todo',
            notes          TEXT    DEFAULT '',
            created_at     TEXT,
            updated_at     TEXT
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# WRITE
# ─────────────────────────────────────────

def save_tasks(
    campaign_id:  int,
    tasks:        List[Task],
    start_date:   Optional[date] = None,
    replace:      bool = True,
) -> int:
    """
    Saves a list of Task objects to the DB for a campaign.

    start_date — if provided, due_date is computed as
                 start_date + timedelta(days=task.due_day - 1).
    replace    — if True, deletes existing tasks for this campaign first.

    Returns number of rows inserted.
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    if replace:
        cur.execute(
            "DELETE FROM campaign_tasks WHERE campaign_id = ?",
            (campaign_id,)
        )

    now = datetime.now().isoformat()
    for t in tasks:
        due_date_str = None
        if start_date and t.due_day:
            due_date_str = (
                start_date + timedelta(days=t.due_day - 1)
            ).isoformat()

        cur.execute("""
            INSERT INTO campaign_tasks
              (campaign_id, channel, category, title, description,
               due_day, due_date, priority, assignee_role,
               assigned_to, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            campaign_id,
            t.channel,
            t.category,
            t.title,
            t.description,
            t.due_day,
            due_date_str,
            t.priority,
            t.assignee_role,
            "",          # assigned_to — filled by user later
            t.status,
            t.notes,
            now,
            now,
        ))

    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def update_task(
    task_id:     int,
    status:      Optional[str] = None,
    assigned_to: Optional[str] = None,
    due_date:    Optional[str] = None,
    notes:       Optional[str] = None,
):
    """
    Updates one or more fields on a single task row.
    Only non-None arguments are applied.
    """
    valid_statuses = {"todo", "in_progress", "done", "blocked"}
    if status and status not in valid_statuses:
        raise ValueError(f"status must be one of {valid_statuses}")

    fields, values = [], []
    if status      is not None: fields.append("status = ?");      values.append(status)
    if assigned_to is not None: fields.append("assigned_to = ?"); values.append(assigned_to)
    if due_date    is not None: fields.append("due_date = ?");    values.append(due_date)
    if notes       is not None: fields.append("notes = ?");       values.append(notes)

    if not fields:
        return

    fields.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(task_id)

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        f"UPDATE campaign_tasks SET {', '.join(fields)} WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()


def bulk_update_status(task_ids: List[int], status: str):
    """Sets the same status on multiple tasks at once."""
    valid = {"todo", "in_progress", "done", "blocked"}
    if status not in valid:
        raise ValueError(f"status must be one of {valid}")
    if not task_ids:
        return
    placeholders = ",".join("?" * len(task_ids))
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        f"UPDATE campaign_tasks SET status = ?, updated_at = ? "
        f"WHERE id IN ({placeholders})",
        [status, now] + list(task_ids)
    )
    conn.commit()
    conn.close()


def delete_task(task_id: int):
    """Hard-deletes a single task row."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM campaign_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()


def delete_campaign_tasks(campaign_id: int):
    """Removes all tasks for a campaign (used on regeneration)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "DELETE FROM campaign_tasks WHERE campaign_id = ?",
        (campaign_id,)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# READ
# ─────────────────────────────────────────

def get_campaign_tasks(
    campaign_id: int,
    channel:     Optional[str] = None,
    category:    Optional[str] = None,
    status:      Optional[str] = None,
) -> pd.DataFrame:
    """
    Returns tasks for a campaign as a DataFrame.
    Optionally filtered by channel, category, or status.
    Sorted by due_day, then priority.
    """
    query  = "SELECT * FROM campaign_tasks WHERE campaign_id = ?"
    params: list = [campaign_id]

    if channel:
        query  += " AND channel = ?"
        params.append(channel)
    if category:
        query  += " AND category = ?"
        params.append(category)
    if status:
        query  += " AND status = ?"
        params.append(status)

    query += " ORDER BY due_day, CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def get_task(task_id: int) -> dict:
    """Returns one task as a dict."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM campaign_tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else {}


def task_exists_for_campaign(campaign_id: int) -> bool:
    """Returns True if any tasks are saved for this campaign."""
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM campaign_tasks WHERE campaign_id = ?",
        (campaign_id,)
    )
    count = cur.fetchone()[0]
    conn.close()
    return count > 0


# ─────────────────────────────────────────
# SUMMARY / STATS
# ─────────────────────────────────────────

def task_summary(campaign_id: int) -> dict:
    """
    Returns a progress summary for a campaign:
        total, done, in_progress, todo, blocked,
        pct_done (0–100)
    """
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)                                      AS total,
            SUM(CASE WHEN status='done'        THEN 1 ELSE 0 END) AS done,
            SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN status='todo'        THEN 1 ELSE 0 END) AS todo,
            SUM(CASE WHEN status='blocked'     THEN 1 ELSE 0 END) AS blocked
        FROM campaign_tasks
        WHERE campaign_id = ?
    """, (campaign_id,))
    row = cur.fetchone()
    conn.close()

    total       = row[0] or 0
    done        = row[1] or 0
    in_progress = row[2] or 0
    todo        = row[3] or 0
    blocked     = row[4] or 0
    pct_done    = round(done / total * 100, 1) if total > 0 else 0.0

    return {
        "total":       total,
        "done":        done,
        "in_progress": in_progress,
        "todo":        todo,
        "blocked":     blocked,
        "pct_done":    pct_done,
    }


def tasks_by_category(campaign_id: int) -> pd.DataFrame:
    """Returns count and completion rate grouped by category."""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT
                category,
                COUNT(*)                                          AS total,
                SUM(CASE WHEN status='done' THEN 1 ELSE 0 END)   AS done
            FROM campaign_tasks
            WHERE campaign_id = ?
            GROUP BY category
            ORDER BY category
        """, conn, params=(campaign_id,))
        if not df.empty:
            df["pct_done"] = (df["done"] / df["total"] * 100).round(1)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def overdue_tasks(campaign_id: int) -> pd.DataFrame:
    """
    Returns tasks whose due_date has passed
    and status is not 'done'.
    """
    today = date.today().isoformat()
    conn  = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("""
            SELECT * FROM campaign_tasks
            WHERE campaign_id = ?
              AND due_date < ?
              AND status != 'done'
            ORDER BY due_date
        """, conn, params=(campaign_id, today))
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df