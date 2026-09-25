from datetime import datetime, timezone
from pathlib import Path

NOW = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
SEED = Path(__file__).parent / "fixtures" / "seed.json"


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now
