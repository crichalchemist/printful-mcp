import dataclasses

import pytest

from printful_core.request import Request


def test_request_defaults_to_v2():
    req = Request("GET", "/catalog-products")
    assert req.version == "v2"
    assert req.params == {}
    assert req.json is None


def test_request_is_frozen():
    req = Request("GET", "/countries")
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.path = "/other"


def test_none_params_are_dropped():
    req = Request("GET", "/catalog-products", params={"limit": 5, "colors": None})
    assert req.params == {"limit": 5}


def test_mutating_the_caller_s_body_does_not_change_the_request():
    body = {"recipient": {"name": "Ada"}}
    req = Request("POST", "/orders", json=body)
    body["recipient"] = {"name": "Grace"}
    body["external_id"] = "swapped-after-the-fact"
    assert req.json == {"recipient": {"name": "Ada"}}


def test_with_params_returns_a_new_request():
    original = Request("GET", "/countries", params={"limit": 20})
    updated = original.with_params(offset=40)
    assert updated.params == {"limit": 20, "offset": 40}
    assert original.params == {"limit": 20}
    assert updated.path == original.path


def test_v1_version_is_preserved():
    assert Request("GET", "/store/products", version="v1").version == "v1"
