from flask import Blueprint, redirect, render_template, request, url_for
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional, Length

from ..access import is_investor
from ..models.entities import Startup
from ..routes.auth import session_user
from ..services.investor import candidate_rows, investor_startup_bundle, is_favorited, toggle_favorite
from ..services.investor_deal import get_deal
from ..services.roadmap import branch_map_state, steps_for_startup

bp = Blueprint("investor", __name__, url_prefix="/investor")


class DealForm(FlaskForm):
    status = SelectField(
        "Статус",
        choices=[
            ("viewed", "Просмотрен"),
            ("interested", "Интерес"),
            ("meeting", "Встреча"),
            ("passed", "Pass"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField("Заметки", validators=[Optional(), Length(max=2000)])


@bp.before_request
def require_investor_account():
    user = session_user()
    if not user:
        return redirect(url_for("auth.login"))
    if not is_investor(user):
        return redirect(url_for("main.home"))
    return None


@bp.get("/")
@bp.get("/candidates")
def candidates():
    user = session_user()
    return render_template(
        "investor/candidates.html",
        active_tab="candidates",
        candidates=candidate_rows(user),
        user=user,
        page_title="Кандидаты",
        page_hint="Стартапы на платформе: команда, прогресс, ТОО и скорость шагов.",
    )


@bp.get("/favorites")
def favorites():
    user = session_user()
    return render_template(
        "investor/candidates.html",
        active_tab="favorites",
        candidates=candidate_rows(user, only_favorites=True),
        user=user,
        page_title="Избранное",
        page_hint="Кандидаты, которых вы отметили звёздочкой.",
    )


@bp.post("/candidates/<int:startup_id>/favorite")
def toggle_favorite_route(startup_id: int):
    user = session_user()
    startup = Startup.query.get_or_404(startup_id)
    favorited = toggle_favorite(user, startup_id)
    return render_template(
        "partials/investor_favorite_button.html",
        startup=startup,
        is_favorite=favorited,
    )


@bp.get("/candidates/<int:startup_id>")
def candidate_detail(startup_id: int):
    user = session_user()
    startup = Startup.query.get_or_404(startup_id)
    bundle = investor_startup_bundle(startup)
    steps = steps_for_startup(startup)
    map_nodes = branch_map_state(startup.roadmap_step, steps, bundle["logs"], startup=startup)
    deal = get_deal(user, startup.id)
    deal_form = DealForm(status=deal.status if deal else "viewed", notes=deal.notes if deal else "")
    return render_template(
        "investor/candidate.html",
        active_tab="candidates",
        user=user,
        startup=startup,
        owner=startup.owner,
        steps=steps,
        progress=bundle["progress"],
        map_nodes=map_nodes,
        too=bundle["too"],
        pace=bundle["pace"],
        current_step_days=bundle["current_step_days"],
        team=bundle["team"],
        step_timeline=bundle["step_timeline"],
        total_completed_days=bundle["total_completed_days"],
        is_favorite=is_favorited(user, startup.id),
        show_step_dates=True,
        show_step_timing=True,
        deal=deal,
        deal_form=deal_form,
        step_logs=bundle["logs"],
        documents=startup.documents,
    )
