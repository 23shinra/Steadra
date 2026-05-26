from datetime import date, timedelta

from ..models import db
from ..models.entities import StepWeeklyGoal
from .roadmap import is_finished, step_at, steps_for_startup

GOAL_TEMPLATES: dict[str, list[str]] = {
    "idea_poll": [
        "Сформулируй гипотезу в одном предложении",
        "Опубликуй опрос в ленте",
        "Собери минимум 5 голосов",
    ],
    "pitch_pre": [
        "Сгенерируй pre-MVP deck",
        "Проверь слайды problem и solution",
        "Покажи deck 2 фаундерам",
    ],
    "pitch": [
        "Вставь текст питча для AI-разбора",
        "Исправь слабые слайды по фидбеку",
        "Доведи score до 60+",
    ],
    "finmodel": [
        "Выбери B2B или B2C",
        "Заполни ключевые метрики",
        "Проверь LTV/CAC или payback",
    ],
    "mvp": [
        "Опиши одну ключевую функцию MVP",
        "Собери лендинг или прототип",
        "Покажи MVP 3 людям из ЦА",
    ],
    "users": [
        "Найди 5 контактов потенциальных пользователей",
        "Проведи 2 интервью о боли",
        "Получи первую регистрацию вне команды",
    ],
    "traction": [
        "Зафиксируй метрику недели (лиды/продажи)",
        "Сделай 3 касания с клиентами",
        "Обнови оффер по обратной связи",
    ],
    "too": [
        "Уточни требования к регистрации ТОО",
        "Собери документы для подачи",
        "Запланируй дату подачи заявки",
    ],
    "money": [
        "Составь список из 5 источников денег",
        "Отправь 1 заявку или питч",
        "Зафиксируй сумму цели на месяц",
    ],
}

DEFAULT_TEMPLATES = [
    "Запиши результат за сегодня",
    "Сделай один звонок или сообщение клиенту",
    "Обнови план на 3 дня вперёд",
]


def week_start_for(day: date | None = None) -> date:
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def ensure_weekly_goals(startup) -> list[StepWeeklyGoal]:
    if not startup or is_finished(startup.roadmap_step, steps_for_startup(startup)):
        return []

    steps = steps_for_startup(startup)
    step_index = startup.roadmap_step
    step = step_at(step_index, steps)
    week = week_start_for()

    existing = (
        StepWeeklyGoal.query.filter_by(
            startup_id=startup.id,
            step_index=step_index,
            week_start=week,
        )
        .order_by(StepWeeklyGoal.sort_order.asc())
        .all()
    )
    if existing:
        return existing

    key = (step.get("key") or "").lower()
    labels = GOAL_TEMPLATES.get(key, DEFAULT_TEMPLATES)[:3]
    goals = []
    for i, label in enumerate(labels):
        goal = StepWeeklyGoal(
            startup_id=startup.id,
            step_index=step_index,
            label=label,
            done=False,
            sort_order=i,
            week_start=week,
        )
        db.session.add(goal)
        goals.append(goal)
    db.session.commit()
    return goals


def toggle_goal(goal_id: int, startup_id: int) -> StepWeeklyGoal | None:
    goal = StepWeeklyGoal.query.filter_by(id=goal_id, startup_id=startup_id).first()
    if not goal:
        return None
    goal.done = not goal.done
    db.session.add(goal)
    db.session.commit()
    return goal


def weekly_goals_summary(startup) -> dict | None:
    if not startup:
        return None
    goals = ensure_weekly_goals(startup)
    if not goals:
        return None
    done = sum(1 for g in goals if g.done)
    return {
        "goals": goals,
        "done": done,
        "total": len(goals),
        "all_done": done == len(goals),
    }
