# -*- coding: utf-8 -*-
#实现了用户登录、注册的图形化交互，并通过 Socket 与服务端进行网络通信，完成身份验证逻辑。
import socket
import base64
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox,
    QFileDialog, QGroupBox
)
from PyQt5.QtCore import Qt, QBuffer, QByteArray, QIODevice
from PyQt5.QtGui import QPixmap, QImage

from utils import SERVER_HOST, SERVER_PORT, send_data, recv_data

class RegisterDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("用户注册")
        self.setFixedSize(350, 250)  # 减小窗口高度
        self.new_user = self.new_pass = None

        # 用户信息输入
        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass2_edit = QLineEdit() # 确认密码
        self.pass2_edit.setEchoMode(QLineEdit.Password)

        # 用户信息表单
        user_group = QGroupBox("用户信息")
        form = QFormLayout()
        form.addRow("用户名:", self.user_edit)
        form.addRow("密码:", self.pass_edit)
        form.addRow("确认密码:", self.pass2_edit)
        user_group.setLayout(form)

        # 按钮
        btn_reg = QPushButton("注册")
        btn_cancel = QPushButton("取消")
        btn_reg.clicked.connect(self.do_register)
        btn_cancel.clicked.connect(self.reject)
        h = QHBoxLayout(); h.addWidget(btn_reg); h.addWidget(btn_cancel)

        # 整体布局
        v = QVBoxLayout(self)
        v.addWidget(user_group)
        v.addLayout(h)

    def do_register(self):
        u, p, p2 = self.user_edit.text().strip(), \
                   self.pass_edit.text(), self.pass2_edit.text()
        if not (u and p):
            # 检测是否输入
            QMessageBox.warning(self, "提示", "请输入用户名和密码"); return
        if p != p2:
            # 确认密码
            QMessageBox.warning(self, "提示", "两次密码不一致"); return
        try:
            sock = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=5)
            
            # 准备注册数据
            register_data = {
                "action": "register", 
                "username": u, 
                "password": p
            }
            
            send_data(sock, register_data)
            resp = recv_data(sock)
            sock.close()
        except Exception:
            QMessageBox.critical(self, "错误", "无法连接服务器"); return
        if resp and resp.get("success"):
            self.new_user, self.new_pass = u, p
            QMessageBox.information(self, "成功", "注册成功，请登录")
            self.accept()
        else:
            QMessageBox.warning(self, "失败", resp.get("error", "注册失败"))


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("用户登录")
        self.setFixedSize(300, 200)
        self.username = None
        self.sock = None

        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit(); self.pass_edit.setEchoMode(QLineEdit.Password)

        form = QFormLayout()
        form.addRow("用户名:", self.user_edit)
        form.addRow("密码:", self.pass_edit)

        btn_login = QPushButton("登录")
        btn_reg = QPushButton("注册")
        btn_login.clicked.connect(self.do_login)
        btn_reg.clicked.connect(self.open_register)
        h = QHBoxLayout(); h.addWidget(btn_login); h.addWidget(btn_reg)

        v = QVBoxLayout(self); v.addLayout(form); v.addLayout(h)

        self.pass_edit.returnPressed.connect(self.do_login)

    def do_login(self):
        u, p = self.user_edit.text().strip(), self.pass_edit.text()
        if not (u and p):
            QMessageBox.warning(self, "提示", "请输入用户名和密码"); return
        try:
            if self.sock:
                self.sock.close()
            self.sock = socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=5)
            send_data(self.sock, {"action": "login", "username": u, "password": p})
            resp = recv_data(self.sock)
            self.sock.settimeout(None)
        except Exception:
            QMessageBox.critical(self, "错误", "无法连接服务器")
            if self.sock:
                self.sock.close(); self.sock = None
            return
        if resp and resp.get("success"):
            self.username = u
            self.accept()
        else:
            QMessageBox.warning(self, "失败", resp.get("error", "登录失败"))

    def open_register(self):
        dlg = RegisterDialog()
        dlg.exec_()
        if dlg.result() == QDialog.Accepted:
            self.user_edit.setText(dlg.new_user)
            self.pass_edit.setText(dlg.new_pass)

    def closeEvent(self, e):
        if self.sock:
            try: self.sock.close()
            except Exception: pass
        e.accept()
