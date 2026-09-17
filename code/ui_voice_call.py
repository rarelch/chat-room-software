# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, 
    QComboBox, QWidget, QCheckBox, QProgressBar
)

class VoiceCallDialog(QDialog):
    """语音通话对话框"""
    
    def __init__(self, parent=None, target_user=""):
        super().__init__(parent)
        self.target_user = target_user
        self.setWindowTitle(f"与 {target_user} 的语音通话")
        self.setMinimumSize(400, 300)
        self.setup_ui()
        
        # 通话时长计时器
        self.call_timer = QTimer()
        self.call_timer.timeout.connect(self.update_call_duration)
        self.call_duration = 0  # 秒
        self.call_timer.start(1000)  # 每秒更新一次
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 通话状态显示
        self.status_label = QLabel(f"正在与 {self.target_user} 通话")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; margin: 20px;")
        main_layout.addWidget(self.status_label)
        
        # 音量可视化
        volume_layout = QHBoxLayout()
        
        # 本地音量显示
        local_volume_layout = QVBoxLayout()
        local_volume_layout.addWidget(QLabel("本地音量"))
        self.local_volume_bar = QProgressBar()
        self.local_volume_bar.setRange(0, 100)
        self.local_volume_bar.setValue(0)
        local_volume_layout.addWidget(self.local_volume_bar)
        volume_layout.addLayout(local_volume_layout)
        
        # 远程音量显示
        remote_volume_layout = QVBoxLayout()
        remote_volume_layout.addWidget(QLabel(f"{self.target_user} 的音量"))
        self.remote_volume_bar = QProgressBar()
        self.remote_volume_bar.setRange(0, 100)
        self.remote_volume_bar.setValue(0)
        remote_volume_layout.addWidget(self.remote_volume_bar)
        volume_layout.addLayout(remote_volume_layout)
        
        main_layout.addLayout(volume_layout)
        
        # 通话时间
        self.duration_label = QLabel("通话时长: 00:00")
        self.duration_label.setAlignment(Qt.AlignCenter)        
        main_layout.addWidget(self.duration_label)
        
        # 控制区域
        control_layout = QHBoxLayout()
        
        # 语音变声
        voice_effect_layout = QVBoxLayout()
        voice_effect_layout.addWidget(QLabel("变声效果:"))
        self.voice_effect_combo = QComboBox()
        self.voice_effect_combo.addItems(["正常", "机器人", "花栗鼠", "低沉", "男声", "女声"])
        self.voice_effect_combo.currentIndexChanged.connect(self.change_voice_effect)
        voice_effect_layout.addWidget(self.voice_effect_combo)
        control_layout.addLayout(voice_effect_layout)
        
        # 静音按钮
        self.mute_checkbox = QCheckBox("静音")
        self.mute_checkbox.toggled.connect(self.toggle_mute)
        control_layout.addWidget(self.mute_checkbox)
        
        # 扬声器按钮
        self.speaker_checkbox = QCheckBox("扬声器")
        self.speaker_checkbox.toggled.connect(self.toggle_speaker)
        control_layout.addWidget(self.speaker_checkbox)
        
        # 结束通话按钮
        self.hang_up_btn = QPushButton("结束通话")
        self.hang_up_btn.setStyleSheet("background-color: #e74c3c; color: white;")
        self.hang_up_btn.clicked.connect(self.end_call)
        control_layout.addWidget(self.hang_up_btn)
        
        main_layout.addLayout(control_layout)
    
    def update_call_duration(self):
        """更新通话时长"""
        self.call_duration += 1
        minutes = self.call_duration // 60
        seconds = self.call_duration % 60
        self.duration_label.setText(f"通话时长: {minutes:02d}:{seconds:02d}")
        
    def update_local_volume(self, audio_data):
        """更新本地音量显示"""
        from audio_utils import calculate_audio_level
        try:
            volume = calculate_audio_level(audio_data, 2)
            print(f"本地音量: {volume}%")            
            self.local_volume_bar.setValue(volume)
            # 更新标签显示具体数值
            self.local_volume_bar.setFormat(f"%p% ({volume})")
        except Exception as e:
            print(f"更新本地音量显示时出错: {e}")
    
    def update_remote_volume(self, audio_data):
        """更新远程音量显示"""
        from audio_utils import calculate_audio_level
        try:
            volume = calculate_audio_level(audio_data, 2)
            print(f"远程音量: {volume}%")
            self.remote_volume_bar.setValue(volume)
            # 更新标签显示具体数值
            self.remote_volume_bar.setFormat(f"%p% ({volume})")
        except Exception as e:
            print(f"更新远程音量显示时出错: {e}")
    
    def change_voice_effect(self, index):
        """修改变声效果"""
        effects = ["normal", "robot", "chipmunk", "deep", "male", "female"]
        if index < len(effects):
            effect = effects[index]
            # 通知语音线程更改效果
            if hasattr(self.parent(), "voice_call_thread"):
                self.parent().voice_call_thread.voice_type = effect
                print(f"已切换语音效果：{effect}")
    
    def toggle_mute(self, checked):
        """切换静音状态"""
        if hasattr(self.parent(), "voice_call_thread"):
            self.parent().voice_call_thread.is_muted = checked
    
    def toggle_speaker(self, checked):
        """切换扬声器状态"""
        # 在实际应用中，这里应该切换音频输出设备
        # 简化实现，仅显示状态变化
        status = "开启" if checked else "关闭"
        print(f"扬声器状态: {status}")
    
    def end_call(self):
        """结束通话"""
        # 停止计时器
        self.call_timer.stop()
        
        # 通知父窗口结束通话
        if hasattr(self.parent(), "end_voice_call"):
            self.parent().end_voice_call()
        
        # 关闭对话框
        self.accept()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 停止计时器
        self.call_timer.stop()
        
        # 通知父窗口结束通话
        if hasattr(self.parent(), "end_voice_call"):
            self.parent().end_voice_call()
        
        event.accept()
