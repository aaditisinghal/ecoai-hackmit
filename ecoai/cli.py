"""Flask CLI commands.

    flask init-db            create tables directly (development shortcut)
    flask create-admin       create or promote an administrator
    flask issue-api-key      mint a key for an existing account
    flask import-legacy      import the pre-2.0 SQLite database

Schema changes in a real deployment go through ``flask db upgrade``, which the
Procfile runs on every release.
"""

from __future__ import annotations

import getpass
import sys

import click
from flask import Flask
from flask.cli import with_appcontext
from sqlalchemy import func, or_, select

from ecoai.extensions import db
from ecoai.models import User, utcnow
from ecoai.services.credentials import (
    PasswordPolicyError,
    generate_api_key,
    hash_password,
    validate_password_policy,
)


def register(app: Flask) -> None:
    app.cli.add_command(init_db)
    app.cli.add_command(create_admin)
    app.cli.add_command(issue_api_key)
    app.cli.add_command(import_legacy)


@click.command("init-db")
@with_appcontext
def init_db() -> None:
    """Create every table from the models.

    Convenient locally. Use ``flask db upgrade`` anywhere that has data worth
    keeping, since this cannot alter an existing table.
    """
    db.create_all()
    click.secho("Tables created.", fg="green")


@click.command("create-admin")
@click.option("--username", prompt=True, help="Username for the administrator.")
@click.option("--email", prompt=True, help="Email address.")
@click.option("--password", default=None, help="Read from a prompt if omitted.")
@with_appcontext
def create_admin(username: str, email: str, password: str | None) -> None:
    """Create an administrator, or promote an existing account.

    Administrator access is a column on the account, granted here. It replaces
    the fixed username and password pair the previous version compared against
    in source, which meant anyone who read the repository was an admin.
    """
    username = username.strip()
    email = email.strip().lower()

    existing = db.session.execute(
        select(User).where(
            or_(func.lower(User.username) == username.lower(), User.email == email)
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.is_admin:
            click.secho(f"{existing.username} is already an administrator.", fg="yellow")
            return
        existing.is_admin = True
        db.session.commit()
        click.secho(f"Promoted {existing.username} to administrator.", fg="green")
        return

    if password is None:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            click.secho("Passwords do not match.", fg="red")
            sys.exit(1)

    try:
        validate_password_policy(password)
    except PasswordPolicyError as exc:
        click.secho(str(exc), fg="red")
        sys.exit(1)

    issued = generate_api_key()
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        is_admin=True,
        api_key_hash=issued.hashed,
        api_key_prefix=issued.prefix,
        api_key_created_at=utcnow(),
    )
    db.session.add(user)
    db.session.commit()

    click.secho(f"Created administrator {username}.", fg="green")
    click.echo(f"API key (shown once): {issued.secret}")


@click.command("issue-api-key")
@click.argument("username")
@with_appcontext
def issue_api_key(username: str) -> None:
    """Mint a new API key, invalidating the account's previous one."""
    user = db.session.execute(
        select(User).where(func.lower(User.username) == username.strip().lower())
    ).scalar_one_or_none()

    if user is None:
        click.secho(f"No account named {username!r}.", fg="red")
        sys.exit(1)

    issued = generate_api_key()
    user.api_key_hash = issued.hashed
    user.api_key_prefix = issued.prefix
    user.api_key_created_at = utcnow()
    db.session.commit()

    click.secho(f"New API key for {user.username} (shown once):", fg="green")
    click.echo(issued.secret)


@click.command("import-legacy")
@click.argument("sqlite_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, help="Report what would change without writing.")
@with_appcontext
def import_legacy(sqlite_path: str, dry_run: bool) -> None:
    """Import a pre-2.0 ``ecoai_portal.db`` into the current schema."""
    from ecoai.migration.legacy_import import import_legacy_database

    report = import_legacy_database(sqlite_path, dry_run=dry_run)

    click.secho(report.render(), fg="cyan")
    if dry_run:
        click.secho("Dry run: nothing was written.", fg="yellow")
