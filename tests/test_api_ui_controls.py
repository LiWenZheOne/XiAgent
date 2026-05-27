from __future__ import annotations

from fastapi.testclient import TestClient

from xiagent.api.app import create_app


def test_list_ui_node_controls(test_settings) -> None:
    app = create_app(settings=test_settings)

    with TestClient(app) as client:
        response = client.get("/api/ui/node-controls")

    assert response.status_code == 200
    payload = response.json()
    control_ids = {item["control_id"] for item in payload["items"]}
    assert "ui.choice.image_three.v1" in control_ids


def test_get_ui_node_control(test_settings) -> None:
    app = create_app(settings=test_settings)

    with TestClient(app) as client:
        response = client.get("/api/ui/node-controls/ui.choice.image_three.v1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["item"]["control_id"] == "ui.choice.image_three.v1"
    assert {variant["name"] for variant in payload["item"]["variants"]} == {
        "equal_grid",
        "hero_list",
        "hover_focus",
    }


def test_get_unknown_ui_node_control_returns_404(test_settings) -> None:
    app = create_app(settings=test_settings)

    with TestClient(app) as client:
        response = client.get("/api/ui/node-controls/ui.missing.v1")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_ui_control"
