"""
app/core/registry.py
Thread-safe registry for dynamically discovering and loading capability providers.
"""

from threading import Lock
from typing import Dict, Optional, Type
from app.capabilities.base import Provider


class ProviderRegistry:
    _instance: Optional["ProviderRegistry"] = None
    _lock: Lock = Lock()

    def __new__(cls) -> "ProviderRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._providers: Dict[str, Dict[str, Type[Provider]]] = {}
        return cls._instance

    def register(self, capability: str, name: str, provider_cls: Type[Provider]) -> None:
        """Register a provider class under a capability."""
        with self._lock:
            if capability not in self._providers:
                self._providers[capability] = {}
            self._providers[capability][name.lower()] = provider_cls

    def get(self, capability: str, name: str) -> Optional[Type[Provider]]:
        """Retrieve a registered provider class."""
        with self._lock:
            return self._providers.get(capability, {}).get(name.lower())

    def list_providers(self, capability: Optional[str] = None) -> Dict[str, list]:
        """List all registered providers, optionally filtered by capability."""
        with self._lock:
            if capability:
                return {capability: list(self._providers.get(capability, {}).keys())}
            return {cap: list(provs.keys()) for cap, provs in self._providers.items()}


# Global singleton instance
registry = ProviderRegistry()