"""JWT verification — algorithm separation and org claim normalisation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.dependencies import (
    _CLERK_JWT_ALGORITHMS,
    _TEST_JWT_ALGORITHMS,
    _normalize_org_claim,
    decode_clerk_rs256_token,
    decode_test_hs256_token,
)


def _hs256_token(**extra: object) -> str:
    payload = {
        "sub": "user_test",
        "org_id": "org_test",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        **extra,
    }
    return jwt.encode(
        payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm
    )


def test_algorithm_lists_are_disjoint_and_fixed() -> None:
    assert _CLERK_JWT_ALGORITHMS == ["RS256"]
    assert _TEST_JWT_ALGORITHMS == ["HS256"]
    assert set(_CLERK_JWT_ALGORITHMS).isdisjoint(_TEST_JWT_ALGORITHMS)


def test_production_decode_access_token_is_rs256_only() -> None:
    """Unpatched entry point must not accept HS256 (alg confusion / secret forge)."""
    token = _hs256_token()
    with pytest.raises(HTTPException) as exc_info:
        # Bypass the autouse HS256 monkeypatch by calling the Clerk function
        # and the real module attribute used outside pytest patches.
        decode_clerk_rs256_token(token)
    assert exc_info.value.status_code in (401, 503)


def test_hs256_helper_accepts_fixture_tokens_but_is_separate() -> None:
    claims = decode_test_hs256_token(_hs256_token())
    assert claims["sub"] == "user_test"
    assert claims["org_id"] == "org_test"


def test_rs256_decode_passes_fixed_algorithms_list_only() -> None:
    token = _hs256_token()  # shape irrelevant; we assert call kwargs
    fake_key = MagicMock()
    fake_key.key = "pem-material"
    fake_jwks = MagicMock()
    fake_jwks.get_signing_key_from_jwt.return_value = fake_key

    with (
        patch("app.dependencies._jwks_client", return_value=fake_jwks),
        patch("app.dependencies.jwt.decode") as mock_decode,
    ):
        mock_decode.return_value = {"sub": "user_x", "org_id": "org_x"}
        decode_clerk_rs256_token(token)
        _args, kwargs = mock_decode.call_args
        assert kwargs["algorithms"] == ["RS256"]
        assert "HS256" not in kwargs["algorithms"]


def test_test_hs256_decode_passes_fixed_algorithms_list_only() -> None:
    token = _hs256_token()
    with patch("app.dependencies.jwt.decode") as mock_decode:
        mock_decode.return_value = {"sub": "user_x", "org_id": "org_x"}
        decode_test_hs256_token(token)
        _args, kwargs = mock_decode.call_args
        assert kwargs["algorithms"] == ["HS256"]
        assert "RS256" not in kwargs["algorithms"]


def test_normalize_org_from_clerk_nested_o_id() -> None:
    claims = _normalize_org_claim(
        {"sub": "user_1", "o": {"id": "org_nested_abc", "rol": "admin"}}
    )
    assert claims["org_id"] == "org_nested_abc"


def test_normalize_org_prefers_explicit_org_id() -> None:
    claims = _normalize_org_claim(
        {"sub": "user_1", "org_id": "org_explicit", "o": {"id": "org_nested"}}
    )
    assert claims["org_id"] == "org_explicit"


def test_autouse_patch_routes_decode_access_token_to_hs256() -> None:
    """Under pytest, decode_access_token is the HS256 helper (see conftest)."""
    import app.dependencies as deps

    claims = deps.decode_access_token(_hs256_token())
    assert claims["org_id"] == "org_test"
