# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_bc_tables_full_starts_empty(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/bc-tables/full")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_operator_cannot_create_bc_table(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.post("/meta/bc-tables", json={"name": "bc_x", "url": "https://example/odata/X"})
    assert resp.status_code == 403


def test_admin_can_create_list_and_delete_bc_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/meta/bc-tables",
        json={"name": "bc_new", "url": "https://example/odata/New", "description": "desc", "incremental": True},
    )
    assert created.status_code == 200
    assert created.json() == {
        "name": "bc_new",
        "description": "desc",
        "url": "https://example/odata/New",
        "incremental": True,
    }

    listed = client.get("/meta/bc-tables/full").json()["items"]
    assert [t["name"] for t in listed] == ["bc_new"]
    # The plain name list (used by the extract-form dropdown) picks it up too.
    assert client.get("/meta/bc-tables").json()["items"] == ["bc_new"]

    assert client.delete("/meta/bc-tables/bc_new").status_code == 204
    assert client.get("/meta/bc-tables/full").json()["items"] == []


def test_admin_can_update_bc_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/bc-tables", json={"name": "bc_edit", "url": "https://example/odata/Old"})

    updated = client.patch(
        "/meta/bc-tables/bc_edit",
        json={"name": "bc_edit", "url": "https://example/odata/New", "description": "desc", "incremental": True},
    )
    assert updated.status_code == 200
    assert updated.json() == {
        "name": "bc_edit",
        "description": "desc",
        "url": "https://example/odata/New",
        "incremental": True,
    }
    assert client.get("/meta/bc-tables/full").json()["items"][0]["url"] == "https://example/odata/New"


def test_update_bc_table_rejects_unknown_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch("/meta/bc-tables/does-not-exist", json={"name": "does-not-exist", "url": "https://example/odata/X"})
    assert resp.status_code == 400


def test_admin_can_rename_bc_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/bc-tables", json={"name": "bc_old_name", "url": "https://example/odata/X"})

    resp = client.patch(
        "/meta/bc-tables/bc_old_name", json={"name": "bc_new_name", "url": "https://example/odata/X"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "bc_new_name"
    assert client.get("/meta/bc-tables").json()["items"] == ["bc_new_name"]


def test_rename_bc_table_rejects_collision_with_another_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/bc-tables", json={"name": "bc_first", "url": "https://example/odata/A"})
    client.post("/meta/bc-tables", json={"name": "bc_second", "url": "https://example/odata/B"})

    resp = client.patch("/meta/bc-tables/bc_first", json={"name": "bc_second", "url": "https://example/odata/A"})
    assert resp.status_code == 400


def test_operator_cannot_update_bc_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/bc-tables", json={"name": "bc_keep", "url": "https://example/odata/Keep"})

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.patch("/meta/bc-tables/bc_keep", json={"url": "https://example/odata/Changed"})
    assert resp.status_code == 403


def test_create_bc_table_rejects_duplicate_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/bc-tables", json={"name": "bc_dup", "url": "https://example/odata/A"})
    resp = client.post("/meta/bc-tables", json={"name": "bc_dup", "url": "https://example/odata/B"})
    assert resp.status_code == 400


def test_operator_cannot_call_bc_available_odata_tables(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/bc-tables/available-odata-tables")
    assert resp.status_code == 403


def _patch_fake_bc_client(monkeypatch, *, odata_tables=None, custom_api_tables=None, seen_extra_groups=None):
    import types

    from src.bc_client import api as bc_api
    from src.bc_client import auth as bc_auth
    from src.bc_client import config as bc_config

    class _FakeClient:
        def __init__(self, *, settings, token_provider):
            pass

        def list_available_odata_tables(self):
            return odata_tables if odata_tables is not None else []

        def list_available_custom_api_tables(self, *, extra_group=None):
            if seen_extra_groups is not None:
                seen_extra_groups.append(extra_group)
            return custom_api_tables if custom_api_tables is not None else []

    fake_settings = types.SimpleNamespace(token_url="", client_id="", client_secret="", scope="")
    monkeypatch.setattr(bc_config, "load_settings", lambda: fake_settings)
    monkeypatch.setattr(bc_auth, "OAuthTokenProvider", lambda **kwargs: object())
    monkeypatch.setattr(bc_api, "BusinessCentralClient", _FakeClient)


def test_admin_can_fetch_bc_available_odata_tables(isolated_state, client, monkeypatch):
    _patch_fake_bc_client(
        monkeypatch, odata_tables=[{"name": "APIabc", "label": "https://example/odata/Company('X')/APIabc"}]
    )

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/bc-tables/available-odata-tables")

    assert resp.status_code == 200
    assert resp.json()["items"] == [{"name": "APIabc", "label": "https://example/odata/Company('X')/APIabc"}]


def test_admin_can_fetch_bc_available_custom_api_tables(isolated_state, client, monkeypatch):
    _patch_fake_bc_client(
        monkeypatch,
        custom_api_tables=[{"name": "Proyecto/recursos", "label": "https://example/api/cade/Proyecto/v1.0/recursos"}],
    )

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/bc-tables/available-custom-api-tables")

    assert resp.status_code == 200
    assert resp.json()["items"] == [
        {"name": "Proyecto/recursos", "label": "https://example/api/cade/Proyecto/v1.0/recursos"}
    ]


def test_bc_available_custom_api_tables_without_query_params_probes_no_extra_group(
    isolated_state, client, monkeypatch
):
    seen_extra_groups = []
    _patch_fake_bc_client(monkeypatch, custom_api_tables=[], seen_extra_groups=seen_extra_groups)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/bc-tables/available-custom-api-tables")

    assert resp.status_code == 200
    assert seen_extra_groups == [None]


def test_bc_available_custom_api_tables_forwards_extra_group_query_params(isolated_state, client, monkeypatch):
    seen_extra_groups = []
    _patch_fake_bc_client(monkeypatch, custom_api_tables=[], seen_extra_groups=seen_extra_groups)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get(
        "/meta/bc-tables/available-custom-api-tables",
        params={"publisher": "cade", "group": "Contabilidad", "version": "v1.0"},
    )

    assert resp.status_code == 200
    assert seen_extra_groups == [("cade", "Contabilidad", "v1.0")]


def test_operator_cannot_call_bc_available_custom_api_tables(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/bc-tables/available-custom-api-tables")
    assert resp.status_code == 403


def test_bc_available_odata_tables_maps_client_error_to_400(isolated_state, client, monkeypatch):
    from src.bc_client import config as bc_config

    def fake_load_settings():
        raise ValueError("Missing required environment variables: BC_CLIENT_SECRET")

    monkeypatch.setattr(bc_config, "load_settings", fake_load_settings)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/bc-tables/available-odata-tables")

    assert resp.status_code == 400


def test_admin_can_create_list_and_delete_factorial_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/meta/factorial-tables",
        json={
            "name": "factorial_new",
            "path": "resources/new/endpoint",
            "fields": ["id", "name"],
            "description": "desc",
            "date_range": False,
            "employee_filter": False,
            "incremental": True,
            "overlap_days": 3,
        },
    )
    assert created.status_code == 200
    body = created.json()
    assert body["name"] == "factorial_new"
    assert body["fields"] == ["id", "name"]
    assert body["overlap_days"] == 3
    assert body["chunk_days"] is None

    listed = client.get("/meta/factorial-tables/full").json()["items"]
    assert [t["name"] for t in listed] == ["factorial_new"]
    assert client.get("/meta/factorial-tables").json()["items"] == ["factorial_new"]

    assert client.delete("/meta/factorial-tables/factorial_new").status_code == 204
    assert client.get("/meta/factorial-tables/full").json()["items"] == []


def test_admin_can_update_factorial_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post(
        "/meta/factorial-tables",
        json={"name": "factorial_edit", "path": "resources/old", "fields": ["id"]},
    )

    updated = client.patch(
        "/meta/factorial-tables/factorial_edit",
        json={
            "name": "factorial_edit",
            "path": "resources/new",
            "fields": ["id", "name"],
            "incremental": True,
            "overlap_days": 3,
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["path"] == "resources/new"
    assert body["fields"] == ["id", "name"]
    assert body["overlap_days"] == 3


def test_update_factorial_table_rejects_unknown_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch(
        "/meta/factorial-tables/does-not-exist",
        json={"name": "does-not-exist", "path": "resources/x", "fields": ["id"]},
    )
    assert resp.status_code == 400


def test_admin_can_rename_factorial_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/factorial-tables", json={"name": "fac_old_name", "path": "resources/x", "fields": ["id"]})

    resp = client.patch(
        "/meta/factorial-tables/fac_old_name",
        json={"name": "fac_new_name", "path": "resources/x", "fields": ["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "fac_new_name"
    assert client.get("/meta/factorial-tables").json()["items"] == ["fac_new_name"]


def test_rename_factorial_table_rejects_collision_with_another_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/factorial-tables", json={"name": "fac_first", "path": "resources/a", "fields": ["id"]})
    client.post("/meta/factorial-tables", json={"name": "fac_second", "path": "resources/b", "fields": ["id"]})

    resp = client.patch(
        "/meta/factorial-tables/fac_first", json={"name": "fac_second", "path": "resources/a", "fields": ["id"]}
    )
    assert resp.status_code == 400


def test_create_factorial_table_requires_at_least_one_field(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.post(
        "/meta/factorial-tables",
        json={"name": "factorial_x", "path": "resources/x", "fields": []},
    )
    assert resp.status_code == 400


def test_operator_cannot_delete_factorial_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post(
        "/meta/factorial-tables",
        json={"name": "factorial_keep", "path": "resources/keep", "fields": ["id"]},
    )

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.delete("/meta/factorial-tables/factorial_keep")
    assert resp.status_code == 403


def test_admin_can_create_list_and_delete_hubspot_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/meta/hubspot-tables",
        json={
            "name": "hubspot_tickets",
            "object_type": "tickets",
            "fields": ["hs_object_id", "subject"],
            "description": "desc",
        },
    )
    assert created.status_code == 200
    assert created.json() == {
        "name": "hubspot_tickets",
        "description": "desc",
        "object_type": "tickets",
        "fields": ["hs_object_id", "subject"],
    }

    listed = client.get("/meta/hubspot-tables/full").json()["items"]
    assert [t["name"] for t in listed] == ["hubspot_tickets"]
    assert client.get("/meta/hubspot-tables").json()["items"] == ["hubspot_tickets"]

    assert client.delete("/meta/hubspot-tables/hubspot_tickets").status_code == 204
    assert client.get("/meta/hubspot-tables/full").json()["items"] == []


def test_admin_can_update_hubspot_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post(
        "/meta/hubspot-tables",
        json={"name": "hubspot_edit", "object_type": "contacts", "fields": ["hs_object_id"]},
    )

    updated = client.patch(
        "/meta/hubspot-tables/hubspot_edit",
        json={"name": "hubspot_edit", "object_type": "companies", "fields": ["hs_object_id", "name"], "description": "desc"},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["object_type"] == "companies"
    assert body["fields"] == ["hs_object_id", "name"]
    assert body["description"] == "desc"


def test_update_hubspot_table_rejects_unknown_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch(
        "/meta/hubspot-tables/does-not-exist",
        json={"name": "does-not-exist", "object_type": "deals", "fields": ["hs_object_id"]},
    )
    assert resp.status_code == 400


def test_admin_can_rename_hubspot_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/hubspot-tables", json={"name": "hs_old_name", "object_type": "deals", "fields": ["id"]})

    resp = client.patch(
        "/meta/hubspot-tables/hs_old_name",
        json={"name": "hs_new_name", "object_type": "deals", "fields": ["id"]},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "hs_new_name"
    assert client.get("/meta/hubspot-tables").json()["items"] == ["hs_new_name"]


def test_rename_hubspot_table_rejects_collision_with_another_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/hubspot-tables", json={"name": "hs_first", "object_type": "deals", "fields": ["id"]})
    client.post("/meta/hubspot-tables", json={"name": "hs_second", "object_type": "deals", "fields": ["id"]})

    resp = client.patch(
        "/meta/hubspot-tables/hs_first", json={"name": "hs_second", "object_type": "deals", "fields": ["id"]}
    )
    assert resp.status_code == 400


def test_create_hubspot_table_requires_at_least_one_field(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.post(
        "/meta/hubspot-tables",
        json={"name": "hubspot_x", "object_type": "deals", "fields": []},
    )
    assert resp.status_code == 400


def test_create_hubspot_table_rejects_duplicate_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/meta/hubspot-tables", json={"name": "hubspot_dup", "object_type": "deals", "fields": ["id"]})
    resp = client.post("/meta/hubspot-tables", json={"name": "hubspot_dup", "object_type": "deals", "fields": ["id"]})
    assert resp.status_code == 400


def test_operator_cannot_create_or_delete_hubspot_table(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post(
        "/meta/hubspot-tables",
        json={"name": "hubspot_keep", "object_type": "deals", "fields": ["id"]},
    )

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    assert client.post(
        "/meta/hubspot-tables", json={"name": "hubspot_x", "object_type": "deals", "fields": ["id"]}
    ).status_code == 403
    assert client.delete("/meta/hubspot-tables/hubspot_keep").status_code == 403


# --------------------------------------------------------------------------------------
# Live "available properties/fields" discovery helpers -- these hit real
# HubSpot/Factorial APIs in production, so every test here mocks the client
# class where the router imports it (a local import inside the endpoint
# function, so patching the module attribute before the call is enough).
# --------------------------------------------------------------------------------------


def test_hubspot_available_properties_requires_object_type(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/hubspot-tables/available-properties", params={"object_type": "  "})
    assert resp.status_code == 400


def test_operator_cannot_call_hubspot_available_properties(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/hubspot-tables/available-properties", params={"object_type": "contacts"})
    assert resp.status_code == 403


def test_admin_can_fetch_hubspot_available_properties(isolated_state, client, monkeypatch):
    from src.hubspot_client import config as hubspot_config

    class _FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def list_properties(self, object_type, *, include_hidden=False):
            assert object_type == "contacts"
            assert include_hidden is False
            return [{"name": "email", "label": "Email"}, {"name": "firstname", "label": "First name"}]

    monkeypatch.setattr(hubspot_config, "load_settings", lambda: object())
    monkeypatch.setattr("src.hubspot_client.api.HubspotClient", _FakeClient)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/hubspot-tables/available-properties", params={"object_type": "contacts"})

    assert resp.status_code == 200
    assert resp.json()["items"] == [
        {"name": "email", "label": "Email"},
        {"name": "firstname", "label": "First name"},
    ]


def test_hubspot_available_properties_maps_client_error_to_400(isolated_state, client, monkeypatch):
    from src.hubspot_client import config as hubspot_config

    def fake_load_settings():
        raise ValueError("Missing required environment variables: HUBSPOT_API_KEY")

    monkeypatch.setattr(hubspot_config, "load_settings", fake_load_settings)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/hubspot-tables/available-properties", params={"object_type": "contacts"})

    assert resp.status_code == 400
    assert "HUBSPOT_API_KEY" in resp.json()["detail"]


def test_factorial_available_fields_requires_path(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/factorial-tables/available-fields", params={"path": ""})
    assert resp.status_code == 400


def test_operator_cannot_call_factorial_available_fields(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/factorial-tables/available-fields", params={"path": "resources/employees/employees"})
    assert resp.status_code == 403


def test_admin_can_fetch_factorial_available_fields(isolated_state, client, monkeypatch):
    from src.factorial_client import config as factorial_config

    class _FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def sample_fields(self, *, path, date_range=False):
            assert path == "resources/employees/employees"
            return ["email", "id"]

    monkeypatch.setattr(factorial_config, "load_settings", lambda: object())
    monkeypatch.setattr("src.factorial_client.api.FactorialClient", _FakeClient)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get(
        "/meta/factorial-tables/available-fields", params={"path": "resources/employees/employees"}
    )

    assert resp.status_code == 200
    assert resp.json()["items"] == [{"name": "email", "label": ""}, {"name": "id", "label": ""}]


def test_operator_cannot_call_hubspot_available_object_types(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/hubspot-tables/available-object-types")
    assert resp.status_code == 403


def test_admin_can_fetch_hubspot_available_object_types(isolated_state, client, monkeypatch):
    from src.hubspot_client import config as hubspot_config

    class _FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def list_object_types(self):
            return [{"name": "contacts", "label": "Contactos"}]

    monkeypatch.setattr(hubspot_config, "load_settings", lambda: object())
    monkeypatch.setattr("src.hubspot_client.api.HubspotClient", _FakeClient)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/hubspot-tables/available-object-types")

    assert resp.status_code == 200
    assert resp.json()["items"] == [{"name": "contacts", "label": "Contactos"}]


def test_hubspot_available_object_types_maps_client_error_to_400(isolated_state, client, monkeypatch):
    from src.hubspot_client import config as hubspot_config

    def fake_load_settings():
        raise ValueError("Missing required environment variables: HUBSPOT_API_KEY")

    monkeypatch.setattr(hubspot_config, "load_settings", fake_load_settings)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/hubspot-tables/available-object-types")

    assert resp.status_code == 400


def test_operator_cannot_call_factorial_available_tables(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/factorial-tables/available-tables")
    assert resp.status_code == 403


def test_admin_can_fetch_factorial_available_tables(isolated_state, client, monkeypatch):
    from src.factorial_client import config as factorial_config

    class _FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def list_available_tables(self):
            return [{"name": "resources/ats/candidates", "label": "Ats > Candidate — Reads all Candidates"}]

    monkeypatch.setattr(factorial_config, "load_settings", lambda: object())
    monkeypatch.setattr("src.factorial_client.api.FactorialClient", _FakeClient)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/factorial-tables/available-tables")

    assert resp.status_code == 200
    assert resp.json()["items"] == [
        {"name": "resources/ats/candidates", "label": "Ats > Candidate — Reads all Candidates"}
    ]


def test_factorial_available_tables_maps_client_error_to_400(isolated_state, client, monkeypatch):
    from src.factorial_client import config as factorial_config

    def fake_load_settings():
        raise ValueError("Missing required environment variables: FACTORIAL_API_KEY")

    monkeypatch.setattr(factorial_config, "load_settings", fake_load_settings)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/meta/factorial-tables/available-tables")

    assert resp.status_code == 400
