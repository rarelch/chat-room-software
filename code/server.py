# -*- coding: utf-8 -*-
#核心服务端，负责所有客户端连接的管理、网络请求的分发与处理、实时消息的转发，是连接客户端和数据库的中间层。它不直接操作数据库表结构，而是调用 db.py 提供的接口完成数据持久化，同时实现了所有需要实时交互的功能。
#TCP 多线程服务器
#监听 8888 端口，接受客户端连接
#每个客户端连接创建一个独立的守护线程，互不干扰
#管理所有在线用户的 socket 连接（online_users 字典）
#网络协议处理，基于 JSON 格式的自定义通信协议，统一的消息收发接口（调用 utils.py 的 recv_data/send_data），所有客户端请求的路由分发（根据 action 字段调用不同处理函数）
#实时消息转发
#实时状态同步
#文件上传处理
#音视频通话信令处理
#连接与资源管理
import logging
import os
import socket
import threading
import base64
import json
import wave
from pathlib import Path
from utils import recv_data, send_data, MAX_FILE_SIZE, UPLOAD_DIR
from db import (
    init_db, check_login, register_user, save_message, get_history, delete_user,
    # 好友相关接口
    send_friend_request, get_friend_requests, handle_friend_request, 
    get_friends, delete_friend, get_request_id_by_users,
    # 群聊相关接口
    create_group, join_group, leave_group, get_user_groups, get_group_members,
    update_member_role, disband_group, get_group_info, remove_group_member,
    # 用户相关接口
    update_avatar, get_avatar,
    # send_group_join_request, get_group_join_requests, handle_group_join_request
)

# ---------------------------------------------------------------------------#
# logging 配置
# ---------------------------------------------------------------------------#
LOG_DIR = Path(__file__).with_name("logs")
LOG_DIR.mkdir(exist_ok=True)
# log函数打印日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "chat_server.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ChatServer")

# ---------------------------------------------------------------------------#
# 常量
# ---------------------------------------------------------------------------#
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8888
UPLOAD_DIR.mkdir(exist_ok=True)

# 在线用户映射表
online_users: dict[str, socket.socket] = {}
online_lock = threading.Lock()

# 用户-群聊映射表，提高消息广播效率
user_groups: dict[str, list[str]] = {}
groups_lock = threading.Lock()

# ---------------------------------------------------------------------------#
# 客户端线程
# ---------------------------------------------------------------------------#
class ClientThread(threading.Thread):
    def __init__(self, conn: socket.socket, addr):
        super().__init__(daemon=True) # 加入守护线程或者线程分离
        self.conn = conn
        self.addr = addr          # (ip, port)
        self.username: str | None = None
        self.log = logging.getLogger(f"Client-{addr[0]}:{addr[1]}")

    # ---------------- 线程主入口 ----------------
    def run(self):
        self.log.info("新连接")
        try:
            if not self._auth_loop():
                return
            self._chat_loop()
        finally:
            self._cleanup()

    # ---------------- 注册、确认  ----------------
    def _auth_loop(self) -> bool:
        while True:
            data = recv_data(self.conn)
            if data is None:
                return False
            
            act = data.get("action")
            if act == "login":
                ok, err = check_login(data["username"], data["password"])
                if ok:
                    with online_lock:
                        if data["username"] in online_users:
                            ok, err = False, "该用户已在别处登录"
                send_data(self.conn, {"action": "login_result", "success": ok, "error": err})
                if ok:
                    self.username = data["username"]
                    with online_lock:
                        online_users[self.username] = self.conn
                    
                    # 登录后获取好友列表
                    friends = get_friends(self.username)
                    send_data(self.conn, {"action": "friend_list", "friends": friends})
                    
                    # 登录后获取群聊列表
                    groups = get_user_groups(self.username)
                    send_data(self.conn, {"action": "group_list", "groups": groups})
                    
                    # 登录后获取好友请求列表
                    friend_requests = get_friend_requests(self.username)
                    send_data(self.conn, {"action": "friend_requests", "requests": friend_requests})
                    
                    # 获取用户头像
                    avatar_data = get_avatar(self.username)
                    if avatar_data:
                        send_data(self.conn, {"action": "avatar_data", "user": self.username, "avatar": avatar_data})
                    
                    self.log.info("用户登录 · username=%s", self.username)
                    self._broadcast_user_status(True)  # 广播上线状态
                    return True
                else:
                    self.log.warning("登录失败: %s", err)
            elif act == "register":
                # 处理注册请求，支持头像
                avatar_data = data.get("avatar")
                ok, err = register_user(data["username"], data["password"], avatar_data)
                send_data(self.conn, {"action": "register_result", "success": ok, "error": err})
                msg = "success" if ok else f"fail({err})"
                self.log.info("注册尝试 %s · username=%s", msg, data["username"])

    # ---------------- 聊天主循环 ----------------
    def _chat_loop(self):
        while True:
            data = recv_data(self.conn)
            if data is None:
                break
                
            act = data.get("action")
            
            # 消息相关
            if act in ("chat", "file", "voice", "video"):
                self._handle_message(data)
            
            # 历史消息获取
            elif act == "get_history":
                is_group = data.get("is_group", False)
                history = get_history(self.username, data.get("target"), is_group)
                send_data(self.conn, {
                    "action": "history", 
                    "target": data.get("target"), 
                    "is_group": is_group,
                    "messages": history
                })
            
            # 好友相关
            elif act == "send_friend_request":
                to_user = data.get("to_user")
                message = data.get("message", "")
                ok, msg = send_friend_request(self.username, to_user, message)
                send_data(self.conn, {
                    "action": "friend_request_result",
                    "success": ok,
                    "message": msg
                })
                
                # 如果对方在线，通知有新好友请求
                if ok and to_user in online_users:
                    try:
                        req = {
                            "from_user": self.username,
                            "message": message,
                            "request_time": "just now"  # 客户端会更新显示
                        }
                        send_data(online_users[to_user], {
                            "action": "new_friend_request",
                            "request": req
                        })
                    except Exception:
                        pass
                        
            elif act == "handle_friend_request":
                request_id = data.get("request_id")
                accepted = data.get("accepted", False)
                from_user = data.get("from_user")
                
                self.log.info(f"收到处理好友请求: request_id={request_id}, from_user={from_user}, accepted={accepted}, username={self.username}")
                
                # 如果request_id是None，则通过from_user查找对应的请求ID
                if request_id is None and from_user:
                    req_id = get_request_id_by_users(from_user, self.username)
                    if req_id:
                        request_id = req_id
                        self.log.info(f"通过用户名找到请求ID: {request_id}")
                    else:
                        self.log.warning(f"通过用户名({from_user}, {self.username})未找到请求ID")
                
                ok, msg = handle_friend_request(request_id, accepted, from_user, self.username)
                self.log.info(f"处理结果: ok={ok}, msg={msg}")
                
                send_data(self.conn, {
                    "action": "handle_request_result",
                    "success": ok,
                    "message": msg
                })
                
                # 获取请求用户名以便通知对方
                if ok and from_user:
                    # 更新自己的好友列表
                    friends = get_friends(self.username)
                    send_data(self.conn, {"action": "friend_list", "friends": friends})
                    
                    # 如果对方在线，通知请求处理结果
                    if from_user in online_users:
                        try:
                            # 通知好友请求处理结果
                            send_data(online_users[from_user], {
                                "action": "friend_request_update",
                                "from": self.username,
                                "accepted": accepted
                            })
                            
                            # 如果被接受，更新对方的好友列表
                            if accepted:
                                other_friends = get_friends(from_user)
                                send_data(online_users[from_user], {"action": "friend_list", "friends": other_friends})
                        except Exception:
                            import traceback
                            self.log.error(traceback.format_exc())
            
            elif act == "delete_friend":
                friend = data.get("friend")
                ok, msg = delete_friend(self.username, friend)
                send_data(self.conn, {
                    "action": "delete_friend_result",
                    "success": ok,
                    "message": msg,
                    "friend": friend
                })
                
                # 通知对方已被删除好友
                if ok and friend in online_users:
                    try:
                        send_data(online_users[friend], {
                            "action": "friend_deleted",
                            "by_user": self.username
                        })
                        
                        # 更新对方的好友列表
                        other_friends = get_friends(friend)
                        send_data(online_users[friend], {"action": "friend_list", "friends": other_friends})
                    except Exception:
                        pass
            
            # 群聊相关
            elif act == "create_group":
                group_id = data.get("group_id")
                group_name = data.get("group_name")
                avatar_data = data.get("avatar")
                
                ok, msg = create_group(group_id, group_name, self.username, avatar_data)
                send_data(self.conn, {
                    "action": "create_group_result",
                    "success": ok,
                    "message": msg,
                    "group_id": group_id
                })
                
                if ok:
                    # 更新群聊列表
                    groups = get_user_groups(self.username)
                    send_data(self.conn, {"action": "group_list", "groups": groups})
                    
                    # 更新用户-群组映射
                    with groups_lock:
                        if self.username not in user_groups:
                            user_groups[self.username] = []
                        user_groups[self.username].append(group_id)
                    
            elif act == "join_group":
                group_id = data.get("group_id")
                ok, msg = join_group(group_id, self.username)
                send_data(self.conn, {
                    "action": "join_group_result",
                    "success": ok,
                    "message": msg,
                    "group_id": group_id
                })
                
                if ok:
                    # 更新群聊列表
                    groups = get_user_groups(self.username)
                    send_data(self.conn, {"action": "group_list", "groups": groups})
                    
                    # 更新群成员列表
                    members = get_group_members(group_id)
                    
                    # 通知群内其他成员有新成员加入
                    group_info = get_group_info(group_id)
                    if group_info:
                        for member in members:
                            if member["username"] != self.username and member["username"] in online_users:
                                try:
                                    send_data(online_users[member["username"]], {
                                        "action": "group_member_joined",
                                        "group_id": group_id,
                                        "group_name": group_info["group_name"],
                                        "username": self.username
                                    })
                                except Exception:
                                    pass
                                    
                    # 更新用户-群组映射
                    with groups_lock:
                        if self.username not in user_groups:
                            user_groups[self.username] = []
                        user_groups[self.username].append(group_id)
                    
            elif act == "leave_group":
                group_id = data.get("group_id")
                ok, msg = leave_group(group_id, self.username)
                send_data(self.conn, {
                    "action": "leave_group_result",
                    "success": ok,
                    "message": msg,
                    "group_id": group_id
                })
                
                if ok:
                    # 更新群聊列表
                    groups = get_user_groups(self.username)
                    send_data(self.conn, {"action": "group_list", "groups": groups})
                    
                    # 更新群成员列表
                    members = get_group_members(group_id)
                    
                    # 通知群内其他成员有成员退出
                    group_info = get_group_info(group_id)
                    if group_info:
                        for member in members:
                            if member["username"] in online_users:
                                try:
                                    send_data(online_users[member["username"]], {
                                        "action": "group_member_left",
                                        "group_id": group_id,
                                        "group_name": group_info["group_name"],
                                        "username": self.username
                                    })
                                except Exception:
                                    pass
                    
                    # 更新用户-群组映射
                    with groups_lock:
                        if self.username in user_groups and group_id in user_groups[self.username]:
                            user_groups[self.username].remove(group_id)
                    
            elif act == "disband_group":
                group_id = data.get("group_id")
                
                # 先获取群成员，解散后就查不到了
                members = get_group_members(group_id)
                group_info = get_group_info(group_id)
                
                ok, msg = disband_group(group_id, self.username)
                send_data(self.conn, {
                    "action": "disband_group_result",
                    "success": ok,
                    "message": msg,
                    "group_id": group_id
                })
                
                if ok and group_info:
                    # 更新自己的群聊列表
                    groups = get_user_groups(self.username)
                    send_data(self.conn, {"action": "group_list", "groups": groups})
                    
                    # 通知所有群成员群被解散
                    for member in members:
                        if member["username"] != self.username and member["username"] in online_users:
                            try:
                                send_data(online_users[member["username"]], {
                                    "action": "group_disbanded",
                                    "group_id": group_id,
                                    "group_name": group_info["group_name"],
                                    "by_user": self.username
                                })
                                
                                # 更新成员的群聊列表
                                member_groups = get_user_groups(member["username"])
                                send_data(online_users[member["username"]], {"action": "group_list", "groups": member_groups})
                            except Exception:
                                pass
                                
                    # 更新用户-群组映射
                    with groups_lock:
                        for member in members:
                            if member["username"] in user_groups and group_id in user_groups[member["username"]]:
                                user_groups[member["username"]].remove(group_id)
                    
            elif act == "update_member_role":
                group_id = data.get("group_id")
                target = data.get("target")
                new_role = data.get("role")
                
                self.log.info(f"更新成员角色: group_id={group_id}, target={target}, new_role={new_role}")
                
                ok, msg = update_member_role(group_id, self.username, target, new_role)
                self.log.info(f"更新结果: ok={ok}, msg={msg}")
                
                send_data(self.conn, {
                    "action": "update_role_result",
                    "success": ok,
                    "message": msg
                })
                
                if ok:
                    # 获取群信息
                    group_info = get_group_info(group_id)
                    
                    # 获取更新后的成员列表
                    members = get_group_members(group_id)
                    self.log.info(f"获取到更新后的成员列表，有 {len(members)} 名成员")
                    
                    # 通知目标用户角色变更
                    if target in online_users and group_info:
                        try:
                            self.log.info(f"通知 {target} 角色已更新为 {new_role}")
                            send_data(online_users[target], {
                                "action": "role_updated",
                                "group_id": group_id,
                                "group_name": group_info["group_name"],
                                "new_role": new_role,
                                "by_user": self.username
                            })
                        except Exception as e:
                            self.log.error(f"通知 {target} 失败: {str(e)}")
                            
                    # 广播群成员列表更新
                    for member in members:
                        member_username = member["username"]
                        if member_username in online_users:
                            try:
                                send_data(online_users[member_username], {
                                    "action": "group_members_list",
                                    "group_id": group_id,
                                    "members": members
                                })
                            except Exception as e:
                                self.log.error(f"广播给 {member_username} 失败: {str(e)}")
            
            elif act == "remove_group_member":
                group_id = data.get("group_id")
                target = data.get("target")
                
                self.log.info(f"移除群成员: group_id={group_id}, target={target}")
                
                # 获取群信息，移除后就获取不到了
                group_info = get_group_info(group_id)
                
                ok, msg = remove_group_member(group_id, self.username, target)
                self.log.info(f"移除结果: ok={ok}, msg={msg}")
                
                send_data(self.conn, {
                    "action": "remove_member_result",
                    "success": ok,
                    "message": msg,
                    "group_id": group_id,
                    "target": target
                })
                
                if ok and group_info:
                    # 获取更新后的成员列表
                    members = get_group_members(group_id)
                    
                    # 通知被移除用户
                    if target in online_users:
                        try:
                            send_data(online_users[target], {
                                "action": "removed_from_group",
                                "group_id": group_id,
                                "group_name": group_info["group_name"],
                                "by_user": self.username
                            })
                            
                            # 更新被移除用户的群聊列表
                            target_groups = get_user_groups(target)
                            send_data(online_users[target], {"action": "group_list", "groups": target_groups})
                        except Exception as e:
                            self.log.error(f"通知 {target} 失败: {str(e)}")
                    
                    # 通知其他群成员有成员被移除
                    for member in members:
                        member_username = member["username"]
                        if member_username in online_users:
                            try:
                                send_data(online_users[member_username], {
                                    "action": "group_member_left",
                                    "group_id": group_id,
                                    "group_name": group_info["group_name"],
                                    "username": target
                                })
                                
                                # 广播更新后的成员列表
                                send_data(online_users[member_username], {
                                    "action": "group_members_list",
                                    "group_id": group_id,
                                    "members": members
                                })
                            except Exception as e:
                                self.log.error(f"广播给 {member_username} 失败: {str(e)}")
            
            elif act == "get_group_members":
                group_id = data.get("group_id")
                members = get_group_members(group_id)
                
                send_data(self.conn, {
                    "action": "group_members_list",
                    "group_id": group_id,
                    "members": members
                })
                
            # 通话相关
            elif act == "call_request":
                to_user = data.get("to_user")
                call_type = data.get("call_type", "voice")  # voice或video
                
                if to_user in online_users:
                    # 转发通话请求
                    try:
                        send_data(online_users[to_user], {
                            "action": "incoming_call",
                            "from_user": self.username,
                            "call_type": call_type
                        })
                        send_data(self.conn, {"action": "call_ringing", "to_user": to_user})
                    except Exception as e:
                        self.log.error(f"发送通话请求失败: {str(e)}")
                        send_data(self.conn, {"action": "call_failed", "reason": "无法连接到对方"})
                else:
                    send_data(self.conn, {"action": "call_failed", "reason": "对方不在线"})
                    
            elif act == "call_response":
                to_user = data.get("to_user")
                accepted = data.get("accepted", False)
                
                if to_user in online_users:
                    try:
                        send_data(online_users[to_user], {
                            "action": "call_answered",
                            "from_user": self.username,
                            "accepted": accepted
                        })
                    except Exception as e:
                        self.log.error(f"发送通话响应失败: {str(e)}")
            
            elif act == "end_call":
                to_user = data.get("to_user")
                
                if to_user in online_users:
                    try:
                        send_data(online_users[to_user], {
                            "action": "call_ended",
                            "from_user": self.username
                        })
                    except Exception as e:
                        self.log.error(f"发送结束通话通知失败: {str(e)}")
            
            # 语音帧转发
            elif act == "voice_frame":
                to_user = data.get("to_user")
                audio = data.get("audio")  # Base64编码的音频帧
                timestamp = data.get("timestamp")
                
                # 记录音频帧大小
                audio_size = len(audio) if audio else 0
                self.log.info(f"收到音频帧: 来自={self.username}, 发送至={to_user}, 大小={audio_size}字节")
                
                if to_user in online_users:
                    try:
                        # 转发音频帧，不保存到数据库
                        send_data(online_users[to_user], {
                            "action": "voice_frame",
                            "from_user": self.username,
                            "audio": audio,
                            "timestamp": timestamp
                        })
                        self.log.info(f"音频帧转发成功: {self.username} -> {to_user}")
                    except Exception as e:
                        self.log.error(f"转发音频帧失败: {str(e)}")
                else:
                    self.log.warning(f"音频帧转发失败: 用户 {to_user} 不在线")
            
            # 视频帧转发
            elif act == "video_frame":
                to_user = data.get("to_user")
                frame = data.get("frame")  # Base64编码的视频帧
                timestamp = data.get("timestamp")
                
                # 记录视频帧大小
                frame_size = len(frame) if frame else 0
                self.log.info(f"收到视频帧: 来自={self.username}, 发送至={to_user}, 大小={frame_size}字节")
                
                if to_user in online_users:
                    try:
                        # 转发视频帧，不保存到数据库
                        send_data(online_users[to_user], {
                            "action": "video_frame",
                            "from_user": self.username,
                            "frame": frame,
                            "timestamp": timestamp
                        })
                        self.log.info(f"视频帧转发成功: {self.username} -> {to_user}")
                    except Exception as e:
                        self.log.error(f"转发视频帧失败: {str(e)}")
                else:
                    self.log.warning(f"视频帧转发失败: 用户 {to_user} 不在线")
                    
            # 修改密码功能
            elif act == "change_password":
                try:
                    old_password = data.get("old_password", "")
                    new_password = data.get("new_password", "")
                    # 验证旧密码
                    ok, _ = check_login(self.username, old_password)
                    if ok and new_password:
                        # 使用db模块中的函数修改密码
                        from db import change_password
                        success = change_password(self.username, new_password)
                        send_data(self.conn, {
                            "action": "change_password_result",
                            "success": success,
                            "message": "密码修改成功" if success else "密码修改失败"
                        })
                    else:
                        send_data(self.conn, {
                            "action": "change_password_result",
                            "success": False,
                            "message": "原密码错误或新密码无效"
                        })
                except Exception as e:
                    self.log.error(f"修改密码异常: {str(e)}")
                    try:
                        send_data(self.conn, {
                            "action": "change_password_result",
                            "success": False,
                            "message": f"服务器处理错误: {str(e)}"
                        })
                    except Exception:
                        pass  # 忽略发送异常响应时的错误
                        
            # 注销账号功能
            elif act == "delete_account":
                # 用户自行注销账号
                password = data.get("password", "")
                # 验证密码
                ok, _ = check_login(self.username, password)
                if ok:
                    # 删除用户记录、消息和文件
                    affected = delete_user(self.username, UPLOAD_DIR)
                    
                    send_data(self.conn, {
                        "action": "delete_account_result",
                        "success": True,
                        "message": f"账号已成功注销，删除了记录"
                    })
                    # 强制下线
                    break
                else:
                    send_data(self.conn, {
                        "action": "delete_account_result",
                        "success": False,
                        "message": "密码错误，无法注销账号"
                    })

    # ---------------- 处理消息 ----------------
    def _handle_message(self, data: dict):
        sender = self.username
        target = data.get("to", "ALL")
        is_group = data.get("is_group", False)
        is_anonymous = data.get("is_anonymous", False)
        anonymous_name = data.get("anonymous_name", "匿名用户") if is_anonymous else None
        
        # 文件类型消息
        if data["action"] == "file":
            self._save_incoming_file(data)
            msg_dict = {
                "action": "file",
                "from": sender,
                "to": target,
                "is_group": is_group,
                "is_anonymous": is_anonymous,
                "anonymous_name": anonymous_name,
                "filename": data["filename"],
                "content": data["content"]
            }
            save_message(sender, target, "file", data["filename"], 
                        target if is_group else None, is_anonymous, anonymous_name)
            self.log.info("FILE from=%s to=%s name=%s size=%dB is_group=%s",
                          sender, target, data["filename"], len(data["content"]), is_group)
        
        # 语音消息
        elif data["action"] == "voice":
            self._save_incoming_file(data, "voice")
            msg_dict = {
                "action": "voice",
                "from": sender,
                "to": target,
                "is_group": is_group,
                "is_anonymous": is_anonymous,
                "anonymous_name": anonymous_name,
                "filename": data["filename"],
                "content": data["content"],
                "duration": data.get("duration", 0)
            }
            save_message(sender, target, "voice", data["filename"], 
                        target if is_group else None, is_anonymous, anonymous_name)
            self.log.info("VOICE from=%s to=%s name=%s size=%dB duration=%ds is_group=%s",
                          sender, target, data["filename"], len(data["content"]),
                          data.get("duration", 0), is_group)
        
        # 视频消息
        elif data["action"] == "video":
            self._save_incoming_file(data, "video")
            msg_dict = {
                "action": "video",
                "from": sender,
                "to": target,
                "is_group": is_group,
                "is_anonymous": is_anonymous,
                "anonymous_name": anonymous_name,
                "filename": data["filename"],
                "content": data["content"],
                "duration": data.get("duration", 0),
                "thumbnail": data.get("thumbnail", "")
            }
            save_message(sender, target, "video", data["filename"], 
                        target if is_group else None, is_anonymous, anonymous_name)
            self.log.info("VIDEO from=%s to=%s name=%s size=%dB duration=%ds is_group=%s",
                          sender, target, data["filename"], len(data["content"]),
                          data.get("duration", 0), is_group)
        
        # 文本和表情消息
        else:
            msg_dict = {
                "action": "chat",
                "from": sender,
                "to": target,
                "is_group": is_group,
                "is_anonymous": is_anonymous,
                "anonymous_name": anonymous_name,
                "type": data.get("type", "text"),
                "content": data.get("content")
            }
            save_message(sender, target, msg_dict["type"], msg_dict["content"], 
                        target if is_group else None, is_anonymous, anonymous_name)
            self.log.info("CHAT from=%s to=%s type=%s len=%d is_group=%s",
                          sender, target, msg_dict['type'], len(msg_dict['content']), is_group)

        self._forward_message(msg_dict, sender, target, is_group) # 处理消息，点对点还是群聊

    # ---------------- 保存上传文件 ----------------
    def _save_incoming_file(self, data, file_type="file"):
        raw = base64.b64decode(data["content"])# 解码
        # 根据文件类型存放在不同目录
        if file_type == "voice":
            save_dir = UPLOAD_DIR / "voice"
        elif file_type == "video":
            save_dir = UPLOAD_DIR / "video"
        else:
            save_dir = UPLOAD_DIR
            
        save_dir.mkdir(exist_ok=True)
        filename = f"{self.username}_{data['filename']}"
        file_path = save_dir / filename
        
        # 对于语音文件，确保创建正确的WAV文件
        if file_type == "voice" and data['filename'].lower().endswith('.wav'):
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
                wf.writeframes(raw)
        else:
            # 其他类型文件直接保存
            with open(file_path, "wb") as f:
                f.write(raw)

    # ---------------- 转发消息 ----------------
    def _forward_message(self, msg, sender, target, is_group=False):
        with online_lock:
            if target == "ALL":
                # 广播给所有在线用户
                targets = (sock for u, sock in online_users.items() if u != sender)
                for sock in targets:
                    try:
                        send_data(sock, msg)
                    except Exception:
                        pass  # 忽略单个发送异常
            elif is_group:
                # 获取群成员并转发
                members = get_group_members(target)
                for member in members:
                    if member["username"] != sender and member["username"] in online_users:
                        try:
                            send_data(online_users[member["username"]], msg)
                        except Exception:
                            pass
            else:
                # 私聊消息转发前检查是否仍是好友关系
                friends = get_friends(sender)
                if target in friends:
                    # 是好友，正常转发
                    sock = online_users.get(target)
                    if sock:
                        try:
                            send_data(sock, msg)
                        except Exception:
                            pass  # 忽略发送异常
                else:
                    # 不是好友，通知发送者对方已删除自己
                    try:
                        send_data(self.conn, {
                            "action": "friend_deleted",
                            "by_user": target
                        })
                    except Exception:
                        pass  # 忽略发送异常

    # ---------------- 广播用户在线状态 ----------------
    def _broadcast_user_status(self, is_online=True):
        """广播用户上线/下线状态 - 已禁用"""
        # 禁用在线状态广播功能
        pass

    # ---------------- 清理资源 ----------------
    def _cleanup(self):
        if self.username:
            # 广播下线状态
            self._broadcast_user_status(False)
            
            with online_lock:
                online_users.pop(self.username, None)
                
            # 清理群组映射
            with groups_lock:
                if self.username in user_groups:
                    del user_groups[self.username]
                    
        try:
            self.conn.close()
        except Exception:
            pass
        self.log.info("连接关闭")



def main():
    init_db()
    srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv_sock.bind((SERVER_HOST, SERVER_PORT))
    srv_sock.listen(100)
    logger.info("服务器启动于 %s:%s", SERVER_HOST, SERVER_PORT)

    while True:
        conn, addr = srv_sock.accept()
        logger.info("TCP连接来自 %s:%s", *addr)
        ClientThread(conn, addr).start()


if __name__ == "__main__":
    main()
