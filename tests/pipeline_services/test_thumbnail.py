import pytest
from pathlib import Path
from packages.pipeline_services.asset_library.thumbnail import ThumbnailGenerator


def test_generator_creates_thumbnail(tmp_path):
    generator = ThumbnailGenerator(ffmpeg_path="ffmpeg")
    video_path = tmp_path / "test.mp4"
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "testsrc=duration=5:size=320x240:rate=25",
        "-pix_fmt", "yuv420p",
        str(video_path)
    ], capture_output=True)
    
    output_path = tmp_path / "thumb.jpg"
    result = generator.generate(video_path, output_path)
    
    assert result is True
    assert output_path.exists()
    assert output_path.stat().st_size > 0