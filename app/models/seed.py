from sqlalchemy import inspect, text

from datetime import datetime, timezone

from ..models import db
from ..models.entities import Activity, RoadmapStepLog, Startup, User


def ensure_user_schema() -> None:
    inspector = inspect(db.engine)
    if not inspector.has_table("user"):
        return
    columns = {column["name"] for column in inspector.get_columns("user")}
    migrations = [
        ("avatar_url", "ALTER TABLE user ADD COLUMN avatar_url VARCHAR(255)"),
        ("age", "ALTER TABLE user ADD COLUMN age INTEGER"),
        ("experience_years", "ALTER TABLE user ADD COLUMN experience_years INTEGER"),
        ("experience_text", "ALTER TABLE user ADD COLUMN experience_text TEXT"),
        ("onboarding_done", "ALTER TABLE user ADD COLUMN onboarding_done BOOLEAN DEFAULT 0"),
        ("account_type", "ALTER TABLE user ADD COLUMN account_type VARCHAR(20) DEFAULT 'user'"),
        ("locale", "ALTER TABLE user ADD COLUMN locale VARCHAR(5) DEFAULT 'ru'"),
        ("theme", "ALTER TABLE user ADD COLUMN theme VARCHAR(10) DEFAULT 'dark'"),
        ("region", "ALTER TABLE user ADD COLUMN region VARCHAR(80)"),
        ("ai_requests_count", "ALTER TABLE user ADD COLUMN ai_requests_count INTEGER DEFAULT 0"),
        ("ai_requests_reset_at", "ALTER TABLE user ADD COLUMN ai_requests_reset_at DATETIME"),
        ("is_verified_investor", "ALTER TABLE user ADD COLUMN is_verified_investor BOOLEAN DEFAULT 0"),
        ("open_for_messages", "ALTER TABLE user ADD COLUMN open_for_messages BOOLEAN DEFAULT 1"),
        ("show_in_leaderboard", "ALTER TABLE user ADD COLUMN show_in_leaderboard BOOLEAN DEFAULT 1"),
        ("show_in_search", "ALTER TABLE user ADD COLUMN show_in_search BOOLEAN DEFAULT 1"),
        ("show_projects_public", "ALTER TABLE user ADD COLUMN show_projects_public BOOLEAN DEFAULT 1"),
        ("show_achievements_public", "ALTER TABLE user ADD COLUMN show_achievements_public BOOLEAN DEFAULT 1"),
        ("active_startup_id", "ALTER TABLE user ADD COLUMN active_startup_id INTEGER"),
        ("investor_linkedin", "ALTER TABLE user ADD COLUMN investor_linkedin VARCHAR(255)"),
        ("investor_fund_name", "ALTER TABLE user ADD COLUMN investor_fund_name VARCHAR(160)"),
        ("is_premium", "ALTER TABLE user ADD COLUMN is_premium BOOLEAN DEFAULT 0"),
    ]
    added_onboarding_done = False
    with db.engine.begin() as conn:
        for column, statement in migrations:
            if column not in columns:
                conn.execute(text(statement))
                if column == "onboarding_done":
                    added_onboarding_done = True
        if added_onboarding_done:
            conn.execute(text("UPDATE user SET onboarding_done = 1"))

        if inspector.has_table("startup"):
            startup_cols = {column["name"] for column in inspector.get_columns("startup")}
            for column, statement in [
                ("roadmap_step", "ALTER TABLE startup ADD COLUMN roadmap_step INTEGER DEFAULT 0"),
                ("roadmap_steps_json", "ALTER TABLE startup ADD COLUMN roadmap_steps_json TEXT"),
                ("roadmap_started_at", "ALTER TABLE startup ADD COLUMN roadmap_started_at DATETIME"),
                ("vertical", "ALTER TABLE startup ADD COLUMN vertical VARCHAR(40)"),
                ("business_model_type", "ALTER TABLE startup ADD COLUMN business_model_type VARCHAR(10)"),
                ("pitch_pre_json", "ALTER TABLE startup ADD COLUMN pitch_pre_json TEXT"),
                ("pitch_analysis_json", "ALTER TABLE startup ADD COLUMN pitch_analysis_json TEXT"),
                ("fin_model_json", "ALTER TABLE startup ADD COLUMN fin_model_json TEXT"),
                ("too_registered_at", "ALTER TABLE startup ADD COLUMN too_registered_at DATETIME"),
                ("bin", "ALTER TABLE startup ADD COLUMN bin VARCHAR(12)"),
                ("step_branches_json", "ALTER TABLE startup ADD COLUMN step_branches_json TEXT"),
            ]:
                if column not in startup_cols:
                    conn.execute(text(statement))

        if inspector.has_table("ai_message"):
            msg_cols = {column["name"] for column in inspector.get_columns("ai_message")}
            if "meta_json" not in msg_cols:
                conn.execute(text("ALTER TABLE ai_message ADD COLUMN meta_json TEXT"))

        if inspector.has_table("ai_thread"):
            thread_cols = {column["name"] for column in inspector.get_columns("ai_thread")}
            for column, statement in [
                ("startup_id", "ALTER TABLE ai_thread ADD COLUMN startup_id INTEGER"),
                ("phase", "ALTER TABLE ai_thread ADD COLUMN phase VARCHAR(20) DEFAULT 'roast'"),
                ("idea_name", "ALTER TABLE ai_thread ADD COLUMN idea_name VARCHAR(100)"),
                ("idea_tagline", "ALTER TABLE ai_thread ADD COLUMN idea_tagline VARCHAR(180)"),
                ("roast_score", "ALTER TABLE ai_thread ADD COLUMN roast_score INTEGER"),
            ]:
                if column not in thread_cols:
                    conn.execute(text(statement))

        if inspector.has_table("roadmap_step_log"):
            log_cols = {column["name"] for column in inspector.get_columns("roadmap_step_log")}
            for column, statement in [
                ("evidence_url", "ALTER TABLE roadmap_step_log ADD COLUMN evidence_url VARCHAR(500)"),
                ("evidence_text", "ALTER TABLE roadmap_step_log ADD COLUMN evidence_text TEXT"),
            ]:
                if column not in log_cols:
                    conn.execute(text(statement))

        if inspector.has_table("team_member"):
            tm_cols = {column["name"] for column in inspector.get_columns("team_member")}
            if "team_role" not in tm_cols:
                conn.execute(text("ALTER TABLE team_member ADD COLUMN team_role VARCHAR(40) DEFAULT 'member'"))

        if inspector.has_table("roadmap_step_log"):
            log_cols = {column["name"] for column in inspector.get_columns("roadmap_step_log")}
            if "validation_request_id" not in log_cols:
                conn.execute(text("ALTER TABLE roadmap_step_log ADD COLUMN validation_request_id INTEGER"))

        if inspector.has_table("step_validation_request"):
            val_cols = {column["name"] for column in inspector.get_columns("step_validation_request")}
            for column, statement in [
                ("evidence_filename", "ALTER TABLE step_validation_request ADD COLUMN evidence_filename VARCHAR(255)"),
                ("evidence_filepath", "ALTER TABLE step_validation_request ADD COLUMN evidence_filepath VARCHAR(500)"),
                ("poll_deadline_at", "ALTER TABLE step_validation_request ADD COLUMN poll_deadline_at DATETIME"),
            ]:
                if column not in val_cols:
                    conn.execute(text(statement))

        if inspector.has_table("activity"):
            activity_cols = {column["name"] for column in inspector.get_columns("activity")}
            if "ai_generated" not in activity_cols:
                conn.execute(text("ALTER TABLE activity ADD COLUMN ai_generated BOOLEAN DEFAULT 0"))

    db.create_all()
    backfill_roadmap_history()
    migrate_user_roles()
    from ..services.achievements import ensure_achievements
    from ..services.partners import ensure_partners

    ensure_achievements()
    ensure_partners()


def backfill_roadmap_history() -> None:
    if not inspect(db.engine).has_table("roadmap_step_log"):
        return

    startups = Startup.query.all()
    for startup in startups:
        if not startup.roadmap_started_at:
            first_activity = (
                Activity.query.filter_by(startup_id=startup.id)
                .order_by(Activity.created_at.asc())
                .first()
            )
            startup.roadmap_started_at = (
                first_activity.created_at if first_activity else datetime.now(timezone.utc)
            )
            db.session.add(startup)

        from ..services.roadmap import steps_for_startup

        steps = steps_for_startup(startup)
        labels = {step["label"]: i for i, step in enumerate(steps)}
        existing = {log.step_index for log in startup.step_logs}
        activities = (
            Activity.query.filter_by(startup_id=startup.id, kind="ship")
            .order_by(Activity.created_at.asc())
            .all()
        )
        for activity in activities:
            title = activity.title or ""
            if not title.startswith("Шаг завершён:"):
                continue
            label = title.removeprefix("Шаг завершён:").strip()
            step_index = labels.get(label)
            if step_index is None or step_index in existing:
                continue
            step = steps[step_index]
            db.session.add(
                RoadmapStepLog(
                    startup_id=startup.id,
                    step_index=step_index,
                    step_key=step.get("key", ""),
                    step_label=step["label"],
                    completed_at=activity.created_at,
                )
            )
            existing.add(step_index)

    db.session.commit()


def migrate_user_roles() -> None:
    from ..access import ACCOUNT_INVESTOR
    from ..roles import INVESTOR_ROLE_LABEL, display_role

    changed = False
    for user in User.query.all():
        if user.account_type == ACCOUNT_INVESTOR:
            if user.role != INVESTOR_ROLE_LABEL:
                user.role = INVESTOR_ROLE_LABEL
                changed = True
            if user.experience_years is not None or user.experience_text:
                user.experience_years = None
                user.experience_text = None
                changed = True
            continue
        if user.role == INVESTOR_ROLE_LABEL:
            user.role = "Основатель"
            changed = True
        new_role = display_role(user.role)
        if new_role != user.role:
            user.role = new_role
            changed = True
    if changed:
        db.session.commit()


def ensure_feed_schema() -> None:
    ensure_user_schema()


def seed_demo_data() -> None:
    ensure_feed_schema()
    if User.query.first():
        return

    users = [
        User(name="Гаухар", phone="77010000001", role="B2B SaaS founder", avatar="G", score=1240, streak=9, onboarding_done=True, region="almaty"),
        User(name="Алихан", phone="77010000002", role="Product maker", avatar="A", score=980, streak=6, onboarding_done=True, region="astana"),
        User(name="Мира", phone="77010000003", role="Growth lead", avatar="M", score=840, streak=5, onboarding_done=True, region="almaty"),
        User(name="Данияр", phone="77010000004", role="AI builder", avatar="D", score=730, streak=4, onboarding_done=True, region="shymkent"),
    ]
    db.session.add_all(users)
    db.session.flush()

    startups = [
        Startup(name="Nomad CRM", tagline="CRM для малого бизнеса в Центральной Азии", stage="MVP", traction=42, health=76, owner=users[0]),
        Startup(name="EduPulse", tagline="AI-тренер для подготовки к экзаменам", stage="Prototype", traction=29, health=64, owner=users[1]),
        Startup(name="CraftPay", tagline="Платежи и витрина для локальных мастеров", stage="Validation", traction=35, health=71, owner=users[2]),
        Startup(name="PitchLab", tagline="Симулятор питча перед инвестором", stage="Idea", traction=18, health=58, owner=users[3]),
    ]
    db.session.add_all(startups)
    db.session.flush()

    activities = [
        Activity(kind="ship", title="Запустили лендинг", body="Собрали первые 37 заявок и нашли 4 повторяющихся боли у клиентов.", impact=18, user=users[0], startup=startups[0]),
        Activity(kind="roast", title="AI Roast вскрыл слабую гипотезу", body="Команда сузила сегмент с 'все школьники' до выпускников IELTS с дедлайном 30 дней.", impact=14, user=users[1], startup=startups[1]),
        Activity(kind="sale", title="Первый платящий клиент", body="CraftPay получил оплату за setup и понял, какой модуль нужен в первую очередь.", impact=22, user=users[2], startup=startups[2]),
        Activity(kind="team", title="Нашёлся co-founder", body="PitchLab закрыл техническую роль через внутреннюю ленту Kangaroo.", impact=16, user=users[3], startup=startups[3]),
    ]
    db.session.add_all(activities)
    db.session.commit()
