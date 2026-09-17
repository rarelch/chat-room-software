# -*- coding: utf-8 -*-
"""音频处理工具模块"""
#语音的采集功能
#变音功能
#音频数据和编码字符串的相互转化
import base64
import numpy as np

def calculate_audio_level(audio_data, sample_width=2):#计算音频音量级别，把声音转换为numpy数组采用对数映射使其对小音频也能灵敏捕捉
    """计算音频数据的音量级别(0-100)"""
    if not audio_data:
        return 0
    
    try:
        # 将字节数据转换为numpy数组
        if sample_width == 2:  # 16位音频
            samples = np.frombuffer(audio_data, dtype=np.int16)
        elif sample_width == 4:  # 32位音频
            samples = np.frombuffer(audio_data, dtype=np.int32)
        else:  # 默认8位音频
            samples = np.frombuffer(audio_data, dtype=np.uint8)
        
        # 计算均方根(RMS)振幅作为音量的估算
        if len(samples) > 0:
            rms = np.sqrt(np.mean(np.square(samples.astype(np.float32))))            # 将RMS映射到0-100的范围，使用对数映射使小信号更明显
            if sample_width == 2:
                # 16位音频的最大振幅是32767
                # 使用更敏感的映射，让较小的声音也能显示
                normalized_rms = rms / 32767.0  # 归一化到0-1
                if normalized_rms > 0:
                    # 对数映射，使小信号更明显
                    level = min(100, max(0, int(50 * (1 + np.log10(normalized_rms * 10)))))
                else:
                    level = 0
            elif sample_width == 4:
                # 32位音频的最大振幅是2147483647
                normalized_rms = rms / 2147483647.0
                if normalized_rms > 0:
                    level = min(100, max(0, int(50 * (1 + np.log10(normalized_rms * 10)))))
                else:
                    level = 0
            else:
                # 8位音频的最大振幅是255
                normalized_rms = rms / 255.0
                if normalized_rms > 0:
                    level = min(100, max(0, int(50 * (1 + np.log10(normalized_rms * 10)))))
                else:
                    level = 0
            return level
    except Exception as e:
        print(f"计算音频级别时出错: {e}")
    
    return 0

def apply_voice_effect(audio_data, effect_type="normal", sample_width=2):#语音特效功能
    """应用语音特效"""
    if not audio_data or effect_type == "normal":
        return audio_data
    
    try:
        # 将字节数据转换为numpy数组
        if sample_width == 2:  # 16位音频
            samples = np.frombuffer(audio_data, dtype=np.int16)
        elif sample_width == 4:  # 32位音频
            samples = np.frombuffer(audio_data, dtype=np.int32)
        else:  # 默认8位音频
            samples = np.frombuffer(audio_data, dtype=np.uint8)
        
        # 应用不同的音频效果
        if effect_type == "robot":
            # 机器人音效 - 通过添加失真和量化效果
            scale = 0.3
            samples = samples * (1 - scale + scale * np.sin(samples / 32767 * np.pi))
            # 量化效果
            samples = (samples / 2000).astype(np.int32) * 2000
            
        elif effect_type == "chipmunk":
            # 花栗鼠音效 - 通过舍弃一半样本点来实现音调提高
            # 注意：这种方法会改变音频长度，实际应用中应使用更复杂的算法
            half_len = len(samples) // 2
            samples = np.repeat(samples[:half_len], 2)
            
        elif effect_type == "deep":
            # 低沉音效 - 通过重复每个样本点来降低音调
            samples = samples[::2]
            samples = np.repeat(samples, 2)
            
        elif effect_type == "male":
            # 男性变音 - 降低音调和增加低频
            # 降低音调
            samples = samples[::3]
            samples = np.repeat(samples, 3)
            # 增加一些低频共振以增强男性声音特性
            if len(samples) > 0:
                # 简单增强低频
                scale_factor = 1.2
                samples = np.int16(np.clip(samples * scale_factor, -32768, 32767))
                
        elif effect_type == "female":
            # 女性变音 - 提高音调并调整音色
            # 提高音调 (比花栗鼠效果温和)
            segment_length = 3
            resampled = []
            for i in range(0, len(samples), segment_length):
                segment = samples[i:i+segment_length]
                if len(segment) > 0:
                    # 保留部分原始样本
                    resampled.extend([segment[0]])
            samples = np.array(resampled, dtype=np.int16)
            # 增加高频成分
            if len(samples) > 0:
                # 简单的音色调整
                samples = samples.astype(np.float32)
                samples = np.int16(np.clip(samples * 1.15, -32768, 32767))
        
        # 转回字节数据
        if sample_width == 2:
            return samples.astype(np.int16).tobytes()
        elif sample_width == 4:
            return samples.astype(np.int32).tobytes()
        else:
            return samples.astype(np.uint8).tobytes()
            
    except Exception as e:
        print(f"应用语音特效时出错: {e}")
        return audio_data

def audio_to_base64(audio_data):
    """将音频数据转换为Base64编码字符串"""
    if not audio_data:
        return ""
    try:
        return base64.b64encode(audio_data).decode('utf-8')
    except Exception as e:
        print(f"音频转Base64时出错: {e}")
        return ""

def base64_to_audio(base64_str):
    """将Base64编码字符串转换为音频数据"""
    if not base64_str:
        print("警告: 收到空的base64字符串")
        return None
    try:
        audio_data = base64.b64decode(base64_str)
        print(f"Base64解码成功，音频数据大小: {len(audio_data)}字节")
        return audio_data
    except Exception as e:
        print(f"Base64转音频时出错: {e}")
        import traceback
        traceback.print_exc()
        return None
