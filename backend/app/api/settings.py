from fastapi import APIRouter

from app import db
from app.config import SUGGESTED_MODELS, settings
from app.llm.taxonomy import PRESETS, from_stored
from app.models import AppSettings, SettingsUpdate

router = APIRouter(tags=["settings"])


def runtime_settings() -> AppSettings:
    """Defaults from .env, overridden by anything saved through POST /settings."""
    stored = db.get_setting("categories")
    return AppSettings(
        model=db.get_setting("model", settings.model),
        tone=db.get_setting("tone", settings.tone),
        categories=from_stored(stored) if stored else PRESETS[settings.category_preset],
        local_only=db.get_setting("local_only", settings.local_only),
        user_name=db.get_setting("user_name", settings.user_name),
        auto_triage=db.get_setting("auto_triage", settings.auto_triage),
        suggested_models=SUGGESTED_MODELS,
        presets=PRESETS,
    )


@router.get("/settings", response_model=AppSettings)
def get_settings():
    return runtime_settings()


@router.post("/settings", response_model=AppSettings)
def update_settings(update: SettingsUpdate):
    for key, value in update.model_dump(exclude_none=True).items():
        db.set_setting(key, value)
    return runtime_settings()
