# -*- coding: utf-8 -*-
import os
import base64
import html
import json
import uuid
import logging
import traceback
from pathlib import Path
from typing import Dict, List, Optional
import time
from datetime import datetime
from PyQt5.QtCore import (QUrl, QThread, pyqtSignal, Qt, QTimer, QSize, 
                         QBuffer, QIODevice, QByteArray, QPoint)
from PyQt5.QtGui import (QFont, QDesktopServices, QTextCursor, QPixmap, 
                        QIcon, QImage, QPainter, QColor, QFontMetrics,
                        QPen, QBrush)
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QLabel,
    QTextBrowser, QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QMenuBar, QAction, QMenu, QInputDialog, QDialog, QRadioButton,
    QGridLayout, QWidgetAction, QFormLayout, QSizePolicy, QTabWidget,
    QListWidgetItem, QSplitter, QFrame, QToolButton, QToolBar, QComboBox,
    QScrollArea, QApplication, QSlider, QCheckBox, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QProgressBar, QTextEdit, QGroupBox
)
from utils import recv_data, send_data, MAX_FILE_SIZE, UPLOAD_DIR, generate_anonymous_name
from utils import voice_change, adjust_video_resolution, apply_video_effect
from functools import partial
logger = logging.getLogger("ChatClient")

# 接收线程
class ReceiverThread(QThread):
    incoming = pyqtSignal(dict)
    def __init__(self, sock):
        super().__init__()
        self.sock = sock
        self.running = True
    def run(self):
        while self.running:
            data = recv_data(self.sock)
            if data is None:
                break
            self.incoming.emit(data)
            
    def stop(self):
        self.running = False

# 创建语音通话线程类
class VoiceCallThread(QThread):
    # 发送音频数据信号
    audio_ready = pyqtSignal(bytes)
    # 通话状态信号
    call_status = pyqtSignal(str)
    # 远程音频数据信号
    remote_audio_ready = pyqtSignal(bytes)
    
    def __init__(self, target_user, sock, voice_type="normal"):
        super().__init__()
        self.target_user = target_user
        self.sock = sock  # 用于发送音频数据
        self.voice_type = voice_type
        self.running = False
        self.is_muted = False
        
        # 设置日志记录
        self.log = logging.getLogger(f"VoiceCall-{target_user}")
        
        # 导入音频处理库
        try:
            import pyaudio
            import numpy as np
            self.pyaudio = pyaudio
            self.np = np
            
            # 音频参数
            self.CHUNK = 1024
            self.FORMAT = pyaudio.paInt16
            self.CHANNELS = 1
            self.RATE = 16000
            
            # 初始化音频处理对象
            self.pa = pyaudio.PyAudio()
            
        except ImportError as e:
            self.log.error(f"导入音频库失败: {e}")
            QMessageBox.warning(None, "音频初始化失败", f"无法加载所需的音频库: {e}\n请确保已安装PyAudio")
            raise
    
    def run(self):
        try:
            self.running = True
            self.call_status.emit("connected")
            self.log.info(f"语音通话线程启动: 目标={self.target_user}")
            
            # 初始化音频设备
            try:
                # 开启录音流
                self.input_stream = self.pa.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK
                )
                
                # 开启播放流
                self.output_stream = self.pa.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    output=True,
                    frames_per_buffer=self.CHUNK
                )
                
                self.log.info("音频设备初始化成功")
            except Exception as e:
                self.log.error(f"初始化音频设备失败: {e}")
                self.call_status.emit(f"error: 初始化音频设备失败: {e}")
                return
            
            # 音频采集和传输循环
            while self.running:
                # 从麦克风采集音频
                if not self.is_muted:
                    try:
                        audio_data = self.input_stream.read(self.CHUNK, exception_on_overflow=False)
                        
                        # 应用变声效果
                        if self.voice_type != "normal":
                            audio_data = self.apply_voice_effect(audio_data)
                        
                        # 发送到对方
                        from audio_utils import audio_to_base64, calculate_audio_level
                        audio_base64 = audio_to_base64(audio_data)
                        
                        # 调试音频音量
                        level = calculate_audio_level(audio_data, 2)
                        self.log.info(f"本地音频音量: {level}%")
                        
                        # 发送音频数据信号，更新本地音量显示
                        self.audio_ready.emit(audio_data)
                        
                        send_data(self.sock, {
                            "action": "voice_frame",
                            "to_user": self.target_user,
                            "audio": audio_base64,
                            "timestamp": time.time()
                        })
                        
                    except Exception as e:
                        self.log.error(f"音频采集或发送错误: {e}")
                
                # 控制发送频率
                time.sleep(0.01)
                
        except Exception as e:
            self.log.error(f"语音通话线程异常: {e}")
            import traceback
            traceback.print_exc()
            self.call_status.emit(f"error: {str(e)}")
        finally:
            # 关闭资源
            try:
                if hasattr(self, 'input_stream'):
                    self.input_stream.stop_stream()
                    self.input_stream.close()
                if hasattr(self, 'output_stream'):
                    self.output_stream.stop_stream()
                    self.output_stream.close()
                if hasattr(self, 'pa'):
                    self.pa.terminate()
                self.log.info("音频资源已释放")
            except Exception as e:
                self.log.error(f"关闭音频设备时出错: {e}")
            
            self.call_status.emit("disconnected")
    
    def apply_voice_effect(self, audio_data):
        """应用变声效果"""
        try:
            # 记录当前使用的变声效果
            self.log.info(f"应用变声效果: {self.voice_type}")
            
            # 使用音频工具模块处理
            from audio_utils import apply_voice_effect
            processed_audio = apply_voice_effect(audio_data, self.voice_type, 2)
            
            # 记录处理前后的音频数据大小
            original_size = len(audio_data) if audio_data else 0
            processed_size = len(processed_audio) if processed_audio else 0
            self.log.debug(f"变声处理前后音频大小: {original_size} -> {processed_size} 字节")
            
            return processed_audio
            
        except Exception as e:
            self.log.error(f"应用变声效果时出错: {e}")
            import traceback
            traceback.print_exc()
            return audio_data  # 出错时返回原始音频
    
    def process_remote_audio(self, audio_data):
        """处理接收到的远程音频数据"""
        try:
            if not audio_data:
                self.log.warning("收到空的远程音频数据")
                return
                
            self.log.info(f"接收到远程音频数据，大小: {len(audio_data)} 字节")
                
            if hasattr(self, 'output_stream') and self.output_stream:
                # 检查输出流状态
                if not self.output_stream.is_active():
                    self.log.warning("输出音频流未激活，尝试重新初始化")
                    try:
                        self.output_stream.start_stream()
                    except Exception as e:
                        self.log.error(f"重新启动音频流失败: {e}")
                
                # 调试远程音频
                from audio_utils import calculate_audio_level
                level = calculate_audio_level(audio_data, 2)
                self.log.info(f"远程音频音量: {level}%")
                
                # 直接播放收到的音频
                self.output_stream.write(audio_data)
                self.log.debug("音频数据已写入输出流")
                
                # 发送信号更新远程音量显示
                self.remote_audio_ready.emit(audio_data)
            else:
                self.log.error("没有有效的输出音频流，无法播放远程音频")
        except Exception as e:
            self.log.error(f"处理远程音频数据时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """停止语音线程"""
        self.log.info("正在停止语音通话线程...")
        self.running = False

# 创建视频通话线程类
class VideoCallThread(QThread):
    # 发送视频帧信号
    frame_ready = pyqtSignal(QImage)
    # 通话状态信号
    call_status = pyqtSignal(str)
    # 远程视频帧信号
    remote_frame_ready = pyqtSignal(QImage)
    
    def __init__(self, target_user, sock, resolution="medium", effect="none"):
        super().__init__()
        self.target_user = target_user
        self.sock = sock  # 用于发送视频帧数据
        self.resolution = resolution
        self.effect = effect
        self.quality = 50  # JPEG压缩质量 (10-100)
        self.running = False
        self.camera_enabled = True
        self.is_muted = False  # 视频通话也可能包含音频
        
        # 设置日志记录
        self.log = logging.getLogger(f"VideoCall-{target_user}")
        
        # 导入cv2和视频处理函数
        import cv2
        from video_utils import (
            cv_to_qimage, adjust_video_resolution, 
            apply_video_effect, frame_to_base64
        )
        self.cv2 = cv2
        self.cv_to_qimage = cv_to_qimage
        self.adjust_video_resolution = adjust_video_resolution
        self.apply_video_effect = apply_video_effect
        self.frame_to_base64 = frame_to_base64
        
    def run(self):
        try:
            self.running = True
            self.call_status.emit("connected")
            
            # 初始化摄像头
            cap = None
            has_camera = False
            
            try:
                # 尝试不同的摄像头索引和API后端
                backends = [self.cv2.CAP_ANY, self.cv2.CAP_DSHOW]
                camera_indices = [0, 1]  # 尝试主摄像头和可能的第二个摄像头
                
                for backend in backends:
                    for idx in camera_indices:
                        try:
                            self.call_status.emit(f"正在尝试初始化摄像头 (索引: {idx}, 后端: {backend})")
                            cap = self.cv2.VideoCapture(idx, backend)
                            if cap.isOpened():
                                has_camera = True
                                self.call_status.emit("摄像头初始化成功")
                                break
                        except Exception:
                            continue
                    if has_camera:
                        break
                        
                if not has_camera:
                    self.call_status.emit("warning: 未能找到可用的摄像头")
            except Exception as e:
                self.call_status.emit(f"warning: 摄像头初始化失败: {str(e)}")
                has_camera = False
            
            # 如果没有摄像头，创建一个黑色背景
            black_frame = None
            if not has_camera:
                black_frame = self.cv2.imread('black.jpg') if self.cv2.os.path.exists('black.jpg') else None
                if black_frame is None:
                    # 创建黑色背景
                    import numpy as np
                    black_frame = np.zeros((480, 640, 3), np.uint8)
                    # 添加文本
                    font = self.cv2.FONT_HERSHEY_SIMPLEX
                    self.cv2.putText(black_frame, '未检测到摄像头', (150, 240), font, 1, (255, 255, 255), 2)
            
            # 计算每帧处理时间
            frame_interval = 1.0 / 15  # 15 FPS
            
            while self.running:
                start_time = time.time()
                
                # 判断是否启用了摄像头
                if has_camera and self.camera_enabled:
                    # 从摄像头采集视频帧
                    ret, frame = cap.read()
                    
                    if not ret:
                        # 如果读取失败，尝试使用黑色背景
                        if black_frame is not None:
                            frame = black_frame.copy()
                        else:
                            continue
                else:
                    # 使用黑色背景
                    if black_frame is not None:
                        frame = black_frame.copy()
                    else:
                        # 创建黑色背景
                        import numpy as np
                        frame = np.zeros((480, 640, 3), np.uint8)
                        # 添加文本
                        font = self.cv2.FONT_HERSHEY_SIMPLEX
                        self.cv2.putText(frame, '摄像头已关闭', (150, 240), font, 1, (255, 255, 255), 2)
                
                # 应用特效
                if self.effect != "none":
                    frame = self.apply_video_effect(frame, self.effect)
                
                # 调整分辨率
                frame = self.adjust_video_resolution(frame, self.resolution)
                
                # 转换为QImage显示在界面上
                qimage = self.cv_to_qimage(frame)
                self.frame_ready.emit(qimage)
                
                # 压缩并发送到远端
                if has_camera and self.camera_enabled:
                    try:
                        # 将帧转为base64编码
                        frame_base64 = self.frame_to_base64(frame, self.quality)
                        
                        # 记录发送信息
                        print(f"正在发送视频帧到 {self.target_user}, 大小: {len(frame_base64)}")
                        
                        # 发送到服务器
                        send_data(self.sock, {
                            "action": "video_frame",
                            "to_user": self.target_user,
                            "frame": frame_base64,
                            "timestamp": time.time()
                        })
                        
                        # 发送成功记录
                        print(f"视频帧发送成功")
                    except Exception as e:
                        print(f"发送视频帧失败: {e}")
                        traceback.print_exc()
                
                # 控制帧率
                elapsed = time.time() - start_time
                sleep_time = max(0, frame_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
        except Exception as e:
            traceback.print_exc()
            self.call_status.emit(f"error: {str(e)}")
        finally:
            # 释放摄像头
            try:
                if cap is not None:
                    cap.release()
                    self.log.info("摄像头资源已释放")
            except Exception as e:
                self.log.error(f"释放摄像头资源失败: {str(e)}")
            
            self.call_status.emit("disconnected")
            
    def stop(self):
        self.running = False
        
    def process_remote_frame(self, frame_data):
        """处理从远端收到的视频帧"""
        try:
            print(f"开始处理远程视频帧，数据大小: {len(frame_data)}")
            from video_utils import base64_to_frame, cv_to_qimage
            
            # 将Base64转为OpenCV图像
            frame = base64_to_frame(frame_data)
            print(f"Base64解码成功，图像尺寸: {frame.shape if frame is not None else 'None'}")
            
            if frame is None:
                print("警告：解码后的帧为None")
                return
                
            # 转为QImage
            qimage = cv_to_qimage(frame)
            print(f"转换为QImage成功，尺寸: {qimage.width()}x{qimage.height()}")
            
            # 发出信号更新远端视频
            self.remote_frame_ready.emit(qimage)
            print("已发出远程帧更新信号")
        except Exception as e:
            print(f"处理远程视频帧错误: {e}")
            import traceback
            traceback.print_exc()

# 简单的Markdown转HTML函数
def markdown_to_html(md_text):
    """简单的Markdown转HTML转换"""
    import re
    
    # 转义HTML特殊字符，但保留Markdown语法所需的字符
    html_text = md_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 处理标题 (## Heading -> <h2>Heading</h2>)
    html_text = re.sub(r'^#\s+(.+?)$', r'<h1>\1</h1>', html_text, flags=re.MULTILINE)
    html_text = re.sub(r'^##\s+(.+?)$', r'<h2>\1</h2>', html_text, flags=re.MULTILINE)
    html_text = re.sub(r'^###\s+(.+?)$', r'<h3>\1</h3>', html_text, flags=re.MULTILINE)
    
    # 处理粗体 (**text** -> <strong>text</strong>)
    html_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_text)
    
    # 处理斜体 (*text* -> <em>text</em>)
    html_text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html_text)
    
    # 处理代码块 (```code``` -> <pre><code>code</code></pre>)
    html_text = re.sub(r'```(.+?)```', r'<pre><code>\1</code></pre>', html_text, flags=re.DOTALL)
    
    # 处理行内代码 (`code` -> <code>code</code>)
    html_text = re.sub(r'`(.+?)`', r'<code>\1</code>', html_text)
    
    # 处理列表项 (- item -> <li>item</li>, 但不添加<ul>标签以简化)
    html_text = re.sub(r'^\s*-\s+(.+?)$', r'• \1<br>', html_text, flags=re.MULTILINE)
    
    # 处理有序列表项
    html_text = re.sub(r'^\s*(\d+)\.\s+(.+?)$', r'\1. \2<br>', html_text, flags=re.MULTILINE)
    
    # 处理链接 ([text](url) -> <a href="url">text</a>)
    html_text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html_text)
    
    # 将换行转换为<br>标签
    html_text = html_text.replace('\n', '<br>')
    
    return html_text

# 主窗口
class MainWindow(QMainWindow):
    def __init__(self, username, sock):
        super().__init__()
        self.username = username
        self.sock = sock
        self.setWindowTitle(f"聊天软件 - {username}")
        self.resize(1000, 680)
        
        # 初始化数据
        self.init_data()
        
        # 创建UI组件
        self.setup_ui()
        
        # 启动接收线程
        self.init_receiver()
        
        # 加载聊天历史
        self.load_chat_history()
    
    def init_data(self):
        """初始化数据存储"""
        # 会话历史
        self.convs = {}  # target -> [html内容]
        
        # 好友列表
        self.friends = []
        
        # 群聊列表
        self.groups = []
        
        # 好友请求
        self.friend_requests = []
        
        # 被删除好友列表 - 记录哪些用户已将我删除
        self.deleted_by_friends = set()
        
        # 通话线程
        self.voice_call_thread = None
        self.video_call_thread = None
        
        # 当前聊天目标
        self.current_chat_target = None
        self.is_group_chat = False
        
        # 匿名名称
        self.anonymous_name = generate_anonymous_name()
        self.is_anonymous_mode = False
        
        # 创建下载目录
        self.downloads_dir = Path(__file__).with_name("downloads")
        self.downloads_dir.mkdir(exist_ok=True)
    
    def setup_ui(self):
        """设置UI界面"""
        # 创建菜单栏
        self.create_menu_bar()
        
        # 主分割器
        main_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧面板 (联系人列表)
        self.contact_widget = self.create_contact_panel()
        main_splitter.addWidget(self.contact_widget)
        
        # 右侧面板 (聊天界面)
        self.chat_widget = self.create_chat_panel()
        main_splitter.addWidget(self.chat_widget)
        
        # 设置分割比例
        main_splitter.setSizes([300, 700])
        
        # 将分割器设为中央组件
        self.setCentralWidget(main_splitter)
    
    def create_menu_bar(self):
        """创建菜单栏"""
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        
        # 账号菜单
        account_menu = menu_bar.addMenu("账号")
        
        # 修改密码
        change_password_action = QAction("修改密码", self)
        change_password_action.triggered.connect(self.change_password)
        account_menu.addAction(change_password_action)
        
        account_menu.addSeparator()
        
        # 注销账号
        delete_account_action = QAction("注销账号", self)
        delete_account_action.triggered.connect(self.delete_account)
        account_menu.addAction(delete_account_action)
        
        # 退出
        logout_action = QAction("退出", self)
        logout_action.triggered.connect(self.logout)
        account_menu.addAction(logout_action)
        
        # 好友菜单
        friend_menu = menu_bar.addMenu("好友")
        
        # 添加好友
        add_friend_action = QAction("添加好友", self)
        add_friend_action.triggered.connect(self.add_friend)
        friend_menu.addAction(add_friend_action)
        
        # 好友请求
        view_requests_action = QAction("查看好友请求", self)
        view_requests_action.triggered.connect(self.view_friend_requests)
        friend_menu.addAction(view_requests_action)
        
        # 群聊菜单
        group_menu = menu_bar.addMenu("群聊")
        
        # 创建群聊
        create_group_action = QAction("创建群聊", self)
        create_group_action.triggered.connect(self.create_group)
        group_menu.addAction(create_group_action)
        
        # 加入群聊
        join_group_action = QAction("加入群聊", self)
        join_group_action.triggered.connect(self.join_group)
        group_menu.addAction(join_group_action)
        
        # 群聊管理
        group_menu.addSeparator()
        manage_group_action = QAction("群聊管理", self)
        manage_group_action.triggered.connect(self.manage_group)
        group_menu.addAction(manage_group_action)
    
    def create_contact_panel(self):
        """创建联系人面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 联系人面板使用选项卡组织
        tab_widget = QTabWidget()
        
        # 好友列表
        self.friend_list = QListWidget()
        self.friend_list.itemDoubleClicked.connect(self.open_friend_chat)
        self.friend_list.setContextMenuPolicy(Qt.CustomContextMenu)  # 允许右键菜单
        self.friend_list.customContextMenuRequested.connect(self.show_friend_context_menu)  # 连接右键菜单信号
        tab_widget.addTab(self.friend_list, "好友")
        
        # 群聊列表
        self.group_list = QListWidget()
        self.group_list.itemDoubleClicked.connect(self.open_group_chat)
        tab_widget.addTab(self.group_list, "群聊")
        
        layout.addWidget(tab_widget)
        
        return widget
    
    def create_chat_panel(self):
        """创建聊天面板"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 聊天窗口顶部信息
        self.chat_title = QLabel("当前未选择聊天")
        self.chat_title.setAlignment(Qt.AlignCenter)
        self.chat_title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(self.chat_title)
        
        # 聊天记录显示
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenLinks(False)  # 与ui_chat.py保持一致
        self.chat_view.anchorClicked.connect(QDesktopServices.openUrl)  # 直接使用QDesktopServices处理链接
        self.chat_view.setFont(QFont("微软雅黑", 10))
        layout.addWidget(self.chat_view)
        
        # 匿名模式切换
        anonymous_layout = QHBoxLayout()
        self.anonymous_checkbox = QCheckBox("匿名模式")
        self.anonymous_checkbox.stateChanged.connect(self.toggle_anonymous_mode)
        self.anonymous_name_edit = QLineEdit(self.anonymous_name)
        self.anonymous_name_edit.setPlaceholderText("匿名昵称")
        self.anonymous_name_edit.setEnabled(False)
        anonymous_layout.addWidget(self.anonymous_checkbox)
        anonymous_layout.addWidget(self.anonymous_name_edit)
        anonymous_layout.addStretch()
        layout.addLayout(anonymous_layout)
        
        # 输入区域
        input_layout = QHBoxLayout()
        
        # 表情按钮
        self.emoji_btn = QToolButton()
        self.emoji_btn.setText("😀")
        self.emoji_btn.setToolTip("表情")
        self.emoji_btn.clicked.connect(self.show_emoji_panel)
        input_layout.addWidget(self.emoji_btn)
        
        # 文件按钮
        self.file_btn = QToolButton()
        self.file_btn.setText("📎")
        self.file_btn.setToolTip("发送文件")
        self.file_btn.clicked.connect(self.send_file)
        input_layout.addWidget(self.file_btn)
        
        # 语音消息按钮
        self.voice_msg_btn = QToolButton()
        self.voice_msg_btn.setText("🎤")
        self.voice_msg_btn.setToolTip("发送语音消息")
        self.voice_msg_btn.clicked.connect(self.send_voice_message)
        input_layout.addWidget(self.voice_msg_btn)
        
        # 语音通话按钮
        self.voice_call_btn = QToolButton()
        self.voice_call_btn.setText("📞")
        self.voice_call_btn.setToolTip("语音通话")
        self.voice_call_btn.clicked.connect(self.start_voice_call)
        input_layout.addWidget(self.voice_call_btn)
        
        # 视频通话按钮
        self.video_call_btn = QToolButton()
        self.video_call_btn.setText("📹")
        self.video_call_btn.setToolTip("视频通话")
        self.video_call_btn.clicked.connect(self.start_video_call)
        input_layout.addWidget(self.video_call_btn)
        
        layout.addLayout(input_layout)
        
        # 消息输入框
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入消息...")
        self.input_edit.returnPressed.connect(self.send_message)
        layout.addWidget(self.input_edit)
        
        # 发送按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.clear_btn = QPushButton("清空")
        self.clear_btn.clicked.connect(self.clear_current_chat)
        button_layout.addWidget(self.clear_btn)
        
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_message)
        button_layout.addWidget(self.send_btn)
        
        layout.addLayout(button_layout)
        
        return widget 
    
    def init_receiver(self):
        """初始化消息接收线程"""
        self.receiver = ReceiverThread(self.sock)
        self.receiver.incoming.connect(self.handle_incoming_message)
        self.receiver.start()
    
    def load_chat_history(self):
        """加载聊天历史"""
        # 添加一个欢迎消息
        welcome_msg = f'<div style="text-align:center;margin:20px;"><h3>欢迎，{self.username}！</h3><p>选择一个联系人或群聊开始聊天</p></div>'
        self.chat_view.setHtml(welcome_msg)
    
    # ====================== 界面交互功能 ======================
    def open_friend_chat(self, item):
        """打开与好友的聊天"""
        friend = item.text()
        self.current_chat_target = friend
        self.is_group_chat = False
        self.chat_title.setText(f"与 {friend} 的聊天")
        
        # 启用/禁用相关按钮
        self.voice_call_btn.setEnabled(True)
        self.video_call_btn.setEnabled(True)
        self.file_btn.setEnabled(True)
        self.voice_msg_btn.setEnabled(True)
        
        # 请求聊天历史
        send_data(self.sock, {
            "action": "get_history",
            "target": friend,
            "is_group": False
        })
        
        # 初始化会话历史（如果不存在）
        if friend not in self.convs:
            self.convs[friend] = []
            self.refresh_chat_view()
    
    def open_group_chat(self, item):
        """打开群聊"""
        group_id = item.data(Qt.UserRole)
        group_name = item.text().split(" (")[0]  # 去掉角色后缀
        
        self.current_chat_target = group_id
        self.is_group_chat = True
        self.chat_title.setText(f"群聊: {group_name}")
        
        # 启用/禁用相关按钮
        self.voice_call_btn.setEnabled(False)  # 群聊不支持通话
        self.video_call_btn.setEnabled(False)  # 群聊不支持通话
        self.file_btn.setEnabled(True)         # 群聊支持文件
        self.voice_msg_btn.setEnabled(True)    # 群聊支持语音消息
        
        # 请求聊天历史
        send_data(self.sock, {
            "action": "get_history",
            "target": group_id,
            "is_group": True
        })
        
        # 初始化会话历史（如果不存在）
        if group_id not in self.convs:
            self.convs[group_id] = []
            self.refresh_chat_view()
    
    def send_message(self):
        """发送文本消息"""
        if not self.current_chat_target:
            QMessageBox.warning(self, "提示", "请先选择聊天对象")
            return
            
        # 检查是否被对方删除了好友
        if hasattr(self, 'deleted_by_friends') and self.current_chat_target in self.deleted_by_friends:
            QMessageBox.warning(self, "无法发送", "对方已将您从好友列表中删除，无法发送消息")
            return
            
        content = self.input_edit.text().strip()
        if not content:
            return
            
        # 构建消息数据 (普通聊天和群聊)
        msg_data = {
            "action": "chat",
            "to": self.current_chat_target,
            "is_group": self.is_group_chat,
            "type": "text",
            "content": content
        }
        
        # 处理匿名模式
        if self.is_anonymous_mode:
            msg_data["is_anonymous"] = True
            msg_data["anonymous_name"] = self.anonymous_name_edit.text() or self.anonymous_name
        
        # 发送消息
        send_data(self.sock, msg_data)
        
        # 在本地显示消息
        display_name = "我" if not self.is_anonymous_mode else f"我 (匿名: {msg_data.get('anonymous_name')})"
        
        html_content = f"{display_name}: {html.escape(content)}"
        self.append_message(self.current_chat_target, html_content)
        
        # 清空输入框
        self.input_edit.clear()
    
    def send_file(self):      
        """发送文件"""
        if not self.current_chat_target:
            QMessageBox.warning(self, "提示", "请先选择聊天对象")
            return
            
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if not file_path:
            return
            
        # 检查文件大小
        if os.path.getsize(file_path) > MAX_FILE_SIZE:
            QMessageBox.warning(self, "文件过大", f"文件大小不能超过 {MAX_FILE_SIZE/1024/1024:.1f} MB")
            return
            
        # 读取文件
        with open(file_path, "rb") as f:
            content = f.read()
            
        # Base64编码
        content_b64 = base64.b64encode(content).decode("utf-8")
        
        # 构建消息数据
        file_name = os.path.basename(file_path)
        msg_data = {
            "action": "file",
            "to": self.current_chat_target,
            "is_group": self.is_group_chat,
            "filename": file_name,
            "content": content_b64
        }
        
        # 处理匿名模式
        if self.is_anonymous_mode:
            msg_data["is_anonymous"] = True
            msg_data["anonymous_name"] = self.anonymous_name_edit.text() or self.anonymous_name
        
        # 发送消息
        send_data(self.sock, msg_data)
        
        # 在本地显示消息
        display_name = "我" if not self.is_anonymous_mode else f"我 (匿名: {msg_data.get('anonymous_name')})"
        
        # 保存到本地
        local_file = self.downloads_dir / file_name
        with open(local_file, "wb") as f:
            f.write(content)
            
        # 构建HTML并显示
        file_link = f'<a href="file:///{local_file}">{html.escape(file_name)}</a>'
        html_content = f"{display_name}: [文件] {file_link}"
        
        # 如果是图片，添加缩略图
        if self.is_image_file(file_name):
            thumb_html = f'<br><a href="file:///{local_file}"><img src="file:///{local_file}" width="200"></a>'
            html_content += thumb_html
            
        self.append_message(self.current_chat_target, html_content)
    
    def send_voice_message(self):
        """发送语音消息"""
        if not self.current_chat_target:
            QMessageBox.warning(self, "提示", "请先选择聊天对象")
            return
        # 检查是否被对方删除了好友
        if hasattr(self, 'deleted_by_friends') and self.current_chat_target in self.deleted_by_friends:
            QMessageBox.warning(self, "无法发送", "对方已将您从好友列表中删除，无法发送消息")
            return
            
        # 导入语音录制对话框
        from ui_voice_record import VoiceRecordDialog
        
        # 检查 PyAudio 是否可用
        if not VoiceRecordDialog.is_pyaudio_available():
            QMessageBox.warning(self, "录音功能不可用", 
                              "无法使用录音功能，请确保已安装 PyAudio 库。\n"
                              "可以使用命令安装：pip install pyaudio")
            return
            
        try:
            # 创建录音对话框
            dialog = VoiceRecordDialog(self)
            # 连接录制完成信号
            dialog.record_complete.connect(self.handle_voice_record_complete)
            
            # 显示对话框
            dialog.exec_()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"打开语音录制对话框时出错: {e}")
            QMessageBox.warning(self, "录制错误", f"无法打开语音录制: {e}\n请确保已安装PyAudio")
    
    def handle_voice_record_complete(self, file_path, duration, audio_data):
        """处理语音录制完成"""
        try:
            # 获取文件名
            file_name = os.path.basename(file_path)
            
            # 将音频数据转换为Base64
            import base64
            with open(file_path, "rb") as f:
                content = f.read()
            content_b64 = base64.b64encode(content).decode('utf-8')
            
            # 构建消息数据
            msg_data = {
                "action": "voice",
                "to": self.current_chat_target,
                "is_group": self.is_group_chat,
                "filename": file_name,
                "content": content_b64,
                "duration": duration  # 录音时长（秒）
            }
            
            # 处理匿名模式
            if self.is_anonymous_mode:
                msg_data["is_anonymous"] = True
                msg_data["anonymous_name"] = self.anonymous_name_edit.text() or self.anonymous_name
            
            # 发送消息
            send_data(self.sock, msg_data)
            
            # 在本地显示消息
            display_name = "我" if not self.is_anonymous_mode else f"我 (匿名: {msg_data.get('anonymous_name')})"
            
            # 保存到本地语音目录
            voice_dir = self.downloads_dir / "voice"
            voice_dir.mkdir(exist_ok=True)
            local_file = voice_dir / file_name
            with open(local_file, "wb") as f:
                f.write(content)
            
            # 构建HTML并显示
            file_uri = QUrl.fromLocalFile(str(local_file)).toString()
            voice_link = f'<a href="{file_uri}">[点击播放] {duration}秒</a>'
            html_content = f"{display_name}: [语音] {voice_link}"
            self.append_message(self.current_chat_target, html_content)
            
            print(f"语音消息已发送，时长: {duration}秒，文件: {file_name}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"处理录音完成时出错: {e}")
            QMessageBox.warning(self, "发送失败", f"无法发送语音消息: {e}")
    
    def start_voice_call(self):
        """发起语音通话"""
        if not self.current_chat_target or self.is_group_chat:
            QMessageBox.warning(self, "提示", "只能与好友进行语音通话")
            return
        
        # 设置当前通话类型
        self.current_call_type = "voice"
        
        # 发送通话请求
        send_data(self.sock, {
            "action": "call_request",
            "to_user": self.current_chat_target,
            "call_type": "voice"
        })
        
        QMessageBox.information(self, "语音通话", f"正在呼叫 {self.current_chat_target}...")
    
    def start_video_call(self):
        """发起视频通话"""
        if not self.current_chat_target or self.is_group_chat:
            QMessageBox.warning(self, "提示", "只能与好友进行视频通话")
            return
        
        # 设置当前通话类型
        self.current_call_type = "video"
        
        # 发送通话请求
        send_data(self.sock, {
            "action": "call_request",
            "to_user": self.current_chat_target,
            "call_type": "video"
        })
        
        QMessageBox.information(self, "视频通话", f"正在呼叫 {self.current_chat_target}...")
    
    def start_voice_call_session(self, target):
        """开始语音通话会话"""
        # 导入语音通话对话框
        from ui_voice_call import VoiceCallDialog
        
        try:
            # 创建并启动语音通话线程
            self.voice_call_thread = VoiceCallThread(target, self.sock)
            self.voice_call_thread.call_status.connect(self.handle_call_status)
            
            # 创建语音通话对话框
            self.voice_dialog = VoiceCallDialog(self, target)
            
            # 连接音频信号
            self.voice_call_thread.audio_ready.connect(self.voice_dialog.update_local_volume)
            self.voice_call_thread.remote_audio_ready.connect(self.voice_dialog.update_remote_volume)
            
            # 启动语音线程
            self.voice_call_thread.start()
            
            print(f"语音通话会话已启动，目标用户: {target}")
            
            # 显示语音对话框
            self.voice_dialog.exec_()
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"启动语音通话会话时出错: {e}")
            QMessageBox.warning(self, "语音通话错误", f"启动语音通话失败: {e}")
    
    def start_video_call_session(self, target):
        """开始视频通话会话"""
        # 导入视频通话对话框
        from ui_video_call import VideoCallDialog
        
        # 创建并启动视频通话线程
        self.video_call_thread = VideoCallThread(target, self.sock)
        self.video_call_thread.call_status.connect(self.handle_call_status)
        
        # 创建视频通话对话框
        self.video_dialog = VideoCallDialog(self, target)
        
        # 连接视频帧信号
        self.video_call_thread.frame_ready.connect(self.video_dialog.update_local_video)
        self.video_call_thread.remote_frame_ready.connect(self.video_dialog.update_remote_video)
        
        # 启动视频线程
        self.video_call_thread.start()
        
        # 显示视频对话框
        self.video_dialog.exec_()
        
    def end_video_call(self):
        """结束视频通话"""
        if hasattr(self, 'video_call_thread') and self.video_call_thread:
            # 停止视频线程
            self.video_call_thread.stop()
            self.video_call_thread.wait()  # 等待线程结束
            
            # 发送结束通话消息
            if self.current_chat_target:
                send_data(self.sock, {
                    "action": "end_call",
                    "to_user": self.current_chat_target
                })
                
            # 在聊天记录中添加通话时长信息
            if hasattr(self, 'video_dialog') and self.current_chat_target:
                duration = self.video_dialog.call_duration
                minutes = duration // 60
                seconds = duration % 60
                call_info = f"视频通话已结束，通话时长 {minutes:02d}:{seconds:02d}"
                html_content = f"<div style='text-align:center;color:#888;'>{call_info}</div>"
                self.append_message(self.current_chat_target, html_content)
                
    def end_voice_call(self):
        """结束语音通话"""
        if hasattr(self, 'voice_call_thread') and self.voice_call_thread:
            # 停止语音线程
            self.voice_call_thread.stop()
            self.voice_call_thread.wait()  # 等待线程结束
            
            # 发送结束通话消息
            if self.current_chat_target:
                send_data(self.sock, {
                    "action": "end_call",
                    "to_user": self.current_chat_target
                })
                
            # 在聊天记录中添加通话时长信息
            if hasattr(self, 'voice_dialog') and self.current_chat_target:
                duration = self.voice_dialog.call_duration
                minutes = duration // 60
                seconds = duration % 60
                call_info = f"语音通话已结束，通话时长 {minutes:02d}:{seconds:02d}"
                html_content = f"<div style='text-align:center;color:#888;'>{call_info}</div>"
                self.append_message(self.current_chat_target, html_content)
    
    def handle_call_status(self, status):
        """处理通话状态更新"""
        if status == "disconnected":
            QMessageBox.information(self, "通话结束", "通话已结束")
        elif status.startswith("error"):
            QMessageBox.warning(self, "通话错误", f"通话发生错误: {status}")
    
    def toggle_anonymous_mode(self, state):
        """切换匿名模式"""
        self.is_anonymous_mode = (state == Qt.Checked)
        self.anonymous_name_edit.setEnabled(self.is_anonymous_mode)
        
        # 更新界面提示
        if self.is_anonymous_mode:
            # 确保 self.anonymous_name_edit.text() 或 self.anonymous_name 有一个有效值
            anon_name_text = self.anonymous_name_edit.text()
            current_anon_name = anon_name_text if anon_name_text else self.anonymous_name
            if not current_anon_name: # 如果两者都为空，生成一个新的
                current_anon_name = generate_anonymous_name()
                self.anonymous_name = current_anon_name # 保存到实例变量
            
            self.input_edit.setPlaceholderText(f"匿名模式已开启 ({current_anon_name})")
            self.anonymous_name_edit.setText(current_anon_name)
            self.anonymous_name_edit.setDisabled(True) # 匿名模式开启时不允许修改匿名
            send_data(self.sock, {"action": "set_anonymous_name", "anonymous_name": current_anon_name})
        else:
            self.input_edit.setPlaceholderText("输入消息...")
            self.anonymous_name_edit.setDisabled(False)
            send_data(self.sock, {"action": "set_anonymous_name", "anonymous_name": None}) # 可选：通知服务器退出匿名
        logger.info(f"匿名模式切换到: {self.is_anonymous_mode}")
    
    def show_emoji_panel(self):
        """显示表情选择面板"""
        # 创建表情菜单
        emoji_menu = QMenu(self)
        
        # 常用表情列表
        emojis = [
            "😀", "😁", "😂", "🤣", "😃", "😄", "😅", "😆", 
            "😉", "😊", "😋", "😎", "😍", "😘", "😗", "😙",
            "🙂", "🤔", "😐", "😑", "😶", "🙄", "😏", "😣",
            "😥", "😮", "🤐", "😯", "😪", "😫", "😴", "😌",
            "🤓", "😛", "😜", "😝", "🤤", "😒", "😓", "😔",
            "😕", "🙃", "🤑", "😲", "☹️", "🙁", "😖", "😞",
            "😟", "😤", "😢", "😭", "😦", "😧", "😨", "😩",
            "😬", "😰", "😱", "😳", "🤪", "😵", "😡", "😠"
        ]
        
        # 创建表情网格
        emoji_widget = QWidget()
        grid_layout = QGridLayout(emoji_widget)
        grid_layout.setSpacing(5)
        
        row, col = 0, 0
        for emoji in emojis:
            btn = QPushButton(emoji)
            btn.setFixedSize(QSize(30, 30))
            btn.clicked.connect(lambda _, e=emoji: self.insert_emoji(e))
            grid_layout.addWidget(btn, row, col)
            
            col += 1
            if col > 7:  # 8列表情
                col = 0
                row += 1
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidget(emoji_widget)
        scroll.setWidgetResizable(True)
        scroll.setFixedSize(270, 200)
        
        # 创建控件动作
        widget_action = QWidgetAction(emoji_menu)
        widget_action.setDefaultWidget(scroll)
        emoji_menu.addAction(widget_action)
        
        # 显示菜单
        emoji_menu.exec_(self.emoji_btn.mapToGlobal(QPoint(0, -200)))
    
    def insert_emoji(self, emoji):
        """在输入框插入表情"""
        current_text = self.input_edit.text()
        cursor_pos = self.input_edit.cursorPosition()
        new_text = current_text[:cursor_pos] + emoji + current_text[cursor_pos:]
        self.input_edit.setText(new_text)
        self.input_edit.setCursorPosition(cursor_pos + len(emoji))
    
    def clear_current_chat(self):
        """清空当前聊天记录"""
        if not self.current_chat_target:
            return
            
        reply = QMessageBox.question(
            self, "确认清空", "确定要清空当前聊天记录吗？\n(仅清空本地显示，不影响服务器存储)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.convs[self.current_chat_target] = []
            self.refresh_chat_view()
    
    # ====================== 用户和好友管理 ======================
    def change_password(self):
        """修改密码"""
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("修改密码")
        dialog.setFixedWidth(300)
        
        # 创建表单
        layout = QFormLayout(dialog)
        
        old_pass = QLineEdit()
        old_pass.setEchoMode(QLineEdit.Password)
        new_pass = QLineEdit()
        new_pass.setEchoMode(QLineEdit.Password)
        confirm_pass = QLineEdit()
        confirm_pass.setEchoMode(QLineEdit.Password)
        
        layout.addRow("原密码:", old_pass)
        layout.addRow("新密码:", new_pass)
        layout.addRow("确认密码:", confirm_pass)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addRow("", btn_layout)
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            # 验证输入
            if not old_pass.text():
                QMessageBox.warning(self, "错误", "请输入原密码")
                return
                
            if not new_pass.text():
                QMessageBox.warning(self, "错误", "请输入新密码")
                return
                
            if new_pass.text() != confirm_pass.text():
                QMessageBox.warning(self, "错误", "两次密码输入不一致")
                return
                
            # 发送修改密码请求
            send_data(self.sock, {
                "action": "change_password",
                "old_password": old_pass.text(),
                "new_password": new_pass.text()
            })
    
    def delete_account(self):
        """注销账号"""
        reply = QMessageBox.question(
            self, "确认注销", "确定要注销您的账号吗？\n此操作将删除您的所有数据且不可恢复！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            password, ok = QInputDialog.getText(
                self, "验证身份", "请输入您的密码以确认注销账号:",
                QLineEdit.Password, ""
            )
            
            if ok and password:
                # 发送注销账号请求
                send_data(self.sock, {
                    "action": "delete_account",
                    "password": password
                })
    
    def add_friend(self):
        """添加好友"""
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("添加好友")
        dialog.setFixedWidth(300)
        
        # 创建表单
        layout = QVBoxLayout(dialog)
        
        # 用户名输入
        form_layout = QFormLayout()
        username_edit = QLineEdit()
        form_layout.addRow("好友用户名:", username_edit)
        
        # 附加消息
        message_edit = QTextEdit()
        message_edit.setPlaceholderText("附加消息（可选）")
        message_edit.setFixedHeight(80)
        
        layout.addLayout(form_layout)
        layout.addWidget(QLabel("附加消息:"))
        layout.addWidget(message_edit)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("发送请求")
        btn_cancel = QPushButton("取消")
        
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            username = username_edit.text().strip()
            message = message_edit.toPlainText()
            
            if not username:
                QMessageBox.warning(self, "错误", "请输入用户名")
                return
                
            # 不能添加自己
            if username == self.username:
                QMessageBox.warning(self, "错误", "不能添加自己为好友")
                return
                
            # 发送好友请求
            try:
                send_data(self.sock, {
                    "action": "send_friend_request",
                    "to_user": username,
                    "message": message
                })
                QMessageBox.information(self, "发送请求", "好友请求已发送，等待对方确认")
            except Exception as e:
                QMessageBox.critical(self, "发送失败", f"发送好友请求失败: {str(e)}")
    
    def view_friend_requests(self):
        """查看好友请求"""
        if not self.friend_requests:
            QMessageBox.information(self, "好友请求", "当前没有新的好友请求")
            return
            
        print(f"打开好友请求列表，有 {len(self.friend_requests)} 个请求")
        
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("好友请求")
        dialog.resize(400, 300)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        
        # 创建请求列表
        request_list = QListWidget()
        layout.addWidget(QLabel("请求列表:"))
        layout.addWidget(request_list)
        
        # 请求详情区域
        details_group = QGroupBox("请求详情")
        details_layout = QFormLayout(details_group)
        from_label = QLabel()
        time_label = QLabel()
        message_label = QLabel()
        message_label.setWordWrap(True)
        
        details_layout.addRow("发送者:", from_label)
        details_layout.addRow("时间:", time_label)
        details_layout.addRow("消息:", message_label)
        
        layout.addWidget(details_group)
        
        # 存储当前选中的请求
        current_request = None
        
        # 填充请求列表
        for req in self.friend_requests:
            req_id = req.get("id")
            from_user = req.get("from_user", "")
            request_time = req.get("request_time", "")
            
            item_text = f"{from_user} - {request_time}"
            item = QListWidgetItem(item_text)
            # 存储整个请求对象作为数据
            item.setData(Qt.UserRole, req)
            request_list.addItem(item)
            
            print(f"添加请求项: id={req_id}, from={from_user}")
        
        # 选择变化处理
        def on_selection_changed():
            nonlocal current_request
            if not request_list.selectedItems():
                current_request = None
                from_label.setText("")
                time_label.setText("")
                message_label.setText("")
                return
            
            item = request_list.selectedItems()[0]
            req = item.data(Qt.UserRole)
            if not req:
                current_request = None
                return
            
            current_request = req
            from_label.setText(req.get("from_user", ""))
            time_label.setText(req.get("request_time", ""))
            message_label.setText(req.get("message", ""))
            
            print(f"选中请求: id={req.get('id')}, from={req.get('from_user')}")
        
        request_list.itemSelectionChanged.connect(on_selection_changed)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        accept_btn = QPushButton("接受")
        reject_btn = QPushButton("拒绝")
        close_btn = QPushButton("关闭")
        
        btn_layout.addWidget(accept_btn)
        btn_layout.addWidget(reject_btn)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        # 接受请求
        def accept_request():
            nonlocal current_request
            if not current_request:
                QMessageBox.warning(dialog, "提示", "请先选择一个请求")
                return
            
            req_id = current_request.get("id")
            from_user = current_request.get("from_user")
            
            if not from_user:
                QMessageBox.warning(dialog, "错误", "请求信息不完整，无法处理")
                return
            
            print(f"接受好友请求: id={req_id}, from_user={from_user}")
            
            # 发送请求到服务器
            send_data(self.sock, {
                "action": "handle_friend_request",
                "request_id": req_id,  # 即使id为None也发送
                "from_user": from_user,
                "accepted": True
            })
            
            # 从请求列表中移除
            for i in range(request_list.count()):
                item = request_list.item(i)
                req = item.data(Qt.UserRole)
                if req and req.get("from_user") == from_user:
                    request_list.takeItem(i)
                    break
            
            # 从好友请求数据中移除
            self.friend_requests = [req for req in self.friend_requests if req.get("from_user") != from_user]
            
            print(f"本地请求列表已更新，当前还剩 {len(self.friend_requests)} 个请求")
            
            # 主动添加到好友列表
            if from_user not in self.friends:
                self.friends.append(from_user)
                self.friend_list.clear()
                for friend in self.friends:
                    item = QListWidgetItem(friend)
                    self.friend_list.addItem(item)
                print(f"主动添加 {from_user} 到好友列表，现有好友: {self.friends}")
            
            QMessageBox.information(dialog, "已接受", f"已接受 {from_user} 的好友请求")
            
            # 如果列表为空，关闭对话框
            if request_list.count() == 0:
                dialog.accept()
            
            # 清除当前选中
            current_request = None
        
        # 拒绝请求
        def reject_request():
            nonlocal current_request
            if not current_request:
                QMessageBox.warning(dialog, "提示", "请先选择一个请求")
                return
            
            req_id = current_request.get("id")
            from_user = current_request.get("from_user")
            
            if not from_user:
                QMessageBox.warning(dialog, "错误", "请求信息不完整，无法处理")
                return
            
            print(f"拒绝好友请求: id={req_id}, from_user={from_user}")
            
            # 发送请求到服务器
            send_data(self.sock, {
                "action": "handle_friend_request",
                "request_id": req_id,  # 即使id为None也发送
                "from_user": from_user,
                "accepted": False
            })
            
            # 从请求列表中移除
            for i in range(request_list.count()):
                item = request_list.item(i)
                req = item.data(Qt.UserRole)
                if req and req.get("from_user") == from_user:
                    request_list.takeItem(i)
                    break
            
            # 从好友请求数据中移除
            self.friend_requests = [req for req in self.friend_requests if req.get("from_user") != from_user]
            
            print(f"本地请求列表已更新，当前还剩 {len(self.friend_requests)} 个请求")
            
            QMessageBox.information(dialog, "已拒绝", f"已拒绝 {from_user} 的好友请求")
            
            # 如果列表为空，关闭对话框
            if request_list.count() == 0:
                dialog.accept()
            
            # 清除当前选中
            current_request = None
        
        # 连接按钮信号
        accept_btn.clicked.connect(accept_request)
        reject_btn.clicked.connect(reject_request)
        close_btn.clicked.connect(dialog.reject)
        
        # 如果有项目，默认选中第一个
        if request_list.count() > 0:
            request_list.setCurrentRow(0)
        
        # 显示对话框
        dialog.exec_()
    
    # ====================== 群聊管理 ======================
    def create_group(self):
        """创建群聊"""
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("创建群聊")
        dialog.setFixedWidth(300)
        
        # 创建表单
        layout = QVBoxLayout(dialog)
        
        # 群聊信息
        form_layout = QFormLayout()
        group_id_edit = QLineEdit()
        group_id_edit.setPlaceholderText("如留空将自动生成")
        group_name_edit = QLineEdit()
        
        form_layout.addRow("群号:", group_id_edit)
        form_layout.addRow("群名称:", group_name_edit)
        layout.addLayout(form_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_create = QPushButton("创建")
        btn_cancel = QPushButton("取消")
        
        btn_create.clicked.connect(dialog.accept)
        btn_cancel.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            group_name = group_name_edit.text().strip()
            group_id = group_id_edit.text().strip()
            
            if not group_name:
                QMessageBox.warning(self, "错误", "请输入群名称")
                return
                
            # 如果群号为空，服务器会自动生成
            if not group_id:
                try:
                    from utils import generate_group_id
                    group_id = generate_group_id()
                except Exception:
                    import random
                    group_id = f"G-{random.randint(10000, 99999)}"
                
            # 准备创建群聊数据
            create_data = {
                "action": "create_group",
                "group_id": group_id,
                "group_name": group_name
            }
                
            # 发送创建群聊请求
            try:
                send_data(self.sock, create_data)
                
                # 显示提示信息
                QMessageBox.information(self, "创建群聊", f"群聊创建请求已发送\n群号: {group_id}")
            except Exception as e:
                QMessageBox.critical(self, "创建失败", f"创建群聊失败: {str(e)}")
    
    def join_group(self):
        """加入群聊"""
        group_id, ok = QInputDialog.getText(
            self, "加入群聊", "请输入群号:", 
            QLineEdit.Normal, ""
        )
        
        if ok and group_id.strip():
            # 发送加入群聊请求
            try:
                send_data(self.sock, {
                    "action": "join_group",
                    "group_id": group_id.strip()
                })
                QMessageBox.information(self, "加入群聊", f"已发送加入群聊请求: {group_id}")
            except Exception as e:
                QMessageBox.critical(self, "加入失败", f"加入群聊失败: {str(e)}")
            
    def manage_group(self):
        """管理群聊"""
        # 检查当前是否选择了群聊
        if not self.groups:
            QMessageBox.information(self, "群聊管理", "您当前没有加入任何群聊")
            return
            
        print("打开群聊管理界面")
        
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("群聊管理")
        dialog.resize(500, 400)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        
        # 选择群聊
        self.group_combo = QComboBox()
        for group in self.groups:
            group_id = group.get("group_id")
            group_name = group.get("group_name")
            role = group.get("role")
            self.group_combo.addItem(f"{group_name} ({role})", group_id)
            print(f"添加群聊到下拉列表: {group_name} ({role}), ID: {group_id}")
        
        layout.addWidget(QLabel("选择要管理的群聊:"))
        layout.addWidget(self.group_combo)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        
        # 基本信息选项卡
        info_widget = QWidget()
        info_layout = QFormLayout(info_widget)
        self.group_id_label = QLabel("")
        self.group_name_label = QLabel("")
        self.creator_label = QLabel("")
        self.create_time_label = QLabel("")
        self.member_count_label = QLabel("")
        
        info_layout.addRow("群号:", self.group_id_label)
        info_layout.addRow("群名称:", self.group_name_label)
        info_layout.addRow("创建者:", self.creator_label)
        info_layout.addRow("创建时间:", self.create_time_label)
        info_layout.addRow("成员数:", self.member_count_label)
        
        tab_widget.addTab(info_widget, "基本信息")
        
        # 成员管理选项卡
        members_widget = QWidget()
        members_layout = QVBoxLayout(members_widget)
        
        self.members_list = QListWidget()
        members_layout.addWidget(QLabel("群成员列表:"))
        members_layout.addWidget(self.members_list)
        
        # 成员操作按钮
        member_btn_layout = QHBoxLayout()
        self.promote_btn = QPushButton("设为管理员")
        self.demote_btn = QPushButton("取消管理员")
        self.remove_btn = QPushButton("移除成员")
        
        member_btn_layout.addWidget(self.promote_btn)
        member_btn_layout.addWidget(self.demote_btn)
        member_btn_layout.addWidget(self.remove_btn)
        members_layout.addLayout(member_btn_layout)
        
        tab_widget.addTab(members_widget, "成员管理")
        
        # 群聊操作选项卡
        op_widget = QWidget()
        op_layout = QVBoxLayout(op_widget)
        
        self.leave_btn = QPushButton("退出群聊")
        self.disband_btn = QPushButton("解散群聊")
        
        op_layout.addWidget(self.leave_btn)
        op_layout.addWidget(self.disband_btn)
        op_layout.addStretch()
        
        tab_widget.addTab(op_widget, "群聊操作")
        
        layout.addWidget(tab_widget)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        # 保存对话框引用，以便回调时使用
        self.current_group_dialog = dialog
        
        # 连接信号
        self.group_combo.currentIndexChanged.connect(self.update_group_info)
        
        # 添加成员选择变化事件，根据选择的成员角色动态控制按钮状态
        def on_member_selection_changed():
            if not self.members_list.selectedItems():
                # 未选择成员时禁用所有按钮
                self.promote_btn.setEnabled(False)
                self.demote_btn.setEnabled(False)
                self.remove_btn.setEnabled(False)
                return
                
            item = self.members_list.selectedItems()[0]
            selected_role = item.data(Qt.UserRole+1)  # 获取当前角色
            
            # 获取当前群组信息
            current_group = None
            for group in self.groups:
                if group.get("group_id") == self.group_combo.currentData():
                    current_group = group
                    break
                    
            if not current_group:
                return
                
            # 获取当前用户在群中的角色
            user_role = current_group.get("role", "")
            
            # 群主可以对所有人进行操作，但不能对自己进行操作
            is_owner = (user_role == "owner")
            
            # 不能对群主进行操作
            if selected_role == "owner":
                self.promote_btn.setEnabled(False)
                self.demote_btn.setEnabled(False)
                self.remove_btn.setEnabled(False)
                return
                
            # 如果当前用户是管理员
            if user_role == "admin":
                # 管理员不能设置/取消管理员权限
                self.promote_btn.setEnabled(False)
                self.demote_btn.setEnabled(False)
                # 管理员只能删除普通成员
                self.remove_btn.setEnabled(selected_role == "member")
            elif is_owner:
                # 群主可以对非群主成员进行所有操作
                self.promote_btn.setEnabled(selected_role == "member")
                self.demote_btn.setEnabled(selected_role == "admin")
                self.remove_btn.setEnabled(True)
                
        # 连接成员选择变化信号
        self.members_list.itemSelectionChanged.connect(on_member_selection_changed)
        
        # 定义成员操作函数
        def promote_member():
            """设置为管理员"""
            if not self.members_list.selectedItems():
                QMessageBox.warning(dialog, "提示", "请先选择一个成员")
                return
            
            item = self.members_list.selectedItems()[0]
            username = item.data(Qt.UserRole)  # 获取用户名
            role = item.data(Qt.UserRole+1)    # 获取当前角色
            
            if role == "owner":
                QMessageBox.warning(dialog, "提示", "群主不需要提升权限")
                return
            
            if role == "admin":
                QMessageBox.warning(dialog, "提示", "该成员已经是管理员")
                return
            
            group_id = self.group_combo.currentData()
            print(f"将成员 {username} 设为管理员, 群组: {group_id}")
            
            # 发送请求
            send_data(self.sock, {
                "action": "update_member_role",
                "group_id": group_id,
                "target": username,
                "role": "admin"  
            })
            
            QMessageBox.information(dialog, "操作成功", f"已将 {username} 设为管理员")
            
            # 重新获取成员列表以刷新显示
            send_data(self.sock, {
                "action": "get_group_members",
                "group_id": group_id
            })
        
        def demote_member():
            """取消管理员"""
            if not self.members_list.selectedItems():
                QMessageBox.warning(dialog, "提示", "请先选择一个成员")
                return
            
            item = self.members_list.selectedItems()[0]
            username = item.data(Qt.UserRole)  # 获取用户名
            role = item.data(Qt.UserRole+1)    # 获取当前角色
            
            if role == "owner":
                QMessageBox.warning(dialog, "提示", "不能降低群主权限")
                return
            
            if role != "admin":
                QMessageBox.warning(dialog, "提示", "该成员不是管理员")
                return
            
            group_id = self.group_combo.currentData()
            print(f"取消成员 {username} 的管理员权限, 群组: {group_id}")
            
            # 发送请求
            send_data(self.sock, {
                "action": "update_member_role",
                "group_id": group_id,
                "target": username,
                "role": "member"  
            })
            
            QMessageBox.information(dialog, "操作成功", f"已取消 {username} 的管理员权限")
            
            # 重新获取成员列表以刷新显示
            send_data(self.sock, {
                "action": "get_group_members",
                "group_id": group_id
            })
        
        def remove_member():
            """移除成员"""
            if not self.members_list.selectedItems():
                QMessageBox.warning(dialog, "提示", "请先选择一个成员")
                return
            
            item = self.members_list.selectedItems()[0]
            username = item.data(Qt.UserRole)  # 获取用户名
            role = item.data(Qt.UserRole+1)    # 获取当前角色
            
            if role == "owner":
                QMessageBox.warning(dialog, "提示", "不能移除群主")
                return
            
            if username == self.username:
                QMessageBox.warning(dialog, "提示", "不能移除自己，请使用退出群聊功能")
                return
            
            # 确认移除
            reply = QMessageBox.question(
                dialog, 
                "确认移除", 
                f"确定要将 {username} 移出群聊吗?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            group_id = self.group_combo.currentData()
            print(f"移除成员 {username}, 群组: {group_id}")
            
            # 发送请求
            send_data(self.sock, {
                "action": "remove_group_member",
                "group_id": group_id,
                "target": username
            })
            
            # 成功信息在回调中显示，不在这里直接显示
            # 重新获取成员列表以刷新显示
            send_data(self.sock, {
                "action": "get_group_members",
                "group_id": group_id
            })
        
        # 退出群聊
        def leave_group():
            try:
                selected_group_id = self.group_combo.currentData()
                selected_group_name = self.group_combo.currentText().split(" (")[0]
                
                reply = QMessageBox.question(
                    dialog, 
                    "确认退出", 
                    f"确定要退出群聊 {selected_group_name} 吗?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    send_data(self.sock, {
                        "action": "leave_group",
                        "group_id": selected_group_id
                    })
                    QMessageBox.information(dialog, "已退出", f"已退出群聊 {selected_group_name}")
                    dialog.accept()
            except Exception as e:
                QMessageBox.critical(dialog, "退出失败", f"退出群聊失败: {str(e)}")
        
        # 解散群聊
        def disband_group():
            try:
                selected_group_id = self.group_combo.currentData()
                selected_group_name = self.group_combo.currentText().split(" (")[0]
                
                reply = QMessageBox.question(
                    dialog, 
                    "确认解散", 
                    f"确定要解散群聊 {selected_group_name} 吗?\n此操作不可恢复!",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    send_data(self.sock, {
                        "action": "disband_group",
                        "group_id": selected_group_id
                    })
                    QMessageBox.information(dialog, "已解散", f"已解散群聊 {selected_group_name}")
                    dialog.accept()
            except Exception as e:
                QMessageBox.critical(dialog, "解散失败", f"解散群聊失败: {str(e)}")
        
        # 连接按钮信号
        self.promote_btn.clicked.connect(promote_member)
        self.demote_btn.clicked.connect(demote_member)
        self.remove_btn.clicked.connect(remove_member)
        self.leave_btn.clicked.connect(leave_group)
        self.disband_btn.clicked.connect(disband_group)
        
        # 初始化显示
        if self.group_combo.count() > 0:
            print("开始初始化群聊信息显示")
            self.update_group_info()
        
        # 显示对话框
        dialog.exec_()
    
    def update_group_info(self):
        try:
            selected_group_id = self.group_combo.currentData()
            print(f"更新群聊信息: {selected_group_id}")
            
            # 查找当前群组信息
            current_group = None
            for group in self.groups:
                if group.get("group_id") == selected_group_id:
                    current_group = group
                    break
            
            if not current_group:
                print(f"找不到群组信息: {selected_group_id}")
                return
                
            print(f"找到群组信息: {current_group}")
            
            # 更新基本信息
            self.group_id_label.setText(current_group.get("group_id", ""))
            self.group_name_label.setText(current_group.get("group_name", ""))
            self.creator_label.setText(current_group.get("creator", "未知"))
            self.create_time_label.setText(current_group.get("create_time", ""))
            
            # 获取群成员列表
            try:
                # 显示加载提示
                self.members_list.clear()
                self.members_list.addItem("加载成员列表中...")
                
                print(f"请求获取群成员列表: {selected_group_id}")
                # 发送请求获取群成员列表
                send_data(self.sock, {
                    "action": "get_group_members",
                    "group_id": selected_group_id
                })
            except Exception as e:
                print(f"获取群成员列表失败: {str(e)}")
                QMessageBox.warning(self, "获取成员失败", f"获取群成员失败: {str(e)}")
                self.members_list.clear()
                self.members_list.addItem("获取成员列表失败")
            
            # 更新按钮状态
            current_role = current_group.get("role", "")
            is_owner = (current_role == "owner")
            is_admin = (current_role == "admin" or is_owner)
            
            # 只有群主才能解散群聊
            self.disband_btn.setEnabled(is_owner)
            
            # 只有群主才能设置/取消管理员
            self.promote_btn.setEnabled(is_owner)
            self.demote_btn.setEnabled(is_owner)
            
            # 管理员和群主都可以移除成员，但后续会根据选择的成员角色动态控制
            self.remove_btn.setEnabled(is_admin)
        except Exception as e:
            print(f"更新群聊信息失败: {str(e)}")
            QMessageBox.warning(self, "更新信息失败", f"更新群信息失败: {str(e)}")
    
    # ====================== 应用退出相关 ======================
    def logout(self):
        """退出登录"""
        reply = QMessageBox.question(
            self, "确认退出", "确定要退出登录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 发送退出登录请求
            try:
                send_data(self.sock, {"action": "logout"})
            except Exception:
                pass
                
            # 停止接收线程
            if hasattr(self, 'receiver') and self.receiver:
                self.receiver.stop()
                
            # 关闭窗口
            self.close()
    
    def closeEvent(self, event):
        """关闭窗口事件"""
        # 停止所有线程
        if hasattr(self, 'receiver') and self.receiver:
            self.receiver.stop()
            
        if hasattr(self, 'voice_call_thread') and self.voice_call_thread:
            self.voice_call_thread.stop()
            
        if hasattr(self, 'video_call_thread') and self.video_call_thread:
            self.video_call_thread.stop()
            
        # 关闭socket
        try:
            send_data(self.sock, {"action": "logout"})
            self.sock.close()
        except Exception:
            pass
            
        event.accept()
    
    # ====================== 接收消息处理 ======================
    # 从ui_main_handle.py导入处理函数
    from ui_main_handle import (
        handle_incoming_message, update_friend_list, update_group_list, 
        update_friend_requests, handle_message, handle_history,
        is_image_file, save_received_file, save_thumbnail, 
        append_message, refresh_chat_view,
        handle_new_friend_request, handle_friend_request_update, 
        handle_friend_deleted, update_user_status,
        handle_group_member_joined, handle_group_member_left, 
        handle_group_disbanded, handle_role_updated,
        handle_removed_from_group, handle_group_members_updated,
        handle_incoming_call, handle_call_ringing, handle_call_answered, 
        handle_call_ended, handle_call_failed,
        handle_delete_friend_result, handle_friend_request_result, handle_remove_member_result,
        handle_video_frame, handle_voice_frame, handle_change_password_result, handle_delete_account_result
    )
    
    # 处理群成员列表响应
    def handle_group_members_list(self, data):
        """处理获取群成员列表的响应"""
        group_id = data.get("group_id", "")
        members = data.get("members", [])
        
        print(f"收到群成员列表响应: {group_id}, 成员数: {len(members)}")
        
        # 如果有群成员管理对话框打开，并且是当前选中的群组，才更新成员列表
        if hasattr(self, 'current_group_dialog') and self.current_group_dialog and self.current_group_dialog.isVisible():
            print(f"当前有群管理对话框打开")
            
            if hasattr(self, 'group_combo'):
                current_group_id = self.group_combo.currentData()
                print(f"当前选中的群组ID: {current_group_id}, 收到的群组ID: {group_id}")
                
                if current_group_id == group_id:
                    print(f"更新成员列表UI")
                    if hasattr(self, 'members_list') and self.members_list:
                        self.members_list.clear()
                        for member in members:
                            username = member.get("username", "")
                            role = member.get("role", "member")
                            join_time = member.get("join_time", "")
                            
                            print(f"添加成员: {username} ({role})")
                            
                            # 显示成员角色
                            display_text = f"{username} ({role})"
                            item = QListWidgetItem(display_text)
                            item.setData(Qt.UserRole, username)
                            item.setData(Qt.UserRole+1, role)
                            
                            # 设置颜色区分角色
                            if role == "owner":
                                item.setForeground(QColor(255, 0, 0))  # 红色
                            elif role == "admin":
                                item.setForeground(QColor(0, 0, 255))  # 蓝色
                            
                            self.members_list.addItem(item)
                        
                        # 更新成员数量标签
                        if hasattr(self, 'member_count_label'):
                            self.member_count_label.setText(str(len(members)))
                            print(f"更新成员数量: {len(members)}")
                    else:
                        print("members_list 对象不存在")
                else:
                    print(f"群组ID不匹配，不更新")
            else:
                print("group_combo 对象不存在")
        else:
            print(f"没有打开的群管理对话框，或对话框不可见")
    
    # 创建群聊结果处理
    def handle_create_group_result(self, data):
        """处理创建群聊的结果"""
        try:
            success = data.get("success", False)
            message = data.get("message", "")
            group_id = data.get("group_id", "")
            
            if success:
                QMessageBox.information(self, "创建群聊", f"群聊创建成功\n群号: {group_id}\n{message}")
            else:
                QMessageBox.warning(self, "创建群聊失败", f"群聊创建失败: {message}")
        except Exception as e:
            print(f"处理创建群聊结果错误: {str(e)}")
            QMessageBox.warning(self, "创建群聊", "处理创建群聊结果时出错")
    # 处理好友请求结果  
    def handle_friend_request_result(self, data):
        """处理发送好友请求的结果"""
        try:
            success = data.get("success", False)
            message = data.get("message", "")
            
            if success:
                QMessageBox.information(self, "好友请求", f"好友请求已发送: {message}")
            else:
                QMessageBox.warning(self, "好友请求失败", f"好友请求发送失败: {message}")
        except Exception as e:
            print(f"处理好友请求结果错误: {str(e)}")
            QMessageBox.warning(self, "好友请求", "处理好友请求结果时出错")
    def show_friend_context_menu(self, position):
        """显示好友列表右键菜单"""
        item = self.friend_list.itemAt(position)
        if not item:
            return
        
        friend_name = item.text()
        
        menu = QMenu()
        delete_action = menu.addAction("删除好友")
        
        action = menu.exec_(self.friend_list.mapToGlobal(position))
        
        if action == delete_action:
            self.delete_friend(friend_name)
    def delete_friend(self, friend_name):
        """删除好友"""
        reply = QMessageBox.question(
            self, 
            "确认删除", 
            f"确定要删除好友 {friend_name} 吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            print(f"删除好友: {friend_name}")
            
            # 发送删除好友请求
            send_data(self.sock, {
                "action": "delete_friend",
                "friend": friend_name
            })
            
            # 本地UI显示上暂时保留，等待服务器响应后再正式更新
    
    # 处理删除好友的结果
    def handle_delete_friend_result(self, data):
        """处理删除好友的结果"""
        try:
            success = data.get("success", False)
            message = data.get("message", "")
            friend = data.get("friend", "")
            
            if success:
                # 从好友列表中移除
                if friend in self.friends:
                    self.friends.remove(friend)
                    # 更新UI
                    self.friend_list.clear()
                    for f in self.friends:
                        self.friend_list.addItem(QListWidgetItem(f))
                
                # 如果正在聊天的对象是被删除的好友，则清空聊天区域
                if self.current_chat_target == friend and not self.is_group_chat:
                    self.current_chat_target = None
                    self.chat_title.setText("当前未选择聊天")
                    self.chat_view.clear()
                    self.chat_view.setHtml('<p style="text-align:center;">已删除好友，聊天记录已关闭</p>')
                
                QMessageBox.information(self, "删除好友", f"已删除好友: {friend}")
            else:
                QMessageBox.warning(self, "删除失败", f"删除好友失败: {message}")
        except Exception as e:
            print(f"处理删除好友结果错误: {str(e)}")
            QMessageBox.warning(self, "删除好友", "处理删除好友结果时出错")
    
    def _handle_anchor_clicked(self, url):
        """处理点击链接事件，使用QDesktopServices打开链接"""
        # 对于任何类型的URL，都直接使用QDesktopServices打开
        # QDesktopServices会自动处理file://协议和http://等其他协议
        QDesktopServices.openUrl(url)
    @staticmethod
    def _uri(path):
        """将本地路径转换为 file:// URI 格式"""
        # 确保 path 是字符串类型
        if hasattr(path, "__str__"):
            path_str = str(path)
        else:
            path_str = path
        return QUrl.fromLocalFile(path_str).toString()