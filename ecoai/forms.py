"""WTForms definitions.

Using forms rather than reading ``request.form`` directly gives every POST
route CSRF protection and server-side validation by construction - both were
absent from the previous implementation, which indexed straight into
``request.form`` and raised a 400 on any missing field.
"""

from __future__ import annotations

import re

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, ValidationError

from ecoai.services.credentials import (
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    validate_password_policy,
)

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"


class LoginForm(FlaskForm):
    identifier = StringField(
        "Username or email",
        validators=[DataRequired(message="Enter your username or email."), Length(max=320)],
    )
    password = PasswordField(
        "Password", validators=[DataRequired(message="Enter your password.")]
    )
    remember = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")


class SignupForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Choose a username."),
            Length(min=3, max=64, message="Username must be between 3 and 64 characters."),
            Regexp(
                USERNAME_PATTERN,
                message="Use letters, numbers, and . _ - only.",
            ),
        ],
    )
    email = StringField(
        "Email",
        validators=[
            DataRequired(message="Enter your email address."),
            Email(message="That does not look like a valid email address."),
            Length(max=320),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Choose a password."),
            Length(
                min=MIN_PASSWORD_LENGTH,
                message=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            ),
        ],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(message="Confirm your password."),
            EqualTo("password", message="Passwords do not match."),
        ],
    )
    submit = SubmitField("Create account")

    def validate_password(self, field) -> None:
        try:
            validate_password_policy(field.data or "")
        except PasswordPolicyError as exc:
            raise ValidationError(str(exc)) from exc

    def validate_username(self, field) -> None:
        # Reserved so they stay available for routes and support addresses.
        if (field.data or "").lower() in {"admin", "administrator", "root", "support", "api"}:
            raise ValidationError("That username is reserved.")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField(
        "Current password", validators=[DataRequired(message="Enter your current password.")]
    )
    new_password = PasswordField(
        "New password",
        validators=[
            DataRequired(message="Choose a new password."),
            Length(min=MIN_PASSWORD_LENGTH),
        ],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[
            DataRequired(),
            EqualTo("new_password", message="Passwords do not match."),
        ],
    )
    submit = SubmitField("Update password")

    def validate_new_password(self, field) -> None:
        try:
            validate_password_policy(field.data or "")
        except PasswordPolicyError as exc:
            raise ValidationError(str(exc)) from exc


class RotateApiKeyForm(FlaskForm):
    """Deliberately field-less: its only job is to carry a CSRF token."""

    submit = SubmitField("Generate new API key")


class SendReportForm(FlaskForm):
    """Emails the impact report.

    There is no recipient field. The report goes to the signed-in account's own
    address, which is what stops this from being the open relay it used to be.
    """

    submit = SubmitField("Email my impact report")


class OptimizeForm(FlaskForm):
    prompt = TextAreaField(
        "Prompt",
        validators=[
            DataRequired(message="Enter a prompt to optimize."),
            Length(max=50_000, message="Prompts are limited to 50,000 characters."),
        ],
    )
    strategy = SelectField(
        "Strategy",
        choices=[
            ("conservative", "Conservative"),
            ("balanced", "Balanced"),
            ("aggressive", "Aggressive"),
        ],
        default="balanced",
    )
    model = StringField("Model", validators=[Length(max=64)], default="gpt-4o-mini")
    region = StringField("Region", validators=[Length(max=64)], default="us-east-1")
    submit = SubmitField("Optimize")


class AdminUserActionForm(FlaskForm):
    """CSRF carrier for admin toggles."""

    submit = SubmitField("Apply")


def normalize_username(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()
