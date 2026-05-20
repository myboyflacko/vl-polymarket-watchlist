import json
from pathlib import Path

from void_liquidity.adapters.polymarket.services.track_whales.schemas import (
    WhaleTrackingProfile,
)


PACKAGE_DIR = Path(__file__).resolve().parent
SERVICE_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SERVICE_DIR.parents[4]
DEFAULT_PROFILE_PATH = SERVICE_DIR / "config" / "whale_tracking_profile.json"


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
