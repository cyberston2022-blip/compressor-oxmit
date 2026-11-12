"""
Oxmit Educational and Modern Glass Progress Cards.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class ProgressState:
    stage: str # QUEUED, DOWNLOADING, TRANSCODING, UPLOADING, COMPLETED
    file_name: str
    orig_size_bytes: int
    current_bytes: int = 0
    percent: float = 0.0
    speed_text: str = ""
    eta_text: str = ""
    profile_name: str = "rostam"
    worker_id: str = "worker-1"
    queue_pos: int = 1

def render_glass_card(state: ProgressState) -> str:
    orig_mb = state.orig_size_bytes / (1024 * 1024)
    filled = int(state.percent / 10)
    bar = "▰" * filled + "▱" * (10 - filled)
    
    stage_icons = {
        "QUEUED": "⏳ Queued",
        "DOWNLOADING": "📥 Downloading (JIT)",
        "PROBING": "🔍 Analyzing Streams",
        "TRANSCODING": "⚙️ Transcoding (SVT Encore)",
        "UPLOADING": "📤 Delivering to Telegram",
        "COMPLETED": "✅ Completed",
        "FAILED": "❌ Failed"
    }
    stage_label = stage_icons.get(state.stage, state.stage)

    lines = [
        "┌ ⚙️ <b>Oxmit Transcode Engine</b>",
        f"├ <b>Status:</b> {stage_label}",
        f"├ <b>File:</b> {state.file_name} ({orig_mb:.1f} MB)",
        f"├ <b>Progress:</b> [{bar}] {state.percent:.1f}%",
    ]
    if state.speed_text or state.eta_text:
        lines.append(f"├ <b>Speed:</b> {state.speed_text} • <b>ETA:</b> {state.eta_text}")
    if state.stage == "QUEUED":
        lines.append(f"└ <b>Queue Position:</b> #{state.queue_pos}")
    else:
        lines.append(f"└ <b>Profile:</b> {state.profile_name} (Active on {state.worker_id})")
    
    return "\n".join(lines)
