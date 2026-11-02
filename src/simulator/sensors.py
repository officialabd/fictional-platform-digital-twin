"""Turn true values into reported values. This gap is what makes spoofing possible to simulate."""

import random

from simulator import config


class Sensors:
    def __init__(self, noise: bool = True, seed: int | None = None) -> None:
        self.noise_sd = config.NOISE_SD if noise else {}
        self.rng = random.Random(seed)

    def _add_noise(self, tag: str, value: float) -> float:
        sd = self.noise_sd.get(tag)
        if sd is None:
            return value
        return max(0.0, value + self.rng.gauss(0.0, sd))

    def read(self, true: dict[str, float], spoofs: dict[str, float]) -> dict[str, float]:
        """Reported value of every tag. A spoofed tag reports the attacker's value instead.

        Spoofed values still get noise, so a flat line does not give the attack away.
        """
        reported = {}
        for tag in config.TAGS:
            value = spoofs.get(tag, true[tag])
            reported[tag] = round(self._add_noise(tag, value), 3)
        return reported
