"""The message format between the simulator and the twin. This is all they have in common."""

import json
from dataclasses import asdict, dataclass

TOPIC_PREFIX = "platform/"
QOS = 1  # at least once: the broker acknowledges, and a resend may duplicate a reading


@dataclass(frozen=True)
class Reading:
    tag: str
    ts: float  # simulated seconds since the run started
    value: float


def topic(tag: str) -> str:
    return TOPIC_PREFIX + tag


def encode(reading: Reading) -> bytes:
    return json.dumps(asdict(reading)).encode()
