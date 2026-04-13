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

Preset files no longer embed long motion arrays directly. Those sequences now live in [sequences](/D:/Project/PyProject/RaspberryPiDemo/sequences).

Typical naming rule:

- `config_<device>_<bus>_<scenario>.py`
- examples:
  - `config_DH116_CANFD_aging.py`
  - `config_DH116S_CANFD_grasp.py`
  - `config_Module_ECAT_aging.py`

The active preset is selected from [active_config.py](/D:/Project/PyProject/RaspberryPiDemo/active_config.py).
