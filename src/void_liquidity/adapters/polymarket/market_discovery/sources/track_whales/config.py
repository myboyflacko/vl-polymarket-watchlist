import json
from pathlib import Path

from void_liquidity.adapters.polymarket.market_discovery.sources.track_whales.schemas import (
    WhaleTrackingProfile,
)


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[6]
DEFAULT_PROFILE_PATH = (
    PACKAGE_DIR / "profiles" / "whale_tracking_profile.json"
)
QUALITY_PROFILE_PATH = (
    PACKAGE_DIR
    / "profiles"
    / "whale_tracking_profile_quality.json"
)


def load_workflow_profile(
    path: str | Path = DEFAULT_PROFILE_PATH,
) -> WhaleTrackingProfile:
    profile_path = Path(path)

    with profile_path.open("r", encoding="utf-8") as profile_file:
        payload = json.load(profile_file)

    return WhaleTrackingProfile.model_validate(payload)


def _resolve_project_path(path: str | Path) -> Path:
    resolved_path = Path(path)

    if resolved_path.is_absolute():
        return resolved_path

    return PROJECT_ROOT / resolved_path
