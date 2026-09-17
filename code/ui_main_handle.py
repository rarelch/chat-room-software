# -*- coding: utf-8 -*-
#主要是各种消息的推送弹窗
import os
import base64
import html
import json
import uuid
import wave
from pathlib import Path
from datetime import datetime
import time

from PyQt5.QtCore import QUrl, QThread, pyqtSignal, Qt, QTimer, QSize
from PyQt5.QtGui import QFont, QTextCursor, QPixmap, QColor, QImage, QIcon
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QFileDialog, QMessageBox, QFormLayout, QListWidget, QListWidgetItem,
    QFrame, QScrollArea, QWidget, QGridLayout, QTextEdit, QGroupBox,
    QCheckBox, QComboBox, QRadioButton, QTabWidget, QProgressBar
)

from utils import send_data, MAX_FILE_SIZE, UPLOAD_DIR

# 处理接收到的消息
def handle_incoming_message(self, data):
    """处理来自服务器的数据"""
    try:
        action = data.get("action")
        
        # 好友和群聊列表更新
        if action == "friend_list":
            self.update_friend_list(data.get("friends", []))
        elif action == "group_list":
            self.update_group_list(data.get("groups", []))
        elif action == "friend_requests":
            self.update_friend_requests(data.get("requests", []))
        
        # 消息相关
        elif action in ("chat", "file", "voice", "video"):
            self.handle_message(data)
        elif action == "history":
            self.handle_history(data)
        
        # 好友相关通知
        elif action == "new_friend_request":
            self.handle_new_friend_request(data)
        elif action == "friend_request_update":
            self.handle_friend_request_update(data)
        elif action == "friend_deleted":
            self.handle_friend_deleted(data)
        elif action == "user_status":            
            self.update_user_status(data)
        elif action == "friend_request_result":
            self.handle_friend_request_result(data)
        elif action == "delete_friend_result":
            self.handle_delete_friend_result(data)
        
        # 群聊相关通知
        elif action == "group_member_joined":
            self.handle_group_member_joined(data)
        elif action == "group_member_left":
            self.handle_group_member_left(data)
        elif action == "group_disbanded":
            self.handle_group_disbanded(data)
        elif action == "role_updated":
            self.handle_role_updated(data)
        elif action == "removed_from_group":
            self.handle_removed_from_group(data)
        elif action == "group_members_updated":
            self.handle_group_members_updated(data)
        elif action == "create_group_result":
            # 转发给ui_main.py中的方法处理
            self.handle_create_group_result(data)
        elif action == "group_members_list":
            self.handle_group_members_list(data)
        elif action == "remove_member_result":
            self.handle_remove_member_result(data)
        
        # 头像相关
        elif action == "avatar_data":
            self.handle_avatar_data(data)
        elif action == "friend_avatar_updated":
            self.handle_friend_avatar_updated(data)
        
        # 通话相关
        elif action == "incoming_call":
            self.handle_incoming_call(data)
        elif action == "call_ringing":
            self.handle_call_ringing(data)
        elif action == "call_answered":
            self.handle_call_answered(data)
        elif action == "call_ended":
            self.handle_call_ended(data)
        elif action == "call_failed":
            self.handle_call_failed(data)
        elif action == "video_frame":
            self.handle_video_frame(data)
        elif action == "voice_frame":
            self.handle_voice_frame(data)
        
        # AI聊天相关
        elif action == "ai_response":
            self.handle_ai_response(data)
            
        # 账户管理相关
        elif action == "change_password_result":
            self.handle_change_password_result(data)
        elif action == "delete_account_result":
            self.handle_delete_account_result(data)
        
    except Exception as e:
        print(f"处理消息错误: {str(e)}")
        import traceback
        traceback.print_exc()

# 更新好友列表界面
def update_friend_list(self, friends):
    """更新好友列表界面"""
    print(f"更新好友列表: {friends}")
    self.friends = friends
    self.friend_list.clear()
    
    for friend in friends:
        item = QListWidgetItem(friend)
        self.friend_list.addItem(item)
    
    print(f"好友列表更新完成，当前有 {len(friends)} 个好友")

# 更新群聊列表界面
def update_group_list(self, groups):
    """更新群聊列表界面"""
    self.groups = groups
    self.group_list.clear()
    
    for group in groups:
        group_id = group.get("group_id")
        group_name = group.get("group_name")
        role = group.get("role")
        
        # 显示群名加角色
        display_name = f"{group_name} ({role})"
        item = QListWidgetItem(display_name)
        item.setData(Qt.UserRole, group_id)
        self.group_list.addItem(item)

# 更新好友请求列表
def update_friend_requests(self, requests):
    """更新好友请求列表"""
    print(f"更新好友请求列表: {requests}")
    self.friend_requests = requests
    
    # 如果有新请求且数量>0，显示提示
    if requests and len(requests) > 0:
        count = len(requests)
        QMessageBox.information(self, "好友请求", f"您有 {count} 个新的好友请求")
    
    print(f"好友请求列表更新完成，当前有 {len(requests)} 个请求")

# 处理聊天消息
def handle_message(self, data):
    """处理接收到的聊天消息"""
    sender = data.get("from")
    target = data.get("to")
    is_group = data.get("is_group", False)
    is_anonymous = data.get("is_anonymous", False)
    anonymous_name = data.get("anonymous_name")
    
    # 确定会话ID
    chat_id = target if is_group else sender
    
    # 处理匿名消息
    if is_anonymous:
        display_name = anonymous_name or "匿名用户"
    else:
        display_name = sender
    
    # 消息内容处理
    if data["action"] == "chat":
        msg_type = data.get("type", "text")
        content = data.get("content", "")
        
        if msg_type == "text":
            html_content = f"{display_name}: {html.escape(content)}"
        elif msg_type == "emoji":
            html_content = f"{display_name}: {content}"  # 表情符号不需要转义
    
    elif data["action"] == "file":
        filename = data.get("filename", "")
        
        # 保存文件到本地
        file_path = self.save_received_file(data)
        
        if file_path:
            # 使用 _uri 方法确保正确的文件 URI 格式
            file_uri = self._uri(file_path)
            # 构建文件链接
            file_link = f'<a href="{file_uri}">{html.escape(filename)}</a>'
            html_content = f"{display_name}: [文件] {file_link}"
            
            # 如果是图片，添加缩略图
            if self.is_image_file(filename):
                thumb_html = f'<br><a href="{file_uri}"><img src="{file_uri}" width="200" height="auto"></a>'
                html_content += thumb_html
        else:
            # 文件保存失败的情况
            html_content = f"{display_name}: [文件] {html.escape(filename)} (保存失败)"
    
    elif data["action"] == "voice":
        filename = data.get("filename", "")
        duration = data.get("duration", 0)
        
        # 保存语音文件
        file_path = self.save_received_file(data, "voice")
        
        if file_path:
            # 构建语音播放链接
            file_uri = self._uri(file_path)
            voice_link = f'<a href="{file_uri}">[点击播放] {duration}秒</a>'
            html_content = f"{display_name}: [语音] {voice_link}"
        else:
            html_content = f"{display_name}: [语音消息] (保存失败)"
    
    elif data["action"] == "video":
        filename = data.get("filename", "")
        duration = data.get("duration", 0)
        
        # 保存视频文件
        file_path = self.save_received_file(data, "video")
        
        if file_path:
            # 构建视频播放链接
            file_uri = self._uri(file_path)
            video_link = f'<a href="{file_uri}">[点击播放] {duration}秒</a>'
            html_content = f"{display_name}: [视频] {video_link}"
        else:
            html_content = f"{display_name}: [视频消息] (保存失败)"
        
        # 如果有缩略图，显示缩略图
        thumbnail = data.get("thumbnail")
        if thumbnail:
            thumb_path = self.save_thumbnail(thumbnail, filename)
            thumb_html = f'<br><a href="file:///{file_path}"><img src="file:///{thumb_path}" width="200"></a>'
            html_content += thumb_html
    
    # 添加到会话历史
    self.append_message(chat_id, html_content)
    
    # 如果当前不是此会话，显示提醒
    if self.current_chat_target != chat_id:
        # 这里可以添加系统通知或者改变联系人列表中的样式
        pass

# 处理历史消息
def handle_history(self, data):
    """处理历史消息记录"""
    target = data.get("target")
    is_group = data.get("is_group", False)
    messages = data.get("messages", [])
    
    # 清空当前会话历史
    self.convs[target] = []
    
    # 处理每条历史消息
    for msg in messages:
        sender = msg.get("from")
        msg_type = msg.get("type")
        is_anonymous = msg.get("is_anonymous", False)
        anonymous_name = msg.get("anonymous_name")
        # 获取原始时间戳
        original_timestamp = msg.get("time")
        
        # 计算显示名称
        if is_anonymous:
            display_name = anonymous_name or "匿名用户"
        elif sender == self.username:
            display_name = "我"
        else:
            display_name = sender
        
        # 根据消息类型构建HTML
        if msg_type in ("text", "emoji"):
            content = msg.get("content", "")
            if msg_type == "text":
                html_content = f"{display_name}: {html.escape(content)}"
            else:
                html_content = f"{display_name}: {content}"  # 表情符号不需要转义
        
        elif msg_type == "file":
            filename = msg.get("filename", "")
            # 文件可能不在本地
            file_path = self.downloads_dir / filename
            if file_path.exists():
                file_uri = self._uri(file_path)
                file_link = f'<a href="{file_uri}">{html.escape(filename)}</a>'
                html_content = f"{display_name}: [文件] {file_link}"
                
                # 如果是图片，添加缩略图
                if self.is_image_file(filename):
                    thumb_html = f'<br><a href="{file_uri}"><img src="{file_uri}" width="200"></a>'
                    html_content += thumb_html
            else:
                html_content = f"{display_name}: [文件] {html.escape(filename)} (文件不在本地)"
        
        elif msg_type == "voice":
            filename = msg.get("filename", "")
            file_path = self.downloads_dir / "voice" / filename
            if file_path.exists():
                file_uri = self._uri(file_path)
                voice_link = f'<a href="{file_uri}">[点击播放]</a>'
                html_content = f"{display_name}: [语音] {voice_link}"
            else:
                html_content = f"{display_name}: [语音] (文件不在本地)"
        
        elif msg_type == "video":
            filename = msg.get("filename", "")
            file_path = self.downloads_dir / "video" / filename
            if file_path.exists():
                file_uri = self._uri(file_path)
                video_link = f'<a href="{file_uri}">[点击播放]</a>'
                html_content = f"{display_name}: [视频] {video_link}"
            else:
                html_content = f"{display_name}: [视频] (文件不在本地)"
        
        else:
            html_content = f"{display_name}: [未知消息类型]"
        
        # 添加到会话历史，并传入原始时间戳
        self.append_message(target, html_content, refresh=False, timestamp=original_timestamp)
    
    # 刷新显示
    if self.current_chat_target == target:
        self.refresh_chat_view()

# 辅助函数 - 判断是否为图片文件
def is_image_file(self, filename):
    """判断文件是否为图片"""
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')
    return filename.lower().endswith(image_extensions)

# 辅助函数 - 保存接收到的文件
def save_received_file(self, data, file_type="file"):
    """保存接收到的文件"""
    filename = data.get("filename", "")
    content_b64 = data.get("content", "")
    
    if not content_b64:
        return None
    
    # 根据文件类型选择保存目录
    if file_type == "voice":
        save_dir = self.downloads_dir / "voice"
    elif file_type == "video":
        save_dir = self.downloads_dir / "video"
    else:
        save_dir = self.downloads_dir
    
    save_dir.mkdir(exist_ok=True)
    file_path = save_dir / filename
    
    try:
        # 解码文件内容
        decoded_data = base64.b64decode(content_b64)
        
        # 对于语音文件，确保创建正确的WAV文件
        if file_type == "voice" and filename.lower().endswith('.wav'):
            import wave
            # 获取音频参数（使用与录音相同的参数）
            channels = 1
            sample_width = 2  # 16位音频
            framerate = 16000
            
            # 创建WAV文件（包含正确的文件头）
            with wave.open(str(file_path), 'wb') as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(sample_width)
                wf.setframerate(framerate)
                wf.writeframes(decoded_data)
        else:
            # 其他类型文件直接保存
            with open(file_path, "wb") as f:
                f.write(decoded_data)
                
        # 返回字符串形式的规范化路径
        return str(file_path.absolute())
    except Exception as e:
        print(f"保存文件错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

# 辅助函数 - 保存视频缩略图
def save_thumbnail(self, thumbnail_b64, video_filename):
    """保存视频缩略图"""
    if not thumbnail_b64:
        return None
    
    thumb_dir = self.downloads_dir / "thumbnails"
    thumb_dir.mkdir(exist_ok=True)
    
    # 生成缩略图文件名
    base_name = os.path.splitext(video_filename)[0]
    thumb_path = thumb_dir / f"{base_name}_thumb.jpg"
    
    try:
        # 解码并保存缩略图
        with open(thumb_path, "wb") as f:
            f.write(base64.b64decode(thumbnail_b64))
        return thumb_path
    except Exception as e:
        print(f"保存缩略图错误: {str(e)}")
        return None

# 辅助函数 - 向会话添加消息
def append_message(self, chat_id, html_content, refresh=True, timestamp=None):
    """向会话历史添加消息"""
    if chat_id not in self.convs:
        self.convs[chat_id] = []
    
    # 添加时间戳，如果没有提供时间戳，使用当前时间
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_with_time = f'<div style="margin-bottom: 8px;"><span style="color: #999; font-size: 0.8em;">{timestamp}</span><br>{html_content}</div>'
    
    self.convs[chat_id].append(html_with_time)
    
    # 如果是当前会话，刷新显示
    if refresh and self.current_chat_target == chat_id:
        self.chat_view.moveCursor(QTextCursor.End)
        self.chat_view.insertHtml(html_with_time)
        self.chat_view.moveCursor(QTextCursor.End)

# 辅助函数 - 刷新聊天界面
def refresh_chat_view(self):
    """刷新当前聊天界面"""
    if not self.current_chat_target:
        return
    
    self.chat_view.clear()
    
    for html_content in self.convs.get(self.current_chat_target, []):
        self.chat_view.insertHtml(html_content)
    
    # 滚动到底部
    self.chat_view.moveCursor(QTextCursor.End)

# 好友相关处理
def handle_new_friend_request(self, data):
    """处理新的好友请求通知"""
    request = data.get("request", {})
    from_user = request.get("from_user", "")
    message = request.get("message", "")
    
    self.friend_requests.append(request)
    
    # 显示通知
    QMessageBox.information(
        self, 
        "新的好友请求", 
        f"用户 {from_user} 请求添加您为好友:\n{message}"
    )

def handle_friend_request_update(self, data):
    """处理好友请求更新的响应"""
    from_user = data.get("from", "")
    accepted = data.get("accepted", False)
    
    print(f"收到好友请求处理结果: from={from_user}, accepted={accepted}")
    
    # 根据结果显示不同消息
    if accepted:
        QMessageBox.information(self, "好友请求", f"{from_user} 已接受您的好友请求")
        
        # 主动更新好友列表，将对方添加为好友
        if from_user not in self.friends:
            print(f"将 {from_user} 添加到好友列表")
            self.friends.append(from_user)
            self.friend_list.clear()
            for friend in self.friends:
                item = QListWidgetItem(friend)
                self.friend_list.addItem(item)
            print(f"好友列表更新完成，当前有 {len(self.friends)} 个好友")
        else:
            print(f"{from_user} 已经在好友列表中，无需添加")
    else:
        QMessageBox.information(self, "好友请求", f"{from_user} 已拒绝您的好友请求")

def handle_friend_deleted(self, data):
    """处理被好友删除通知"""
    by_user = data.get("by_user", "")
    
    QMessageBox.information(
        self, 
        "好友关系解除", 
        f"{by_user} 已将您从好友列表中删除"
    )
    
    # 添加到被删除好友列表，防止继续发送消息
    self.deleted_by_friends.add(by_user)
    print(f"用户 {by_user} 已将您删除，已添加到deleted_by_friends列表")
    
    # 从好友列表中移除
    if by_user in self.friends:
        self.friends.remove(by_user)
        # 更新UI
        self.friend_list.clear()
        for f in self.friends:
            self.friend_list.addItem(QListWidgetItem(f))
        
        # 如果正在聊天的对象是删除自己的好友，则清空聊天区域
        if self.current_chat_target == by_user and not self.is_group_chat:
            self.current_chat_target = None
            self.chat_title.setText("当前未选择聊天")
            self.chat_view.clear()
            self.chat_view.setHtml('<p style="text-align:center;">对方已将您从好友列表中删除，聊天记录已关闭</p>')

def update_user_status(self, data):
    """更新好友在线状态"""
    username = data.get("username", "")
    status = data.get("status", "offline")
    
    # 不再使用颜色显示在线状态
    pass

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
        else:
            QMessageBox.warning(self, "删除失败", f"删除好友失败: {message}")
    except Exception as e:
        print(f"处理删除好友结果错误: {str(e)}")
        QMessageBox.warning(self, "删除好友", "处理删除好友结果时出错")

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

# 群聊相关处理
def handle_group_member_joined(self, data):
    """处理群成员加入通知"""
    group_id = data.get("group_id", "")
    group_name = data.get("group_name", "")
    username = data.get("username", "")
    
    # 添加系统消息到群聊历史
    system_msg = f'<span style="color: #666;">[系统] 用户 {username} 加入了群聊</span>'
    self.append_message(group_id, system_msg)

def handle_group_member_left(self, data):
    """处理群成员退出通知"""
    group_id = data.get("group_id", "")
    group_name = data.get("group_name", "")
    username = data.get("username", "")
    
    # 添加系统消息到群聊历史
    system_msg = f'<span style="color: #666;">[系统] 用户 {username} 退出了群聊</span>'
    self.append_message(group_id, system_msg)

def handle_group_disbanded(self, data):
    """处理群聊被解散通知"""
    group_id = data.get("group_id", "")
    group_name = data.get("group_name", "")
    by_user = data.get("by_user", "")
    
    # 弹窗通知
    QMessageBox.information(
        self, 
        "群聊已解散", 
        f"群聊 {group_name} 已被 {by_user} 解散"
    )
    
    # 如果当前正在查看这个群聊，显示提示并切换到无会话状态
    if self.current_chat_target == group_id:
        self.current_chat_target = None
        self.is_group_chat = False
        self.chat_title.setText("当前群聊已解散")
        self.chat_view.clear()
        self.chat_view.setHtml('<p style="color: red; text-align: center;">该群聊已被解散</p>')

def handle_role_updated(self, data):
    """处理群内角色更新通知"""
    group_id = data.get("group_id", "")
    group_name = data.get("group_name", "")
    new_role = data.get("new_role", "")
    by_user = data.get("by_user", "")
    
    # 弹窗通知
    QMessageBox.information(
        self, 
        "群聊角色已更新", 
        f"在群聊 {group_name} 中，您的角色已被 {by_user} 更新为 {new_role}"
    )
    
    # 添加系统消息到群聊历史
    system_msg = f'<span style="color: #666;">[系统] 您的角色已被更新为 {new_role}</span>'
    self.append_message(group_id, system_msg)

def handle_removed_from_group(self, data):
    """处理被踢出群聊通知"""
    group_id = data.get("group_id", "")
    group_name = data.get("group_name", "")
    by_user = data.get("by_user", "")
    
    # 弹窗通知
    QMessageBox.information(
        self, 
        "已被移出群聊", 
        f"您已被 {by_user} 从群聊 {group_name} 中移除"
    )
    
    # 如果当前正在查看这个群聊，显示提示并切换到无会话状态
    if self.current_chat_target == group_id:
        self.current_chat_target = None
        self.is_group_chat = False
        self.chat_title.setText("当前无聊天")
        self.chat_view.clear()
        self.chat_view.setHtml('<p style="color: red; text-align: center;">您已被移出该群聊</p>')

def handle_group_members_updated(self, data):
    """处理群成员列表更新"""
    # 在实际应用中，可以更新缓存的群成员列表
    pass

def handle_remove_member_result(self, data):
    """处理移除群成员的结果"""
    try:
        success = data.get("success", False)
        message = data.get("message", "")
        group_id = data.get("group_id", "")
        target = data.get("target", "")
        
        if success:
            QMessageBox.information(self, "移除成员", f"已成功将 {target} 移出群聊")
            
            # 如果有缓存的成员列表，也同步更新
            if hasattr(self, 'group_members') and group_id in self.group_members:
                self.group_members[group_id] = [m for m in self.group_members[group_id] 
                                              if m.get('username') != target]
                
            # 添加系统消息到群聊
            system_msg = f'<span style="color: #666;">[系统] 成员 {target} 已被您移出群聊</span>'
            self.append_message(group_id, system_msg)
        else:
            QMessageBox.warning(self, "移除失败", f"移除成员失败: {message}")
    except Exception as e:
        print(f"处理移除成员结果错误: {str(e)}")
        QMessageBox.warning(self, "移除成员", "处理移除成员结果时出错")

# 通话相关处理
def handle_incoming_call(self, data):
    """处理来电请求"""
    from_user = data.get("from_user", "")
    call_type = data.get("call_type", "voice")
    
    # 询问用户是否接受通话
    reply = QMessageBox.question(
        self,
        f"来电 - {call_type}通话",
        f"{from_user} 请求与您进行{call_type}通话，是否接受？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    # 发送响应
    accepted = (reply == QMessageBox.Yes)
    send_data(self.sock, {
        "action": "call_response",
        "to_user": from_user,
        "accepted": accepted
    })
    
    # 如果接受，启动通话
    if accepted:
        if call_type == "voice":
            self.start_voice_call_session(from_user)
        else:
            self.start_video_call_session(from_user)

def handle_call_ringing(self, data):
    """处理呼叫正在振铃通知"""
    # 可以显示"正在振铃"状态
    pass

def handle_call_answered(self, data):
    """处理通话应答"""
    from_user = data.get("from_user", "")
    accepted = data.get("accepted", False)
    
    if accepted:
        # 对方接受通话，启动通话会话
        QMessageBox.information(self, "通话已接通", f"{from_user} 已接受您的通话请求")
        
        # 检查当前通话类型
        if hasattr(self, "current_call_type") and self.current_call_type == "video":
            self.start_video_call_session(from_user)
        else:
            self.start_voice_call_session(from_user)
    else:
        # 对方拒绝通话
        QMessageBox.information(self, "通话已拒绝", f"{from_user} 拒绝了您的通话请求")

def handle_call_ended(self, data):
    """处理通话结束"""
    from_user = data.get("from_user", "")
    
    # 结束当前通话
    self.handle_call_failed(data)

def handle_call_failed(self, data):
    """处理通话失败"""
    from_user = data.get("from_user", "")
    reason = data.get("reason", "未知原因")
    
    # 显示通话失败提示
    QMessageBox.warning(self, "通话失败", f"与 {from_user} 的通话失败: {reason}")
    
    # 如果有通话线程正在运行，停止它
    if hasattr(self, 'voice_call_thread') and self.voice_call_thread and self.voice_call_thread.isRunning():
        self.voice_call_thread.stop()
        
    if hasattr(self, 'video_call_thread') and self.video_call_thread and self.video_call_thread.isRunning():
        self.video_call_thread.stop()

# AI聊天相关
def handle_ai_response(self, data):
    """处理AI聊天响应"""
    # 实现AI聊天响应的处理逻辑
    pass

# 处理修改密码响应
def handle_change_password_result(self, data):
    """处理修改密码结果"""
    success = data.get("success", False)
    message = data.get("message", "")
    
    if success:
        QMessageBox.information(self, "修改密码", "密码修改成功！")
    else:
        QMessageBox.warning(self, "修改密码失败", message or "密码修改失败，请重试")

# 处理注销账户响应
def handle_delete_account_result(self, data):
    """处理注销账号结果"""
    success = data.get("success", False)
    message = data.get("message", "")
    
    if success:
        QMessageBox.information(self, "账号注销", message or "账号已成功注销")
        # 关闭应用程序
        self.close()
    else:
        QMessageBox.warning(self, "注销失败", message or "注销账号失败")

@staticmethod
def _uri(path):
    """将本地路径转换为标准 file:// URI 格式"""
    return QUrl.fromLocalFile(path).toString()

def handle_video_frame(self, data):
    """处理接收到的视频帧"""
    try:
        from_user = data.get("from_user")
        frame_data = data.get("frame")
        
        # 记录接收到的视频帧
        frame_size = len(frame_data) if frame_data else 0
        print(f"收到视频帧: 来自={from_user}, 大小={frame_size}字节")
        
        # 检查是否正在视频通话
        if not hasattr(self, "video_call_thread") or not self.video_call_thread or not self.video_call_thread.isRunning():
            print(f"没有活跃的视频通话线程，忽略来自 {from_user} 的视频帧")
            return
            
        # 验证发送方是否是当前通话对象
        if self.video_call_thread.target_user != from_user:
            print(f"收到非当前通话对象的视频帧: {from_user} != {self.video_call_thread.target_user}")
            return
            
        # 处理视频帧
        if frame_data:
            print(f"正在处理来自 {from_user} 的视频帧...")
            self.video_call_thread.process_remote_frame(frame_data)
            print("视频帧处理完成")
        else:
            print(f"收到来自 {from_user} 的空视频帧")
    except Exception as e:
        print(f"处理视频帧错误: {str(e)}")
        import traceback
        traceback.print_exc()

def handle_voice_frame(self, data):
    """处理接收到的语音帧"""
    try:
        from_user = data.get("from_user")
        audio_data = data.get("audio")
        timestamp = data.get("timestamp", 0)
        
        # 记录接收到的语音帧
        audio_size = len(audio_data) if audio_data else 0
        print(f"收到语音帧: 来自={from_user}, 大小={audio_size}字节, 时间戳={timestamp}")
        
        # 检查是否正在语音通话
        if not hasattr(self, "voice_call_thread") or not self.voice_call_thread or not self.voice_call_thread.isRunning():
            print(f"没有活跃的语音通话线程，忽略来自 {from_user} 的语音帧")
            return
            
        # 验证发送方是否是当前通话对象
        if self.voice_call_thread.target_user != from_user:
            print(f"收到非当前通话对象的语音帧: {from_user} != {self.voice_call_thread.target_user}")
            return
            
        # 处理语音帧
        if audio_data:
            print(f"正在处理来自 {from_user} 的语音帧，数据长度={len(audio_data)}...")
            try:
                # 解码Base64数据
                from audio_utils import base64_to_audio, calculate_audio_level
                decoded_audio = base64_to_audio(audio_data)
                
                if decoded_audio:
                    # 检查解码后的音频数据
                    level = calculate_audio_level(decoded_audio, 2)
                    print(f"解码后的音频数据长度={len(decoded_audio)}字节，音量级别={level}%")
                    
                    # 交给语音线程处理
                    self.voice_call_thread.process_remote_audio(decoded_audio)
                    print("语音帧处理完成")
                else:
                    print(f"Base64解码失败，无法处理来自 {from_user} 的音频帧")
            except Exception as e:
                print(f"解码或处理音频帧时出错: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print(f"收到来自 {from_user} 的空语音帧")
    except Exception as e:
        print(f"处理语音帧错误: {str(e)}")
        import traceback
        traceback.print_exc()