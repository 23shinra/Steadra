from __future__ import annotations

from sqlalchemy import or_

from ..models import db
from ..models.entities import Partner

DEFAULT_PARTNERS = [
    {
        "name": "Astana Hub",
        "category": "accelerator",
        "description": "IT-хаб и резидентство для tech-стартапов в РК.",
        "url": "https://astanahub.com",
        "region": "astana",
        "roadmap_step_key": "mvp",
        "sort_order": 1,
    },
    {
        "name": "MOST Ventures",
        "category": "investor",
        "description": "Венчурный фонд для ранних стартапов Центральной Азии.",
        "url": "https://mostventures.com",
        "region": None,
        "roadmap_step_key": "traction",
        "sort_order": 2,
    },
    {
        "name": "eGov Mobile",
        "category": "gov",
        "description": "Госуслуги РК: регистрация ТОО и бизнес-разрешения.",
        "url": "https://egov.kz",
        "region": None,
        "roadmap_step_key": "too",
        "sort_order": 3,
    },
    {
        "name": "Kaspi Business",
        "category": "finance",
        "description": "Расчётный счёт и платежи для ИП и ТОО.",
        "url": "https://kaspi.kz/business",
        "region": None,
        "roadmap_step_key": "too",
        "sort_order": 4,
    },
]


def ensure_partners() -> None:
    if Partner.query.first():
        return
    for item in DEFAULT_PARTNERS:
        db.session.add(Partner(**item))
    db.session.commit()


def partners_for_step(step_key: str | None = None, region: str | None = None) -> list[Partner]:
    q = Partner.query.filter_by(active=True)
    if step_key:
        q = q.filter(
            or_(Partner.roadmap_step_key == step_key, Partner.roadmap_step_key.is_(None))
        )
    if region:
        q = q.filter(or_(Partner.region == region, Partner.region.is_(None)))
    return q.order_by(Partner.sort_order.asc()).all()
