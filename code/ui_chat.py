# -*- coding: utf-8 -*-
#表情功能
#消息发送功能 发送文本 / 表情消息：校验输入，区分 “文本 / 表情” 类型，通过 socket 发送到服务器，同时本地展示消息
#发送文件：选择本地文件，限制大小（≤10MB），base64 编码后发送，本地展示文件链接
import os, base64, socket, html, uuid
from pathlib import Path
from typing import Dict, List

from PyQt5.QtCore import QUrl, QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont, QDesktopServices, QTextCursor, QPixmap
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QLabel,
    QTextBrowser, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QMenuBar, QAction, QMenu, QInputDialog, QDialog, QRadioButton,
    QGridLayout, QWidgetAction, QFormLayout, QSizePolicy          # ← 新增
)


from utils import recv_data, send_data, MAX_FILE_SIZE
from functools import partial
import logging


class ReceiverThread(QThread):# 只需要接收线程、不用发送线程
    # QThread写法
    incoming = pyqtSignal(dict)

    def __init__(self, sock):
        super().__init__()
        self.sock = sock

    def run(self):
        while True:
            data = recv_data(self.sock)
            if data is None:
                break
            self.incoming.emit(data)


class ChatWindow(QMainWindow):
    THUMB_W = 240          # 缩略宽度

    def __init__(self, username, sock):
        super().__init__()
        self.username = username
        self.sock = sock
        self.setWindowTitle(f"聊天室 - {username}")
        self.resize(780, 540)

        # ---- 左侧 ----
        self.user_list = QListWidget()
        self.user_list.addItem("所有人")
        self.user_list.setCurrentRow(0)
        self.user_list.currentRowChanged.connect(self._switch)

        lbox = QVBoxLayout(); lbox.addWidget(QLabel("在线用户")); lbox.addWidget(self.user_list)

        # ---- 右侧 ----
        self.chat_view = QTextBrowser()
        self.chat_view.setFont(QFont("微软雅黑", 10))
        self.chat_view.setOpenLinks(False)
        self.chat_view.anchorClicked.connect(lambda u: QDesktopServices.openUrl(u))

        self.input_edit = QLineEdit(placeholderText="输入消息…")
        self.input_edit.returnPressed.connect(self._send_text)

        btn_send = QPushButton("发送")
        btn_file = QPushButton("文件")
        btn_emoji = QPushButton("😀")
        btn_clear = QPushButton("清空")
        btn_send.clicked.connect(self._send_text)
        btn_file.clicked.connect(self._send_file)
        btn_emoji.clicked.connect(self._emoji_menu)
        btn_clear.clicked.connect(self._clear_current_chat)
        for btn in (btn_emoji, btn_file, btn_clear,btn_send):
            btn.setMinimumWidth(70)  # 设置统一最小宽度
            btn.setFixedHeight(30)  # 设置一致高度
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # 可以均匀拉伸

        bar = QHBoxLayout(); bar.addWidget(btn_emoji); bar.addWidget(btn_file); bar.addWidget(btn_clear)
        bar.addStretch(); bar.addWidget(btn_send)

        rbox = QVBoxLayout(); rbox.addWidget(self.chat_view); rbox.addWidget(self.input_edit); rbox.addLayout(bar)

        central = QWidget(); hl = QHBoxLayout(central)
        hl.addLayout(lbox, 1); hl.addLayout(rbox, 3)
        self.setCentralWidget(central)

        # ---- 添加菜单 ----
        menu_bar = QMenuBar(self)
        menu = menu_bar.addMenu("账号")

        # 修改密码菜单项
        change_pass_action = QAction("修改密码", self)
        change_pass_action.triggered.connect(self._change_password)
        menu.addAction(change_pass_action)

        # 注销账号菜单项
        delete_account_action = QAction("注销账号", self)
        delete_account_action.triggered.connect(self._delete_account)
        menu.addAction(delete_account_action)

        # 退出菜单项
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)

        # ---- 数据 ----
        self.convs: Dict[str, List[str]] = {"ALL": []}

        # 启动接收线程
        self.recv = ReceiverThread(sock)
        self.recv.incoming.connect(self._handle_in)
        self.recv.start()

        # 加载历史消息
        # self._load_history("ALL")

    # ====== 辅助 ======
    def _cur(self):                      # 当前会话 key
        it = self.user_list.currentItem()
        return "ALL" if not it or it.text() == "所有人" else it.text()

    @staticmethod
    def _uri(path):                      # 本地路径 -> file:// URI
        return QUrl.fromLocalFile(path).toString()

    def _append(self, key, raw_html):    # 统一插入 <p> 断开锚点
        html_line = f"<p>{raw_html}</p><p></p>"
        self.convs.setdefault(key, []).append(html_line)
        if self._cur() == key:
            self.chat_view.moveCursor(QTextCursor.End)
            self.chat_view.insertHtml(html_line)
            self.chat_view.moveCursor(QTextCursor.End)

    def _switch(self):                   # 切换会话
        key = self._cur()
        self.chat_view.clear()

        # 如果没有消息历史，从服务器获取
        if key not in self.convs:
            # self._load_history(key)
            pass
        else:
            for h in self.convs.get(key, []):
                self.chat_view.insertHtml(h)

    # ====== 加载历史聊天记录 ======
    def _load_history(self, target):
        # 发送请求加载历史消息
        send_data(self.sock, {
            "action": "get_history",
            "target": target
        })

    # ====== 处理历史记录 ======
    # 失败了、难受捏
    # def _process_history(self, target, messages):
    #     if not messages:
    #         return
    #
    #     key = target
    #     self.convs.setdefault(key, [])
    #
    #     # 清空现有聊天内容
    #     if self._cur() == key:
    #         self.chat_view.clear()
    #
    #     # 处理历史消息
    #     for msg in messages:
    #         sender = msg["from"]
    #         msg_type = msg["type"]
    #
    #         if msg_type == "text" or msg_type == "emoji":
    #             content = msg["content"]
    #             display_name = "我" if sender == self.username else sender
    #             self._append(key, f"{display_name}: {html.escape(content)}")
    #
    #         elif msg_type == "file":
    #             filename = msg["filename"]
    #             display_name = "我" if sender == self.username else sender
    #
    #             # 检查文件是否在下载目录中
    #             downloads_dir = Path(__file__).with_name("downloads")
    #             downloads_dir.mkdir(exist_ok=True)
    #             local_file = downloads_dir / filename
    #
    #             if local_file.exists():
    #                 # 如果本地有文件，显示可点击链接
    #                 link = f'<a href="{self._uri(str(local_file))}">{html.escape(filename)}</a>'
    #                 self._append(key, f"{display_name}: [文件] {link}")
    #
    #                 # 如果是图片，生成缩略图
    #                 if self._is_img(filename):
    #                     thumb_path = self._make_thumb(str(local_file))
    #                     img = f'<a href="{self._uri(str(local_file))}"><img src="{self._uri(thumb_path)}" width="{self.THUMB_W}"></a>'
    #                     self._append(key, img)
    #             else:
    #                 # 如果本地没有文件，只显示文件名
    #                 self._append(key, f"{display_name}: [文件] {html.escape(filename)} (文件不在本地)")

    # ====== 发送文本 / 表情 ======
    def _send_text(self):
        txt = self.input_edit.text().strip()
        if not txt:
            return
        is_emoji = len(txt) == 1 and txt in {"😀", "😅", "😂", "😍", "😭", "😡", "👍", "🙏", "🙌",
                  "👌", "💕", "😎", "😙", "🤩", "💩","🎶","✌️","🤞","🤨","😐","😫","🤑"}
        send_data(self.sock, {
            "action": "chat", "from": self.username, "to": self._cur(),
            "type": "emoji" if is_emoji else "text", "content": txt
        })
        self._append(self._cur(), f"我: {html.escape(txt)}")
        self.input_edit.clear()

    # ====== 发送文件 ======
    def _send_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if not path:
            return
        if os.path.getsize(path) > MAX_FILE_SIZE:
            QMessageBox.warning(self, "提示", "文件大于 10 MB"); return
        with open(path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        fname = os.path.basename(path)
        send_data(self.sock, {
            "action": "file", "from": self.username, "to": self._cur(),
            "filename": fname, "content": encoded
        })
        self._show_file(self.username, self._cur(), path, fname, sender_self=True)

    # ====== 表情菜单 ======
    def _emoji_menu(self):
        # 表情列表
        emojis = ["😀", "😅", "😂", "😍", "😭", "😡", "👍", "🙏", "🙌",
                  "👌", "💕", "😎", "😙", "🤩", "💩","🎶","✌️","🤞","🤨","😐","😫","🤑"]

        # 创建对话框
        dlg = QDialog(self)
        dlg.setWindowTitle("选择表情")
        dlg.setFixedSize(300, 200)
        layout = QVBoxLayout(dlg)

        # 创建网格布局, 每行5个表情
        grid = QGridLayout()
        row, col = 0, 0
        for emoji in emojis:
            btn = QPushButton(emoji)
            btn.setFixedSize(40, 40)
            # 使用部分函数应用而不是lambda捕获变量
            btn.clicked.connect(partial(self._insert_emoji, emoji, dlg))
            grid.addWidget(btn, row, col)
            col += 1
            if col >= 5:  # 每行5个
                col = 0
                row += 1

        layout.addLayout(grid)
        dlg.exec_()

    # 插入表情
    def _insert_emoji(self, emoji, dlg):
        try:
            self.input_edit.insert(emoji)
            dlg.accept()
        except Exception as e:
            logging.error(f"插入表情时出错: {e}")
            # 确保对话框正常关闭
            try:
                dlg.accept()
            except:
                pass

    # ====== 接收处理 ======
    def _handle_in(self, d):
        action = d.get("action", "")

        # 优先处理密码修改响应
        if action == "change_password_result":
            # 处理修改密码结果
            success = d.get("success", False) # 默认False
            message = d.get("message", "")
            if success:
                QMessageBox.information(self, "成功", "密码修改成功")
            else:
                QMessageBox.warning(self, "失败", message or "密码修改失败")
            return

        # 处理其他消息
        if action == "chat":
            sender, target = d["from"], d["to"]
            key = "ALL" if target == "ALL" else (sender if sender != self.username else target)
            self._append(key, f"{sender}: {html.escape(d['content'])}")

        elif action == "file":
            sender, target, fname = d["from"], d["to"], d["filename"]
            save_dir = Path(__file__).with_name("downloads"); save_dir.mkdir(exist_ok=True)
            fpath = save_dir / fname
            with open(fpath, "wb") as f:
                f.write(base64.b64decode(d["content"]))
            key = "ALL" if target == "ALL" else (sender if sender != self.username else target)
            self._show_file(sender, key, str(fpath), fname, sender_self=False)

        elif action == "user_list":
            self._refresh_users(d["users"])

        elif action == "history":
            self._process_history(d["target"], d["messages"])

        elif action == "delete_account_result":
            # 处理注销账号结果
            success = d.get("success", False)
            message = d.get("message", "")
            if success:
                QMessageBox.information(self, "成功", message or "账号已成功注销")
                self.close()
            else:
                QMessageBox.warning(self, "失败", message or "注销账号失败")

    # ====== 文件/图片展示 ======
    def _show_file(self, sender, key, path, fname, sender_self=False):
        link = f'<a href="{self._uri(path)}">{html.escape(fname)}</a>'
        prefix = "我: " if sender_self else f"{sender}: "
        self._append(key, f"{prefix}[文件] {link}")

        if self._is_img(fname):
            thumb_path = self._make_thumb(path)
            img = f'<a href="{self._uri(path)}"><img src="{self._uri(thumb_path)}" width="{self.THUMB_W}"></a>'
            self._append(key, img)

    # 生成缩略图文件
    def _make_thumb(self, full_path: str) -> str:
        pix = QPixmap(full_path)
        if pix.isNull():
            return full_path
        scaled = pix.scaledToWidth(self.THUMB_W, Qt.SmoothTransformation)
        thumb_dir = Path(full_path).with_suffix("")  # same folder
        thumb = thumb_dir.parent / f"{thumb_dir.name}_{uuid.uuid4().hex[:6]}.png"
        scaled.save(str(thumb), "PNG")
        return str(thumb)

    @staticmethod
    def _is_img(name): return name.lower().endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".bmp"))

    # ====== 在线用户 ======
    def _refresh_users(self, users):
        cur = self._cur()
        self.user_list.blockSignals(True)
        self.user_list.clear(); self.user_list.addItem("所有人")

        # 将在线用户添加到列表
        for u in sorted(users):
            if u != self.username:
                self.user_list.addItem(u)
                # 预加载与该用户的历史聊天记录
                # if u not in self.convs:
                #    self._load_history(u)

        # 恢复当前选中的会话
        for i in range(self.user_list.count()):
            if self.user_list.item(i).text() == cur:
                self.user_list.setCurrentRow(i); break
        self.user_list.blockSignals(False)

    # ====== 清空当前聊天记录 ======
    def _clear_current_chat(self):
        key = self._cur()
        reply = QMessageBox.question(self, "确认",
                                    f"确定要清空与'{key}'的聊天记录吗？\n(仅清除本地显示，不会删除服务器存档)",
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.convs[key] = []
            self.chat_view.clear()

    # ====== 修改密码 ======
    def _change_password(self):
        try:
            # 显示修改密码对话框
            dlg = QDialog(self)
            dlg.setWindowTitle("修改密码")
            dlg.resize(300, 180)
            layout = QVBoxLayout(dlg)

            form = QFormLayout()
            old_pass = QLineEdit()
            old_pass.setEchoMode(QLineEdit.Password)
            new_pass = QLineEdit()
            new_pass.setEchoMode(QLineEdit.Password)
            confirm_pass = QLineEdit()
            confirm_pass.setEchoMode(QLineEdit.Password)

            form.addRow("原密码:", old_pass)
            form.addRow("新密码:", new_pass)
            form.addRow("确认新密码:", confirm_pass)
            layout.addLayout(form)

            btn_ok = QPushButton("确定")
            btn_cancel = QPushButton("取消")

            # 使用lambda避免闭包中的引用问题
            btn_ok.clicked.connect(lambda: dlg.accept())
            btn_cancel.clicked.connect(lambda: dlg.reject())

            btn_layout = QHBoxLayout()
            btn_layout.addWidget(btn_ok)
            btn_layout.addWidget(btn_cancel)
            layout.addLayout(btn_layout)

            result = dlg.exec_()

            if result == QDialog.Accepted:
                old_password = old_pass.text()
                new_password = new_pass.text()
                confirm = confirm_pass.text()

                # 检查输入
                if not old_password:
                    QMessageBox.warning(self, "提示", "请输入原密码")
                    return
                if not new_password:
                    QMessageBox.warning(self, "提示", "请输入新密码")
                    return
                if new_password != confirm:
                    QMessageBox.warning(self, "提示", "两次输入的新密码不一致")
                    return

                # 发送请求到服务器
                send_data(self.sock, {
                    "action": "change_password",
                    "old_password": old_password,
                    "new_password": new_password
                })
                # 结果会在_handle_in中处理
        except Exception as e:
            QMessageBox.critical(self, "错误", f"修改密码时出现错误: {str(e)}")

    # ====== 注销账号 ======
    def _delete_account(self):
        # 确认对话框
        reply = QMessageBox.question(self, "注销确认",
                                   "确定要注销账号吗？此操作将删除您的所有数据且无法恢复！",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # 输入密码确认
        password, ok = QInputDialog.getText(self, "密码确认",
                                           "请输入密码以确认注销操作:",
                                           QLineEdit.Password)
        if not ok or not password:
            return

        # 发送请求
        send_data(self.sock, {
            "action": "delete_account",
            "password": password
        })
        # 结果会在_handle_in中处理

    # ====== 关闭 ======
    def closeEvent(self, e):
        try:
            send_data(self.sock, {"action": "logout"})
        except Exception: pass
        try:
            self.sock.close()
        except Exception: pass
        self.recv.quit(); self.recv.wait(400)
        e.accept()
