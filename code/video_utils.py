import cv2
import numpy as np
import base64
import json
import socket
import time
from PyQt5.QtGui import QImage

def cv_to_qimage(cv_image):
    """
    将OpenCV图像转换为QImage
    
    参数:
        cv_image: OpenCV格式的图像 (numpy.ndarray)
    返回:
        QImage对象
    """
    height, width, channels = cv_image.shape
    bytes_per_line = channels * width
    # 将BGR转换为RGB
    cv_image_rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
    return QImage(cv_image_rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)

def qimage_to_cv(qimage):
    """
    将QImage转换为OpenCV图像
    
    参数:
        qimage: QImage对象
    返回:
        OpenCV格式的图像 (numpy.ndarray)
    """
    width = qimage.width()
    height = qimage.height()
    
    # 将QImage转换为numpy array
    ptr = qimage.constBits()
    ptr.setsize(qimage.byteCount())
    arr = np.array(ptr).reshape(height, width, 4)  # 4 通道，RGBA
    
    # 转换为BGR格式
    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

def adjust_video_resolution(frame, resolution):
    """
    调整视频帧的分辨率
    
    参数:
        frame: OpenCV格式的图像帧
        resolution: 目标分辨率 ("low", "medium", "high", "hd")
    
    返回:
        调整后的帧
    """
    from utils import VIDEO_RESOLUTIONS
    
    # 获取目标分辨率
    target_width, target_height = VIDEO_RESOLUTIONS.get(resolution, (640, 480))
    
    # 调整分辨率
    return cv2.resize(frame, (target_width, target_height))

def apply_video_effect(frame, effect):#视频特效
    """
    应用视频特效
    
    参数:
        frame: OpenCV格式的图像帧
        effect: 特效名称 ("none", "gray", "binary", "edge", "blur")
    
    返回:
        处理后的帧
    """
    if effect == "none":
        return frame
    
    elif effect == "gray":
        # 灰度化 把RGB三通道转换成单通道
        return cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    
    elif effect == "binary":
        # 二值化 灰度化之后找一个阈值
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)
    
    elif effect == "edge":
        # 边缘检测 Canny边缘检测算法
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
    
    elif effect == "blur":
        # 模糊 高斯模糊
        return cv2.GaussianBlur(frame, (15, 15), 0)
    
    # 如果是未知效果，返回原始帧
    return frame

def compress_frame(frame, quality=50):
    """
    压缩视频帧为JPEG格式
    
    参数:
        frame: OpenCV格式的图像帧
        quality: JPEG压缩质量 (0-100)
    
    返回:
        压缩后的字节数据
    """
    # 设置JPEG压缩参数
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    
    # 压缩为JPEG
    _, buffer = cv2.imencode('.jpg', frame, encode_param)
    
    return buffer

def frame_to_base64(frame, quality=50):
    """
    将图像帧转换为base64编码
    
    参数:
        frame: OpenCV格式的图像帧
        quality: JPEG压缩质量 (0-100)
    
    返回:
        base64编码的字符串
    """
    compressed = compress_frame(frame, quality)
    return base64.b64encode(compressed).decode('utf-8')

def base64_to_frame(base64_str):
    """
    将base64编码的字符串转换为图像帧
    
    参数:
        base64_str: base64编码的字符串
    
    返回:
        OpenCV格式的图像帧
    """
    # 解码base64
    img_data = base64.b64decode(base64_str)
    
    # 将字节数据转换为numpy数组
    nparr = np.frombuffer(img_data, np.uint8)
    
    # 解码图像
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
