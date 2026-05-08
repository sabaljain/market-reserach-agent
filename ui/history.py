import json
import re
from datetime import datetime
from pathlib import Path

HISTORY_DIR = Path(__file__).parent.parent / "run_history"


def save_run(industry: str, geography: str, state: dict, duration: float) -> None:
    HISTORY_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]", "_", industry)[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = HISTORY_DIR / f"{ts}_{slug}.json"
    path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now().isoformat(),
                "inputs": {"industry": industry, "geography": geography},
                "state": state,
                "duration_seconds": round(duration, 1),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_recent_runs(n: int = 5) -> list[dict]:
    if not HISTORY_DIR.exists():
        return []
    runs = []
    for path in sorted(HISTORY_DIR.glob("*.json"), reverse=True)[:n]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_filepath"] = str(path)
            runs.append(data)
        except Exception:
            pass
    return runs


def load_run(filepath: str) -> dict:
    return json.loads(Path(filepath).read_text(encoding="utf-8"))
