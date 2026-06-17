from __future__ import annotations

import pytest
from pydantic import ValidationError

from corelib.schemas import TokenPayload


def test_valid_payload():
    payload = TokenPayload(
        sub="abc",
        iss="http://kc/realms/r",
        aud="client",
        exp=9999999999,
        iat=1000000000,
    )
    assert payload.sub == "abc"
    assert payload.preferred_username is None


def test_extra_claims_allowed():
    payload = TokenPayload(
        sub="abc",
        iss="http://kc/realms/r",
        aud=["client", "account"],
        exp=9999999999,
        iat=1000000000,
        custom_claim="hello",
    )
    assert payload.model_extra["custom_claim"] == "hello"


def test_audience_as_list():
    payload = TokenPayload(
        sub="abc",
        iss="http://kc/realms/r",
        aud=["client", "account"],
        exp=9999999999,
        iat=1000000000,
    )
    assert isinstance(payload.aud, list)
    assert "client" in payload.aud


def test_realm_access_roles():
    payload = TokenPayload(
        sub="abc",
        iss="http://kc/realms/r",
        aud="client",
        exp=9999999999,
        iat=1000000000,
        realm_access={"roles": ["admin", "viewer"]},
    )
    assert "admin" in payload.realm_access["roles"]


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        TokenPayload(
            iss="http://kc/realms/r",
            aud="client",
            exp=9999999999,
            iat=1000000000,
        )
