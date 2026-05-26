from __future__ import annotations

from ..models import db
from ..models.entities import InvestorDealStatus, Startup, User


def get_deal(investor: User, startup_id: int) -> InvestorDealStatus | None:
    return InvestorDealStatus.query.filter_by(investor_id=investor.id, startup_id=startup_id).first()


def set_deal_status(investor: User, startup: Startup, status: str, notes: str | None = None) -> InvestorDealStatus:
    deal = get_deal(investor, startup.id)
    if not deal:
        deal = InvestorDealStatus(investor_id=investor.id, startup_id=startup.id)
        db.session.add(deal)
    deal.status = status
    if notes is not None:
        deal.notes = notes.strip()[:2000] or None
    from datetime import datetime, timezone

    deal.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return deal


def deals_for_investor(investor: User) -> list[InvestorDealStatus]:
    return (
        InvestorDealStatus.query.filter_by(investor_id=investor.id)
        .order_by(InvestorDealStatus.updated_at.desc())
        .all()
    )
