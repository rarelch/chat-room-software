# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, 
    QComboBox, QWidget, QSplitter, QCheckBox, QSlider
)
from PyQt5.QtGui import QPixmap, QImage

class VideoCallDialog(QDialog):
    """视频通话对话框"""
    
    def __init__(self, parent=None, target_user="", local_camera_available=True):
        super().__init__(parent)
        self.target_user = target_user
        self.local_camera_available = local_camera_available
        self.setWindowTitle(f"与 {target_user} 的视频通话")
        self.setMinimumSize(800, 500)
        self.setup_ui()
        
        # 通话时长计时器
        self.call_timer = QTimer()
        self.call_timer.timeout.connect(self.update_call_duration)
        self.call_duration = 0  # 秒
        self.call_timer.start(1000)  # 每秒更新一次
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 创建视频显示区域
        video_area = QSplitter(Qt.Horizontal)
        
        # 本地视频
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)
        
        self.local_label = QLabel("本地视频")
        self.local_label.setAlignment(Qt.AlignCenter)
        self.local_video = QLabel()
        self.local_video.setAlignment(Qt.AlignCenter)
        self.local_video.setStyleSheet("background-color: #222; min-width: 320px; min-height: 240px;")
        
        local_layout.addWidget(self.local_label)
        local_layout.addWidget(self.local_video)
        
        # 远程视频
        remote_widget = QWidget()
        remote_layout = QVBoxLayout(remote_widget)
        
        self.remote_label = QLabel(f"{self.target_user} 的视频")
        self.remote_label.setAlignment(Qt.AlignCenter)
        self.remote_video = QLabel()
        self.remote_video.setAlignment(Qt.AlignCenter)
        self.remote_video.setStyleSheet("background-color: #222; min-width: 320px; min-height: 240px;")
        
        remote_layout.addWidget(self.remote_label)
        remote_layout.addWidget(self.remote_video)
        
        video_area.addWidget(local_widget)
        video_area.addWidget(remote_widget)
        video_area.setSizes([1, 2])  # 设置初始分割比例
        
        main_layout.addWidget(video_area)
        
        # 通话控制区域
        control_layout = QHBoxLayout()
        
        # 通话时间
        self.duration_label = QLabel("通话时长: 00:00")
        control_layout.addWidget(self.duration_label)
        
        control_layout.addStretch()
        
        # 视频分辨率选择
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(QLabel("分辨率:"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["低 (320x240)", "中 (640x480)", "高 (1280x720)", "超高清 (1920x1080)"])
        self.resolution_combo.setCurrentIndex(1)  # 默认中等分辨率
        self.resolution_combo.currentIndexChanged.connect(self.change_resolution)
        resolution_layout.addWidget(self.resolution_combo)
        control_layout.addLayout(resolution_layout)
        
        # 视频特效选择
        effect_layout = QHBoxLayout()
        effect_layout.addWidget(QLabel("特效:"))
        self.effect_combo = QComboBox()
        self.effect_combo.addItems(["无", "灰度", "二值化", "边缘检测", "模糊"])
        self.effect_combo.currentIndexChanged.connect(self.change_effect)
        effect_layout.addWidget(self.effect_combo)
        control_layout.addLayout(effect_layout)
        
        # 视频质量调整
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("质量:"))
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setMinimum(10)
        self.quality_slider.setMaximum(100)
        self.quality_slider.setValue(50)
        self.quality_slider.setFixedWidth(100)
        self.quality_slider.valueChanged.connect(self.change_quality)
        quality_layout.addWidget(self.quality_slider)
        control_layout.addLayout(quality_layout)
        
        # 静音和关闭摄像头
        self.mute_checkbox = QCheckBox("静音")
        self.mute_checkbox.toggled.connect(self.toggle_mute)
        control_layout.addWidget(self.mute_checkbox)
        self.camera_checkbox = QCheckBox("关闭摄像头")
        self.camera_checkbox.toggled.connect(self.toggle_camera)
        control_layout.addWidget(self.camera_checkbox)
        
        # 结束通话按钮
        self.hang_up_btn = QPushButton("结束通话")
        self.hang_up_btn.clicked.connect(self.end_call)
        control_layout.addWidget(self.hang_up_btn)
        main_layout.addLayout(control_layout)
    
    def update_local_video(self, image):
        """更新本地视频显示"""
        if image:
            pixmap = QPixmap.fromImage(image)
            self.local_video.setPixmap(pixmap.scaled(
                self.local_video.width(), 
                self.local_video.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
        else:
            self.local_video.setText("摄像头已关闭")
            
    def update_remote_video(self, image):
        """更新远程视频显示"""
        print(f"正在更新远程视频: {'有图像数据' if image else '无图像数据'}")
        if image:
            pixmap = QPixmap.fromImage(image)
            print(f"创建Pixmap: {pixmap.width()}x{pixmap.height()}")
            self.remote_video.setPixmap(pixmap.scaled(
                self.remote_video.width(), 
                self.remote_video.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))
            print("远程视频已更新")
        else:
            self.remote_video.setText("对方摄像头已关闭")
            print("显示对方摄像头已关闭信息")
    
    def update_call_duration(self):
        """更新通话时长"""
        self.call_duration += 1
        minutes = self.call_duration // 60
        seconds = self.call_duration % 60
        self.duration_label.setText(f"通话时长: {minutes:02d}:{seconds:02d}")
    
    def change_resolution(self, index):
        """修改视频分辨率"""
        resolutions = ["low", "medium", "high", "hd"]
        if index < len(resolutions):
            resolution = resolutions[index]
            # 发射信号通知视频线程更改分辨率
            if hasattr(self.parent(), "video_call_thread"):
                self.parent().video_call_thread.resolution = resolution
    
    def change_effect(self, index):
        """修改视频特效"""
        effects = ["none", "gray", "binary", "edge", "blur"]
        if index < len(effects):
            effect = effects[index]
            # 发射信号通知视频线程更改特效
            if hasattr(self.parent(), "video_call_thread"):
                self.parent().video_call_thread.effect = effect
    
    def change_quality(self):
        """修改视频质量"""
        quality = self.quality_slider.value()
        # 发射信号通知视频线程更改质量
        if hasattr(self.parent(), "video_call_thread"):
            self.parent().video_call_thread.quality = quality
    
    def toggle_mute(self, checked):
        """切换静音状态"""
        # 在实际应用中，这里应该与音频设备交互
        if hasattr(self.parent(), "video_call_thread"):
            self.parent().video_call_thread.is_muted = checked
    
    def toggle_camera(self, checked):
        """切换摄像头状态"""
        if hasattr(self.parent(), "video_call_thread"):
            self.parent().video_call_thread.camera_enabled = not checked
    
    def end_call(self):
        """结束通话"""
        # 停止计时器
        self.call_timer.stop()
        
        # 通知父窗口结束通话
        if hasattr(self.parent(), "end_video_call"):
            self.parent().end_video_call()
        
        # 关闭对话框
        self.accept()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止计时器
        self.call_timer.stop()
        
        # 通知父窗口结束通话
        if hasattr(self.parent(), "end_video_call"):
            self.parent().end_video_call()
        
        event.accept()
