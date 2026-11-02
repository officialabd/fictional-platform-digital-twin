"""The MQTT connection to the broker, which stands in for the DMZ and the satellite link."""

import logging
from collections import deque

import paho.mqtt.client as mqtt

from shared.messages import QOS, Reading, encode, topic

log = logging.getLogger(__name__)

MAX_INFLIGHT = 200


class MqttLink:
    def __init__(self, host: str, port: int, client_id: str) -> None:
        self.connected = False
        # Filled on paho's network thread and emptied on the tick loop. A deque is safe for that,
        # so the two threads share no locks.
        self._acks: deque[int] = deque()

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.max_inflight_messages_set(MAX_INFLIGHT)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.connect_async(host, port)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = not reason_code.is_failure
        log.info("broker connect: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = False
        log.warning("broker disconnected: %s", reason_code)

    def _on_publish(self, client, userdata, message_id, reason_code, properties) -> None:
        self._acks.append(message_id)

    def publish(self, reading: Reading) -> int | None:
        info = self.client.publish(topic(reading.tag), encode(reading), qos=QOS)
        return info.mid if info.rc == mqtt.MQTT_ERR_SUCCESS else None

    def take_acks(self) -> list[int]:
        acks = []
        while self._acks:
            acks.append(self._acks.popleft())
        return acks

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()
