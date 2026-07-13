"""CLI 入口：python -m packages.deploy_health"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    """运行部署体检并输出结果。"""
    from packages.deploy_health.checker import DeployHealthChecker

    root_dir = Path.cwd()
    checker = DeployHealthChecker(root_dir=root_dir)
    result = checker.check_all()

    # 输出 JSON 结果
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    # 返回 0 表示健康，1 表示有问题
    if result.overall == "healthy":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
