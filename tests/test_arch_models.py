"""Tests for RuntimeConfig and PowerCycleRunner state machine."""

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_models import build_runtime_config  # noqa: E402
from power_cycle_runner import (  # noqa: E402
    make_managed_runner,
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    PowerCyclePhase,
    PowerCycleRunner,
)


class RuntimeConfigTests(unittest.TestCase):
    def _raw(self):
        return {
            "communication": {"default_mode": "CANFD", "default_launch_count": 4},
            "device": {"current_hand_type": 1, "canfd_node_id": 2, "rs485_port_name": None},
            "motion": {
                "default_home_time": 5.0,
                "default_cycle_count": 10,
                "default_cycle_velocity": 20000,
                "default_cycle_velocities": [20000] * 6,
                "default_cycle_interval": 0.8,
                "default_cycle_current": 1000,
                "default_cycle_currents": [1000] * 6,
                "cycle_run_plan": [{"cycles": 10, "velocity_scale": 1.0}],
                "cycle_move_positions": [{"positions": [0] * 6, "velocities": [20000] * 6,
                                          "currents": [1000] * 6, "interval": 0.8}],
                "cycle_finish_position": [7000, 5000, 5000, 0, 0, 0],
            },
            "grasp": {"mode": "repeat", "repeat_count": 3, "repeat": {"steps": []},
                      "hold": {"grip": {"steps": []}, "release": {"steps": []}}},
            "features": {
                "auto_connect": True,
                "auto_cycle_running": True,
                "enable_alarm_check": True,
                "enable_home_check": False,
                "enable_torque_control": False,
            },
        }

    def test_build_typed_config(self):
        cfg = build_runtime_config(self._raw())
        self.assertEqual(cfg.communication.default_mode, "CANFD")
        self.assertEqual(cfg.device.canfd_node_id, 2)
        self.assertEqual(cfg.motion.cycle_run_plan[0].cycles, 10)
        self.assertEqual(len(cfg.motion.default_cycle_velocities), 6)
        self.assertFalse(cfg.features.enable_home_check)

    def test_rejects_missing_key(self):
        raw = self._raw()
        del raw["device"]["canfd_node_id"]
        with self.assertRaises(KeyError):
            build_runtime_config(raw)

    def test_power_cycle_defaults(self):
        cfg = build_runtime_config(self._raw())
        self.assertFalse(cfg.features.enable_main_power_cycle)
        self.assertAlmostEqual(cfg.features.main_power_cycle_on_seconds, 10.0)


class PowerCycleRunnerTests(unittest.TestCase):
    def _runner(self, *, connect_ok=True, start_ok=True, stop_ok=True, disconnect_ok=True):
        return PowerCycleRunner(
            on_power_on=lambda: 0.0,
            on_connect=lambda: connect_ok,
            on_start_motion=lambda: start_ok,
            on_stop_motion=lambda: stop_ok,
            on_disconnect=lambda: disconnect_ok,
            on_power_off=lambda: 0.0,
        )

    def test_happy_path_reaches_power_off(self):
        runner = self._runner()
        with mock.patch("power_cycle_runner.time.sleep"):
            outcome = runner.run_cycle(
                start_delay=0.0, on_seconds=0.2, disconnect_lead_seconds=0.0,
                force_off_at_deadline=True, off_seconds=0.1,
            )
        self.assertTrue(outcome.cleanup_succeeded)
        self.assertTrue(outcome.communication_released)
        self.assertEqual(runner.phase, PowerCyclePhase.POWER_OFF)
        self.assertTrue(any(h.startswith("running->cleanup") for h in runner.history))
        self.assertTrue(any(h.startswith("cleanup->power_off") for h in runner.history))

    def test_connect_failure_still_powers_off(self):
        runner = self._runner(connect_ok=False)
        with mock.patch("power_cycle_runner.time.sleep"):
            outcome = runner.run_cycle(
                start_delay=0.0, on_seconds=0.1, disconnect_lead_seconds=0.0,
                force_off_at_deadline=True, off_seconds=0.1,
            )
        self.assertFalse(outcome.cleanup_succeeded)
        self.assertEqual(runner.phase, PowerCyclePhase.POWER_OFF)

    def test_illegal_transition_rejected(self):
        runner = self._runner()
        with self.assertRaises(IllegalTransition):
            runner._transition(PowerCyclePhase.POWER_OFF, "skip everything")

    def test_allowed_graph_idempotent(self):
        self.assertIn(PowerCyclePhase.CONNECTING, ALLOWED_TRANSITIONS[PowerCyclePhase.POWER_ON])


class ManagedRunnerFactoryTests(unittest.TestCase):
    def test_factory_wraps_callbacks(self):
        calls = []
        runner = make_managed_runner(
            power_on=lambda: calls.append("on") or 1.0,
            request_start=lambda: calls.append("start") or True,
            request_stop=lambda: calls.append("stop") or True,
            power_off=lambda: calls.append("off") or 2.0,
        )
        with mock.patch("power_cycle_runner.time.sleep"):
            outcome = runner.run_cycle(
                start_delay=0.0, on_seconds=0.05, disconnect_lead_seconds=0.0,
                force_off_at_deadline=True, off_seconds=0.01,
            )
        self.assertEqual(calls, ["on", "start", "stop", "off"])
        self.assertTrue(outcome.communication_released)
        self.assertEqual(runner.phase, PowerCyclePhase.POWER_OFF)


if __name__ == "__main__":
    unittest.main()
