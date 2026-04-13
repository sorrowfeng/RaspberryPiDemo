# Preset Configs

`configs/` stores ready-to-use preset configurations.

Naming rule:
- `config_<device>_<bus>_<scenario>.py`
- examples: `config_DH116_CANFD_aging.py`, `config_DH116S_CANFD_grasp.py`

All preset files now follow the same structure as the root [`config.py`](/D:/Project/PyProject/RaspberryPiDemo/config.py):
- `COMMUNICATION_CONFIG`
- `DEVICE_CONFIG`
- `MOTION_CONFIG`
- `GRASP_CONFIG`
- `FEATURE_FLAGS`

Each file also exports the old flat constants for backward compatibility, so existing runtime code can keep importing values like `DEFAULT_CYCLE_COUNT` or `GRASP_MODE`.
