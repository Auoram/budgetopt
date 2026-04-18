import sys
from pathlib import Path

# Make sure project root is on the path
sys.path.append(str(Path(__file__).parent.parent))

# Import and run the classic app
# All the logic stays in app_classic.py — this is just the entry point
exec(open(Path(__file__).parent.parent / "app_classic.py", encoding="utf-8").read())