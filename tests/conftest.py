"""Test configuration and fixtures."""

import os

import pytest
from hypothesis import Verbosity, settings

# Register Hypothesis profiles per AGENTS.md and TASKS.md
settings.register_profile(
    "dev",
    max_examples=25,
    deadline=None,
    verbosity=Verbosity.normal,
)

settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    verbosity=Verbosity.normal,
)

# Load profile based on environment: CI or default to dev
profile_name = "ci" if os.getenv("CI") == "true" else "dev"
settings.load_profile(profile_name)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Fixture that removes all HWQ_* environment variables."""
    for key in list(os.environ.keys()):
        if key.startswith("HWQ_"):
            monkeypatch.delenv(key, raising=False)
    return monkeypatch
