import pytest
from datetime import datetime, timezone
from bot.oxmit.quality import pick_best_version
from bot.oxmit.decision_engine import make_decision

def test_pick_best_version_handles_mixed_and_none_created_at():
    # Candidate 1: datetime
    # Candidate 2: None
    # Candidate 3: float
    versions = [
        {'profile': 'rostam', 'out_w': 1280, 'out_h': 720, 'out_bitrate': 500000, 'created_at': datetime.now(timezone.utc)},
        {'profile': 'edu720', 'out_w': 1280, 'out_h': 720, 'out_bitrate': 500000, 'created_at': None},
        {'profile': 'custom', 'out_w': 1280, 'out_h': 720, 'out_bitrate': 500000, 'created_at': 1700000000.0},
    ]
    # In unpatched code, this raises TypeError: '>' not supported between instances
    best = pick_best_version(versions)
    assert best is not None
    assert best['profile'] in ('rostam', 'custom')

def test_decision_engine_computes_missing_bitrate_and_protects_low_bitrate():
    # 1.0 GB video, 4 hours (similar to watermarked.mp4) without bitrate in probe
    probe = {
        'width': 1280,
        'height': 720,
        'fps': 30.0,
        'duration_s': 14591.0,
        'vcodec': 'h264',
        'acodec': 'aac',
        # bitrate missing or 0
    }
    size_bytes = 1073741824 # 1.0 GB (~588 kbps)
    dec = make_decision(probe=probe, profile_key='rostam', size_bytes=size_bytes)
    # Bitrate should be computed (~588,714 bps <= 650k) -> triggers CRF 34
    assert dec.profile_params is not None
    assert dec.profile_params.get('crf') == '34'
