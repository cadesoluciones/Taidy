# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def _payload(**overrides):
    payload = {
        "name": "bc_contact_a_hubspot_contacts",
        "source": {"system": "business_central", "table": "bc_contact"},
        "target": {"system": "hubspot", "table": "hubspot_contacts"},
        "matching_key": {"source": "email", "target": "email"},
        "date_field": {"source": "systemModifiedAt", "target": "lastmodifieddate"},
        "fields": [
            {"source": "email", "target": "email"},
            {"source": "name", "target": "firstname"},
        ],
        "description": "Contactos BC -> HubSpot",
    }
    payload.update(overrides)
    return payload


def test_sync_mappings_starts_empty(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/sync/mappings")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_operator_cannot_create_mapping(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.post("/sync/mappings", json=_payload())
    assert resp.status_code == 403


def test_admin_can_create_list_and_delete_mapping(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post("/sync/mappings", json=_payload())
    assert created.status_code == 200
    assert created.json() == {
        "name": "bc_contact_a_hubspot_contacts",
        "description": "Contactos BC -> HubSpot",
        "source": {"system": "business_central", "table": "bc_contact"},
        "target": {"system": "hubspot", "table": "hubspot_contacts"},
        "matching_key": {"source": "email", "target": "email"},
        "date_field": {"source": "systemModifiedAt", "target": "lastmodifieddate"},
        "fields": [
            {"source": "email", "target": "email"},
            {"source": "name", "target": "firstname"},
        ],
        "source_filter": None,
        "target_filter": None,
    }

    listed = client.get("/sync/mappings").json()["items"]
    assert [m["name"] for m in listed] == ["bc_contact_a_hubspot_contacts"]

    assert client.delete("/sync/mappings/bc_contact_a_hubspot_contacts").status_code == 204
    assert client.get("/sync/mappings").json()["items"] == []


def test_admin_can_update_mapping(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/sync/mappings", json=_payload())

    updated = client.patch(
        "/sync/mappings/bc_contact_a_hubspot_contacts",
        json=_payload(
            fields=[
                {"source": "email", "target": "email"},
                {"source": "name", "target": "firstname"},
                {"source": "phoneNo", "target": "phone"},
            ]
        ),
    )
    assert updated.status_code == 200
    assert len(updated.json()["fields"]) == 3


def test_update_mapping_rejects_unknown_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch("/sync/mappings/does-not-exist", json=_payload())
    assert resp.status_code == 400


def test_admin_can_rename_mapping(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/sync/mappings", json=_payload())

    resp = client.patch(
        "/sync/mappings/bc_contact_a_hubspot_contacts", json=_payload(name="renamed_mapping")
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "renamed_mapping"
    assert [m["name"] for m in client.get("/sync/mappings").json()["items"]] == ["renamed_mapping"]


def test_rename_mapping_rejects_collision_with_another_mapping(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/sync/mappings", json=_payload(name="mapping_a"))
    client.post("/sync/mappings", json=_payload(name="mapping_b"))

    resp = client.patch("/sync/mappings/mapping_a", json=_payload(name="mapping_b"))
    assert resp.status_code == 400


def test_create_mapping_rejects_duplicate_name(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/sync/mappings", json=_payload())
    resp = client.post("/sync/mappings", json=_payload())
    assert resp.status_code == 400


def test_create_mapping_rejects_duplicate_source_field(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.post(
        "/sync/mappings",
        json=_payload(
            fields=[
                {"source": "email", "target": "email"},
                {"source": "email", "target": "firstname"},
            ]
        ),
    )
    assert resp.status_code == 400


def test_create_mapping_rejects_invalid_system(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.post(
        "/sync/mappings",
        json=_payload(source={"system": "salesforce", "table": "contacts"}),
    )
    assert resp.status_code == 400


def test_create_mapping_requires_matching_key(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.post("/sync/mappings", json=_payload(matching_key={"source": "", "target": "email"}))
    assert resp.status_code == 400


def test_operator_cannot_delete_mapping(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/sync/mappings", json=_payload())

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.delete("/sync/mappings/bc_contact_a_hubspot_contacts")
    assert resp.status_code == 403


def test_admin_can_create_mapping_with_row_filters(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/sync/mappings",
        json=_payload(source_filter={"field": "type", "equals": "Person"}),
    )
    assert created.status_code == 200
    assert created.json()["source_filter"] == {"field": "type", "equals": "Person"}
    assert created.json()["target_filter"] is None


def test_create_mapping_rejects_incomplete_row_filter(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.post(
        "/sync/mappings",
        json=_payload(source_filter={"field": "type", "equals": ""}),
    )
    assert resp.status_code == 400


def test_admin_can_update_mapping_to_clear_a_row_filter(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/sync/mappings", json=_payload(source_filter={"field": "type", "equals": "Person"}))

    updated = client.patch(
        "/sync/mappings/bc_contact_a_hubspot_contacts",
        json=_payload(),  # no source_filter this time
    )
    assert updated.status_code == 200
    assert updated.json()["source_filter"] is None


def test_bc_table_fields_empty_when_never_extracted(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/meta/bc-tables/some_never_extracted_table/fields")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
