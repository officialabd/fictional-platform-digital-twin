import json

from shared.messages import Reading, encode, topic


def test_topic_is_per_tag():
    assert topic("LT201") == "platform/LT201"


def test_payload_holds_tag_timestamp_and_value_only():
    payload = encode(Reading("LT201", 412.0, 51.3))
    assert json.loads(payload) == {"tag": "LT201", "ts": 412.0, "value": 51.3}
