# app/migrations.py
from flask_sqlalchemy import SQLAlchemy

def ensure_chat_session_columns(db: SQLAlchemy):
    """
    Idempotent migration for chat_session:
    - Adds visitor_id (TEXT, nullable)
    - Adds scope (TEXT, default 'public')
    - Back-fills scope='account' where user_mobile IS NOT NULL and scope IS NULL/empty
    """
    rows = db.session.execute("PRAGMA table_info(chat_session);").fetchall()
    cols = {r[1] for r in rows}

    if "visitor_id" not in cols:
        db.session.execute("ALTER TABLE chat_session ADD COLUMN visitor_id TEXT;")

    if "scope" not in cols:
        db.session.execute("ALTER TABLE chat_session ADD COLUMN scope TEXT DEFAULT 'public';")

    db.session.commit()

    # Backfill scope for old rows that actually belong to logged-in users
    db.session.execute("""
        UPDATE chat_session
           SET scope = 'account'
         WHERE user_mobile IS NOT NULL
           AND (scope IS NULL OR scope = '')
    """)
    db.session.commit()
