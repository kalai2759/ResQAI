"""Create the database and demo data.  Usage:
    python scripts/init_db.py            # create tables + seed demo data (once)
    python scripts/init_db.py --reset    # delete demo records and re-insert them
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config  # noqa: E402
from database import Database  # noqa: E402

db = Database(Config.DATABASE_PATH)
db.init_schema()
if "--reset" in sys.argv:
    db.reset_demo_data()
    print("Demo data reset.")
else:
    print("Demo data inserted." if db.seed_demo_data() else "Demo data already present - nothing to do.")
print("Database:", Config.DATABASE_PATH)
