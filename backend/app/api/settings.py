from fastapi import APIRouter

from app import db
from app.config import DEFAULT_CATEGORIES, SUGGESTED_MODELS, settings
from app.models import AppSettings, SettingsUpdate

router = APIRouter(tags=["settings"])


def runtime_settings() -> AppSettings:
    """Defaults from .env, overridden by anything saved through POST /settings."""
    return AppSettings(
        model=db.get_setting("model", settings.model),
        tone=db.get_setting("tone", settings.tone),
        categories=db.get_setting("categories", DEFAULT_CATEGORIES),
        local_only=db.get_setting("local_only", settings.local_only),
        user_name=db.get_setting("user_name", settings.user_name),
        suggested_models=SUGGESTED_MODELS,
    )


@router.get("/settings", response_model=AppSettings)
def get_settings():
    return runtime_settings()


@router.post("/settings", response_model=AppSettings)
def update_settings(update: SettingsUpdate):
    for key, value in update.model_dump(exclude_none=True).items():
        db.set_setting(key, value)
    return runtime_settings()
