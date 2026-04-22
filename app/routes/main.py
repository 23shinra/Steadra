from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, jsonify, make_response, redirect, render_template, request, url_for

from ..forms import ApplyOrderForm, CreateOrderForm
from .auth import current_user

bp = Blueprint("main", __name__)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _require_auth():
    if current_user():
        return None
    if _is_htmx():
        resp = make_response("", 200)
        resp.headers["HX-Redirect"] = url_for("auth.start")
        return resp
    return redirect(url_for("auth.start"))


_CATEGORY_LABELS: dict[str, str] = {
    "dev": "Разработка",
    "design": "Дизайн",
    "marketing": "Маркетинг",
    "ai": "AI-услуги",
    "content": "Контент",
    "consulting": "Консалтинг",
    "offline": "Оффлайн-услуги",
}


def _mock_orders() -> list[dict]:
    return [
        {
            "id": 1201,
            "title": "Дизайн лендинга + адаптив (Figma)",
            "description": "Нужен минимализм, темная тема, 7 дней. Отдать Figma + экспорт ассетов.",
            "format": "online",
            "category": "design",
            "duration": "oneoff",
            "performer": "solo",
            "country": "EU",
            "language": "ru/en",
            "budget": "$400–700",
            "verified": True,
        },
        {
            "id": 1202,
            "title": "Backend интеграции + платежи (MVP marketplace)",
            "description": "Нужны интеграции Stripe/PayPal, вебхуки, базовый биллинг. Стек обсуждаем.",
            "format": "hybrid",
            "category": "dev",
            "duration": "long",
            "performer": "team",
            "country": "KZ/EU",
            "language": "en",
            "budget": "$2k–5k",
            "verified": False,
        },
        {
            "id": 1203,
            "title": "AI-ассистент: промпт‑пак + сценарии продаж",
            "description": "Нужно собрать 20–30 промптов и сценарии для поддержки/продаж. Желательно опыт b2b.",
            "format": "online",
            "category": "ai",
            "duration": "oneoff",
            "performer": "solo",
            "country": "Global",
            "language": "ru",
            "budget": "$300–600",
            "verified": True,
        },
        {
            "id": 1204,
            "title": "Growth маркетолог: запуск в EU (B2B)",
            "description": "План экспериментов на 4 недели: ICP, каналы, офферы, ретеншн. KPI и отчетность.",
            "format": "online",
            "category": "marketing",
            "duration": "long",
            "performer": "solo",
            "country": "EU",
            "language": "en",
            "budget": "$1k–3k/mo",
            "verified": False,
        },
        {
            "id": 1205,
            "title": "Оффлайн: видеосъемка промо‑ролика в Дубае",
            "description": "Нужна команда: съемка + монтаж. 1 день съемки, 30–45 сек ролик, 2 правки.",
            "format": "offline",
            "category": "offline",
            "duration": "oneoff",
            "performer": "agency",
            "country": "UAE",
            "language": "en/ru",
            "budget": "$800–1500",
            "verified": True,
        },
        {
            "id": 1206,
            "title": "Контент‑стратегия + 10 постов для профиля фаундера",
            "description": "Позиционирование, тональность, контент‑пилоны, 10 черновиков постов + редактура.",
            "format": "online",
            "category": "content",
            "duration": "oneoff",
            "performer": "solo",
            "country": "Global",
            "language": "ru",
            "budget": "$250–450",
            "verified": False,
        },
    ]


def _get_market_filters() -> dict[str, str]:
    args = request.args
    return {
        "q": (args.get("q") or "").strip(),
        "format": (args.get("format") or "").strip(),
        "category": (args.get("category") or "").strip(),
        "duration": (args.get("duration") or "").strip(),
        "performer": (args.get("performer") or "").strip(),
    }


def _filter_orders(orders: list[dict], f: dict[str, str]) -> list[dict]:
    q = f["q"].lower()

    def matches(o: dict) -> bool:
        if q and q not in (o["title"] + " " + o["description"]).lower():
            return False
        if f["format"] and o["format"] != f["format"]:
            return False
        if f["category"] and o["category"] != f["category"]:
            return False
        if f["duration"] and o["duration"] != f["duration"]:
            return False
        if f["performer"] and o["performer"] != f["performer"]:
            return False
        return True

    return [o for o in orders if matches(o)]


@bp.get("/")
def index():
    # Если пользователь авторизован — открываем чат по умолчанию.
    if current_user():
        return redirect(url_for("main.ui_tab", tab="chat"))
    return redirect(url_for("auth.start"))


@bp.get("/pwa/manifest.json")
def manifest():
    return jsonify(
        {
            "name": "Steadra",
            "short_name": "Steadra",
            "start_url": url_for("main.index"),
            "display": "standalone",
            "background_color": "#0b1020",
            "theme_color": "#0b1020",
            "icons": [
                {
                    "src": url_for("static", filename="icons/steadra-192.png"),
                    "sizes": "192x192",
                    "type": "image/png",
                    "purpose": "any",
                },
                {
                    "src": url_for("static", filename="icons/steadra-512.png"),
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any",
                },
            ],
        }
    )


@bp.get("/pwa/service-worker.js")
def service_worker():
    return render_template("service-worker.js", build=str(int(datetime.utcnow().timestamp()))), 200, {
        "Content-Type": "application/javascript; charset=utf-8"
    }


@bp.get("/ui/<tab>")
def ui_tab(tab: str):
    guard = _require_auth()
    if guard:
        return guard

    tab = (tab or "").lower()
    known = {"feed", "leaderboard", "market", "startup", "chat", "profile", "teams", "passport", "growth", "home", "ai"}
    if tab not in known:
        tab = "feed"

    if _is_htmx():
        if tab == "home":
            return redirect(url_for("main.ui_tab", tab="feed"))
        if tab == "feed":
            return render_template("partials/feed.html", active="feed")
        if tab == "ai":
            return redirect(url_for("main.ui_tab", tab="chat"))
        if tab == "chat":
            return render_template("partials/chat.html", active="chat")
        if tab == "market":
            return redirect(url_for("main.ui_tab", tab="leaderboard"))
        if tab == "leaderboard":
            return render_template("partials/leaderboard.html", active="leaderboard")
        if tab == "startup":
            return render_template("partials/startup.html", active="startup")
        return render_template(f"partials/{tab}.html", active=tab)
    # Full-page render for direct navigation (prevents redirect loops)
    if tab in {"home", "feed"}:
        return render_template("index.html", active="feed")
    if tab == "ai":
        return render_template("index.html", active="chat")
    if tab in {"leaderboard", "market", "startup", "chat", "profile"}:
        if tab == "market":
            return redirect(url_for("main.ui_tab", tab="leaderboard"))
        if tab == "leaderboard":
            return render_template("index.html", active="leaderboard")
        return render_template("index.html", active=tab)
    return render_template("index.html", active="feed")


@bp.get("/ui/startup/<section>")
def startup_section(section: str):
    section = (section or "rooms").lower()
    if section not in {"rooms", "growth"}:
        section = "rooms"
    if _is_htmx():
        return render_template(f"partials/startup_{section}.html", active="startup")
    return redirect(url_for("main.ui_tab", tab="startup"))


@bp.get("/ui/teams")
def legacy_teams():
    return redirect(url_for("main.ui_tab", tab="startup"))


@bp.get("/ui/market/<int:order_id>")
def market_detail(order_id: int):
    order = next((o for o in _mock_orders() if o["id"] == order_id), None)
    if not order:
        abort(404)
    if _is_htmx():
        return render_template("partials/market_detail.html", active="market", order=order, category_labels=_CATEGORY_LABELS)
    return redirect(url_for("main.ui_tab", tab="market"))


@bp.route("/ui/market/<int:order_id>/apply", methods=["GET", "POST"])
def market_apply(order_id: int):
    order = next((o for o in _mock_orders() if o["id"] == order_id), None)
    if not order:
        abort(404)

    form = ApplyOrderForm()
    if form.validate_on_submit():
        if _is_htmx():
            return render_template(
                "partials/toast.html",
                title="Отклик отправлен",
                body="Заказчик получит уведомление. Если будет ответ — он появится во входящих.",
            )
        return redirect(url_for("main.market_detail", order_id=order_id))

    template = "partials/market_apply.html" if _is_htmx() else "index.html"
    return render_template(template, active="market", order=order, form=form, category_labels=_CATEGORY_LABELS)


@bp.route("/ui/market/create-order", methods=["GET", "POST"])
def create_order():
    form = CreateOrderForm()
    if form.validate_on_submit():
        # Mock response for the prototype (no persistence yet).
        if _is_htmx():
            return render_template(
                "partials/toast.html",
                title="Заявка создана (макет)",
                body="Дальше подключим БД и модуль сделок/паспортов.",
            )
        return redirect(url_for("main.ui_tab", tab="market"))

    template = "partials/market_create_order.html" if _is_htmx() else "index.html"
    return render_template(template, form=form, active="market")

