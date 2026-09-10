from __future__ import annotations

import random

from ..models.entities import User

_GREETINGS = [
    "{name}, с чего начнём?",
    "Привет, {name}. Какую идею прожарим?",
    "{name}, что строим сегодня?",
    "С чего начнём, {name}?",
    "{name}, какую гипотезу проверим?",
    "Что строим, {name}?",
    "{name}, одна фраза про стартап — погнали",
    "Какую боль закрываем, {name}?",
    "{name}, расскажи про продукт в одном предложении",
    "Ну что, {name}, какой стартап на стол?",
]

_GREETINGS_ANON = [
    "С чего начнём?",
    "Какую идею прожарим?",
    "Одна фраза про стартап — начнём",
    "Что строим сегодня?",
    "Какую гипотезу проверим?",
    "Расскажи про продукт в одном предложении",
]

_ONBOARDING = [
    "{name}, добро пожаловать. С чего начнём?",
    "Рад видеть, {name}. Какую идею разберём?",
    "{name}, начнём с одной фразы про продукт?",
]

_ONBOARDING_ANON = [
    "Добро пожаловать. С чего начнём?",
    "Начнём с одной фразы про продукт?",
]


def _first_name(user: User | None) -> str | None:
    if not user:
        return None
    name = (user.name or "").strip()
    if not name or name == "Founder":
        return None
    return name.split()[0]


def greeting_for_user(user: User | None, *, onboarding: bool = False) -> str:
    first = _first_name(user)
    if onboarding:
        pool = _ONBOARDING if first else _ONBOARDING_ANON
    else:
        pool = _GREETINGS if first else _GREETINGS_ANON
    template = random.choice(pool)
    if first:
        return template.format(name=first)
    return template
