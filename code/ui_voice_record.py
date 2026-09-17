# -*- coding: utf-8 -*-
"""语音消息录制对话框"""

import time
import uuid
import os
import wave
import struct
from pathlib import Path
import base64

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, 
    QComboBox, QProgressBar, QMessageBox
)

from audio_utils import apply_voice_effect, calculate_audio_level

class VoiceRecordDialog(QDialog):
    """语音消息录制对话框"""
    
    # 录制完成信号，发送录制完成的文件路径和时长
    record_complete = pyqtSignal(str, int, bytes)
    
    @staticmethod
    def is_pyaudio_available():
        """检查 PyAudio 是否可用"""
        try:
            import pyaudio
            return True
        except ImportError:
            return False
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("录制语音消息")
        self.setMinimumSize(400, 300)
          # 初始化录音状态
        self.recording = False
        self.duration = 0  # 录制时长（秒）
        self.max_duration = 60  # 最大录制时长（秒）
        self.min_duration = 1   # 最小录制时长（秒）
        self.voice_type = "normal"
        self.audio_data = bytearray()  # 存储录制的音频数据
        
        # 设置UI
        self.setup_ui()
        
        # 录制计时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_duration)
        
        # 导入PyAudio
        try:
            import pyaudio
            import numpy as np
            self.pyaudio = pyaudio
            
            # 音频参数 (与语音通话相同)
            self.CHUNK = 1024
            self.FORMAT = pyaudio.paInt16
            self.CHANNELS = 1
            self.RATE = 16000
            
            # 初始化音频处理对象
            self.pa = pyaudio.PyAudio()
            self.input_stream = None
            
        except ImportError as e:
            print(f"导入音频库失败: {e}")
            QMessageBox.warning(None, "音频初始化失败", 
                              f"无法加载所需的音频库: {e}\n请确保已安装PyAudio")
            self.reject()
    
    def setup_ui(self):
        """设置UI界面"""
        main_layout = QVBoxLayout(self)
        
        # 状态显示
        self.status_label = QLabel("准备录制")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; margin: 20px;")
        main_layout.addWidget(self.status_label)
        
        # 时长显示
        self.duration_label = QLabel("00:00 / 01:00")
        self.duration_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.duration_label)
        
        # 音量可视化
        self.volume_label = QLabel("音量:")
        main_layout.addWidget(self.volume_label)
        
        self.volume_bar = QProgressBar()
        self.volume_bar.setRange(0, 100)
        self.volume_bar.setValue(0)
        main_layout.addWidget(self.volume_bar)
        
        # 变声效果选择
        effect_layout = QHBoxLayout()
        effect_layout.addWidget(QLabel("变声效果:"))
        self.voice_effect_combo = QComboBox()
        self.voice_effect_combo.addItems(["正常", "机器人", "花栗鼠", "低沉", "男声", "女声"])
        self.voice_effect_combo.currentIndexChanged.connect(self.change_voice_effect)
        effect_layout.addWidget(self.voice_effect_combo)
        main_layout.addLayout(effect_layout)
        
        # 控制按钮
        buttons_layout = QHBoxLayout()
        
        self.record_btn = QPushButton("开始录制")
        self.record_btn.clicked.connect(self.toggle_recording)
        buttons_layout.addWidget(self.record_btn)
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        
        self.finish_btn = QPushButton("完成")
        self.finish_btn.clicked.connect(self.finish_recording)
        self.finish_btn.setEnabled(False)
        buttons_layout.addWidget(self.finish_btn)
        
        main_layout.addLayout(buttons_layout)
    
    def toggle_recording(self):
        """切换录制状态"""
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """开始录音"""
        try:
            # 初始化音频输入流
            self.input_stream = self.pa.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.CHUNK,
                stream_callback=self.audio_callback
            )
            
            # 重置录音数据
            self.audio_data = bytearray()
            self.duration = 0
            
            # 开始录音
            self.recording = True
            self.record_btn.setText("停止录制")
            self.status_label.setText("正在录制...")
            self.finish_btn.setEnabled(False)
            
            # 启动计时器
            self.timer.start(1000)  # 每秒更新一次
            
            print("开始录音...")
            
        except Exception as e:
            print(f"开始录音时出错: {e}")
            QMessageBox.warning(self, "录音错误", f"无法开始录音: {e}")
    
    def stop_recording(self):
        """停止录音"""
        if self.recording and hasattr(self, "input_stream") and self.input_stream:
            # 停止录音
            self.recording = False
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None
            
            # 停止计时器
            self.timer.stop()
            
            # 更新UI
            self.record_btn.setText("重新录制")
            self.status_label.setText("录制已完成")
            self.finish_btn.setEnabled(True)
            print(f"录音已停止，时长: {self.duration}秒，数据大小: {len(self.audio_data)}字节")
    
    def finish_recording(self):
        """完成录音并返回数据"""
        # 确保录音已停止
        if self.recording:
            self.stop_recording()
            
        # 检查录制时长是否达到最小要求
        if self.duration < self.min_duration:
            QMessageBox.warning(self, "录制时间过短", 
                             f"录制时间太短，请至少录制 {self.min_duration} 秒")
            return
        
        # 生成随机文件名
        # 使用项目根目录下的 temp/voice 目录
        base_dir = Path(__file__).parent
        temp_dir = base_dir / "temp" / "voice"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"voice_msg_{uuid.uuid4().hex[:8]}_{int(time.time())}.wav"
        file_path = str(temp_dir / filename)
        try:
            # 使用wave模块创建WAV文件（包含正确的文件头）
            with wave.open(file_path, 'wb') as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(self.pa.get_sample_size(self.FORMAT))
                wf.setframerate(self.RATE)
                # 写入原始音频数据
                wf.writeframes(bytes(self.audio_data))
            
            # 发射录制完成信号 - 转换 bytearray 到 bytes
            audio_bytes = bytes(self.audio_data)
            self.record_complete.emit(file_path, self.duration, audio_bytes)
            self.accept()
        except Exception as e:
            print(f"保存录音文件时出错: {e}")
            QMessageBox.warning(self, "保存录音失败", f"无法保存录音文件: {e}")
    
    def update_duration(self):
        """更新录制时长"""
        self.duration += 1
        minutes = self.duration // 60
        seconds = self.duration % 60
        
        # 显示剩余时间
        remain = self.max_duration - self.duration
        remain_min = remain // 60
        remain_sec = remain % 60
        
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d} / {remain_min:02d}:{remain_sec:02d}")
        
        # 达到最大时长时自动停止
        if self.duration >= self.max_duration:
            self.stop_recording()
    
    def update_volume_display(self, level):
        """更新音量显示"""
        self.volume_bar.setValue(level)
        self.volume_bar.setFormat(f"%p% ({level})")
    
    def change_voice_effect(self, index):
        """修改变声效果"""
        effects = ["normal", "robot", "chipmunk", "deep", "male", "female"]
        if index < len(effects):
            self.voice_type = effects[index]
            print(f"已切换语音效果：{self.voice_type}")
    
    def audio_callback(self, in_data, frame_count, time_info, status):
        """音频数据回调"""
        if self.recording:
            try:
                # 应用变声效果
                audio_chunk = in_data
                if self.voice_type != "normal":
                    audio_chunk = apply_voice_effect(in_data, self.voice_type, 2)
                
                # 添加到录音数据中
                self.audio_data.extend(audio_chunk)
                
                # 计算并显示音量级别
                level = calculate_audio_level(in_data, 2)
                self.update_volume_display(level)
                
            except Exception as e:
                print(f"处理音频数据时出错: {e}")
                
        return (in_data, self.pyaudio.paContinue)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 确保录音已停止
        if self.recording:
            self.stop_recording()
            
        # 清理音频资源
        if hasattr(self, 'pa'):
            try:
                self.pa.terminate()
            except:
                pass
            
        event.accept()
