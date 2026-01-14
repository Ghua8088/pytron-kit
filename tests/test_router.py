import pytest
import logging
from unittest.mock import MagicMock
from pytron.router import Router, DeepLink


def test_router_basic_match():
    router = Router()
    handler = MagicMock()

    router.add_route("home", handler)
    router.dispatch("myapp://home")

    handler.assert_called_once()


def test_router_param_match():
    router = Router()
    handler = MagicMock()

    router.add_route("user/{id}", handler)
    router.dispatch("myapp://user/123")

    handler.assert_called_once()
    # Check injection
    call_kwargs = handler.call_args[1]
    # By default, _invoke_handler only injects if the function signature asks for it.
    # But MagicMock accepts anything. However, the logic in _invoke_handler uses inspect.signature(func).
    # Inspecting a mock signature can be tricky unless configured.

    # Better to use a real function
    result = {}

    def real_handler(id):
        result["id"] = id

    router.add_route("post/{id}", real_handler)
    router.dispatch("myapp://post/456")

    assert result["id"] == "456"


def test_router_query_params():
    router = Router()
    result = {}

    def real_handler(q, page):
        result["q"] = q
        result["page"] = page

    router.add_route("search", real_handler)
    router.dispatch("myapp://search?q=python&page=1")

    assert result["q"] == "python"
    assert result["page"] == "1"


def test_deep_link_object_injection():
    router = Router()
    result = {}

    def real_handler(link):
        result["scheme"] = link.scheme
        result["path"] = link.path

    router.add_route("settings", real_handler)
    router.dispatch("pytron://settings")

    assert result["scheme"] == "pytron"
    # path in DeepLink is parsed using urllib.parse.urlparse.
    # For "pytron://settings", netloc="settings", path="".
    assert result["path"] == ""


def test_no_match_default_handler():
    router = Router()
    default = MagicMock()
    router.set_default_handler(default)

    router.dispatch("myapp://unknown/path")
    default.assert_called_once()


def test_partial_param_injection():
    # Only inject what's requested
    router = Router()
    result = {}

    def real_handler(id):  # Doesn't ask for 'slug'
        result["id"] = id

    router.add_route("blog/{id}/{slug}", real_handler)
    router.dispatch("myapp://blog/99/hello-world")

    assert result["id"] == "99"
    assert "slug" not in result
