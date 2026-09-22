"""Shared motor-init helpers for LHandProController."""

import logging
import time

logger = logging.getLogger(__name__)


class CommonInitMixin:
    """Enable motors / home / DOF discovery shared by all transports."""

def _common_initialization(self, enable_motors, home_motors, home_wait_time, on_home_start=None):
        """通用初始化步骤"""
        # 获取自由度
        self.dof_total, self.dof_active = self.lhp.get_dof()
        logger.info("自由度: 总共 %s, 主动 %s", self.dof_total, self.dof_active)

        # 使能电机
        if enable_motors:
            self.lhp.set_enable(0, True)
            logger.info("等待使能完成")
            time.sleep(1.0)

        # 回零
        if home_motors:
            logger.info("正在回零")
            self.lhp.home_motors(0)
            if on_home_start:
                try:
                    on_home_start()
                except Exception as exc:
                    logger.exception("回零开始回调失败: %s", exc)
            time.sleep(home_wait_time)

        return True
