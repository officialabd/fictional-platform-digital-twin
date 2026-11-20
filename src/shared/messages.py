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


SUBSCRIPTION = TOPIC_PREFIX + "#"


def decode(payload: bytes) -> Reading:
    """Raises ValueError on anything that is not a well formed reading."""
    try:
        data = json.loads(payload)
        return Reading(str(data["tag"]), float(data["ts"]), float(data["value"]))
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"bad reading: {payload[:80]!r}") from error
