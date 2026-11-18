"""Canonical evidence reports without nondeterministic timestamps."""

import hashlib
import json
from dataclasses import asdict

from datavouch.core.models import Report


def render(report: Report) -> str:
    """Serialize conclusions and their raw inputs in a stable order."""
    data = asdict(report)
    experiment = data["experiment"]
    for group in (experiment["baseline"]["observations"], experiment["candidate"]):
        for observation in group:
            observation["measurements"] = sorted(
                observation["measurements"], key=lambda m: m["metric"]["name"]
            )
    experiment["baseline"]["observations"] = sorted(
        experiment["baseline"]["observations"], key=lambda o: o["execution"]["id"]
    )
    experiment["candidate"] = sorted(experiment["candidate"], key=lambda o: o["execution"]["id"])
    evidence = json.dumps(
        {"experiment": experiment, "policy": data["policy"]}, sort_keys=True, allow_nan=False
    )
    data["input_sha256"] = hashlib.sha256(evidence.encode()).hexdigest()
    data["schema_version"] = "0.1"
    return json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n"
