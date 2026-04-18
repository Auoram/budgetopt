import sys
from pathlib import Path

# Make sure project root is on the path
sys.path.append(str(Path(__file__).parent.parent))

# Import and run the agent app
# All the logic stays in app_agent.py — this is just the entry point
exec(open(Path(__file__).parent.parent / "app_agent.py", encoding="utf-8").read())