from __future__ import annotations


class WorkflowCache:
    def __init__(self) -> None:
        self._store: dict[str, dict[str, object]] = {}

    def set(self, namespace: str, key: str, value: object) -> None:
        self._store.setdefault(namespace, {})[key] = value

    def get(
        self,
        namespace: str,
        key: str,
        default: object | None = None,
    ) -> object | None:
        return self._store.get(namespace, {}).get(key, default)

    def require(self, namespace: str, key: str) -> object:
        if not self.has(namespace, key):
            raise KeyError(f"Cache entry not found: {namespace}.{key}")

        return self._store[namespace][key]

    def has(self, namespace: str, key: str) -> bool:
        return key in self._store.get(namespace, {})

    def delete(self, namespace: str, key: str) -> None:
        values = self._store.get(namespace)
        if values is None:
            return

        values.pop(key, None)
        if not values:
            self._store.pop(namespace, None)

    def clear(self, namespace: str | None = None) -> None:
        if namespace is None:
            self._store.clear()
            return

        self._store.pop(namespace, None)
