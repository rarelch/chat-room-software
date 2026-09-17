# -*- coding: utf-8 -*-
import json
import socket
import base64
import os
#import numpy as np
from pathlib import Path

#SERVER_HOST = "10.167.109.245"
SERVER_HOST = "10.109.135.245"
SERVER_PORT = 8888
MAX_FILE_SIZE = 30 * 1024 * 1024          # 最大文件大小
UPLOAD_DIR = Path(__file__).with_name("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 语音处理相关常量
VOICE_SAMPLE_RATE = 44100
MAX_VOICE_DURATION = 60  # 最大语音时长（秒）

# 视频处理相关常量
VIDEO_RESOLUTIONS = {
    "low": (320, 240),
    "medium": (640, 480),
    "high": (1280, 720),
    "hd": (1920, 1080),
}

# 头像文件目录
AVATAR_DIR = Path(__file__).with_name("avatars")
AVATAR_DIR.mkdir(exist_ok=True)

# 聊天消息类型
MESSAGE_TYPES = {
    "text": "文本消息",
    "emoji": "表情消息",
    "file": "文件消息",
    "voice": "语音消息",
    "video": "视频消息",
    "image": "图片消息",
    "system": "系统消息",
}

HEADER_LEN = 10                           # 固定 10 字节消息头，表示 JSON 长度
'''
    设计思路：
        先写序列化与反序列化的函数，客户端与服务端都需要用到
        写的信息为字典型变量，例如：{"action": "change_password",
                    "password": "123456",
                    }
        字典真的好用，是这个世界上最好用的东西
        便于直接提取信息
        发送的信息需要经过json.dumps序列化
        接收的信息需要经过json.loads反序化
'''

def send_data(sock: socket.socket, data: dict) -> None:#发送信息 将字典类型的数据序列化后通过 socket 发送，适配聊天系统的消息传输
    """Send dict via socket with fixed-length header."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    header = str(len(body)).zfill(HEADER_LEN).encode("utf-8")
    
    # 检查如果是视频帧，输出大小信息
    if data.get("action") == "video_frame":
        print(f"发送视频帧: 大小={len(body)}字节")
    
    sock.sendall(header + body) # 一次性发完所以数据


def recv_data(sock: socket.socket):#接收信息 从 socket 读取数据，解析固定消息头，分块接收消息体，反序列化为字典；
    try:
        header = b"" # 消息是二进制流，不是Unicode
        while len(header) < HEADER_LEN:
            chunk = sock.recv(HEADER_LEN - len(header))
            if not chunk:
                return None
            header += chunk
        length = int(header.decode("utf-8"))
        
        # 打印大型数据包的信息
        if length > 100000:  # 大于100KB的数据包
            print(f"接收大型数据包: 期望大小={length}字节")
            
        body = b""
        while len(body) < length:
            # 对于大型数据包，使用更大的缓冲区
            buffer_size = min(4096, length - len(body))
            chunk = sock.recv(buffer_size)
            if not chunk:
                return None
            body += chunk
            
            # 显示接收进度
            if length > 100000 and len(body) % 100000 < 4096:
                print(f"接收进度: {len(body)}/{length}字节 ({len(body)*100//length}%)")
                
        data = json.loads(body.decode("utf-8"))
        
        # 检查如果是视频帧，记录接收信息
        if data.get("action") == "video_frame":
            frame_size = len(data.get("frame", "")) if "frame" in data else 0
            print(f"接收到视频帧: 来自={data.get('from_user', '未知')}, 大小={frame_size}字节")
            
        return data
    except Exception as e:
        import traceback
        print(f"接收数据错误: {e}")
        traceback.print_exc()
        return None

# 用于生成随机的群组ID
def generate_group_id():
    """生成随机的群ID，格式为：G-xxxx"""
    import random
    return f"G-{random.randint(10000, 99999)}"

# 用于生成随机的匿名名称
def generate_anonymous_name():
    """生成随机的匿名名称"""
    import random
    adjectives = ["快乐的", "神秘的", "可爱的", "聪明的", "勇敢的", "温柔的", "热情的", "有趣的", "活泼的", "善良的"]
    nouns = ["猫咪", "狗狗", "狐狸", "熊猫", "兔子", "老虎", "大象", "狮子", "长颈鹿", "海豚"]
    return f"{random.choice(adjectives)}{random.choice(nouns)}"

# 语音变声处理函数
def voice_change(voice_data, change_type):
    """
    对语音数据进行变声处理
    
    参数:
        voice_data: 原始语音数据
        change_type: 变声类型 ("male", "female", "normal")
    
    返回:
        变声后的语音数据
    """
    try:
        # 这里只是示例，实际应用中需要使用专业的音频处理库
        # 如librosa, pydub等进行处理
        if change_type == "normal":
            return voice_data
        
        # 在实际应用中，你可以使用类似以下代码:
        # import librosa
        # import soundfile as sf
        # y, sr = librosa.load(io.BytesIO(voice_data), sr=None)
        # 
        # if change_type == "male":
        #     # 降低音调使声音更低沉
        #     y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=-4)
        # elif change_type == "female":
        #     # 提高音调使声音更尖细
        #     y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=4)
        # 
        # # 转回字节数据
        # buffer = io.BytesIO()
        # sf.write(buffer, y_shifted, sr, format='wav')
        # return buffer.getvalue()
        
        # 由于可能需要额外安装库，这里仅返回原始数据
        return voice_data
    except Exception as e:
        print(f"语音处理错误: {str(e)}")
        return voice_data

# 视频处理函数
def adjust_video_resolution(video_data, resolution):
    """
    调整视频分辨率
    
    参数:
        video_data: 原始视频数据
        resolution: 目标分辨率 ("low", "medium", "high", "hd")
        
    返回:
        处理后的视频数据
    """
    try:
        # 这里只是示例，实际应用中需要使用专业的视频处理库
        # 如OpenCV, ffmpeg等
        # 
        # import cv2
        # import io
        # import numpy as np
        # from tempfile import NamedTemporaryFile
        # 
        # # 写入临时文件
        # with NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        #     f.write(video_data)
        #     temp_name = f.name
        # 
        # # 读取视频
        # cap = cv2.VideoCapture(temp_name)
        # 
        # # 获取分辨率
        # target_width, target_height = VIDEO_RESOLUTIONS.get(resolution, (640, 480))
        # 
        # # 处理视频
        # fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        # output_file = temp_name + "_resized.mp4"
        # out = cv2.VideoWriter(output_file, fourcc, cap.get(cv2.CAP_PROP_FPS), 
        #                      (target_width, target_height))
        # 
        # while cap.isOpened():
        #     ret, frame = cap.read()
        #     if not ret:
        #         break
        #     resized = cv2.resize(frame, (target_width, target_height))
        #     out.write(resized)
        # 
        # cap.release()
        # out.release()
        # 
        # # 读取处理后的视频
        # with open(output_file, 'rb') as f:
        #     processed_data = f.read()
        # 
        # # 清理临时文件
        # os.unlink(temp_name)
        # os.unlink(output_file)
        # 
        # return processed_data
        
        # 由于可能需要额外安装库，这里仅返回原始数据
        return video_data
    except Exception as e:
        print(f"视频处理错误: {str(e)}")
        return video_data

# 视频特效处理函数
def apply_video_effect(video_data, effect_type):
    """
    应用视频特效
    
    参数:
        video_data: 原始视频数据
        effect_type: 特效类型 ("black_white", "blur", "cartoon", "none")
        
    返回:
        处理后的视频数据
    """
    try:
        # 实际应用中需要使用专业的视频处理库
        # 如OpenCV实现各种特效
        # 
        # import cv2
        # import io
        # import numpy as np
        # from tempfile import NamedTemporaryFile
        # 
        # # 写入临时文件
        # with NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        #     f.write(video_data)
        #     temp_name = f.name
        # 
        # # 读取视频
        # cap = cv2.VideoCapture(temp_name)
        # 
        # # 获取原始视频参数
        # width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        # height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # fps = cap.get(cv2.CAP_PROP_FPS)
        # 
        # # 准备输出
        # fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        # output_file = temp_name + "_effect.mp4"
        # out = cv2.VideoWriter(output_file, fourcc, fps, (width, height))
        # 
        # while cap.isOpened():
        #     ret, frame = cap.read()
        #     if not ret:
        #         break
        #         
        #     # 应用不同效果
        #     if effect_type == "black_white":
        #         frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        #         frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        #     elif effect_type == "blur":
        #         frame = cv2.GaussianBlur(frame, (15, 15), 0)
        #     elif effect_type == "cartoon":
        #         # 简单的卡通效果
        #         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        #         gray = cv2.medianBlur(gray, 5)
        #         edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, 
        #                                    cv2.THRESH_BINARY, 9, 9)
        #         color = cv2.bilateralFilter(frame, 9, 300, 300)
        #         frame = cv2.bitwise_and(color, color, mask=edges)
        # 
        #     out.write(frame)
        # 
        # cap.release()
        # out.release()
        # 
        # # 读取处理后的视频
        # with open(output_file, 'rb') as f:
        #     processed_data = f.read()
        # 
        # # 清理临时文件
        # os.unlink(temp_name)
        # os.unlink(output_file)
        # 
        # return processed_data
        
        # 由于可能需要额外安装库，这里仅返回原始数据
        return video_data
    except Exception as e:
        print(f"视频特效处理错误: {str(e)}")
        return video_data
