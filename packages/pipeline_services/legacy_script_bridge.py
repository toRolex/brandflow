from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from kimi_two_stage_script import generate_script


class LegacyScriptBridge:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir

    def generate(self, product: str, output_dir: Path, mock: bool, custom_prompt: str = "") -> dict[str, Any]:
        args = Namespace(
            product=product,
            brand="滋元堂",
            scene="",
            material="",
            output_dir=str(output_dir),
            interval_seconds=10.0,
            mock=mock,
            custom_prompt=custom_prompt,
        )
        return generate_script(args)
