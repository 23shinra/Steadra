from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, SelectMultipleField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, Regexp, URL


class CreateOrderForm(FlaskForm):
    title = StringField("Заголовок", validators=[DataRequired(), Length(max=200)])
    category = SelectField(
        "Категория",
        choices=[
            ("dev", "Разработка"),
            ("design", "Дизайн"),
            ("marketing", "Маркетинг"),
            ("ai", "AI-услуги"),
            ("content", "Контент"),
            ("consulting", "Консалтинг"),
            ("offline", "Оффлайн-услуги"),
        ],
    )
    format = SelectField(
        "Формат",
        choices=[("online", "Онлайн"), ("offline", "Оффлайн"), ("hybrid", "Гибрид")],
    )
    description = TextAreaField("Описание", validators=[Length(max=4000)])


class ApplyOrderForm(FlaskForm):
    message = TextAreaField("Сообщение", validators=[DataRequired(), Length(max=2000)])
    rate = StringField("Ставка/условия (опционально)", validators=[Optional(), Length(max=80)])
    portfolio_url = StringField("Портфолио (ссылка)", validators=[Optional(), URL(), Length(max=300)])


class PhoneForm(FlaskForm):
    phone = StringField(
        "Номер телефона",
        validators=[DataRequired(), Length(max=32), Regexp(r"^[0-9+()\-\s]+$", message="Введите номер телефона")],
    )


class CodeForm(FlaskForm):
    code = StringField("Код из SMS", validators=[DataRequired(), Length(min=4, max=6)])


class PasswordForm(FlaskForm):
    password = PasswordField("Пароль", validators=[DataRequired(), Length(min=4, max=64)])


class SkillsForm(FlaskForm):
    full_name = StringField("Имя и фамилия", validators=[DataRequired(), Length(max=160)])
    skills = SelectMultipleField(
        "Скиллы",
        choices=[
            ("Product", "Продукт"),
            ("Founder", "Фаундер"),
            ("Backend", "Бэкенд"),
            ("Frontend", "Фронтенд"),
            ("Design", "Дизайн"),
            ("Growth", "Рост"),
            ("AI", "AI"),
            ("Sales", "Продажи"),
        ],
    )

