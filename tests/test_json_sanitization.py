import json
import math
from src.communication.message_protocols import MessageProtocol, MessageMetadata, MessageType, Priority


def test_message_protocol_to_json_sanitizes_non_finite_numbers():
    metadata = MessageMetadata(
        timestamp=0.0,
        message_id="test",
        sender="tester",
        message_type=MessageType.SENSOR_DATA,
        priority=Priority.NORMAL,
    )
    payload = {
        "finite": 1.23,
        "nan": float("nan"),
        "inf": float("inf"),
        "ninf": float("-inf"),
        "nested": {"a": float("inf"), "b": [1, float("nan"), 3]},
    }
    mp = MessageProtocol(metadata=metadata, payload=payload)
    s = mp.to_json()
    # Must be valid JSON (no NaN/Infinity tokens)
    data = json.loads(s)
    assert data["payload"]["finite"] == 1.23
    assert data["payload"]["nan"] is None
    assert data["payload"]["inf"] is None
    assert data["payload"]["ninf"] is None
    assert data["payload"]["nested"]["a"] is None
    assert data["payload"]["nested"]["b"][0] == 1
    assert data["payload"]["nested"]["b"][1] is None
    assert data["payload"]["nested"]["b"][2] == 3
