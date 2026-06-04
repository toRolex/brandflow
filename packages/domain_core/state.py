PHASE_ORDER = [
    "queued",
    "script_generating",
    "script_review",
    "tts_generating",
    "tts_review",
    "subtitle_generating",
    "asset_retrieving",
    "asset_review",
    "video_rendering",
    "final_review",
    "completed",
]


def next_phase(current: str) -> str:
    index = PHASE_ORDER.index(current)
    if index >= len(PHASE_ORDER) - 1:
        raise ValueError(f"phase {current!r} has no next phase")
    return PHASE_ORDER[index + 1]


def rewind_from_phase(start_phase: str) -> list[str]:
    index = PHASE_ORDER.index(start_phase)
    return PHASE_ORDER[index:-1]
