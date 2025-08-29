# check_db.py
import sqlite3
from pathlib import Path

DB = Path("app/db/data/agents.sqlite")
con = sqlite3.connect(DB)
cur = con.execute("""
  SELECT id, platform, external_id, text, likes, recasts, replies, created_at
  FROM posts
  ORDER BY created_at DESC;
""")
for row in cur.fetchall():
    print(row)
con.close()

