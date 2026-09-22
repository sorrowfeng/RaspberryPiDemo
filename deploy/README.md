# 开机自启部署

目标：开机自动 `launch.py` → 读 `active_config.py` → 按 preset 驱动灵巧手。

## 启动链

```text
systemd (rpd.service)
  └─ launch.py
       ├─ [默认] N × main.py
       └─ [enable_main_power_cycle] main_power_cycle.py → 长驻 main.py
```

模式来源：
1. `active_config.py` 的 `ACTIVE_PRESET` + `RUNTIME_OVERRIDES`
2. `configs/config_*.py` preset 元数据

## 安装

```bash
sudo mkdir -p /opt/RaspberryPiDemo
sudo cp -a . /opt/RaspberryPiDemo/
sudo cp deploy/rpd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rpd.service
journalctl -u rpd -f
```

## 模式切换

- GPIO `SWITCH_CONFIG` 短按轮转 → 写 `active_config.py` → 重启生效
- `setup.py` 产线写入
- 直接改 `active_config.py` 后 `sudo systemctl restart rpd`

## 注意

- `config_switcher` 使用明文 sudo 密码执行 `shutdown -r`（现场约定）
- 子进程 `main.py` 意外退出由 `launch.py` 监督并按 preset 重拉
