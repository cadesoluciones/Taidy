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
        json={"url": "https://example/odata/New", "description": "desc", "incremental": True},
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
    resp = client.patch("/meta/bc-tables/does-not-exist", json={"url": "https://example/odata/X"})
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
        json={"path": "resources/new", "fields": ["id", "name"], "incremental": True, "overlap_days": 3},
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
        "/meta/factorial-tables/does-not-exist", json={"path": "resources/x", "fields": ["id"]}
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
        json={"object_type": "companies", "fields": ["hs_object_id", "name"], "description": "desc"},
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
        "/meta/hubspot-tables/does-not-exist", json={"object_type": "deals", "fields": ["hs_object_id"]}
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
