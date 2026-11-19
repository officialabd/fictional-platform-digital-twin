import json

import pytest

from shared.messages import Reading, decode, encode, topic


def test_topic_is_per_tag():
    assert topic("LT201") == "platform/LT201"


def test_payload_holds_tag_timestamp_and_value_only():
    payload = encode(Reading("LT201", 412.0, 51.3))
    assert json.loads(payload) == {"tag": "LT201", "ts": 412.0, "value": 51.3}


def test_decode_reverses_encode():
    reading = Reading("PT201", 61.0, 19.04)
    assert decode(encode(reading)) == reading


def test_decode_rejects_bad_payloads():
    for payload in (b"not json", b'{"tag": "PT201"}', b'{"tag": "PT201", "ts": 1, "value": "x"}'):
        with pytest.raises(ValueError):
            decode(payload)
