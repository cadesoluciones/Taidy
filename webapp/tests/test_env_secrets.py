# -*- coding: utf-8 -*-
"""
Regression: env_secrets.set_field() must never fail when `.env` is a
single-file Docker bind mount (as it is in production, specifically so an
admin's edit via "Claves de servicio" survives a redeploy -- see
docker-compose.yml). python-dotenv's own set_key() writes via a temp file +
os.replace() onto the target path, which the kernel refuses with
"OSError: [Errno 16] Device or resource busy" when that target is itself a
bind-mounted file -- reproduced live against the real deployment. set_field()
must work around this by never renaming onto the real path.
"""

from __future__ import annotations

import os

import pytest

from webapp import env_secrets


@pytest.fixture(autouse=True)
def _isolated_env_path(tmp_path, monkeypatch):
    monkeypatch.setattr(env_secrets, "_ENV_PATH", tmp_path / ".env")
    before = dict(os.environ)
    yield
    for key in set(os.environ) - set(before):
        del os.environ[key]
    os.environ.update(before)


def test_set_field_works_when_env_path_is_a_pre_existing_empty_file():
    env_secrets._ENV_PATH.write_text("", encoding="utf-8")
    env_secrets.set_field("HUBSPOT_API_KEY", "pat-eu1-real-token")
    assert "HUBSPOT_API_KEY=" in env_secrets._ENV_PATH.read_text(encoding="utf-8")
    assert os.environ["HUBSPOT_API_KEY"] == "pat-eu1-real-token"


def test_set_field_never_renames_onto_the_real_env_path(monkeypatch):
    """Simulates the exact production failure: os.replace()/os.rename() onto
    _ENV_PATH raises "Device or resource busy" because it's a Docker
    single-file bind mount. set_field() must still succeed by only ever
    renaming within its own throwaway temp directory, never onto _ENV_PATH."""
    env_secrets._ENV_PATH.write_text("BC_CLIENT_SECRET=old-value\n", encoding="utf-8")

    real_replace = os.replace

    def _guarded_replace(src, dst):
        if os.fspath(dst) == os.fspath(env_secrets._ENV_PATH):
            raise OSError(16, "Device or resource busy")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _guarded_replace)

    result = env_secrets.set_field("HUBSPOT_API_KEY", "pat-eu1-real-token")

    assert result["value"] == "pat-eu1-real-token"
    content = env_secrets._ENV_PATH.read_text(encoding="utf-8")
    assert "pat-eu1-real-token" in content
    assert "BC_CLIENT_SECRET" in content  # untouched sibling line preserved
    assert os.environ["HUBSPOT_API_KEY"] == "pat-eu1-real-token"


def test_set_field_creates_env_file_when_missing():
    assert not env_secrets._ENV_PATH.exists()
    env_secrets.set_field("HUBSPOT_API_KEY", "pat-eu1-real-token")
    assert env_secrets._ENV_PATH.is_file()
    assert os.environ["HUBSPOT_API_KEY"] == "pat-eu1-real-token"
