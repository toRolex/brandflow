"""Quick regression test: project delete + list consistency."""

import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app

_HERE = Path(__file__).resolve().parent.parent.parent


def test_project_delete_removes_from_list() -> None:
    client = TestClient(create_app())

    # create a project with unique name
    name = f"regression-test-{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/projects", json={"name": name})
    assert resp.status_code == 200
    pid = resp.json()["id"]
    assert pid is not None

    # verify it appears in listing
    all_before = {p["id"] for p in client.get("/api/projects").json()}
    assert pid in all_before, f"project {pid} should be in listing after create"

    # delete it
    resp = client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # verify it is gone from the filesystem
    project_dir = Path.cwd() / "workspace" / "projects" / pid
    assert not project_dir.exists(), (
        f"project directory {project_dir} should be removed"
    )

    # verify it is gone from the listing
    all_after = {p["id"] for p in client.get("/api/projects").json()}
    assert pid not in all_after, (
        f"project {pid} should not appear in listing after delete"
    )

    # clean up any orphan test dir
    import shutil

    if project_dir.exists():
        shutil.rmtree(project_dir)
