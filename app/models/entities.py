from datetime import datetime, timezone

from . import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    phone = db.Column(db.String(32), unique=True, nullable=False, index=True)
    role = db.Column(db.String(120), nullable=False, default="Founder")
    avatar = db.Column(db.String(8), nullable=False, default="K")
    avatar_url = db.Column(db.String(255), nullable=True)
    score = db.Column(db.Integer, nullable=False, default=0)
    streak = db.Column(db.Integer, nullable=False, default=0)
    age = db.Column(db.Integer, nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    experience_text = db.Column(db.Text, nullable=True)
    onboarding_done = db.Column(db.Boolean, nullable=False, default=False)
    account_type = db.Column(db.String(20), nullable=False, default="user")
    locale = db.Column(db.String(5), nullable=False, default="ru")
    region = db.Column(db.String(80), nullable=True)
    ai_requests_count = db.Column(db.Integer, nullable=False, default=0)
    ai_requests_reset_at = db.Column(db.DateTime, nullable=True)
    is_verified_investor = db.Column(db.Boolean, nullable=False, default=False)
    open_for_messages = db.Column(db.Boolean, nullable=False, default=True)
    active_startup_id = db.Column(db.Integer, db.ForeignKey("startup.id", use_alter=True, name="fk_user_active_startup"), nullable=True)
    investor_linkedin = db.Column(db.String(255), nullable=True)
    investor_fund_name = db.Column(db.String(160), nullable=True)
    is_premium = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    startups = db.relationship("Startup", back_populates="owner", lazy=True, foreign_keys="Startup.owner_id")
    activities = db.relationship("Activity", back_populates="user", lazy=True)
    investor_favorites = db.relationship(
        "InvestorFavorite",
        back_populates="investor",
        lazy=True,
        cascade="all, delete-orphan",
    )
    team_memberships = db.relationship(
        "TeamMember",
        back_populates="user",
        lazy=True,
        cascade="all, delete-orphan",
        foreign_keys="TeamMember.user_id",
    )
    team_invites_sent = db.relationship(
        "TeamInvitation",
        back_populates="inviter",
        lazy=True,
        foreign_keys="TeamInvitation.inviter_id",
    )
    team_invites_received = db.relationship(
        "TeamInvitation",
        back_populates="invitee",
        lazy=True,
        foreign_keys="TeamInvitation.invitee_id",
    )


class Startup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tagline = db.Column(db.String(180), nullable=False)
    stage = db.Column(db.String(40), nullable=False, default="Idea")
    roadmap_step = db.Column(db.Integer, nullable=False, default=0)
    roadmap_steps_json = db.Column(db.Text, nullable=True)
    roadmap_started_at = db.Column(db.DateTime, nullable=True)
    traction = db.Column(db.Integer, nullable=False, default=0)
    health = db.Column(db.Integer, nullable=False, default=12)
    vertical = db.Column(db.String(40), nullable=True)
    business_model_type = db.Column(db.String(10), nullable=True)
    pitch_pre_json = db.Column(db.Text, nullable=True)
    pitch_analysis_json = db.Column(db.Text, nullable=True)
    fin_model_json = db.Column(db.Text, nullable=True)
    too_registered_at = db.Column(db.DateTime, nullable=True)
    bin = db.Column(db.String(12), nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    owner = db.relationship("User", back_populates="startups", foreign_keys=[owner_id])
    activities = db.relationship("Activity", back_populates="startup", lazy=True)
    step_logs = db.relationship(
        "RoadmapStepLog",
        back_populates="startup",
        lazy=True,
        order_by="RoadmapStepLog.completed_at.asc()",
        cascade="all, delete-orphan",
    )
    investor_favorites = db.relationship(
        "InvestorFavorite",
        back_populates="startup",
        lazy=True,
        cascade="all, delete-orphan",
    )
    team_members = db.relationship(
        "TeamMember",
        back_populates="startup",
        lazy=True,
        cascade="all, delete-orphan",
    )
    team_invitations = db.relationship(
        "TeamInvitation",
        back_populates="startup",
        lazy=True,
        cascade="all, delete-orphan",
    )


class InvestorFavorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    investor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    investor = db.relationship("User", back_populates="investor_favorites")
    startup = db.relationship("Startup", back_populates="investor_favorites")

    __table_args__ = (db.UniqueConstraint("investor_id", "startup_id", name="uq_investor_favorite"),)


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    team_role = db.Column(db.String(40), nullable=False, default="member")
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    startup = db.relationship("Startup", back_populates="team_members")
    user = db.relationship("User", back_populates="team_memberships", foreign_keys=[user_id])

    __table_args__ = (db.UniqueConstraint("startup_id", "user_id", name="uq_team_member"),)


class TeamInvitation(db.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"

    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    inviter_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    invitee_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    responded_at = db.Column(db.DateTime, nullable=True)

    startup = db.relationship("Startup", back_populates="team_invitations")
    inviter = db.relationship("User", back_populates="team_invites_sent", foreign_keys=[inviter_id])
    invitee = db.relationship("User", back_populates="team_invites_received", foreign_keys=[invitee_id])

    __table_args__ = (db.UniqueConstraint("startup_id", "invitee_id", name="uq_team_invite"),)


class RoadmapStepLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    step_index = db.Column(db.Integer, nullable=False)
    step_key = db.Column(db.String(40), nullable=False, default="")
    step_label = db.Column(db.String(160), nullable=False)
    evidence_url = db.Column(db.String(500), nullable=True)
    evidence_text = db.Column(db.Text, nullable=True)
    validation_request_id = db.Column(db.Integer, db.ForeignKey("step_validation_request.id"), nullable=True)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    startup = db.relationship("Startup", back_populates="step_logs")

    __table_args__ = (db.UniqueConstraint("startup_id", "step_index", name="uq_startup_step_log"),)


class StepValidationRequest(db.Model):
    STATUS_PENDING_AI = "pending_ai"
    STATUS_AI_REJECTED = "ai_rejected"
    STATUS_PENDING_ADMIN = "pending_admin"
    STATUS_ADMIN_APPROVED = "admin_approved"
    STATUS_ADMIN_REJECTED = "admin_rejected"

    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    step_index = db.Column(db.Integer, nullable=False)
    step_key = db.Column(db.String(40), nullable=False, default="")
    step_label = db.Column(db.String(160), nullable=False)
    report = db.Column(db.Text, nullable=False)
    evidence_url = db.Column(db.String(500), nullable=True)
    evidence_filename = db.Column(db.String(255), nullable=True)
    evidence_filepath = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(24), nullable=False, default=STATUS_PENDING_AI, index=True)
    ai_verdict = db.Column(db.Text, nullable=True)
    ai_feedback = db.Column(db.Text, nullable=True)
    ai_confidence = db.Column(db.Integer, nullable=True)
    ai_approved_at = db.Column(db.DateTime, nullable=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    admin_decided_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    startup = db.relationship("Startup", backref=db.backref("validation_requests", lazy=True))
    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("validation_requests", lazy=True))
    admin = db.relationship("User", foreign_keys=[admin_id])


class TooValidationRequest(db.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    company_name = db.Column(db.String(160), nullable=False)
    bin = db.Column(db.String(12), nullable=False)
    message = db.Column(db.Text, nullable=False, default="")
    chat_excerpt = db.Column(db.Text, nullable=True)
    evidence_url = db.Column(db.String(500), nullable=True)
    evidence_filename = db.Column(db.String(255), nullable=True)
    evidence_filepath = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(16), nullable=False, default=STATUS_PENDING, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    startup = db.relationship("Startup", backref=db.backref("too_validations", lazy=True))
    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("too_validations", lazy=True))
    admin = db.relationship("User", foreign_keys=[admin_id])


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    impact = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=True)

    user = db.relationship("User", back_populates="activities")
    startup = db.relationship("Startup", back_populates="activities")
    likes = db.relationship("ActivityLike", back_populates="activity", cascade="all, delete-orphan", lazy=True)
    comments = db.relationship(
        "ActivityComment",
        back_populates="activity",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="ActivityComment.created_at.asc()",
    )


class ActivityLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activity.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    activity = db.relationship("Activity", back_populates="likes")
    user = db.relationship("User", backref=db.backref("activity_likes", lazy=True))

    __table_args__ = (db.UniqueConstraint("activity_id", "user_id", name="uq_activity_like"),)


class ActivityComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activity.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    activity = db.relationship("Activity", back_populates="comments")
    user = db.relationship("User", backref=db.backref("activity_comments", lazy=True))


class AiThread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=True, index=True)
    title = db.Column(db.String(120), nullable=False, default="Новый чат")
    phase = db.Column(db.String(20), nullable=False, default="roast")
    idea_name = db.Column(db.String(100), nullable=True)
    idea_tagline = db.Column(db.String(180), nullable=True)
    roast_score = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    startup = db.relationship("Startup", foreign_keys=[startup_id])

    user = db.relationship("User", backref=db.backref("ai_threads", lazy=True))
    messages = db.relationship(
        "AiMessage",
        back_populates="thread",
        lazy=True,
        order_by="AiMessage.created_at.asc()",
        cascade="all, delete-orphan",
    )


class AiMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("ai_thread.id"), nullable=False, index=True)
    role = db.Column(db.String(16), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    thread = db.relationship("AiThread", back_populates="messages")


class StepWeeklyGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    step_index = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(160), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    week_start = db.Column(db.Date, nullable=False, index=True)

    startup = db.relationship("Startup", backref=db.backref("weekly_goals", lazy=True))

    __table_args__ = (
        db.UniqueConstraint("startup_id", "step_index", "sort_order", "week_start", name="uq_step_weekly_goal"),
    )


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False, default="")
    href = db.Column(db.String(255), nullable=False, default="/app")
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("notifications", lazy=True))


class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref=db.backref("push_subscriptions", lazy=True))

    __table_args__ = (db.UniqueConstraint("user_id", "endpoint", name="uq_push_subscription"),)


class CacheEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(40), unique=True, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=False, default="")
    icon = db.Column(db.String(8), nullable=False, default="★")


class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey("achievement.id"), nullable=False, index=True)
    earned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref=db.backref("achievements", lazy=True))
    achievement = db.relationship("Achievement")

    __table_args__ = (db.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)


class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    sender = db.relationship("User", foreign_keys=[sender_id], backref=db.backref("messages_sent", lazy=True))
    recipient = db.relationship("User", foreign_keys=[recipient_id], backref=db.backref("messages_received", lazy=True))


class InvestorDealStatus(db.Model):
    STATUS_VIEWED = "viewed"
    STATUS_INTERESTED = "interested"
    STATUS_MEETING = "meeting"
    STATUS_PASSED = "passed"

    id = db.Column(db.Integer, primary_key=True)
    investor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_VIEWED)
    notes = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    investor = db.relationship("User", backref=db.backref("deal_statuses", lazy=True))
    startup = db.relationship("Startup", backref=db.backref("deal_statuses", lazy=True))

    __table_args__ = (db.UniqueConstraint("investor_id", "startup_id", name="uq_investor_deal"),)


class StartupDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False, default="pitch")
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    startup = db.relationship("Startup", backref=db.backref("documents", lazy=True))


class Partner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(60), nullable=False, default="service")
    description = db.Column(db.Text, nullable=False, default="")
    url = db.Column(db.String(500), nullable=True)
    region = db.Column(db.String(80), nullable=True)
    roadmap_step_key = db.Column(db.String(40), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)


class AnalyticsEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    event = db.Column(db.String(80), nullable=False, index=True)
    meta_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    user = db.relationship("User", backref=db.backref("analytics_events", lazy=True))


class IdeaPoll(db.Model):
    VERDICT_PENDING = "pending"
    VERDICT_GOOD = "good"
    VERDICT_UNCLEAR = "unclear"
    VERDICT_WEAK = "weak"

    id = db.Column(db.Integer, primary_key=True)
    startup_id = db.Column(db.Integer, db.ForeignKey("startup.id"), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activity.id"), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    hypothesis = db.Column(db.Text, nullable=False)
    verdict = db.Column(db.String(16), nullable=False, default=VERDICT_PENDING, index=True)
    score = db.Column(db.Integer, nullable=False, default=0)
    yes_count = db.Column(db.Integer, nullable=False, default=0)
    no_count = db.Column(db.Integer, nullable=False, default=0)
    maybe_count = db.Column(db.Integer, nullable=False, default=0)
    engagement_count = db.Column(db.Integer, nullable=False, default=0)
    computed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    startup = db.relationship("Startup", backref=db.backref("idea_polls", lazy=True))
    activity = db.relationship("Activity", backref=db.backref("idea_poll", uselist=False))
    user = db.relationship("User", backref=db.backref("idea_polls", lazy=True))
    votes = db.relationship("IdeaPollVote", back_populates="poll", cascade="all, delete-orphan", lazy=True)


class IdeaPollVote(db.Model):
    CHOICE_YES = "yes"
    CHOICE_NO = "no"
    CHOICE_MAYBE = "maybe"

    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey("idea_poll.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    choice = db.Column(db.String(8), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    poll = db.relationship("IdeaPoll", back_populates="votes")
    user = db.relationship("User", backref=db.backref("poll_votes", lazy=True))

    __table_args__ = (db.UniqueConstraint("poll_id", "user_id", name="uq_poll_vote"),)


class ActivityReaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activity.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    reaction = db.Column(db.String(16), nullable=False, default="fire")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    activity = db.relationship("Activity", backref=db.backref("reactions", lazy=True, cascade="all, delete-orphan"))
    user = db.relationship("User", backref=db.backref("activity_reactions", lazy=True))

    __table_args__ = (db.UniqueConstraint("activity_id", "user_id", "reaction", name="uq_activity_reaction"),)
