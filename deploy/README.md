# 开机自启部署（lhandpro_ethercat.service）

目标：开机自动运行 `launch.py` → 读取 `active_config.py` → 按 preset 启动一个或多个
`main.py`，或按配置进入主电源通断测试。

## 启动链

```text
systemd (lhandpro_ethercat.service)
  └─ launch.py
       ├─ [默认] N × main.py
       └─ [enable_main_power_cycle] main_power_cycle.py → 长驻 main.py
```

模式来源：

1. `active_config.py` 的 `ACTIVE_PRESET` + `RUNTIME_OVERRIDES`
2. `configs/config_*.py` preset 元数据

## 现场路径

当前设备上的实际路径：

```text
项目：/home/ubuntu/Documents/aarch64/share/LHandProLib/examples/RaspberryPiDemo
服务：/etc/systemd/system/lhandpro_ethercat.service
```

`deploy/lhandpro_ethercat.service` 中的 `ExecStart` 和 `WorkingDirectory` 与上述路径一致。
如果项目部署到其它目录，先修改这两行再安装。

## 安装 / 更新

```bash
sudo cp deploy/lhandpro_ethercat.service /etc/systemd/system/lhandpro_ethercat.service
sudo systemctl daemon-reload
sudo systemctl enable --now lhandpro_ethercat.service
journalctl -u lhandpro_ethercat.service -f
```

## 模式切换

- 直接编辑 `active_config.py`，然后 `sudo systemctl restart lhandpro_ethercat.service`
- GPIO `SWITCH_CONFIG` 短按轮转 preset，写回 `active_config.py` 并重启
- 修改 `configs/config_*.py` 只影响对应 preset，不会自动切换当前 preset

## 注意

- unit 使用 `User=root`，并保留 `sudo` 调用，与现场现有 unit 保持一致。
- `launch.py` 监督子进程；`main.py` 异常退出会由 `launch.py` 按当前 preset 重拉。
- `config_switcher` 使用明文 sudo 密码执行重启，属现场约定，按需求保留。
- 日志在 `logs/<run_id>/`，运行时控制文件在 `runtime/`；更新代码时不要覆盖这两个目录。
- SDK 动态库在 `lib/`，被 `.gitignore` 忽略，部署时要单独同步。
