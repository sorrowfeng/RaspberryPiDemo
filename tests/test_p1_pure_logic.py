"""Unit tests for pure config / runtime-control helpers (no hardware needed)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config_support import (  # noqa: E402
    merge_overrides,
    normalize_axis_values,
    normalize_cycle_run_plan,
    normalize_sequence,
)
from app.config_switcher import discover_config_presets, feedback_id_to_digits  # noqa: E402
from app.runtime_control import (  # noqa: E402
    atomic_write_json,
    device_label,
    read_json_file,
    runtime_command_path,
    runtime_pid_path,
)


class MergeOverridesTests(unittest.TestCase):
    def test_nested_merge(self):
        base = {"device": {"a": 1, "b": 2}, "motion": {"x": 1}}
        overrides = {"device": {"b": 9}, "motion": {"y": 2}}
        merged = merge_overrides(base, overrides)
        self.assertEqual(merged["device"], {"a": 1, "b": 9})
        self.assertEqual(merged["motion"], {"x": 1, "y": 2})
        self.assertEqual(base["device"]["b"], 2)

    def test_empty_overrides_returns_copy(self):
        base = {"device": {"a": 1}}
        merged = merge_overrides(base, None)
        self.assertEqual(merged, base)
        self.assertIsNot(merged, base)


class NormalizeAxisValuesTests(unittest.TestCase):
    def test_scalar_expands(self):
        self.assertEqual(normalize_axis_values(5, 3, "v"), [5, 5, 5])

    def test_list_passthrough(self):
        self.assertEqual(normalize_axis_values([1, 2, 3], 3, "v"), [1, 2, 3])

    def test_list_length_mismatch(self):
        with self.assertRaises(ValueError):
            normalize_axis_values([1, 2], 3, "v")


class NormalizeSequenceTests(unittest.TestCase):
    def test_defaults_fill_steps(self):
        seq = normalize_sequence(
            {
                "default_velocities": [10, 20, 30, 40, 50, 60],
                "default_currents": 100,
                "default_interval": 0.5,
                "steps": [{"positions": [1, 2, 3, 4, 5, 6]}],
            },
            6,
        )
        step = seq["steps"][0]
        self.assertEqual(step["velocities"], [10, 20, 30, 40, 50, 60])
        self.assertEqual(step["currents"], [100] * 6)
        self.assertEqual(step["interval"], 0.5)

    def test_gesture_step(self):
        seq = normalize_sequence(
            {"steps": [{"gesture_id": 3, "name": "wave", "interval": 2.0}]},
            6,
        )
        step = seq["steps"][0]
        self.assertEqual(step["gesture_id"], 3)
        self.assertEqual(step["name"], "wave")
        self.assertEqual(step["interval"], 2.0)
        self.assertNotIn("positions", step)

    def test_positions_length_mismatch(self):
        with self.assertRaises(ValueError):
            normalize_sequence({"steps": [{"positions": [1, 2]}]}, 6)


class NormalizeCycleRunPlanTests(unittest.TestCase):
    def test_default_plan(self):
        plan = normalize_cycle_run_plan({"default_cycle_count": 4})
        self.assertEqual(plan, [{"cycles": 4, "velocity_scale": 1.0}])

    def test_plan_total_must_match(self):
        with self.assertRaises(ValueError):
            normalize_cycle_run_plan(
                {
                    "default_cycle_count": 3,
                    "cycle_run_plan": [{"cycles": 2, "velocity_scale": 1.0}],
                }
            )

    def test_zero_cycles_rejected(self):
        with self.assertRaises(ValueError):
            normalize_cycle_run_plan(
                {
                    "default_cycle_count": 3,
                    "cycle_run_plan": [
                        {"cycles": 0, "velocity_scale": 1.0},
                        {"cycles": 3, "velocity_scale": 1.0},
                    ],
                }
            )


class FeedbackIdTests(unittest.TestCase):
    def test_digits(self):
        self.assertEqual(feedback_id_to_digits(0), [0])
        self.assertEqual(feedback_id_to_digits(7), [7])
        self.assertEqual(feedback_id_to_digits(15), [1, 5])

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            feedback_id_to_digits(-1)


class DiscoverPresetsTests(unittest.TestCase):
    def test_covers_all_config_modules(self):
        presets = discover_config_presets()
        modules = [item["module"] for item in presets]
        self.assertEqual(modules[0], "configs.config_runtime_default")
        self.assertIn("configs.config_DH116S_CANFD_aging", modules)
        self.assertIn("configs.config_DH116S_ECAT_power_cycle_test", modules)
        self.assertIn("configs.config_Module_CANFD_aging", modules)
        self.assertEqual(len(modules), len(set(modules)))
        for index, item in enumerate(presets):
            self.assertEqual(item["feedback_id"], index)

    def test_expected_count_matches_configs_dir(self):
        config_files = sorted((ROOT / "configs").glob("config_*.py"))
        presets = discover_config_presets()
        self.assertEqual(len(presets), len(config_files))


class RuntimeControlTests(unittest.TestCase):
    def test_path_helpers(self):
        self.assertEqual(device_label(None), "auto")
        self.assertEqual(device_label(3), "3")
        self.assertTrue(runtime_pid_path("CANFD", 1).endswith("main_CANFD_device_1.pid"))
        self.assertTrue(
            runtime_command_path("RS485", None).endswith(
                "main_RS485_device_auto.command.json"
            )
        )

    def test_atomic_write_and_read_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "cmd.json")
            atomic_write_json(path, {"id": "x", "action": "start_cycle"})
            loaded = read_json_file(path)
            self.assertEqual(loaded, {"id": "x", "action": "start_cycle"})
            self.assertIsNone(read_json_file(os.path.join(tmp, "missing.json")))


if __name__ == "__main__":
    unittest.main()
