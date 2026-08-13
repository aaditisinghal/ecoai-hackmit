"""Password hashing and API key issuance."""

from __future__ import annotations

import hashlib

import pytest

from ecoai.services.credentials import (
    API_KEY_PREFIX,
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    generate_api_key,
    hash_api_key,
    hash_password,
    looks_like_api_key,
    needs_rehash,
    validate_password_policy,
    verify_password,
)


class TestPasswordHashing:
    def test_round_trip(self):
        digest = hash_password("a-decent-password")
        assert verify_password(digest, "a-decent-password") is True
        assert verify_password(digest, "a-decent-passwore") is False

    def test_hashes_are_salted(self):
        assert hash_password("identical") != hash_password("identical")

    def test_empty_candidate_never_verifies(self):
        assert verify_password(hash_password("something"), "") is False

    def test_missing_hash_never_verifies(self):
        assert verify_password(None, "anything") is False
        assert verify_password("", "anything") is False


class TestLegacyHashes:
    def test_legacy_digest_verifies(self):
        legacy = hashlib.sha256(b"legacy").hexdigest()
        assert verify_password(legacy, "legacy") is True
        assert verify_password(legacy, "other") is False

    def test_legacy_digest_is_flagged_for_rehash(self):
        assert needs_rehash(hashlib.sha256(b"x").hexdigest()) is True

    def test_current_digest_is_not_flagged(self):
        assert needs_rehash(hash_password("x-long-enough")) is False

    def test_uppercase_hex_is_not_mistaken_for_legacy(self):
        """Only lowercase 64-hex is the legacy shape; anything else is not."""
        assert needs_rehash("A" * 64) is False


class TestPasswordPolicy:
    def test_accepts_a_long_password(self):
        validate_password_policy("x" * MIN_PASSWORD_LENGTH)

    def test_rejects_short_passwords(self):
        with pytest.raises(PasswordPolicyError, match=str(MIN_PASSWORD_LENGTH)):
            validate_password_policy("x" * (MIN_PASSWORD_LENGTH - 1))

    def test_rejects_breached_passwords(self):
        with pytest.raises(PasswordPolicyError, match="breach"):
            validate_password_policy("password123")

    def test_breach_check_is_case_insensitive(self):
        with pytest.raises(PasswordPolicyError):
            validate_password_policy("PassWord123")


class TestApiKeys:
    def test_shape(self):
        issued = generate_api_key()
        assert issued.secret.startswith(API_KEY_PREFIX)
        assert len(issued.secret) > 40
        assert issued.prefix == issued.secret[:14]

    def test_hash_matches_sha256(self):
        issued = generate_api_key()
        assert issued.hashed == hashlib.sha256(issued.secret.encode()).hexdigest()
        assert hash_api_key(issued.secret) == issued.hashed

    def test_keys_are_unique(self):
        assert len({generate_api_key().secret for _ in range(200)}) == 200

    def test_hash_ignores_surrounding_whitespace(self):
        """A key pasted with a stray newline must still authenticate."""
        issued = generate_api_key()
        assert hash_api_key(f"  {issued.secret}\n") == issued.hashed

    @pytest.mark.parametrize(
        "candidate,expected",
        [
            ("ecoai_" + "a" * 30, True),
            ("ecoai_short", False),
            ("wrong-prefix-not-an-ecoai-key-at-all", False),
            ("", False),
            ("   ", False),
        ],
    )
    def test_shape_check(self, candidate, expected):
        assert looks_like_api_key(candidate) is expected
