from __future__ import annotations

from flask import g, session

SUPPORTED_LOCALES = frozenset({"ru", "kk", "en"})
DEFAULT_LOCALE = "ru"

MESSAGES: dict[str, dict[str, str]] = {
    "nav.home": {"ru": "Главная", "kk": "Басты", "en": "Home"},
    "nav.feed": {"ru": "Лента", "kk": "Жентақ", "en": "Feed"},
    "nav.ai": {"ru": "ИИ", "kk": "AI", "en": "AI"},
    "nav.progress": {"ru": "Путь", "kk": "Бағыт", "en": "Path"},
    "nav.profile": {"ru": "Профиль", "kk": "Профиль", "en": "Profile"},
    "nav.search": {"ru": "Поиск", "kk": "Іздеу", "en": "Search"},
    "nav.messages": {"ru": "Сообщения", "kk": "Хабарламалар", "en": "Messages"},
    "nav.partners": {"ru": "Партнёры", "kk": "Серіктестер", "en": "Partners"},
    "nav.notifications": {"ru": "Уведомления", "kk": "Хабарламалар", "en": "Notifications"},
    "feed.ai_generated": {
        "ru": "Сгенерировано с помощью ИИ",
        "kk": "AI көмегімен жасалған",
        "en": "Generated with AI",
    },
    "profile.message": {"ru": "Написать", "kk": "Жазу", "en": "Message"},
    "profile.tab.projects": {"ru": "Проекты", "kk": "Жобалар", "en": "Projects"},
    "profile.tab.team": {"ru": "Команда", "kk": "Команда", "en": "Team"},
    "profile.tab.achievements": {"ru": "Достижения", "kk": "Жетістіктер", "en": "Achievements"},
    "profile.tab.settings": {"ru": "Настройки", "kk": "Баптаулар", "en": "Settings"},
    "profile.my_projects": {"ru": "Мои проекты", "kk": "Менің жобаларым", "en": "My projects"},
    "profile.projects": {"ru": "Проекты", "kk": "Жобалар", "en": "Projects"},
    "profile.no_projects_own": {"ru": "Нет проектов", "kk": "Жобалар жоқ", "en": "No projects"},
    "profile.no_projects_other": {"ru": "Проектов пока нет", "kk": "Әзірше жобалар жоқ", "en": "No projects yet"},
    "profile.no_projects_hint_own": {
        "ru": "После создания стартапа он появится здесь.",
        "kk": "Стартап құрғаннан кейін ол осында пайда болады.",
        "en": "After you launch a startup, it will appear here.",
    },
    "profile.no_projects_hint_other": {
        "ru": "У этого пользователя пока нет стартапов на платформе.",
        "kk": "Бұл пайдаланушыда әзірше стартаптар жоқ.",
        "en": "This user has no startups on the platform yet.",
    },
    "profile.logout": {"ru": "Выйти", "kk": "Шығу", "en": "Log out"},
    "profile.streak_tip_own": {
        "ru": "Стрик — сколько шагов карты ты закрыл подряд без паузы.",
        "kk": "Стрик — картадағы қатарынан жабылған қадамдар.",
        "en": "Streak — consecutive roadmap steps you closed without a break.",
    },
    "profile.streak_tip_other": {
        "ru": "Стрик — закрытые подряд шаги на карте.",
        "kk": "Стрик — картадағы қатарынан жабылған қадамдар.",
        "en": "Streak — consecutive closed roadmap steps.",
    },
    "profile.streak_yours": {"ru": "Ваш стрик", "kk": "Сіздің стрик", "en": "Your streak"},
    "profile.streak_label": {"ru": "Стрик", "kk": "Стрик", "en": "Streak"},
    "profile.day_one": {"ru": "шаг", "kk": "қадам", "en": "step"},
    "profile.day_few": {"ru": "шага", "kk": "қадам", "en": "steps"},
    "profile.day_many": {"ru": "шагов", "kk": "қадам", "en": "steps"},
    "settings.language_partial": {
        "ru": "Пока переведены настройки и навигация. Остальной интерфейс на русском.",
        "kk": "Әзірше баптаулар мен навигация аударылған. Қалғаны орысша.",
        "en": "Settings and navigation are translated so far. Most of the UI stays in Russian.",
    },
    "profile.stat.projects": {"ru": "проекты", "kk": "жобалар", "en": "projects"},
    "profile.stat.streak": {"ru": "стрик", "kk": "стрик", "en": "streak"},
    "profile.stat.xp": {"ru": "XP", "kk": "XP", "en": "XP"},
    "profile.stat.achievements": {"ru": "награды", "kk": "марапаттар", "en": "badges"},
    "profile.stat.team": {"ru": "команда", "kk": "команда", "en": "team"},
    "profile.stat.favorites": {"ru": "избранное", "kk": "таңдаулы", "en": "saved"},
    "metric.health": {"ru": "Здоровье", "kk": "Денсаулық", "en": "Health"},
    "metric.traction": {"ru": "Тяга", "kk": "Тартым", "en": "Traction"},
    "metric.updates": {"ru": "Апдейты", "kk": "Жаңартулар", "en": "Updates"},
    "metric.score": {"ru": "Балл", "kk": "Балл", "en": "Score"},
    "common.proof": {"ru": "Доказательство", "kk": "Дәлел", "en": "Proof"},
    "settings.panel_title": {"ru": "Интерфейс", "kk": "Интерфейс", "en": "Interface"},
    "settings.theme": {"ru": "Тема", "kk": "Стиль", "en": "Theme"},
    "settings.theme_desc": {"ru": "Оформление интерфейса", "kk": "Интерфейс көрінісі", "en": "Interface appearance"},
    "settings.theme_dark": {"ru": "Тёмная", "kk": "Қараңғы", "en": "Dark"},
    "settings.theme_light": {"ru": "Светлая", "kk": "Жарық", "en": "Light"},
    "settings.theme_saved": {
        "ru": "Тема обновлена",
        "kk": "Стиль жаңартылды",
        "en": "Theme updated",
    },
    "settings.language": {"ru": "Язык", "kk": "Тіл", "en": "Language"},
    "settings.language_desc": {"ru": "Язык интерфейса", "kk": "Интерфейс тілі", "en": "Interface language"},
    "settings.language_saved": {
        "ru": "Язык интерфейса изменён",
        "kk": "Интерфейс тілі өзгертілді",
        "en": "Interface language updated",
    },
    "settings.edit_profile": {"ru": "Редактировать профиль", "kk": "Профильді өңдеу", "en": "Edit profile"},
    "settings.edit_profile_desc": {
        "ru": "Имя, роль, аватар и телефон",
        "kk": "Аты, рөлі, аватар және телефон",
        "en": "Name, role, avatar and phone",
    },
    "settings.back": {"ru": "← Профиль", "kk": "← Профиль", "en": "← Profile"},
    "settings.title": {"ru": "Редактировать профиль", "kk": "Профильді өңдеу", "en": "Edit profile"},
    "settings.section": {"ru": "Профиль", "kk": "Профиль", "en": "Profile"},
    "settings.save": {"ru": "Сохранить", "kk": "Сақтау", "en": "Save"},
    "settings.cancel": {"ru": "Отмена", "kk": "Болдырмау", "en": "Cancel"},
    "settings.profile_saved": {"ru": "Профиль сохранён", "kk": "Профиль сақталды", "en": "Profile saved"},
    "achievements.progress": {"ru": "Прогресс", "kk": "Прогресс", "en": "Progress"},
    "achievements.of": {"ru": "из", "kk": "ішінен", "en": "of"},
    "achievements.received": {"ru": "Получено", "kk": "Алынды", "en": "Earned"},
    "achievements.not_received": {"ru": "Не получено", "kk": "Алынбады", "en": "Not earned"},
    "ach.registration.title": {"ru": "Регистрация", "kk": "Тіркелу", "en": "Registration"},
    "ach.registration.desc": {
        "ru": "Создал аккаунт в Kangaroo",
        "kk": "Kangaroo-да аккаунт ашты",
        "en": "Created a Kangaroo account",
    },
    "ach.first_ship.title": {"ru": "Первый шаг", "kk": "Бірінші қадам", "en": "First ship"},
    "ach.first_ship.desc": {
        "ru": "Закрыл первый шаг на карте",
        "kk": "Картадағы бірінші қадамды аяқтады",
        "en": "Completed the first roadmap step",
    },
    "ach.streak_7.title": {"ru": "7 дней подряд", "kk": "7 күн қатарынан", "en": "7 days in a row"},
    "ach.streak_7.desc": {"ru": "Стрик 7+ дней", "kk": "7+ күн стрик", "en": "7+ day streak"},
    "ach.too_open.title": {"ru": "ТОО открыто", "kk": "ТОО ашылды", "en": "Company registered"},
    "ach.too_open.desc": {
        "ru": "Зарегистрировал компанию",
        "kk": "Компанияны тіркеді",
        "en": "Registered a company",
    },
    "ach.xp_100.title": {"ru": "100 XP", "kk": "100 XP", "en": "100 XP"},
    "ach.xp_100.desc": {
        "ru": "Набрал 100 очков роста",
        "kk": "100 өсу ұпайы жинады",
        "en": "Earned 100 growth points",
    },
    "ach.first_post.title": {"ru": "Первый пост", "kk": "Бірінші пост", "en": "First post"},
    "ach.first_post.desc": {
        "ru": "Опубликовал в ленте",
        "kk": "Жentaқta жариялады",
        "en": "Published in the feed",
    },
    "ach.roast_done.title": {"ru": "Прожарка пройдена", "kk": "Прожарка өтті", "en": "Roast completed"},
    "ach.roast_done.desc": {
        "ru": "Прошёл AI roast идеи",
        "kk": "AI прожаркадан өтті",
        "en": "Completed the AI idea roast",
    },
}

ACHIEVEMENT_KEYS = {
    "registration": ("ach.registration.title", "ach.registration.desc"),
    "first_ship": ("ach.first_ship.title", "ach.first_ship.desc"),
    "streak_7": ("ach.streak_7.title", "ach.streak_7.desc"),
    "too_open": ("ach.too_open.title", "ach.too_open.desc"),
    "xp_100": ("ach.xp_100.title", "ach.xp_100.desc"),
    "first_post": ("ach.first_post.title", "ach.first_post.desc"),
    "roast_done": ("ach.roast_done.title", "ach.roast_done.desc"),
}


def _normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    code = str(value).strip().lower()[:5]
    return code if code in SUPPORTED_LOCALES else None


def get_request_locale() -> str:
    from flask import g, request

    url_locale = _normalize_locale(getattr(g, "url_locale", None))
    if url_locale:
        return url_locale

    env_locale = _normalize_locale(request.environ.get("kangaroo.locale"))
    if env_locale:
        return env_locale

    session_locale = _normalize_locale(session.get("locale"))
    if session_locale:
        return session_locale

    from ..routes.auth import session_user

    user = session_user()
    user_locale = _normalize_locale(getattr(user, "locale", None) if user else None)
    if user_locale:
        return user_locale

    from flask import request

    best = request.accept_languages.best_match(list(SUPPORTED_LOCALES))
    return _normalize_locale(best) or DEFAULT_LOCALE


def set_request_locale(locale: str) -> str:
    code = _normalize_locale(locale) or DEFAULT_LOCALE
    session["locale"] = code
    session.modified = True
    from flask import g

    g.user_locale = code
    return code


def resolve_locale(locale: str | None = None) -> str:
    if locale in SUPPORTED_LOCALES:
        return locale
    return get_request_locale()


def translate(key: str, locale: str | None = None, **kwargs) -> str:
    lang = resolve_locale(locale)
    catalog = MESSAGES.get(key, {})
    text = catalog.get(lang) or catalog.get(DEFAULT_LOCALE) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def achievement_labels(key: str, locale: str | None = None) -> tuple[str, str]:
    title_key, desc_key = ACHIEVEMENT_KEYS.get(key, ("", ""))
    if not title_key:
        return key, ""
    return translate(title_key, locale), translate(desc_key, locale)


def streak_days_word(count: int, locale: str | None = None) -> str:
    lang = resolve_locale(locale)
    if lang == "en":
        return "day" if count == 1 else "days"
    n10 = count % 10
    n100 = count % 100
    if n10 == 1 and n100 != 11:
        return translate("profile.day_one", lang)
    if n10 in {2, 3, 4} and n100 not in {12, 13, 14}:
        return translate("profile.day_few", lang)
    return translate("profile.day_many", lang)
