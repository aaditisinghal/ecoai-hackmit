"""Password hashing and API key issuance.

Two different problems that deserve two different tools:

*Passwords* are low entropy and chosen by humans, so they need a deliberately
slow KDF. We use Werkzeug's default (scrypt), and transparently upgrade the
unsalted SHA-256 digests inherited from the previous implementation the first
time a legacy user successfully logs in.

*API keys* are 256 bits of CSPRNG output. Brute-forcing one is infeasible no
matter how fast the digest is, so a slow KDF here would buy nothing while
adding scrypt's cost to every authenticated API request - a self-inflicted
denial of service. Plain SHA-256 is the correct choice for a high-entropy
secret, and it keeps lookup to a single indexed query.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from werkzeug.security import check_password_hash, generate_password_hash

API_KEY_PREFIX = "ecoai_"
# 32 bytes -> 43 URL-safe characters. Comfortably beyond brute force.
API_KEY_ENTROPY_BYTES = 32
# Characters kept in cleartext so a user can recognise which key is which.
API_KEY_DISPLAY_CHARS = 14

# A bare 64-character hex string is the fingerprint of the legacy
# hashlib.sha256(password).hexdigest() scheme. Modern Werkzeug hashes always
# carry a "method$salt$digest" structure, so the two can never be confused.
_LEGACY_SHA256 = re.compile(r"^[0-9a-f]{64}$")

MIN_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class IssuedApiKey:
    """A freshly minted key. ``secret`` is the only time the full value exists."""

    secret: str
    hashed: str
    prefix: str


class PasswordPolicyError(ValueError):
    """Raised when a proposed password does not meet the minimum policy."""


def hash_password(password: str) -> str:
    """Hash a password with the current default KDF."""
    return generate_password_hash(password)


def verify_password(stored_hash: str | None, candidate: str) -> bool:
    """Check a password against either a current or a legacy hash.

    Returns False for accounts with no password at all, which is how OAuth-only
    users are prevented from authenticating through the password form.
    """
    if not stored_hash or not candidate:
        return False

    if _LEGACY_SHA256.match(stored_hash):
        legacy_digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_digest, stored_hash)

    return check_password_hash(stored_hash, candidate)


def needs_rehash(stored_hash: str | None) -> bool:
    """True when a hash uses the deprecated scheme and should be upgraded."""
    return bool(stored_hash) and bool(_LEGACY_SHA256.match(stored_hash))


def validate_password_policy(password: str) -> None:
    """Enforce the minimum password policy, raising on violation.

    Length is the dominant factor in resisting offline cracking, so the policy
    is a length floor plus a check against the handful of passwords that show
    up in every credential stuffing list. Composition rules ("must contain a
    symbol") are deliberately omitted; they push users toward predictable
    substitutions without materially increasing entropy.
    """
    # Breach check first: it is the more specific diagnosis, and most entries
    # in the list are shorter than the length floor, so checking length first
    # would make the breach message unreachable.
    if password.lower() in _COMMON_PASSWORDS:
        raise PasswordPolicyError("That password appears in known breach lists. Choose another.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )


_COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password123",
        "passw0rd123",
        "123456789012",
        "qwertyuiop12",
        "letmein12345",
        "administrator",
        "iloveyou1234",
        "welcome12345",
        "changeme1234",
    }
)


def generate_api_key() -> IssuedApiKey:
    """Mint a new API key.

    The caller must persist ``hashed`` and ``prefix`` and show ``secret`` to the
    user exactly once - it cannot be recovered afterwards.
    """
    secret = f"{API_KEY_PREFIX}{secrets.token_urlsafe(API_KEY_ENTROPY_BYTES)}"
    return IssuedApiKey(
        secret=secret,
        hashed=hash_api_key(secret),
        prefix=secret[:API_KEY_DISPLAY_CHARS],
    )


def hash_api_key(secret: str) -> str:
    """Digest used for storage and lookup."""
    return hashlib.sha256(secret.strip().encode("utf-8")).hexdigest()


def looks_like_api_key(value: str) -> bool:
    """Cheap shape check, used to reject junk before touching the database."""
    value = value.strip()
    return value.startswith(API_KEY_PREFIX) and len(value) >= len(API_KEY_PREFIX) + 20
