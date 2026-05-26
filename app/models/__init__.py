from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from .entities import Activity, ActivityComment, ActivityLike, AiMessage, AiThread, InvestorFavorite, Notification, PushSubscription, RoadmapStepLog, Startup, StepWeeklyGoal, TeamInvitation, TeamMember, User  # noqa: E402,F401
