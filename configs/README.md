# Presets

`configs/` stores preset metadata.

Each preset file now contains:

- `DISPLAY_NAME`
- `PRESET`

`PRESET` describes:

- communication mode and launch count
- device type / node id / RS485 port
- home time / cycle count / finish position
- which sequence files should be used for cycle / grasp repeat / hold grip / hold release
- feature flags
- CANFD transport backend in `features` (optional): `canfd_driver`, one of
  `gsusb` / `socketcan` / `libcanbus` / `hcanbus`, or `None` for runtime auto-selection;
  omitted keys fall back to `DEFAULT_CANFD_DRIVER` in
  [config_support.py](/D:/Project/PyProject/RaspberryPiDemo/config_support.py)
- log retention limits in `features` (optional): `log_max_bytes`, `log_backup_count`,
  `log_max_sessions`, `log_max_total_bytes`; omitted keys fall back to the defaults in
  [log.py](/D:/Project/PyProject/RaspberryPiDemo/log.py)

Preset files no longer embed long motion arrays directly. Those sequences now live in [sequences](../sequences).

Typical naming rule:

- `config_<device>_<bus>_<scenario>.py`
- examples:
  - `config_DH116_CANFD_aging.py`
  - `config_DH116S_CANFD_grasp.py`
  - `config_Module_ECAT_aging.py`

The active preset is selected from [active_config.py](../active_config.py).
