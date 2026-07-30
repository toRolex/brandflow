"""Worker 路由下线后的 404 契约。

#414 删除了 control-plane 对 ``workers`` 路由的注册，因此所有
``/workers/*`` 端点必须返回 404。该测试把"删除意图"锁在测试里，
防止路由被无意中复活。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


@pytest.mark.parametrize(
    "path",
    [
        "/workers/poll",
        "/workers/tasks/abc/heartbeat",
        "/workers/tasks/abc/artifacts",
        "/workers/tasks/abc/report",
        "/workers/tasks/abc/input-bundle",
    ],
)
def test_workers_endpoints_return_404(path: str, tmp_path: Path) -> None:
    with TestClient(create_app(root_dir=tmp_path)) as client:
        poll_response = client.post(path, json={})
        assert poll_response.status_code == 404, (
            f"POST {path} should be 404 after Worker removal, "
            f"got {poll_response.status_code}"
        )

        input_bundle_response = client.get(path)
        assert input_bundle_response.status_code == 404, (
            f"GET {path} should be 404 after Worker removal, "
            f"got {input_bundle_response.status_code}"
        )
