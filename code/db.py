# -*- coding: utf-8 -*-
#数据库操作层，负责各种数据存储与管理
#增删好友功能
import sqlite3
import os
import shutil
from pathlib import Path
import base64

DB_FILE = Path(__file__).with_name("chat.db")


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # users 表 - 增加头像和其他用户信息
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            avatar BLOB,
            status TEXT DEFAULT 'online',
            create_time DATETIME DEFAULT (datetime('now','localtime'))
        )
    """)

    # 好友关系表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1 TEXT,
            user2 TEXT,
            status TEXT DEFAULT 'pending', -- pending, accepted, rejected, deleted
            request_time DATETIME DEFAULT (datetime('now','localtime')),
            accept_time DATETIME,
            FOREIGN KEY (user1) REFERENCES users(username) ON DELETE CASCADE,
            FOREIGN KEY (user2) REFERENCES users(username) ON DELETE CASCADE,
            UNIQUE(user1, user2)
        )
    """)

    # 群聊表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            creator TEXT NOT NULL,
            create_time DATETIME DEFAULT (datetime('now','localtime')),
            avatar BLOB,
            FOREIGN KEY (creator) REFERENCES users(username) ON DELETE CASCADE
        )
    """)

    # 群成员表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            username TEXT,
            role TEXT DEFAULT 'member', -- 'owner', 'admin', 'member'
            join_time DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (group_id) REFERENCES groups(group_id) ON DELETE CASCADE,
            FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE,
            UNIQUE(group_id, username)
        )
    """)

    # messages 表（带 msg_type 字段）- 扩展消息类型
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT,
            to_user TEXT,
            to_group TEXT,
            msg_type TEXT, -- text, emoji, file, voice, image, video, etc.
            content TEXT,
            file_name TEXT,
            is_anonymous INTEGER DEFAULT 0,
            anonymous_name TEXT,
            ts DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (from_user) REFERENCES users(username) ON DELETE CASCADE
        )
    """)

    # 好友请求表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT,
            to_user TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending', -- pending, accepted, rejected
            request_time DATETIME DEFAULT (datetime('now','localtime')),
            response_time DATETIME,
            FOREIGN KEY (from_user) REFERENCES users(username) ON DELETE CASCADE,
            FOREIGN KEY (to_user) REFERENCES users(username) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()


def check_login(username: str, password: str):#登录验证。验证用户名 + 密码，返回登录结果及错误提示；
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT password FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, "用户名不存在"
    return (password == row[0]), ("密码错误" if password != row[0] else None)


def register_user(username: str, password: str, avatar_data=None):#用户注册（校验用户名唯一性，自动绑定默认头像）
    """注册用户，使用默认头像"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return False, "用户名已存在"
    
    # 总是使用默认头像
    default_avatar = None
    try:
        from pathlib import Path
        avatar_path = Path(__file__).parent / "default_avatar.png"
        if avatar_path.exists():
            with open(avatar_path, "rb") as f:
                default_avatar = f.read()
    except Exception as e:
        print(f"读取默认头像失败: {str(e)}")
    
    # 插入用户记录
    cur.execute("INSERT INTO users(username, password, avatar) VALUES (?,?,?)", 
               (username, password, default_avatar))
    
    conn.commit()
    conn.close()
    return True, None


def save_message(sender: str, target: str, msg_type: str, content: str, #保存消息（适配私聊 / 群聊、多消息类型：文本 / 文件 / 语音 / 图片 / 视频等，支持匿名消息）
                to_group=None, is_anonymous=0, anonymous_name=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages(from_user, to_user, to_group, msg_type, content, file_name, 
                            is_anonymous, anonymous_name)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
    """, (sender, 
          None if to_group else target, 
          to_group,
          msg_type,
          None if msg_type in ("file", "voice", "video") else content,
          content if msg_type in ("file", "voice", "video") else None,
          is_anonymous,
          anonymous_name))
    
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def get_history(user: str, target: str, is_group=False):#获取聊天记录
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    if target == "ALL":
        cur.execute("""
            SELECT from_user, to_user, msg_type, content, file_name, 
                  is_anonymous, anonymous_name, ts
            FROM messages
            WHERE to_user='ALL'
            ORDER BY id
        """)
    elif is_group:
        cur.execute("""
            SELECT from_user, to_group, msg_type, content, file_name, 
                  is_anonymous, anonymous_name, ts
            FROM messages
            WHERE to_group=?
            ORDER BY id
        """, (target,))
    else:
        cur.execute("""
            SELECT from_user, to_user, msg_type, content, file_name, 
                  is_anonymous, anonymous_name, ts
            FROM messages
            WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)
            ORDER BY id
        """, (user, target, target, user))
    
    rows = cur.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        msg = dict(zip(("from", "to", "type", "content", "filename", 
                       "is_anonymous", "anonymous_name", "time"), r))
        # 对于文件类型，确保content为None，filename有值
        if msg["type"] in ("file", "voice", "video"):
            msg["content"] = None
        result.append(msg)
    
    return result


# ======== 用户管理功能 ========
def change_password(username: str, new_password: str):#修改密码
    """修改用户密码"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        # 检查用户是否存在
        cur.execute("SELECT 1 FROM users WHERE username=?", (username,))
        if not cur.fetchone():
            return False
            
        # 执行更新
        cur.execute("UPDATE users SET password=? WHERE username=?", 
                   (new_password, username))
        conn.commit()
        return True
    except Exception:
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def delete_user(username: str, uploads_dir: Path = None):#删除用户
    """删除用户及其所有聊天记录和文件"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
    cur = conn.cursor()
    
    # 删除用户
    cur.execute("DELETE FROM users WHERE username=?", (username,))
    
    # 获取提交结果
    affected = conn.total_changes
    conn.commit()
    conn.close()
    
    # 删除用户上传的文件
    file_count = 0
    if uploads_dir and uploads_dir.exists():
        for file in uploads_dir.iterdir():
            # 检查文件是否属于该用户
            if file.name.startswith(f"{username}_"):
                try:
                    file.unlink()  # 删除文件
                    file_count += 1
                except Exception:
                    pass
                    
    return affected, file_count


def update_avatar(username: str, avatar_data):#更新 / 获取用户头像（二进制 BLOB 存储
    """更新用户头像"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        cur.execute("UPDATE users SET avatar=? WHERE username=?", 
                   (avatar_data, username))
        conn.commit()
        return True
    except Exception:
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def get_avatar(username: str):#更新 / 获取用户头像（二进制 BLOB 存储
    """获取用户头像"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    cur.execute("SELECT avatar FROM users WHERE username=?", (username,))
    result = cur.fetchone()
    conn.close()
    
    return result[0] if result and result[0] else None


# ======== 好友管理功能 ========
def send_friend_request(from_user: str, to_user: str, message: str = ""):#发送好友请求
    """发送好友请求"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        # 检查是否已经是好友
        cur.execute("""
            SELECT status FROM friends 
            WHERE (user1=? AND user2=?) OR (user1=? AND user2=?)
        """, (from_user, to_user, to_user, from_user))
        
        existing = cur.fetchone()
        if existing:
            if existing[0] == 'accepted':
                return False, "已经是好友"
            elif existing[0] == 'pending':
                return False, "已发送过好友请求，等待对方确认"
            
        # 检查是否已存在好友请求
        cur.execute("""
            SELECT status FROM friend_requests
            WHERE from_user=? AND to_user=? AND status='pending'
        """, (from_user, to_user))
        
        if cur.fetchone():
            return False, "已发送过好友请求，等待对方确认"
            
        # 添加好友请求
        cur.execute("""
            INSERT INTO friend_requests(from_user, to_user, message)
            VALUES(?, ?, ?)
        """, (from_user, to_user, message))
        
        conn.commit()
        return True, "好友请求已发送"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"发送好友请求失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def get_friend_requests(username: str):#获取当前用户的待处理好友请求
    """获取用户收到的好友请求"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, from_user, message, request_time
        FROM friend_requests
        WHERE to_user=? AND status='pending'
        ORDER BY request_time DESC
    """, (username,))
    
    requests = []
    for row in cur.fetchall():
        requests.append({
            'id': row[0],
            'from_user': row[1],
            'message': row[2],
            'request_time': row[3]
        })
    
    conn.close()
    return requests


def get_request_id_by_users(from_user: str, to_user: str):#查找好友请求 ID
    """根据发送者和接收者查找好友请求ID"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        print(f"DB - 根据用户名查找好友请求: from_user={from_user}, to_user={to_user}")
        
        # 查找未处理的好友请求
        cur.execute("""
            SELECT id FROM friend_requests
            WHERE from_user=? AND to_user=? AND status='pending'
        """, (from_user, to_user))
        
        result = cur.fetchone()
        if result:
            print(f"DB - 找到好友请求ID: {result[0]}")
            return result[0]
        print(f"DB - 未找到符合条件的好友请求")
        
        # 尝试反向查找（有时候可能方向记错）
        cur.execute("""
            SELECT id FROM friend_requests
            WHERE from_user=? AND to_user=? AND status='pending'
        """, (to_user, from_user))
        
        result = cur.fetchone()
        if result:
            print(f"DB - 反向找到好友请求ID: {result[0]}")
            return result[0]
            
        return None
    except Exception as e:
        print(f"DB - 查找好友请求ID失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if conn:
            conn.close()


def handle_friend_request(request_id, accepted: bool, from_user=None, to_user=None):#处理好友请求
    """处理好友请求
    request_id: 请求ID，可能为None
    accepted: 是否接受
    from_user: 请求发送方，当request_id为None时使用
    to_user: 请求接收方，当request_id为None时使用
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        print(f"DB - 处理好友请求: request_id={request_id}, accepted={accepted}, from_user={from_user}, to_user={to_user}")
        
        # 如果有请求ID，优先使用ID查询
        if request_id:
            cur.execute("""
                SELECT from_user, to_user FROM friend_requests
                WHERE id=? AND status='pending'
            """, (request_id,))
            
            req = cur.fetchone()
            if not req:
                print(f"DB - 通过ID={request_id}未找到请求或已处理")
                
                # 如果提供了用户信息，尝试通过用户名查找
                if from_user and to_user:
                    # 通过用户名查找请求ID
                    req_id = get_request_id_by_users(from_user, to_user)
                    if req_id:
                        print(f"DB - 通过用户名找到请求ID: {req_id}")
                        # 重新查询请求信息
                        cur.execute("""
                            SELECT from_user, to_user FROM friend_requests
                            WHERE id=? AND status='pending'
                        """, (req_id,))
                        req = cur.fetchone()
                        request_id = req_id
                
                if not req:
                    # 如果仍然找不到，但提供了用户名，直接使用用户名处理
                    if from_user and to_user:
                        req = (from_user, to_user)
                        print(f"DB - 未找到请求记录，使用提供的用户信息: {req}")
                    else:
                        return False, "请求不存在或已处理"
        else:
            # 如果没有请求ID，但有用户信息，直接使用用户信息
            if from_user and to_user:
                req = (from_user, to_user)
                print(f"DB - 没有请求ID，使用提供的用户信息: {req}")
            else:
                return False, "请求信息不完整"
            
        from_user, to_user = req
        print(f"DB - 请求信息: from={from_user}, to={to_user}")
        
        # 如果有请求ID，更新请求状态
        status = 'accepted' if accepted else 'rejected'
        if request_id:
            cur.execute("""
                UPDATE friend_requests
                SET status=?, response_time=datetime('now','localtime')
                WHERE id=?
            """, (status, request_id))
            print(f"DB - 更新请求状态为: {status}, 影响行数: {cur.rowcount}")
        
        if accepted:
            # 先检查是否已经是好友，避免重复添加
            cur.execute("""
                SELECT 1 FROM friends
                WHERE (user1=? AND user2=?) OR (user1=? AND user2=?)
            """, (from_user, to_user, to_user, from_user))
            
            existing = cur.fetchone()
            if not existing:
                # 添加好友关系
                cur.execute("""
                    INSERT INTO friends(user1, user2, status, accept_time)
                    VALUES(?, ?, 'accepted', datetime('now','localtime'))
                """, (from_user, to_user))
                print(f"DB - 添加新好友关系: {from_user} - {to_user}")
            else:
                print(f"DB - 已是好友关系，无需添加")
            
            # 查找并更新相反方向的请求（如果存在）
            cur.execute("""
                UPDATE friend_requests
                SET status='accepted', response_time=datetime('now','localtime')
                WHERE from_user=? AND to_user=? AND status='pending'
            """, (to_user, from_user))
            print(f"DB - 更新了 {cur.rowcount} 个相反方向的请求")
            
        conn.commit()
        print(f"DB - 好友请求处理完成: {from_user} -> {to_user}, 状态: {status}")
        
        # 验证好友添加结果
        if accepted:
            cur.execute("""
                SELECT 1 FROM friends
                WHERE (user1=? AND user2=?) OR (user1=? AND user2=?)
            """, (from_user, to_user, to_user, from_user))
            
            if cur.fetchone():
                print(f"DB - 验证成功: {from_user}和{to_user}现在是好友关系")
            else:
                print(f"DB - 警告: {from_user}和{to_user}的好友关系未成功添加")
        
        return True, "已添加为好友" if accepted else "已拒绝好友请求"
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"DB - 处理好友请求失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, f"处理好友请求失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def delete_friend(user1: str, user2: str):#删除好友
    """删除好友关系"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        # 删除好友关系
        cur.execute("""
            DELETE FROM friends 
            WHERE (user1=? AND user2=?) OR (user1=? AND user2=?)
        """, (user1, user2, user2, user1))
        
        if cur.rowcount == 0:
            return False, "不是好友关系"
        
        # 删除聊天记录
        delete_chat_history(user1, user2)
            
        conn.commit()
        return True, "好友已删除"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"删除好友失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def delete_chat_history(user1: str, user2: str):#删除聊天记录 清理聊天记录 清除聊天记录
    """删除两个用户之间的聊天记录"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        # 删除私聊消息记录
        cur.execute("""
            DELETE FROM messages 
            WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?)
        """, (user1, user2, user2, user1))
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"删除聊天记录失败: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()


def get_friends(username: str):#获取用户好友列表
    """获取用户的好友列表"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    print(f"DB - 获取用户 {username} 的好友列表")
    
    cur.execute("""
        SELECT CASE 
            WHEN user1=? THEN user2
            ELSE user1
        END as friend
        FROM friends
        WHERE (user1=? OR user2=?) AND status='accepted'
    """, (username, username, username))
    
    friends = [row[0] for row in cur.fetchall()]
    print(f"DB - 找到 {len(friends)} 个好友: {friends}")
    conn.close()
    
    return friends


# ======== 群聊管理功能 ========
def create_group(group_id: str, group_name: str, creator: str, avatar_data=None):#创建群聊功能
    """创建群聊"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        # 检查群号是否已存在
        cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
        if cur.fetchone():
            return False, "群号已存在"
            
        # 创建群聊
        if avatar_data:
            cur.execute("""
                INSERT INTO groups(group_id, group_name, creator, avatar)
                VALUES(?, ?, ?, ?)
            """, (group_id, group_name, creator, avatar_data))
        else:
            cur.execute("""
                INSERT INTO groups(group_id, group_name, creator)
                VALUES(?, ?, ?)
            """, (group_id, group_name, creator))
        
        # 将创建者添加为群主
        cur.execute("""
            INSERT INTO group_members(group_id, username, role)
            VALUES(?, ?, 'owner')
        """, (group_id, creator))
        
        conn.commit()
        return True, "群聊创建成功"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"创建群聊失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def join_group(group_id: str, username: str):#加入群聊功能 
    """加入群聊"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        # 检查群聊是否存在
        cur.execute("SELECT 1 FROM groups WHERE group_id=?", (group_id,))
        if not cur.fetchone():
            return False, "群聊不存在"
        
        # 检查是否已经是群成员
        cur.execute("""
            SELECT 1 FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, username))
        
        if cur.fetchone():
            return False, "已经是群成员"
            
        # 将用户添加为群成员
        cur.execute("""
            INSERT INTO group_members(group_id, username)
            VALUES(?, ?)
        """, (group_id, username))
        
        conn.commit()
        return True, "已加入群聊"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"加入群聊失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def leave_group(group_id: str, username: str):#退出群聊功能 群主不可退出
    """退出群聊"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        # 检查是否是群主
        cur.execute("""
            SELECT role FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, username))
        
        row = cur.fetchone()
        if not row:
            return False, "不是群成员"
            
        if row[0] == 'owner':
            return False, "群主不能退出群聊，请先转让群主或解散群聊"
            
        # 退出群聊
        cur.execute("""
            DELETE FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, username))
        
        conn.commit()
        return True, "已退出群聊"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"退出群聊失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def get_user_groups(username: str):#获取用户加入的所有群聊及角色
    """获取用户加入的群聊"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT g.group_id, g.group_name, gm.role, g.creator, g.create_time
        FROM groups g
        JOIN group_members gm ON g.group_id = gm.group_id
        WHERE gm.username=?
    """, (username,))
    
    groups = []
    for row in cur.fetchall():
        groups.append({
            'group_id': row[0],
            'group_name': row[1],
            'role': row[2],
            'creator': row[3],
            'create_time': row[4]
        })
    
    conn.close()
    return groups


def get_group_members(group_id: str):#获取群成员列表
    """获取群成员列表"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    print(f"DB - 获取群成员列表: {group_id}")
    
    cur.execute("""
        SELECT username, role, join_time
        FROM group_members
        WHERE group_id=?
        ORDER BY CASE 
            WHEN role='owner' THEN 1
            WHEN role='admin' THEN 2
            ELSE 3
        END, join_time
    """, (group_id,))
    
    members = []
    for row in cur.fetchall():
        members.append({
            'username': row[0],
            'role': row[1],
            'join_time': row[2]
        })
    
    print(f"DB - 找到 {len(members)} 个成员")
    for member in members:
        print(f"  - {member['username']} ({member['role']})")
    
    conn.close()
    return members


def update_member_role(group_id: str, operator: str, username: str, new_role: str):
    """更新群成员角色 (需要操作者有权限)"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        print(f"DB - 更新成员角色: group_id={group_id}, operator={operator}, target={username}, new_role={new_role}")
        
        # 检查操作者权限
        cur.execute("""
            SELECT role FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, operator))
        
        op_row = cur.fetchone()
        if not op_row:
            print(f"DB - 操作者 {operator} 不是群成员")
            return False, "您不是群成员"
            
        operator_role = op_row[0]
        # 只有群主可以设置/取消管理员，管理员没有此权限
        if operator_role != 'owner':
            print(f"DB - 操作者 {operator} 不是群主，无法设置或取消管理员")
            return False, "只有群主可以设置或取消管理员权限"
        
        # 检查目标用户是否存在
        cur.execute("""
            SELECT role FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, username))
        
        target_row = cur.fetchone()
        if not target_row:
            print(f"DB - 目标用户 {username} 不是群成员")
            return False, "目标用户不是群成员"
            
        target_role = target_row[0]
        
        # 群主权限检查
        if target_role == 'owner':
            print(f"DB - 不能修改群主的角色")
            return False, "不能修改群主的角色"
            
        # 管理员权限检查: 管理员只能修改普通成员的角色
        if operator_role == 'admin' and target_role == 'admin':
            print(f"DB - 管理员不能修改其他管理员的角色")
            return False, "管理员不能修改其他管理员的角色"
            
        # 检查新角色是否有效
        if new_role not in ('admin', 'member'):
            print(f"DB - 无效的角色: {new_role}")
            return False, "无效的角色"
            
        # 更新角色
        cur.execute("""
            UPDATE group_members
            SET role=?
            WHERE group_id=? AND username=?
        """, (new_role, group_id, username))
        
        conn.commit()
        print(f"DB - 角色更新成功: {username} 的角色已设为 {new_role}")
        return True, f"{username} 的角色已更新为 {new_role}"
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"DB - 更新角色失败: {str(e)}")
        return False, f"更新角色失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def disband_group(group_id: str, username: str):
    """解散群聊 (仅群主可操作)"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("PRAGMA foreign_keys = ON")
        cur = conn.cursor()
        
        # 检查是否是群主
        cur.execute("""
            SELECT 1 FROM group_members 
            WHERE group_id=? AND username=? AND role='owner'
        """, (group_id, username))
        
        if not cur.fetchone():
            return False, "只有群主才能解散群聊"
            
        # 删除群聊
        cur.execute("DELETE FROM groups WHERE group_id=?", (group_id,))
        
        conn.commit()
        return True, "群聊已解散"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"解散群聊失败: {str(e)}"
    finally:
        if conn:
            conn.close()


def get_group_info(group_id: str):
    """获取群聊信息"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    
    print(f"DB - 获取群聊信息: {group_id}")
    
    cur.execute("""
        SELECT group_id, group_name, creator, create_time, avatar
        FROM groups
        WHERE group_id=?
    """, (group_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        print(f"DB - 找不到群聊: {group_id}")
        return None
        
    info = {
        'group_id': row[0],
        'group_name': row[1],
        'creator': row[2],
        'create_time': row[3],
        'avatar': row[4]
    }
    
    print(f"DB - 群聊信息: {info['group_id']}, {info['group_name']}, 创建者: {info['creator']}")
    return info


def remove_group_member(group_id: str, operator: str, target: str):
    """移除群成员 (群主或管理员可操作)"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        
        # 检查操作者权限
        cur.execute("""
            SELECT role FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, operator))
        
        op_row = cur.fetchone()
        if not op_row or op_row[0] not in ('owner', 'admin'):
            return False, "没有权限执行此操作"
            
        # 检查目标成员
        cur.execute("""
            SELECT role FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, target))
        
        target_row = cur.fetchone()
        if not target_row:
            return False, "用户不是群成员"
            
        # 权限检查: 管理员不能移除群主或其他管理员
        if op_row[0] == 'admin' and target_row[0] in ('owner', 'admin'):
            return False, "管理员只能移除普通成员"
            
        # 群主不能被移除
        if target_row[0] == 'owner':
            return False, "不能移除群主"
            
        # 移除成员
        cur.execute("""
            DELETE FROM group_members 
            WHERE group_id=? AND username=?
        """, (group_id, target))
        
        conn.commit()
        return True, "成员已移除"
    except Exception as e:
        if conn:
            conn.rollback()
        return False, f"移除成员失败: {str(e)}"
    finally:
        if conn:
            conn.close()
