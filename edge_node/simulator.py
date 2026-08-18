"""
edge_node/simulator.py
-----------------------
Simulates an embedded IoT micro-Doppler radar sensor ("edge node") pushing
telemetry to the Flask/SocketIO server at a fixed duty cycle (default 10Hz).

In a real deployment this module would be replaced by firmware on the actual
radar hardware (e.g. an FMCW/CW radar front-end + MCU) publishing samples over
MQTT/UDP/serial into the same `on_sample` callback contract used here.

Design notes
------------
- Runs in a native background `threading.Thread` (daemon) so it does not block
  the Flask-SocketIO event loop / workers.
- Generates one of several "target scenarios" (drone, bird, human, vehicle,
  clutter/noise) for a few seconds at a time, producing physically plausible
  micro-Doppler spectra, then switches scenario — mimicking targets entering
  and leaving the radar's field of view.
- Talks to the rest of the app ONLY through the `on_sample` callback so it has
  no direct dependency on Flask, SQLAlchemy, or SocketIO (easy to unit test /
  swap for real hardware).
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

SPEED_OF_LIGHT = 3.0e8
RADAR_CENTER_FREQ_HZ = 24.125e9  # typical low-power CW/FMCW radar band (24 GHz ISM)

SCENARIOS = {
    "drone": {
        "base_velocity_mps": (2.0, 14.0),
        "micro_doppler_hz": (60, 400),     # rotor blade flutter frequency
        "spread_hz": (150, 500),
        "power_db": (-35, -15),
        "duration_s": (6, 14),
    },
    "bird": {
        "base_velocity_mps": (3.0, 12.0),
        "micro_doppler_hz": (5, 25),       # wingbeat frequency
        "spread_hz": (40, 120),
        "power_db": (-45, -25),
        "duration_s": (4, 10),
    },
    "human": {
        "base_velocity_mps": (0.6, 2.5),
        "micro_doppler_hz": (2, 8),        # gait cadence
        "spread_hz": (20, 80),
        "power_db": (-40, -20),
        "duration_s": (8, 20),
    },
    "vehicle": {
        "base_velocity_mps": (6.0, 30.0),
        "micro_doppler_hz": (1, 6),        # engine vibration harmonic
        "spread_hz": (10, 40),
        "power_db": (-20, -5),
        "duration_s": (5, 15),
    },
    "clutter": {
        "base_velocity_mps": (0.0, 0.5),
        "micro_doppler_hz": (0, 3),
        "spread_hz": (5, 20),
        "power_db": (-55, -40),
        "duration_s": (3, 8),
    },
}

N_SPECTRUM_BINS = 64


@dataclass
class RadarSampleData:
    doppler_freq_hz: float
    signal_power_db: float
    radial_velocity_mps: float
    spectrum_bins: list = field(default_factory=list)
    scenario: str = "clutter"
    node_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class EdgeNodeSimulator:
    """A single simulated radar sensor pushing samples at a fixed rate."""

    def __init__(
        self,
        node_id: str,
        on_sample: Callable[[RadarSampleData], None],
        rate_hz: float = 10.0,
        seed: Optional[int] = None,
    ):
        self.node_id = node_id
        self.on_sample = on_sample
        self.rate_hz = rate_hz
        self._interval = 1.0 / rate_hz
        self._rng = random.Random(seed)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._scenario_name = "clutter"
        self._scenario_elapsed = 0.0
        self._scenario_duration = 0.0
        self._phase = 0.0
        self._pick_new_scenario()

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"edge-sim-{self.node_id[:8]}")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # -- internals -------------------------------------------------------
    def _pick_new_scenario(self):
        self._scenario_name = self._rng.choices(
            population=list(SCENARIOS.keys()),
            weights=[0.30, 0.20, 0.20, 0.20, 0.10],
            k=1,
        )[0]
        profile = SCENARIOS[self._scenario_name]
        self._scenario_elapsed = 0.0
        self._scenario_duration = self._rng.uniform(*profile["duration_s"])
        self._base_velocity = self._rng.uniform(*profile["base_velocity_mps"])
        if self._rng.random() < 0.5:
            self._base_velocity *= -1  # inbound vs outbound
        self._micro_doppler_hz = self._rng.uniform(*profile["micro_doppler_hz"])
        self._spread_hz = self._rng.uniform(*profile["spread_hz"])
        self._power_db_base = self._rng.uniform(*profile["power_db"])

    def _generate_sample(self) -> RadarSampleData:
        profile = SCENARIOS[self._scenario_name]
        self._scenario_elapsed += self._interval
        self._phase += self._interval

        if self._scenario_elapsed >= self._scenario_duration:
            self._pick_new_scenario()
            profile = SCENARIOS[self._scenario_name]

        # Bulk Doppler shift from the base radial velocity (physics-based):
        #   f_d = 2 * v * f_c / c
        bulk_doppler_hz = (2 * self._base_velocity * RADAR_CENTER_FREQ_HZ) / SPEED_OF_LIGHT

        # Add micro-Doppler modulation (limbs / rotors / wings / vibration)
        micro_component = self._spread_hz * math.sin(2 * math.pi * self._micro_doppler_hz * self._phase)
        noise = self._rng.gauss(0, self._spread_hz * 0.08)
        doppler_freq_hz = bulk_doppler_hz / 1000.0 + micro_component + noise  # scaled to a readable Hz range for UI

        signal_power_db = self._power_db_base + self._rng.gauss(0, 2.0)

        radial_velocity_mps = self._base_velocity + self._rng.gauss(0, 0.15)

        spectrum_bins = self._generate_spectrum(doppler_freq_hz, profile)

        return RadarSampleData(
            doppler_freq_hz=doppler_freq_hz,
            signal_power_db=signal_power_db,
            radial_velocity_mps=radial_velocity_mps,
            spectrum_bins=spectrum_bins,
            scenario=self._scenario_name,
            node_id=self.node_id,
            timestamp=time.time(),
        )

    def _generate_spectrum(self, center_hz: float, profile: dict) -> list:
        """Build a simple synthetic micro-Doppler spectrogram row (N bins)."""
        bins = []
        spread = self._spread_hz
        for i in range(N_SPECTRUM_BINS):
            bin_freq = -300 + (600 / N_SPECTRUM_BINS) * i
            distance = abs(bin_freq - center_hz)
            magnitude = math.exp(-(distance ** 2) / (2 * (spread + 1e-6) ** 2))
            magnitude *= (10 ** (self._power_db_base / 20))
            magnitude += self._rng.uniform(0, 0.02)  # noise floor
            bins.append(round(magnitude, 4))
        return bins

    def _run(self):
        next_tick = time.monotonic()
        while not self._stop_event.is_set():
            sample = self._generate_sample()
            try:
                self.on_sample(sample)
            except Exception as exc:  # noqa: BLE001 - keep the sim alive
                print(f"[edge_node] on_sample callback error: {exc}")

            next_tick += self._interval
            sleep_time = next_tick - time.monotonic()
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)
            else:
                next_tick = time.monotonic()
