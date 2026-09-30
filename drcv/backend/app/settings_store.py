from sqlalchemy.orm import Session

from . import config
from .models import Setting

DEFAULTS = {
    "organization_name": "DRCV Verification Lab",
    "ocr_enabled": True,
    "max_upload_mb": config.MAX_UPLOAD_MB,
    "similarity_threshold": 0.15,
    "relationship_min_score": 0.2,
    "name_variation_threshold": 0.72,
    "low_ocr_confidence": 70,
    "show_demo_guide": True,
}


def get_settings(db: Session) -> dict:
    out = dict(DEFAULTS)
    for s in db.query(Setting).all():
        if s.key in DEFAULTS:
            out[s.key] = s.value.get("v") if isinstance(s.value, dict) else s.value
    return out


def set_setting(db: Session, key: str, value):
    row = db.get(Setting, key)
    if row:
        row.value = {"v": value}
    else:
        db.add(Setting(key=key, value={"v": value}))
