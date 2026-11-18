"""Explicit trusted adapter registration; no entry-point discovery or import strings."""

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from datavouch.adapters.contracts import (
    API_VERSION,
    Adapter,
    AdapterError,
    AdapterInfo,
    ObservationBatch,
)
from datavouch.core.configuration import _object


class Registry:
    def __init__(self) -> None:
        self._adapters: dict[str, tuple[AdapterInfo, Adapter]] = {}

    def register(self, adapter: Adapter) -> None:
        try:
            info = adapter.info
            if not isinstance(info, AdapterInfo) or info.api_version != API_VERSION:
                raise AdapterError("Incompatible adapter API")
            if not callable(adapter.validate_config) or not callable(adapter.collect):
                raise AdapterError("Adapter methods are missing")
            if info.name in self._adapters:
                raise AdapterError("Adapter name already registered")
        except AdapterError:
            raise
        except Exception:
            raise AdapterError("Invalid adapter registration") from None
        self._adapters[info.name] = (info, adapter)

    def list(self) -> tuple[AdapterInfo, ...]:
        return tuple(self._adapters[name][0] for name in sorted(self._adapters))

    def collect(
        self, connector: object, *, fixture: Path | None = None, live: bool = False
    ) -> dict[str, Any]:
        try:
            envelope = _object(connector, {"adapter", "api_version", "config_version", "config"})
            if (
                not isinstance(envelope["adapter"], str)
                or envelope["adapter"] not in self._adapters
            ):
                raise AdapterError("Adapter is not registered")
            info, adapter = self._adapters[envelope["adapter"]]
            if (
                envelope["api_version"] != API_VERSION
                or envelope["config_version"] != info.config_version
            ):
                raise AdapterError("Incompatible connector version")
            if type(live) is not bool or (fixture is None) == (not live):
                raise AdapterError("Select a fixture or explicitly enable live collection")
            if fixture is not None and not isinstance(fixture, Path):
                raise AdapterError("Expected a fixture path")
            mode = "live" if live else "fixture"
            if mode not in info.modes:
                raise AdapterError("Adapter does not support this collection mode")
            if not isinstance(envelope["config"], dict):
                raise AdapterError("Connector config must be an object")
            config = copy.deepcopy(envelope["config"])
            # Adapter validation must be side-effect-free. Failures never start collection.
            try:
                adapter.validate_config(copy.deepcopy(config))
                batch = adapter.collect(config, fixture=fixture, live=live)
                if not isinstance(batch, ObservationBatch):
                    raise TypeError("Invalid adapter result")
                if any(
                    m.metric not in info.metrics for o in batch.observations for m in o.measurements
                ):
                    raise ValueError("Undeclared metric or unit")
                data = asdict(batch)
            except Exception:
                raise AdapterError(
                    "Adapter configuration, collection or output validation failed"
                ) from None
            # Normalize tuple ordering as well as JSON keys for reproducible evidence.
            data["observations"] = sorted(data["observations"], key=lambda o: o["execution"]["id"])
            data["requested_ids"] = sorted(data["requested_ids"])
            data["missing_ids"] = sorted(data["missing_ids"])
            data["exclusions"] = sorted(data["exclusions"], key=lambda e: e["execution_id"])
            return {
                "schema_version": "adapter-collection-1",
                "adapter": asdict(info),
                "mode": mode,
                **data,
            }
        except AdapterError:
            raise
        except (ValueError, TypeError, OverflowError, RecursionError):
            raise AdapterError("Invalid connector configuration") from None


def render(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def builtin_registry() -> Registry:
    from datavouch.adapters.bigquery.adapter import BigQueryAdapter

    registry = Registry()
    registry.register(BigQueryAdapter())
    return registry
