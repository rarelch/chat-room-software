#!/usr/bin/env python
# -*- coding: utf-8 -*-
#客户端应用核心程序
#基础系统 / 网络模块：socket（网络通信）、sys（系统参数 / 程序退出）、logging（日志记录）、ctypes（Windows 系统进程标识配置）
#PyQt5 GUI 模块：QApplication（Qt 应用入口）、QIcon（窗口图标）、LoginDialog（登录对话框，来自ui_login）、MainWindow（主窗口，来自ui_main）
#从utils导入recv_data（接收网络数据）、send_data（发送网络数据），是核心的网络收发逻辑。
import socket
import sys
import logging
import ctypes
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from ui_login import LoginDialog
from ui_main import MainWindow
from utils import recv_data, send_data

# 配置日志
#配置全局日志系统，用于调试和错误排查：
#日志级别设为DEBUG（最详细级别），格式包含「时间 + 日志级别 + 日志名称 + 消息」；
#日志输出双端：
#文件输出：写入client_debug.log，编码utf-8，模式为w（覆盖式写入）；
#控制台输出：实时打印到终端；
#创建专属日志实例logger = logging.getLogger("Client")，便于区分日志来源。
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("client_debug.log", encoding="utf-8", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Client")

def patch_networking():#网络函数日志增强，替换utils模块的原生send_data/recv_data，添加日志输出，无侵入式增强调试能力：
    """替换网络收发函数，添加日志输出"""
    orig_send_data = send_data
    orig_recv_data = recv_data
    
    def logged_send_data(sock, data):
        action = data.get("action", "unknown")
        to_user = data.get("to_user", "")
        to = data.get("to", "")
        target = to_user or to
        logger.debug(f"发送 {action} -> {target}")
        if action == "handle_friend_request":
            logger.info(f"发送好友请求处理: request_id={data.get('request_id')}, from_user={data.get('from_user')}, accepted={data.get('accepted')}")
        return orig_send_data(sock, data)
        #logged_send_data（包装发送函数）：
        #提取发送数据中的action（操作类型）、to_user/to（目标用户），打印 DEBUG 级日志（记录 “发送 XX 操作到 XX 用户”）；
        #最终调用原生send_data完成实际发送。
    def logged_recv_data(sock):
        data = orig_recv_data(sock)
        if data:
            action = data.get("action", "unknown")
            logger.debug(f"接收 {action}")
            
            if action == "friend_list":
                friends = data.get("friends", [])
                logger.info(f"收到好友列表更新: {friends}")
            elif action == "friend_request_update":
                from_user = data.get("from", "")
                accepted = data.get("accepted", False)
                logger.info(f"收到好友请求更新: from={from_user}, accepted={accepted}")
            elif action == "friend_requests":
                requests = data.get("requests", [])
                logger.info(f"收到好友请求列表: {requests}")
            #包装接收函数，和上面的类似
        return data
    
    # 替换全局函数
    import utils
    utils.send_data = logged_send_data
    utils.recv_data = logged_recv_data

def main():
    logger.info("启动Client调试客户端")
    
    # 添加网络调试日志
    patch_networking()
    
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("myappid")
        
        # 启动应用
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        dlg = LoginDialog()
        dlg.setWindowIcon(QIcon("./222.ico"))
        
        if dlg.exec_() == dlg.Accepted:
            logger.info(f"用户 {dlg.username} 登录成功")
            # 使用新的主窗口
            win = MainWindow(dlg.username, dlg.sock)
            win.show()
            win.setWindowIcon(QIcon("./222.ico"))
            sys.exit(app.exec_())
        sys.exit(0)
    except Exception as e:
        logger.error(f"发生错误: {str(e)}", exc_info=True)

if __name__ == "__main__":#程序入口保护
    main()

