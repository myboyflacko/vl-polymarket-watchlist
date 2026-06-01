import pytest

from void_liquidity.core.cache import WorkflowCache


def test_workflow_cache_stores_values_by_namespace_and_key() -> None:
    cache = WorkflowCache()

    cache.set("workflow", "latest", {"value": 1})

    assert cache.get("workflow", "latest") == {"value": 1}
    assert cache.has("workflow", "latest") is True
    assert cache.get("other", "latest") is None


def test_workflow_cache_returns_default_for_missing_entry() -> None:
    cache = WorkflowCache()

    assert cache.get("workflow", "missing", default=[]) == []


def test_workflow_cache_require_raises_for_missing_entry() -> None:
    cache = WorkflowCache()

    with pytest.raises(KeyError, match="workflow.missing"):
        cache.require("workflow", "missing")


def test_workflow_cache_clears_one_namespace() -> None:
    cache = WorkflowCache()
    cache.set("first", "value", 1)
    cache.set("second", "value", 2)

    cache.clear("first")

    assert cache.has("first", "value") is False
    assert cache.get("second", "value") == 2


def test_workflow_cache_clears_all_namespaces() -> None:
    cache = WorkflowCache()
    cache.set("first", "value", 1)
    cache.set("second", "value", 2)

    cache.clear()

    assert cache.has("first", "value") is False
    assert cache.has("second", "value") is False


def test_workflow_cache_delete_removes_entry() -> None:
    cache = WorkflowCache()
    cache.set("workflow", "latest", "value")

    cache.delete("workflow", "latest")

    assert cache.has("workflow", "latest") is False
