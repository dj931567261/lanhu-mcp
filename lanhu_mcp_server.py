#!/usr/bin/env python3
"""
蓝湖Axure文档提取MCP服务器
使用FastMCP实现
"""
import asyncio
import os
import re
import base64
import json
import hashlib
import copy
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional, Union, List, Any

# 加载 .env 文件中的环境变量（必须在其他导入之前）
# 注意：在 Docker 容器中，环境变量通常已由 docker-compose 通过 env_file 设置
# load_dotenv() 默认不会覆盖已存在的环境变量，所以与 Docker Compose 兼容
try:
    from dotenv import load_dotenv
    # 从项目根目录加载 .env 文件（如果存在）
    # override=False 确保不会覆盖已存在的环境变量（如 Docker Compose 设置的）
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=False)
    else:
        # 如果 .env 文件不存在，尝试从当前目录加载（用于本地开发）
        load_dotenv(override=False)
except ImportError:
    # 如果 python-dotenv 未安装，跳过加载（使用系统环境变量）
    pass

# 东八区时区（北京时间）
CHINA_TZ = timezone(timedelta(hours=8))
from urllib.parse import urlparse

# 元数据缓存配置（基于版本号的永久缓存）
_metadata_cache = {}  # {cache_key: {'data': {...}, 'version_id': str}}

import httpx
from fastmcp import Context
from bs4 import BeautifulSoup
from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from playwright.async_api import async_playwright

# 创建FastMCP服务器
mcp = FastMCP("Lanhu Axure Extractor")

# 全局配置
DEFAULT_COOKIE = "your_lanhu_cookie_here"  # 请替换为你的蓝湖Cookie，从浏览器开发者工具中获取

# 从环境变量读取Cookie，如果没有则使用默认值
COOKIE = os.getenv("LANHU_COOKIE", DEFAULT_COOKIE)

BASE_URL = "https://lanhuapp.com"
CDN_URL = "https://axure-file.lanhuapp.com"

# 飞书机器人Webhook配置（支持环境变量）
DEFAULT_FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-key-here"
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", DEFAULT_FEISHU_WEBHOOK)

# 数据存储目录
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# HTTP 请求超时时间（秒）
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))

# 设计标注输出单位换算：基于 750 设计稿宽度转为 411dp 逻辑宽度
ANNOTATION_DP_SCALE = 411 / 750

# 浏览器视口尺寸（影响页面初始渲染，不影响全页截图）
# 注意：截图使用 full_page=True，会自动截取完整页面，不受此限制
VIEWPORT_WIDTH = int(os.getenv("VIEWPORT_WIDTH", "1920"))
VIEWPORT_HEIGHT = int(os.getenv("VIEWPORT_HEIGHT", "1080"))

# 调试模式
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# 角色枚举（用于识别用户身份）
VALID_ROLES = ["后端", "前端", "客户端", "开发", "运维", "产品", "项目经理"]

# ⚠️ @提醒只允许具体人名，禁止使用角色
# 示例人名列表，请根据你的团队成员修改
MENTION_ROLES = [
    "张三", "李四", "王五", "赵六", "钱七", "孙八",
    "周九", "吴十", "郑十一", "冯十二", "陈十三", "褚十四",
    "卫十五", "蒋十六", "沈十七", "韩十八", "杨十九", "朱二十"
]

# 飞书用户ID映射
# 示例映射，请替换为你团队成员的实际飞书用户ID
# 飞书用户ID可以通过飞书开放平台获取
FEISHU_USER_ID_MAP = {
    '张三': '0000000000000000001',
    '李四': '0000000000000000002',
    '王五': '0000000000000000003',
    '赵六': '0000000000000000004',
    '钱七': '0000000000000000005',
    '孙八': '0000000000000000006',
    '周九': '0000000000000000007',
    '吴十': '0000000000000000008',
    '郑十一': '0000000000000000009',
    '冯十二': '0000000000000000010',
    '陈十三': '0000000000000000011',
    '褚十四': '0000000000000000012',
    '卫十五': '0000000000000000013',
    '蒋十六': '0000000000000000014',
    '沈十七': '0000000000000000015',
    '韩十八': '0000000000000000016',
    '杨十九': '0000000000000000017',
    '朱二十': '0000000000000000018',
}

# 角色映射规则（按优先级排序，越具体的越靠前）
ROLE_MAPPING_RULES = [
    # 后端相关
    (["后端", "backend", "服务端", "server", "java", "php", "python", "go", "golang", "node", "nodejs", ".net", "c#"], "后端"),
    # 前端相关
    (["前端", "frontend", "h5", "web", "vue", "react", "angular", "javascript", "js", "ts", "typescript", "css"], "前端"),
    # 客户端相关（优先于"开发"）
    (["客户端", "client", "ios", "android", "安卓", "移动端", "mobile", "app", "flutter", "rn", "react native", "swift", "kotlin", "objective-c", "oc"], "客户端"),
    # 运维相关
    (["运维", "ops", "devops", "sre", "dba", "运营维护", "系统管理", "infra", "infrastructure"], "运维"),
    # 产品相关
    (["产品", "product", "pm", "产品经理", "需求"], "产品"),
    # 项目经理相关
    (["项目经理", "项目", "pmo", "project manager", "scrum", "敏捷"], "项目经理"),
    # 开发（通用，优先级最低）
    (["开发", "dev", "developer", "程序员", "coder", "engineer", "工程师"], "开发"),
]


def normalize_role(role: str) -> str:
    """
    将用户角色归一化到标准角色组
    
    Args:
        role: 用户原始角色名（如 "php后端"、"iOS开发"）
    
    Returns:
        标准角色名（如 "后端"、"客户端"）
    """
    if not role:
        return "未知"
    
    role_lower = role.lower()
    
    # 如果已经是标准角色，直接返回
    if role in VALID_ROLES:
        return role
    
    # 按规则匹配
    for keywords, standard_role in ROLE_MAPPING_RULES:
        for keyword in keywords:
            if keyword.lower() in role_lower:
                return standard_role
    
    # 无法匹配，返回原值
    return role


def _get_metadata_cache_key(project_id: str, doc_id: str = None) -> str:
    """生成元数据缓存键（不含版本号，用于查找）"""
    if doc_id:
        return f"{project_id}_{doc_id}"
    return project_id


def _get_cached_metadata(cache_key: str, version_id: str = None) -> Optional[dict]:
    """
    获取缓存的元数据
    
    Args:
        cache_key: 缓存键
        version_id: 文档版本ID，如果提供则检查版本是否匹配
    
    Returns:
        缓存的元数据，如果未命中或版本不匹配则返回None
    """
    if cache_key in _metadata_cache:
        cache_entry = _metadata_cache[cache_key]
        
        # 如果提供了version_id，检查版本是否匹配
        if version_id:
            if cache_entry.get('version_id') == version_id:
                return cache_entry['data']
            else:
                # 版本不匹配，删除旧缓存
                del _metadata_cache[cache_key]
                return None
        
        # 没有version_id，直接返回缓存（用于项目级别缓存）
        return cache_entry['data']
    
    return None


def _set_cached_metadata(cache_key: str, metadata: dict, version_id: str = None):
    """
    设置缓存（基于版本号的永久缓存）
    
    Args:
        cache_key: 缓存键
        metadata: 元数据
        version_id: 文档版本ID，存储后只要版本不变就永久有效
    """
    _metadata_cache[cache_key] = {
        'data': metadata.copy(),
        'version_id': version_id  # 版本号作为缓存有效性标识
    }


# ============================================
# 飞书机器人通知功能
# ============================================

async def send_feishu_notification(
    summary: str,
    content: str,
    author_name: str,
    author_role: str,
    mentions: List[str],
    message_type: str,
    project_name: str = None,
    doc_name: str = None,
    doc_url: str = None
) -> bool:
    """
    发送飞书机器人通知
    
    Args:
        summary: 留言标题
        content: 留言内容
        author_name: 作者名称
        author_role: 作者角色
        mentions: @的人名列表（必须是具体的人名，不能是角色）
        message_type: 消息类型
        project_name: 项目名称
        doc_name: 文档名称
        doc_url: 文档链接
    
    Returns:
        bool: 发送成功返回True，失败返回False
    """
    if not mentions:
        return False  # 没有@任何人，不发送通知
    
    # 消息类型emoji映射
    type_emoji = {
        "normal": "📢",
        "task": "📋",
        "question": "❓",
        "urgent": "🚨",
        "knowledge": "💡"
    }
    
    emoji = type_emoji.get(message_type, "📝")
    
    # 构建飞书@用户信息
    at_user_ids = []
    mention_names = []
    for name in mentions:
        user_id = FEISHU_USER_ID_MAP.get(name)
        if user_id:
            at_user_ids.append(user_id)
            mention_names.append(name)
    
    # 递归提取纯文本内容
    def extract_text(obj):
        """递归提取JSON中的纯文本"""
        if isinstance(obj, str):
            # 尝试解析字符串是否为JSON
            try:
                parsed = json.loads(obj)
                return extract_text(parsed)
            except:
                return obj
        elif isinstance(obj, list):
            texts = []
            for item in obj:
                text = extract_text(item)
                if text:
                    texts.append(text)
            return " ".join(texts)
        elif isinstance(obj, dict):
            # 提取text字段
            if "text" in obj:
                return extract_text(obj["text"])
            return ""
        else:
            return str(obj) if obj else ""
    
    plain_content = extract_text(content)
    
    # 限制内容长度
    if len(plain_content) > 500:
        plain_content = plain_content[:500] + "..."
    
    # 构建富文本内容（使用飞书post格式支持@功能）
    content_list = [
        # 发布者信息
        [{"tag": "text", "text": f"👤 发布者：{author_name}（{author_role}）\n"}],
        # 类型
        [{"tag": "text", "text": f"🏷️ 类型：{message_type}\n"}],
    ]
    
    # @提醒行（如果有@的人）
    if at_user_ids:
        mention_line = [{"tag": "text", "text": "📨 提醒："}]
        for user_id, name in zip(at_user_ids, mention_names):
            mention_line.append({"tag": "at", "user_id": user_id})
            mention_line.append({"tag": "text", "text": " "})
        mention_line.append({"tag": "text", "text": "\n"})
        content_list.append(mention_line)
    
    # 项目信息
    if project_name:
        content_list.append([{"tag": "text", "text": f"📁 项目：{project_name}\n"}])
    if doc_name:
        content_list.append([{"tag": "text", "text": f"📄 文档：{doc_name}\n"}])
    
    # 内容
    content_list.append([{"tag": "text", "text": f"\n📝 内容：\n{plain_content}\n"}])
    
    # 链接
    if doc_url:
        content_list.append([
            {"tag": "text", "text": "\n🔗 "},
            {"tag": "a", "text": "查看需求文档", "href": doc_url}
        ])
    
    # 飞书消息payload（使用富文本post格式）
    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": summary,  # 直接使用summary，不再添加emoji（用户自己会加）
                    "content": content_list
                }
            }
        }
    }
    
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(
                FEISHU_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            result = response.json()
            
            # 飞书成功响应: {"code":0,"msg":"success"}
            if result.get("code") == 0:
                if mention_names:
                    print(f"✅ 飞书通知发送成功: {summary} @{','.join(mention_names)}")
                else:
                    print(f"✅ 飞书通知发送成功: {summary}")
                return True
            else:
                print(f"⚠️ 飞书通知发送失败: {result}")
                return False
                
    except Exception as e:
        print(f"❌ 飞书通知发送异常: {e}")
        return False


# ============================================
# 消息存储类
# ============================================

class MessageStore:
    """消息存储管理类 - 支持团队留言板功能"""
    
    def __init__(self, project_id: str = None):
        """
        初始化消息存储
        
        Args:
            project_id: 项目ID，如果为None则用于全局操作模式
        """
        self.project_id = project_id
        self.storage_dir = DATA_DIR / "messages"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        if project_id:
            self.file_path = self.storage_dir / f"{project_id}.json"
            self._data = self._load()
        else:
            # 全局模式，不加载单个文件
            self.file_path = None
            self._data = None
    
    def _load(self) -> dict:
        """加载项目数据"""
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "project_id": self.project_id,
            "next_id": 1,
            "messages": [],
            "collaborators": []
        }
    
    def _save(self):
        """保存项目数据"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
    
    def _get_now(self) -> str:
        """获取当前时间字符串（东八区/北京时间）"""
        return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    
    def _check_mentions_me(self, mentions: List[str], user_role: str) -> bool:
        """检查消息是否@了当前用户（支持角色归一化匹配）"""
        if not mentions:
            return False
        if "所有人" in mentions:
            return True
        
        # 将用户角色归一化后匹配
        normalized_user_role = normalize_role(user_role)
        
        # 直接匹配原始角色
        if user_role in mentions:
            return True
        
        # 匹配归一化后的角色
        if normalized_user_role in mentions:
            return True
        
        return False
    
    def record_collaborator(self, name: str, role: str):
        """记录/更新协作者"""
        if not name or not role:
            return
        
        now = self._get_now()
        collaborators = self._data.get("collaborators", [])
        
        # 查找是否已存在
        for collab in collaborators:
            if collab["name"] == name and collab["role"] == role:
                collab["last_seen"] = now
                self._save()
                return
        
        # 新增协作者
        collaborators.append({
            "name": name,
            "role": role,
            "first_seen": now,
            "last_seen": now
        })
        self._data["collaborators"] = collaborators
        self._save()
    
    def get_collaborators(self) -> List[dict]:
        """获取协作者列表"""
        return self._data.get("collaborators", [])
    
    def save_message(self, summary: str, content: str, author_name: str, 
                     author_role: str, mentions: List[str] = None,
                     message_type: str = 'normal',
                     project_name: str = None, folder_name: str = None,
                     doc_id: str = None, doc_name: str = None,
                     doc_type: str = None, doc_version: str = None,
                     doc_updated_at: str = None, doc_url: str = None) -> dict:
        """
        保存新消息（包含标准元数据）
        
        Args:
            summary: 消息概要
            content: 消息内容
            author_name: 作者名称
            author_role: 作者角色
            mentions: @的角色列表
            message_type: 留言类型 (normal/task/question/urgent)
            project_name: 项目名称
            folder_name: 文件夹名称
            doc_id: 文档ID
            doc_name: 文档名称
            doc_type: 文档类型
            doc_version: 文档版本
            doc_updated_at: 文档更新时间
            doc_url: 文档URL
        """
        msg_id = self._data["next_id"]
        self._data["next_id"] += 1
        
        now = self._get_now()
        message = {
            "id": msg_id,
            "summary": summary,
            "content": content,
            "mentions": mentions or [],
            "message_type": message_type,  # 新增：留言类型
            "author_name": author_name,
            "author_role": author_role,
            "created_at": now,
            "updated_at": None,
            "updated_by_name": None,
            "updated_by_role": None,
            
            # 标准元数据（10个字段）
            "project_id": self.project_id,
            "project_name": project_name,
            "folder_name": folder_name,
            "doc_id": doc_id,
            "doc_name": doc_name,
            "doc_type": doc_type,
            "doc_version": doc_version,
            "doc_updated_at": doc_updated_at,
            "doc_url": doc_url
        }
        
        self._data["messages"].append(message)
        self._save()
        return message
    
    def get_messages(self, user_role: str = None) -> List[dict]:
        """获取所有消息（不含content，用于列表展示）"""
        messages = []
        for msg in self._data.get("messages", []):
            msg_copy = {k: v for k, v in msg.items() if k != "content"}
            if user_role:
                msg_copy["mentions_me"] = self._check_mentions_me(msg.get("mentions", []), user_role)
            messages.append(msg_copy)
        # 按创建时间倒序排列
        messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return messages
    
    def get_message_by_id(self, msg_id: int, user_role: str = None) -> Optional[dict]:
        """根据ID获取消息（含content）"""
        for msg in self._data.get("messages", []):
            if msg["id"] == msg_id:
                msg_copy = msg.copy()
                if user_role:
                    msg_copy["mentions_me"] = self._check_mentions_me(msg.get("mentions", []), user_role)
                return msg_copy
        return None
    
    def update_message(self, msg_id: int, editor_name: str, editor_role: str,
                       summary: str = None, content: str = None, 
                       mentions: List[str] = None) -> Optional[dict]:
        """更新消息"""
        for msg in self._data.get("messages", []):
            if msg["id"] == msg_id:
                if summary is not None:
                    msg["summary"] = summary
                if content is not None:
                    msg["content"] = content
                if mentions is not None:
                    msg["mentions"] = mentions
                msg["updated_at"] = self._get_now()
                msg["updated_by_name"] = editor_name
                msg["updated_by_role"] = editor_role
                self._save()
                return msg
        return None
    
    def delete_message(self, msg_id: int) -> bool:
        """删除消息"""
        messages = self._data.get("messages", [])
        for i, msg in enumerate(messages):
            if msg["id"] == msg_id:
                messages.pop(i)
                self._save()
                return True
        return False
    
    def get_all_messages(self, user_role: str = None) -> List[dict]:
        """
        获取所有项目的留言（全局查询）
        
        Args:
            user_role: 用户角色，用于判断是否@了该用户
        
        Returns:
            包含所有项目消息的列表（已排序）
        """
        all_messages = []
        
        # 遍历所有JSON文件
        for json_file in self.storage_dir.glob("*.json"):
            project_id = json_file.stem
            try:
                project_store = MessageStore(project_id)
                messages = project_store.get_messages(user_role=user_role)
                
                # 消息中已包含元数据，直接添加
                all_messages.extend(messages)
            except Exception:
                # 某个项目加载失败不影响其他项目
                continue
        
        # 全局排序（按创建时间倒序）
        all_messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_messages
    
    def get_all_messages_grouped(self, user_role: str = None, user_name: str = None) -> List[dict]:
        """
        获取所有项目的留言（分组返回，节省token）
        
        按项目+文档分组，每组的元数据只出现一次，避免重复
        
        Args:
            user_role: 用户角色，用于判断是否@了该用户
            user_name: 用户名，用于判断消息是否是自己发的
        
        Returns:
            分组列表，每组包含元数据和该组的消息
        """
        # 先获取所有消息
        all_messages = self.get_all_messages(user_role)
        
        # 按 (project_id, doc_id) 分组
        from collections import defaultdict
        groups_dict = defaultdict(list)
        
        for msg in all_messages:
            # 生成分组键
            project_id = msg.get('project_id', 'unknown')
            doc_id = msg.get('doc_id', 'no_doc')
            group_key = f"{project_id}_{doc_id}"
            
            groups_dict[group_key].append(msg)
        
        # 构建分组结果
        groups = []
        for group_key, messages in groups_dict.items():
            if not messages:
                continue
            
            # 从第一条消息中提取元数据（组内共享）
            first_msg = messages[0]
            
            # 构建组信息
            group = {
                # 元数据（只出现一次）
                "project_id": first_msg.get('project_id'),
                "project_name": first_msg.get('project_name'),
                "folder_name": first_msg.get('folder_name'),
                "doc_id": first_msg.get('doc_id'),
                "doc_name": first_msg.get('doc_name'),
                "doc_type": first_msg.get('doc_type'),
                "doc_version": first_msg.get('doc_version'),
                "doc_updated_at": first_msg.get('doc_updated_at'),
                "doc_url": first_msg.get('doc_url'),
                
                # 统计信息
                "message_count": len(messages),
                "mentions_me_count": sum(1 for m in messages if m.get("mentions_me")),
                
                # 消息列表（移除元数据字段）
                "messages": []
            }
            
            # 移除消息中的元数据字段，只保留核心信息
            meta_fields = {
                'project_id', 'project_name', 'folder_name',
                'doc_id', 'doc_name', 'doc_type', 'doc_version',
                'doc_updated_at', 'doc_url'
            }
            
            for msg in messages:
                # 创建精简消息（不含元数据）
                slim_msg = {k: v for k, v in msg.items() if k not in meta_fields}
                # 清理null字段并添加is_edited/is_mine标志
                slim_msg = _clean_message_dict(slim_msg, user_name)
                group["messages"].append(slim_msg)
            
            groups.append(group)
        
        # 按组内最新消息时间排序
        groups.sort(
            key=lambda g: max((m.get('created_at', '') for m in g['messages']), default=''),
            reverse=True
        )
        
        return groups



def get_user_info(ctx: Context) -> tuple:
    """
    从URL query参数获取用户信息
    
    MCP连接URL格式：http://xxx:port/mcp?role=后端&name=张三
    """
    env_name = os.getenv("LANHU_MCP_USER_NAME", "匿名")
    env_role = os.getenv("LANHU_MCP_USER_ROLE", "未知")
    try:
        # 使用 FastMCP 提供的 get_http_request 获取当前请求
        from fastmcp.server.dependencies import get_http_request
        req = get_http_request()
        
        # 从 query 参数获取
        name = req.query_params.get('name', env_name)
        role = req.query_params.get('role', env_role)
        return name, role
    except Exception:
        pass
    return env_name, env_role


def _clean_message_dict(msg: dict, current_user_name: str = None) -> dict:
    """
    清理消息字典，移除null值的更新字段，并添加快捷标志
    
    优化：
    1. 如果消息未被编辑，省略 updated_at/updated_by_name/updated_by_role
    2. 添加 is_edited 标志
    3. 添加 is_mine 标志（如果提供了current_user_name）
    """
    cleaned = msg.copy()
    
    # 如果消息未被编辑，省略这些字段
    if cleaned.get('updated_at') is None:
        cleaned.pop('updated_at', None)
        cleaned.pop('updated_by_name', None)
        cleaned.pop('updated_by_role', None)
        cleaned['is_edited'] = False
    else:
        cleaned['is_edited'] = True
    
    # 添加is_mine标志
    if current_user_name:
        cleaned['is_mine'] = (cleaned.get('author_name') == current_user_name)
    
    return cleaned


def get_project_id_from_url(url: str) -> str:
    """从URL中提取project_id"""
    if not url or url.lower() == 'all':
        return None
    extractor = LanhuExtractor()
    params = extractor.parse_url(url)
    return params.get('project_id', '')


async def _fetch_metadata_from_url(url: str) -> dict:
    """
    从蓝湖URL获取标准元数据（10个字段）- 支持基于版本号的永久缓存
    
    Args:
        url: 蓝湖URL
    
    Returns:
        包含10个元数据字段的字典，获取失败的字段为None
    """
    metadata = {
        'project_id': None,
        'project_name': None,
        'folder_name': None,
        'doc_id': None,
        'doc_name': None,
        'doc_type': None,
        'doc_version': None,
        'doc_updated_at': None,
        'doc_url': None
    }
    
    extractor = LanhuExtractor()
    try:
        params = extractor.parse_url(url)
        project_id = params.get('project_id')
        doc_id = params.get('doc_id')
        team_id = params.get('team_id')
        
        metadata['project_id'] = project_id
        metadata['doc_id'] = doc_id
        
        if not project_id:
            return metadata
        
        # 生成缓存键
        cache_key = _get_metadata_cache_key(project_id, doc_id)
        
        # 如果有doc_id，获取文档信息和版本号
        version_id = None
        if doc_id:
            doc_info = await extractor.get_document_info(project_id, doc_id)
            
            # 获取版本ID
            versions = doc_info.get('versions', [])
            if versions:
                version_id = versions[0].get('id')
                metadata['doc_version'] = versions[0].get('version_info')
            
            # 检查缓存（基于版本号）
            cached = _get_cached_metadata(cache_key, version_id)
            if cached:
                return cached
            
            # 缓存未命中，继续获取数据
            metadata['doc_name'] = doc_info.get('name')
            metadata['doc_type'] = doc_info.get('type', 'axure')
            
            # 格式化更新时间
            update_time = doc_info.get('update_time')
            if update_time:
                try:
                    dt = datetime.fromisoformat(update_time.replace('Z', '+00:00'))
                    dt_china = dt.astimezone(CHINA_TZ)
                    metadata['doc_updated_at'] = dt_china.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    metadata['doc_updated_at'] = update_time
            
            # 构建文档URL
            if team_id and project_id and doc_id:
                metadata['doc_url'] = (
                    f"https://lanhuapp.com/web/#/item/project/product"
                    f"?tid={team_id}&pid={project_id}&docId={doc_id}"
                )
        
        # 获取项目信息
        if project_id and team_id:
            try:
                response = await extractor.client.get(
                    f"{BASE_URL}/api/project/multi_info",
                    params={
                        'project_id': project_id,
                        'team_id': team_id,
                        'doc_info': 1
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get('code') == '00000':
                        project_info = data.get('result', {})
                        metadata['project_name'] = project_info.get('name')
                        metadata['folder_name'] = project_info.get('folder_name')
            except Exception:
                pass
        
        # 存入缓存（基于版本号）
        _set_cached_metadata(cache_key, metadata, version_id)
    
    except Exception:
        pass
    finally:
        await extractor.close()
    
    return metadata



class LanhuExtractor:
    """蓝湖提取器"""

    CACHE_META_FILE = ".lanhu_cache.json"  # 缓存元数据文件名

    def __init__(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://lanhuapp.com/web/",
            "Accept": "application/json, text/plain, */*",
            "Cookie": COOKIE,
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "request-from": "web",
            "real-path": "/item/project/product"
        }
        self.client = httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=headers, follow_redirects=True)

    def _check_auth(self, response: httpx.Response):
        """检查响应是否表示 Cookie 过期或鉴权失败，若是则抛出明确提示"""
        _auth_error_msg = (
            "蓝湖认证失败 (HTTP {detail})，Cookie 已过期或无效。"
            "请重新从浏览器复制 Cookie 并更新 cookie 文件后重启 MCP。"
        )
        # HTTP 层鉴权失败（418 是蓝湖对无效 Cookie 的实际返回码）
        if response.status_code in (401, 403, 418):
            raise Exception(_auth_error_msg.format(detail=response.status_code))
        # 蓝湖 API 层鉴权失败（返回特定错误码或关键词）
        if response.status_code == 200:
            try:
                data = response.json()
                code = data.get('code')
                msg = data.get('msg', '') or data.get('message', '') or ''
                auth_fail_codes = {10001, '10001', 10003, '10003', 401, '401'}
                auth_fail_keywords = ['登录', 'login', '未登录', '请登录', 'token', '过期', 'expired', '认证失败']
                if code in auth_fail_codes or any(kw in msg.lower() for kw in auth_fail_keywords):
                    raise Exception(_auth_error_msg.format(detail=f"code={code}, msg={msg}"))
            except (ValueError, AttributeError):
                pass  # 非 JSON 响应，跳过检查

    def parse_url(self, url: str) -> dict:
        """
        解析蓝湖URL，支持多种格式：
        1. 完整URL: https://lanhuapp.com/web/#/item/project/product?tid=...&pid=...
        2. 完整URL: https://lanhuapp.com/web/#/item/project/stage?tid=...&pid=...
        3. 参数部分: ?tid=...&pid=...
        4. 参数部分（无?）: tid=...&pid=...

        Args:
            url: 蓝湖URL或参数字符串

        Returns:
            包含project_id, team_id, doc_id, version_id的字典
        """
        # 如果是完整URL，提取fragment部分
        if url.startswith('http'):
            parsed = urlparse(url)
            fragment = parsed.fragment

            if not fragment:
                raise ValueError("Invalid Lanhu URL: missing fragment part")

            # 从fragment中提取参数部分
            if '?' in fragment:
                url = fragment.split('?', 1)[1]
            else:
                url = fragment

        # 处理只有参数的情况
        if url.startswith('?'):
            url = url[1:]

        # 解析参数
        params = {}
        for part in url.split('&'):
            if '=' in part:
                key, value = part.split('=', 1)
                params[key] = value

        # 提取必需参数
        team_id = params.get('tid')
        project_id = params.get('pid')
        doc_id = params.get('docId') or params.get('image_id')
        version_id = params.get('versionId')

        # 验证必需参数
        if not project_id:
            raise ValueError(f"URL parsing failed: missing required param pid (project_id)")

        if not team_id:
            raise ValueError(f"URL parsing failed: missing required param tid (team_id)")

        return {
            'team_id': team_id,
            'project_id': project_id,
            'doc_id': doc_id,
            'version_id': version_id
        }

    async def get_document_info(self, project_id: str, doc_id: str) -> dict:
        """获取文档信息"""
        api_url = f"{BASE_URL}/api/project/image"
        params = {'pid': project_id, 'image_id': doc_id}

        response = await self.client.get(api_url, params=params)
        self._check_auth(response)
        response.raise_for_status()

        data = response.json()
        code = data.get('code')
        success = (code == 0 or code == '0' or code == '00000')

        if not success:
            raise Exception(f"API Error: {data.get('msg')} (code={code})")

        return data.get('data') or data.get('result', {})

    def _get_cache_meta_path(self, output_dir: Path) -> Path:
        """获取缓存元数据文件路径"""
        return output_dir / self.CACHE_META_FILE

    def _load_cache_meta(self, output_dir: Path) -> dict:
        """加载缓存元数据"""
        meta_path = self._get_cache_meta_path(output_dir)
        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache_meta(self, output_dir: Path, meta_data: dict):
        """保存缓存元数据"""
        meta_path = self._get_cache_meta_path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)

    def _check_file_integrity(self, output_dir: Path, expected_files: dict) -> dict:
        """
        检查文件完整性

        Args:
            output_dir: 输出目录
            expected_files: 期望的文件字典 {相对路径: md5签名}

        Returns:
            {
                'missing': [缺失的文件列表],
                'corrupted': [损坏的文件列表],
                'valid': [有效的文件列表]
            }
        """
        result = {
            'missing': [],
            'corrupted': [],
            'valid': []
        }

        for rel_path, expected_md5 in expected_files.items():
            file_path = output_dir / rel_path

            if not file_path.exists():
                result['missing'].append(rel_path)
            elif expected_md5:
                # 如果有MD5签名，验证文件
                # 注意：这里简化处理，只检查文件是否存在
                # 完整的MD5验证会比较慢
                result['valid'].append(rel_path)
            else:
                result['valid'].append(rel_path)

        return result

    def _should_update_cache(self, output_dir: Path, current_version_id: str, project_mapping: dict) -> tuple:
        """
        检查是否需要更新缓存

        Returns:
            (需要更新, 缺失的文件列表)
        """
        cache_meta = self._load_cache_meta(output_dir)

        # 检查版本
        cached_version = cache_meta.get('version_id')
        if cached_version != current_version_id:
            return (True, 'version_changed', [])

        # 检查文件完整性
        pages = project_mapping.get('pages', {})
        expected_files = {}

        # 收集所有应该存在的文件
        for html_filename in pages.keys():
            expected_files[html_filename] = None

        # 检查关键目录
        for key_dir in ['data', 'resources', 'files', 'images']:
            expected_files[key_dir] = None

        integrity = self._check_file_integrity(output_dir, expected_files)

        if integrity['missing']:
            return (True, 'files_missing', integrity['missing'])

        return (False, 'up_to_date', [])

    async def get_pages_list(self, url: str) -> dict:
        """获取文档的所有页面列表（仅包含sitemap中的页面，与Web界面一致）"""
        params = self.parse_url(url)
        doc_info = await self.get_document_info(params['project_id'], params['doc_id'])

        # 获取项目详细信息（包含创建者等信息）
        project_info = None
        try:
            response = await self.client.get(
                f"{BASE_URL}/api/project/multi_info",
                params={
                    'project_id': params['project_id'],
                    'team_id': params['team_id'],
                    'doc_info': 1
                }
            )
            response.raise_for_status()
            data = response.json()
            if data.get('code') == '00000':
                project_info = data.get('result', {})
        except Exception:
            pass  # 如果获取失败，继续使用基本信息

        # 获取项目级mapping JSON
        versions = doc_info.get('versions', [])
        if not versions:
            raise Exception("Document version info not found")

        latest_version = versions[0]
        json_url = latest_version.get('json_url')
        if not json_url:
            raise Exception("Mapping JSON URL not found")

        response = await self.client.get(json_url)
        self._check_auth(response)
        response.raise_for_status()
        project_mapping = response.json()

        # 从sitemap获取页面列表（只返回在导航中显示的页面）
        sitemap = project_mapping.get('sitemap', {})
        root_nodes = sitemap.get('rootNodes', [])

        # 递归提取所有页面（保留层级结构）
        def extract_pages(nodes, pages_list, parent_path="", level=0, parent_folder=None):
            """
            递归提取页面，保留层级信息
            
            根据真实蓝湖sitemap结构：
            - 纯文件夹：type="Folder" 且 url=""
            - 页面节点：有url字段（type="Wireframe"等）
            - 页面可以有children（子页面）
            
            Args:
                nodes: 当前层级的节点列表
                pages_list: 输出的页面列表
                parent_path: 父级路径（用/分隔）
                level: 当前层级深度（0为根）
                parent_folder: 所属文件夹名称（最近的Folder节点）
            """
            for node in nodes:
                page_name = node.get('pageName', '')
                url = node.get('url', '')
                node_type = node.get('type', 'Wireframe')
                node_id = node.get('id', '')
                
                # 构建当前路径
                current_path = f"{parent_path}/{page_name}" if parent_path else page_name
                
                # 判断是否为纯文件夹（type=Folder 且 无url）
                is_pure_folder = (node_type == 'Folder' and not url)
                
                if page_name and url:
                    # 这是一个页面（有url的都是页面）
                    pages_list.append({
                        'index': len(pages_list) + 1,
                        'name': page_name,
                        'filename': url,
                        'id': node_id,
                        'type': node_type,
                        'level': level,
                        'folder': parent_folder or '根目录',  # 所属文件夹
                        'path': current_path,  # 完整路径
                        'has_children': bool(node.get('children'))  # 是否有子页面
                    })
                
                # 递归处理子节点
                children = node.get('children', [])
                if children:
                    # 如果当前是纯文件夹，更新parent_folder
                    # 如果当前是页面，保持原parent_folder
                    next_folder = page_name if is_pure_folder else parent_folder
                    
                    extract_pages(
                        children, 
                        pages_list, 
                        parent_path=current_path,
                        level=level + 1,
                        parent_folder=next_folder
                    )

        pages_list = []
        extract_pages(root_nodes, pages_list)

        # 格式化时间（转换为东八区/北京时间）
        def format_time(time_str):
            if not time_str:
                return None
            try:
                # 处理ISO格式时间，转换为东八区
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                dt_china = dt.astimezone(CHINA_TZ)
                return dt_china.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return time_str

        # 统计分组信息
        from collections import defaultdict
        folder_stats = defaultdict(int)
        max_level = 0
        pages_with_children = 0
        
        for page in pages_list:
            folder = page.get('folder', '根目录')
            folder_stats[folder] += 1
            max_level = max(max_level, page.get('level', 0))
            if page.get('has_children'):
                pages_with_children += 1
        
        # 构建返回结果
        result = {
            'document_id': params['doc_id'],
            'document_name': doc_info.get('name', 'Unknown'),
            'document_type': doc_info.get('type', 'axure'),
            'total_pages': len(pages_list),
            'max_level': max_level,
            'pages_with_children': pages_with_children,  # 有子页面的页面数
            'folder_statistics': dict(folder_stats),  # 每个文件夹下有多少页面（按纯Folder统计）
            'pages': pages_list
        }

        # 添加时间信息
        if doc_info.get('create_time'):
            result['create_time'] = format_time(doc_info.get('create_time'))
        if doc_info.get('update_time'):
            result['update_time'] = format_time(doc_info.get('update_time'))

        # 添加版本信息
        result['total_versions'] = len(versions)
        if latest_version.get('version_info'):
            result['latest_version'] = latest_version.get('version_info')

        # 添加项目信息（如果成功获取）
        if project_info:
            if project_info.get('creator_name'):
                result['creator_name'] = project_info.get('creator_name')
            if project_info.get('folder_name'):
                result['folder_name'] = project_info.get('folder_name')
            if project_info.get('save_path'):
                result['project_path'] = project_info.get('save_path')
            if project_info.get('member_cnt'):
                result['member_count'] = project_info.get('member_cnt')

        return result

    async def download_resources(self, url: str, output_dir: str, force_update: bool = False) -> dict:
        """
        下载所有Axure资源（支持智能缓存）

        Args:
            url: 蓝湖文档URL
            output_dir: 输出目录
            force_update: 强制更新，忽略缓存

        Returns:
            {
                'status': 'downloaded' | 'cached' | 'updated',
                'version_id': 版本ID,
                'reason': 更新原因,
                'output_dir': 输出目录
            }
        """
        params = self.parse_url(url)
        doc_info = await self.get_document_info(params['project_id'], params['doc_id'])

        # 获取项目级mapping JSON
        versions = doc_info.get('versions', [])
        version_info = versions[0]
        version_id = version_info.get('id', '')  # 版本ID字段名是'id'
        json_url = version_info.get('json_url')

        response = await self.client.get(json_url)
        self._check_auth(response)
        response.raise_for_status()
        project_mapping = response.json()

        # 创建输出目录
        output_path = Path(output_dir)

        # 检查是否需要更新
        if not force_update and output_path.exists():
            need_update, reason, missing_files = self._should_update_cache(
                output_path, version_id, project_mapping
            )

            if not need_update:
                return {
                    'status': 'cached',
                    'version_id': version_id,
                    'reason': reason,
                    'output_dir': output_dir
                }

            # 如果只是文件缺失，可以增量下载
            if reason == 'files_missing' and missing_files:
                # 这里可以实现增量下载逻辑
                # 为了简化，暂时还是全量下载
                pass

        output_path.mkdir(parents=True, exist_ok=True)

        # 下载每个页面的资源
        pages = project_mapping.get('pages', {})
        is_first_page = True

        downloaded_files = []

        for html_filename, page_info in pages.items():
            html_data = page_info.get('html', {})
            html_file_with_md5 = html_data.get('sign_md5', '')
            page_mapping_md5 = page_info.get('mapping_md5', '')

            if not html_file_with_md5:
                continue

            # 下载HTML
            html_url = f"{CDN_URL}/{html_file_with_md5}"
            response = await self.client.get(html_url)
            response.raise_for_status()
            html_content = response.text

            # 下载页面级mapping JSON
            if page_mapping_md5:
                mapping_url = f"{CDN_URL}/{page_mapping_md5}"
                response = await self.client.get(mapping_url)
                response.raise_for_status()
                page_mapping = response.json()

                # 下载所有依赖资源
                await self._download_page_resources(
                    page_mapping, output_path, skip_document_js=(not is_first_page)
                )
                is_first_page = False

            # 保存HTML
            html_path = output_path / html_filename
            html_path.write_text(html_content, encoding='utf-8')
            downloaded_files.append(html_filename)

        # 保存缓存元数据
        cache_meta = {
            'version_id': version_id,
            'document_id': params['doc_id'],
            'document_name': doc_info.get('name', 'Unknown'),
            'download_time': asyncio.get_event_loop().time(),
            'pages': list(pages.keys()),
            'total_files': len(downloaded_files)
        }
        self._save_cache_meta(output_path, cache_meta)

        return {
            'status': 'downloaded',
            'version_id': version_id,
            'reason': 'first_download' if not output_path.exists() else 'version_changed',
            'output_dir': output_dir
        }

    async def _download_page_resources(self, page_mapping: dict, output_dir: Path, skip_document_js: bool = False):
        """下载页面资源"""
        tasks = []

        # 下载CSS
        for local_path, info in page_mapping.get('styles', {}).items():
            sign_md5 = info.get('sign_md5', '')
            if sign_md5:
                url = sign_md5 if sign_md5.startswith('http') else f"{CDN_URL}/{sign_md5}"
                tasks.append(self._download_file(url, output_dir / local_path))

        # 下载JS
        for local_path, info in page_mapping.get('scripts', {}).items():
            if skip_document_js and local_path == 'data/document.js':
                continue
            sign_md5 = info.get('sign_md5', '')
            if sign_md5:
                url = sign_md5 if sign_md5.startswith('http') else f"{CDN_URL}/{sign_md5}"
                tasks.append(self._download_file(url, output_dir / local_path))

        # 下载图片
        for local_path, info in page_mapping.get('images', {}).items():
            sign_md5 = info.get('sign_md5', '')
            if sign_md5:
                url = sign_md5 if sign_md5.startswith('http') else f"{CDN_URL}/{sign_md5}"
                tasks.append(self._download_file(url, output_dir / local_path))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _download_file(self, url: str, local_path: Path):
        """下载单个文件"""
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            response = await self.client.get(url)
            response.raise_for_status()
            local_path.write_bytes(response.content)
        except Exception:
            pass

    async def _fetch_design_payload(self, image_id: str, team_id: str, project_id: str) -> dict:
        """获取设计图详情及其最新版本 JSON。"""
        url = f"{BASE_URL}/api/project/image"
        params = {
            "dds_status": 1,
            "image_id": image_id,
            "team_id": team_id,
            "project_id": project_id
        }
        response = await self.client.get(url, params=params)
        self._check_auth(response)
        response.raise_for_status()
        data = response.json()

        code = data.get('code')
        if code != '00000':
            raise Exception(f"Failed to get design: {data.get('msg', 'Unknown error')}")

        result = data.get('result') or data.get('data') or {}
        versions = result.get('versions', [])
        if not versions:
            raise Exception("Design version info not found")

        latest_version = versions[0]
        json_url = latest_version.get('json_url')
        if not json_url:
            raise Exception("Design JSON URL not found")

        json_response = await self.client.get(json_url)
        json_response.raise_for_status()

        return {
            'design': result,
            'latest_version': latest_version,
            'sketch_data': json_response.json()
        }

    @staticmethod
    def _safe_number(value: Any) -> Optional[Union[int, float]]:
        """将数值字段安全转换为 int/float。"""
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value
        try:
            number = float(value)
            if number.is_integer():
                return int(number)
            return number
        except (TypeError, ValueError):
            return None

    @classmethod
    def _infer_dp_scale(cls, design_width: Any) -> float:
        """根据设计稿宽度自动推断 px→dp 缩放系数。"""
        w = cls._safe_number(design_width)
        if w is None or w <= 0:
            return ANNOTATION_DP_SCALE  # fallback
        if w <= 480:
            # 已经是 dp 尺寸（360/375/390/414 等）
            return 1.0
        if w <= 840:
            # 2x 设计稿（720/750/828 等）
            return 0.5
        # 3x 设计稿（1080/1125 等）
        return 1.0 / 3.0

    @classmethod
    def _to_dp(cls, value: Any, scale: float = None) -> Optional[int]:
        """将原始设计稿数值按缩放系数转换为整数 dp。"""
        number = cls._safe_number(value)
        if number is None:
            return None
        s = scale if scale is not None else ANNOTATION_DP_SCALE
        return int(round(number * s))

    @classmethod
    def _convert_position_to_dp(cls, position: Optional[dict], scale: float = None) -> Optional[dict]:
        if not isinstance(position, dict):
            return position
        return {
            'x': cls._to_dp(position.get('x'), scale),
            'y': cls._to_dp(position.get('y'), scale)
        }

    @classmethod
    def _convert_size_to_dp(cls, size: Optional[dict], scale: float = None) -> Optional[dict]:
        if not isinstance(size, dict):
            return size
        return {
            'width': cls._to_dp(size.get('width'), scale),
            'height': cls._to_dp(size.get('height'), scale)
        }

    @classmethod
    def _convert_text_spec_to_dp(cls, text_spec: Optional[dict], scale: float = None) -> Optional[dict]:
        if not isinstance(text_spec, dict):
            return text_spec

        converted = copy.deepcopy(text_spec)
        converted['font_size'] = cls._to_dp(converted.get('font_size'), scale)
        converted['line_height'] = cls._to_dp(converted.get('line_height'), scale)
        converted['letter_spacing'] = cls._to_dp(converted.get('letter_spacing'), scale)
        return converted

    @classmethod
    def _convert_style_spec_to_dp(cls, style_spec: Optional[dict], scale: float = None) -> Optional[dict]:
        if not isinstance(style_spec, dict):
            return style_spec

        converted = copy.deepcopy(style_spec)
        # 圆角转 dp
        converted['border_radius'] = cls._to_dp(converted.get('border_radius'), scale)
        converted['border_radius_raw'] = cls._to_dp(converted.get('border_radius_raw'), scale)
        detail_raw = converted.get('border_radius_detail_raw')
        if isinstance(detail_raw, dict):
            for k in list(detail_raw.keys()):
                detail_raw[k] = cls._to_dp(detail_raw.get(k), scale)
        elif isinstance(detail_raw, list):
            converted['border_radius_detail_raw'] = [cls._to_dp(v, scale) for v in detail_raw]

        for border in converted.get('borders') or []:
            if isinstance(border, dict) and 'thickness' in border:
                border['thickness'] = cls._to_dp(border.get('thickness'), scale)

        shadow_dimension_keys = {
            'blurRadius', 'blur', 'spread', 'spreadRadius',
            'offsetX', 'offsetY', 'shadowOffsetX', 'shadowOffsetY',
            'x', 'y'
        }
        for shadow in converted.get('shadows') or []:
            if not isinstance(shadow, dict):
                continue
            for key in shadow_dimension_keys:
                if key in shadow:
                    shadow[key] = cls._to_dp(shadow.get(key), scale)

        return converted

    @classmethod
    def _layer_rect(cls, layer: dict) -> Optional[dict]:
        """返回图层矩形，用于测量间距与包含关系。"""
        position = layer.get('position') or {}
        size = layer.get('size') or {}
        x = cls._safe_number(position.get('x'))
        y = cls._safe_number(position.get('y'))
        width = cls._safe_number(size.get('width'))
        height = cls._safe_number(size.get('height'))
        if None in (x, y, width, height):
            return None
        return {
            'left': x,
            'top': y,
            'right': x + width,
            'bottom': y + height,
            'width': width,
            'height': height,
        }

    @staticmethod
    def _is_meaningful_named_layer(layer: dict) -> bool:
        return bool(layer.get('name')) and bool(layer.get('visible', True))

    @staticmethod
    def _contains_rect(outer: dict, inner: dict, epsilon: float = 1e-6) -> bool:
        return (
            outer['left'] <= inner['left'] + epsilon and
            outer['top'] <= inner['top'] + epsilon and
            outer['right'] >= inner['right'] - epsilon and
            outer['bottom'] >= inner['bottom'] - epsilon
        )

    @classmethod
    def _measure_rect_relationship(cls, source_rect: dict, target_rect: dict) -> dict:
        """计算两个矩形之间的边缘间距与方向关系。"""
        horizontal_gap = max(
            target_rect['left'] - source_rect['right'],
            source_rect['left'] - target_rect['right'],
            0
        )
        vertical_gap = max(
            target_rect['top'] - source_rect['bottom'],
            source_rect['top'] - target_rect['bottom'],
            0
        )

        if horizontal_gap and vertical_gap:
            edge_distance = math.hypot(horizontal_gap, vertical_gap)
        else:
            edge_distance = max(horizontal_gap, vertical_gap)

        source_inside_target = cls._contains_rect(target_rect, source_rect)
        target_inside_source = cls._contains_rect(source_rect, target_rect)

        if source_inside_target and not target_inside_source:
            relation = 'inside'
        elif target_inside_source and not source_inside_target:
            relation = 'contains'
        elif horizontal_gap == 0 and vertical_gap == 0:
            relation = 'overlap'
        elif horizontal_gap > 0 and vertical_gap > 0:
            relation = 'diagonal'
        elif target_rect['left'] >= source_rect['right']:
            relation = 'right'
        elif target_rect['right'] <= source_rect['left']:
            relation = 'left'
        elif target_rect['top'] >= source_rect['bottom']:
            relation = 'below'
        else:
            relation = 'above'

        return {
            'relation': relation,
            'horizontal_gap': cls._safe_number(horizontal_gap),
            'vertical_gap': cls._safe_number(vertical_gap),
            'edge_distance': cls._safe_number(edge_distance),
        }

    @classmethod
    def _is_icon_measurement_candidate(cls, layer: dict) -> bool:
        """判断图层是否适合作为 icon / 小型视觉元素测量对象。"""
        if layer.get('kind') == 'text' or not cls._is_meaningful_named_layer(layer):
            return False

        rect = cls._layer_rect(layer)
        if not rect:
            return False

        width = rect['width']
        height = rect['height']
        source_type = str(layer.get('source_type') or '').lower()
        name = str(layer.get('name') or '').lower()

        icon_keywords = ['icon', 'wifi', 'battery', 'cellular', 'arrow', '返回', 'close', 'menu']
        if layer.get('kind') == 'icon' or any(keyword in name for keyword in icon_keywords):
            return True

        return (
            max(width, height) <= 128 and
            (
                layer.get('kind') in {'image', 'shape'} or
                'shape' in source_type or
                'bitmap' in source_type or
                'vector' in source_type or
                'path' in source_type
            )
        )

    @classmethod
    def _extract_layer_frame(cls, obj: dict) -> dict:
        """提取图层几何信息。"""
        return obj.get('frame') or obj.get('bounds') or {}

    @classmethod
    def _extract_position(cls, obj: dict) -> Optional[dict]:
        """提取图层位置。"""
        frame = cls._extract_layer_frame(obj)
        x = cls._safe_number(frame.get('x', frame.get('left', obj.get('left'))))
        y = cls._safe_number(frame.get('y', frame.get('top', obj.get('top'))))
        if x is None and y is None:
            return None
        return {'x': x, 'y': y}

    @classmethod
    def _extract_size(cls, obj: dict) -> Optional[dict]:
        """提取图层尺寸。"""
        frame = cls._extract_layer_frame(obj)
        width = cls._safe_number(frame.get('width', obj.get('width')))
        height = cls._safe_number(frame.get('height', obj.get('height')))

        if (width is None or height is None) and obj.get('ddsImage'):
            size_value = obj['ddsImage'].get('size')
            if isinstance(size_value, str) and 'x' in size_value:
                width_str, height_str = size_value.lower().split('x', 1)
                width = width if width is not None else cls._safe_number(width_str)
                height = height if height is not None else cls._safe_number(height_str)

        if width is None and height is None:
            return None
        return {'width': width, 'height': height}

    @staticmethod
    def _extract_text_content(value: Any) -> Optional[str]:
        """从嵌套结构中提取文本内容。"""
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, list):
            parts = [LanhuExtractor._extract_text_content(item) for item in value]
            combined = " ".join(part for part in parts if part)
            return combined or None
        if isinstance(value, dict):
            for key in ['text', 'string', 'content', 'value']:
                if key in value:
                    extracted = LanhuExtractor._extract_text_content(value[key])
                    if extracted:
                        return extracted
            for key in ['fragments', 'runs', 'children', 'items']:
                if key in value:
                    extracted = LanhuExtractor._extract_text_content(value[key])
                    if extracted:
                        return extracted
        return None

    @staticmethod
    def _parse_fill_color(fills: Any) -> Optional[str]:
        """从 fills 数组提取第一个 enabled 颜色，返回 #RRGGBB 或 #AARRGGBB hex。"""
        if not isinstance(fills, list):
            return None
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            if fill.get('isEnabled') is False:
                continue
            color = fill.get('color')
            if not isinstance(color, dict):
                continue
            r = color.get('r')
            g = color.get('g')
            b = color.get('b')
            a = color.get('a', 1)
            if r is None or g is None or b is None:
                continue
            # r/g/b 可能是 0-1 百分比或 0-255；若全部 <= 1.0 则视为百分比
            if r <= 1.0 and g <= 1.0 and b <= 1.0:
                ri, gi, bi = round(r * 255), round(g * 255), round(b * 255)
            else:
                ri, gi, bi = round(r), round(g), round(b)
            ri = max(0, min(255, ri))
            gi = max(0, min(255, gi))
            bi = max(0, min(255, bi))
            if a is not None and isinstance(a, (int, float)) and a == 0 and (ri > 0 or gi > 0 or bi > 0):
                return f"#00{ri:02X}{gi:02X}{bi:02X}"  # fully transparent but has color
            if a is not None and isinstance(a, (int, float)) and a < 0.995:
                ai = max(0, min(255, round(a * 255)))
                return f"#{ai:02X}{ri:02X}{gi:02X}{bi:02X}"
            return f"#{ri:02X}{gi:02X}{bi:02X}"
        return None

    @staticmethod
    def _color_to_hex(color: dict) -> Optional[str]:
        """将 {r,g,b,a} 颜色对象转为 hex 字符串。支持 0-1 百分比和 0-255 整数两种格式。"""
        if not isinstance(color, dict):
            return None
        r, g, b, a = color.get('r'), color.get('g'), color.get('b'), color.get('a', 1)
        # Sketch 有时 r/g/b=0 但 value 里有真实颜色，需要从 value 兜底
        if (r == 0 and g == 0 and b == 0) and color.get('value'):
            import re
            m = re.match(r'rgba?\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)', str(color['value']))
            if m:
                rv, gv, bv = float(m.group(1)), float(m.group(2)), float(m.group(3))
                if rv > 1 or gv > 1 or bv > 1:
                    r, g, b = rv, gv, bv
        if r is None or g is None or b is None:
            return None
        if r <= 1.0 and g <= 1.0 and b <= 1.0:
            ri, gi, bi = round(r * 255), round(g * 255), round(b * 255)
        else:
            ri, gi, bi = round(r), round(g), round(b)
        ri, gi, bi = max(0, min(255, ri)), max(0, min(255, gi)), max(0, min(255, bi))
        if ri == 0 and gi == 0 and bi == 0 and (a == 0 or a is None):
            return None  # fully transparent / no color
        if a is not None and isinstance(a, (int, float)) and a < 0.995:
            ai = max(0, min(255, round(a * 255)))
            return f"#{ai:02X}{ri:02X}{gi:02X}{bi:02X}"
        return f"#{ri:02X}{gi:02X}{bi:02X}"

    @classmethod
    def _parse_fill_gradient(cls, fills: Any) -> Optional[dict]:
        """从 fills 数组提取第一个 enabled 渐变，返回简化的渐变描述。"""
        if not isinstance(fills, list):
            return None
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            if fill.get('isEnabled') is False:
                continue
            if fill.get('type') != 'gradient':
                continue
            gradient = fill.get('gradient')
            if not isinstance(gradient, dict):
                continue
            stops = gradient.get('stops') or gradient.get('colorStops')
            if not isinstance(stops, list) or len(stops) < 2:
                continue
            from_pt = gradient.get('from', {})
            to_pt = gradient.get('to', {})
            parsed_stops = []
            for stop in stops:
                if not isinstance(stop, dict):
                    continue
                hex_color = cls._color_to_hex(stop.get('color', {}))
                if hex_color:
                    parsed_stops.append({
                        'color': hex_color,
                        'position': stop.get('position', 0)
                    })
            if len(parsed_stops) < 2:
                continue
            # 判断方向
            fx, fy = from_pt.get('x', 0.5), from_pt.get('y', 0)
            tx, ty = to_pt.get('x', 0.5), to_pt.get('y', 1)
            if abs(fx - tx) < 0.01:
                direction = 'vertical'
            elif abs(fy - ty) < 0.01:
                direction = 'horizontal'
            else:
                direction = 'diagonal'
            return {
                'direction': direction,
                'from': {'x': round(fx, 3), 'y': round(fy, 3)},
                'to': {'x': round(tx, 3), 'y': round(ty, 3)},
                'stops': parsed_stops
            }
        return None

    @classmethod
    def _parse_borders(cls, borders: Any) -> Optional[list]:
        """从 borders 数组解析出简化的边框描述列表。"""
        if not isinstance(borders, list) or not borders:
            return None
        result = []
        for b in borders:
            if not isinstance(b, dict):
                continue
            if b.get('isEnabled') is False:
                continue
            color_hex = cls._color_to_hex(b.get('color', {}))
            if not color_hex:
                continue
            result.append({
                'color': color_hex,
                'width': b.get('width'),
                'style': b.get('style', 'solid'),
                'alignment': b.get('lineAlignment', 'center'),
            })
        return result if result else None

    @classmethod
    def _build_text_spec(cls, obj: dict) -> Optional[dict]:
        """标准化文本样式。"""
        text_style = obj.get('textStyle') or {}
        paragraph_style = text_style.get('paragraphStyle') if isinstance(text_style, dict) else {}
        if not isinstance(paragraph_style, dict):
            paragraph_style = {}

        # Figma 路径: obj['text']['style']['font']
        nested_text = obj.get('text')
        nested_font = {}
        if isinstance(nested_text, dict):
            nested_style = nested_text.get('style') if isinstance(nested_text.get('style'), dict) else {}
            nested_font = nested_style.get('font') if isinstance(nested_style.get('font'), dict) else {}

        # Sketch 路径: obj['font'] → {font, displayName, size, color, content, align, line, styles[]}
        sketch_font = obj.get('font') if isinstance(obj.get('font'), dict) else {}

        # 蓝湖 API: 文本颜色在 obj['style']['fills'] 里
        style_obj = obj.get('style') if isinstance(obj.get('style'), dict) else {}
        style_fills = style_obj.get('fills')

        # Sketch font.color 是 {r,g,b,a} 0-255 格式
        sketch_color = cls._color_to_hex(sketch_font.get('color', {})) if sketch_font else None

        # Sketch font.displayName 如 "Roboto Medium" → 拆分出 family 和 weight
        sketch_display = sketch_font.get('displayName') or ''
        sketch_family = sketch_display.split()[0] if sketch_display else None
        sketch_weight = ' '.join(sketch_display.split()[1:]) if len(sketch_display.split()) > 1 else None

        spec = {
            'content': cls._extract_text_content(
                obj.get('text') or obj.get('attributedString') or obj.get('content') or obj.get('string')
                or sketch_font.get('content')
            ),
            'font_family': (text_style.get('fontFamily') or text_style.get('fontName')
                            or text_style.get('fontPostscriptName')
                            or nested_font.get('name')
                            or sketch_family),
            'font_size': cls._safe_number(
                text_style.get('fontSize') or obj.get('fontSize')
                or nested_font.get('size')
                or sketch_font.get('size')),
            'font_weight': (text_style.get('fontWeight') or text_style.get('fontStyle')
                            or nested_font.get('type')
                            or sketch_weight),
            'line_height': cls._safe_number(
                text_style.get('lineHeight') or paragraph_style.get('lineHeight')
                or paragraph_style.get('lineHeightMultiple')
                or nested_font.get('lineHeight')
                or sketch_font.get('line')
            ),
            'letter_spacing': cls._safe_number(
                text_style.get('letterSpacing') or text_style.get('kerning')
                or nested_font.get('letterSpacing')
                or sketch_font.get('spacing') or sketch_font.get('kerning')
            ),
            'text_align': (text_style.get('textAlign') or text_style.get('alignment')
                           or paragraph_style.get('alignment')
                           or nested_font.get('align')
                           or sketch_font.get('align')),
            'color': (cls._parse_fill_color(style_fills)
                      or cls._parse_fill_color(obj.get('fills') or text_style.get('fills'))
                      or sketch_color),
        }
        has_text_signal = any([
            spec['content'],
            spec['font_family'],
            spec['font_size'] is not None,
            spec['font_weight'],
            spec['line_height'] is not None,
            spec['letter_spacing'] is not None,
            spec['text_align'],
            spec['color'],
            bool(text_style),
        ])
        if has_text_signal:
            return spec
        return None

    @classmethod
    def _first_present_value(cls, obj: dict, *keys: str) -> Any:
        """返回第一个显式存在的字段值，避免 0 被 or 逻辑吞掉。"""
        for key in keys:
            if key in obj:
                return obj.get(key)
        return None

    @classmethod
    def _extract_border_radius_spec(cls, obj: dict) -> Any:
        """提取圆角结构，兼容单值、四角详情和嵌套样式对象。"""
        direct_radius = cls._extract_direct_border_radius_spec(obj)
        if direct_radius not in (None, '', [], {}):
            return direct_radius

        for candidate in cls._iter_border_radius_candidates(obj):
            if isinstance(candidate, dict):
                nested_radius = cls._extract_direct_border_radius_spec(candidate)
            else:
                nested_radius = cls._extract_point_radius_spec(candidate)

            if nested_radius not in (None, '', [], {}):
                return nested_radius

        return None

    @classmethod
    def _extract_direct_border_radius_spec(cls, obj: dict) -> Any:
        """提取当前节点直接声明的圆角结构。"""
        direct_value = cls._first_present_value(
            obj,
            'radius',
            'cornerRadius',
            'radii',
            'cornerRadii',
            'rectRadii',
            'borderRadius',
            'fixedRadius',
        )
        if direct_value not in (None, '', [], {}):
            return direct_value

        corner_mappings = [
            ('topLeftRadius', 'top_left'),
            ('topRightRadius', 'top_right'),
            ('bottomRightRadius', 'bottom_right'),
            ('bottomLeftRadius', 'bottom_left'),
            ('topLeft', 'top_left'),
            ('topRight', 'top_right'),
            ('bottomRight', 'bottom_right'),
            ('bottomLeft', 'bottom_left'),
        ]
        corners = {}
        for source_key, target_key in corner_mappings:
            if source_key not in obj:
                continue
            value = obj.get(source_key)
            if value in (None, '', [], {}):
                continue
            corners[target_key] = value

        if corners:
            return corners

        return cls._extract_point_radius_spec(obj.get('points'))

    @classmethod
    def _extract_point_radius_spec(cls, points: Any) -> Any:
        """从点位数组中推导圆角。常见于矩形路径点数据。"""
        if not isinstance(points, list):
            return None

        radii = []
        for point in points:
            if not isinstance(point, dict):
                continue
            point_radius = cls._first_present_value(point, 'cornerRadius', 'radius', 'cornerRadiusRaw')
            if point_radius in (None, '', [], {}):
                continue
            radii.append(point_radius)

        if not radii:
            return None

        normalized = [cls._safe_number(value) if cls._safe_number(value) is not None else value for value in radii]
        if len(set(str(value) for value in normalized)) == 1:
            return radii[0]

        if len(radii) >= 4:
            return {
                'top_left': radii[0],
                'top_right': radii[1],
                'bottom_right': radii[2],
                'bottom_left': radii[3],
            }

        return {'all': radii}

    @classmethod
    def _iter_border_radius_candidates(cls, obj: dict):
        """遍历可能承载圆角信息的嵌套对象。"""
        preferred_keys = (
            'style',
            'shapeStyle',
            'sharedStyle',
            'props',
            'shape',
            'rectangle',
            'rect',
            'path',
            'shapePath',
            'metadata',
            'meta',
            'data',
            'points',
        )
        skip_keys = {
            'fills',
            'borders',
            'strokes',
            'shadows',
            'textStyle',
            'attributedString',
            'image',
            'ddsImage',
            'export',
            'content',
            'string',
        }

        seen = set()
        queue = []

        def enqueue(value: Any, depth: int):
            if depth > 4 or not isinstance(value, (dict, list)):
                return
            marker = id(value)
            if marker in seen:
                return
            seen.add(marker)
            queue.append((value, depth))

        for key in preferred_keys:
            if key in obj:
                enqueue(obj.get(key), 1)

        for key, value in obj.items():
            if key in preferred_keys or key in skip_keys:
                continue
            enqueue(value, 1)

        while queue:
            current, depth = queue.pop(0)
            yield current

            if depth >= 4:
                continue

            if isinstance(current, dict):
                for key in preferred_keys:
                    if key in current:
                        enqueue(current.get(key), depth + 1)
                for key, value in current.items():
                    if key in preferred_keys or key in skip_keys:
                        continue
                    enqueue(value, depth + 1)
            else:
                for item in current:
                    enqueue(item, depth + 1)

    @classmethod
    def _build_style_spec(cls, obj: dict) -> dict:
        """标准化通用视觉样式。"""
        border_radius_detail = cls._extract_border_radius_spec(obj)
        border_radius_scalar = cls._safe_number(border_radius_detail)
        # 蓝湖 API: fills/borders/shadows 在 obj['style'] 子对象里
        style_obj = obj.get('style') if isinstance(obj.get('style'), dict) else {}
        raw_fills = obj.get('fills') or style_obj.get('fills') or []
        raw_borders = obj.get('borders') or obj.get('strokes') or style_obj.get('borders') or style_obj.get('strokes') or []
        raw_shadows = obj.get('shadows') or style_obj.get('shadows') or []
        # 解析 border 简化信息
        parsed_borders = cls._parse_borders(raw_borders)
        # 图层级 opacity（影响整个图层及其子元素）
        layer_opacity = cls._safe_number(obj.get('opacity'))
        return {
            'fills': raw_fills,
            'borders': raw_borders,
            'borders_parsed': parsed_borders,
            'shadows': raw_shadows,
            'color': cls._parse_fill_color(raw_fills),
            'gradient': cls._parse_fill_gradient(raw_fills),
            'opacity': layer_opacity if layer_opacity is not None and layer_opacity < 1.0 else None,
            'border_radius': border_radius_scalar,
            'border_radius_raw': border_radius_scalar,
            'border_radius_detail_raw': border_radius_detail
        }

    @classmethod
    def _build_export_spec(cls, obj: dict) -> Optional[dict]:
        """标准化导出资源信息。"""
        image_data = obj.get('image') or {}
        dds_image = obj.get('ddsImage') or {}
        image_url = image_data.get('imageUrl') or dds_image.get('imageUrl')
        svg_url = image_data.get('svgUrl')
        export_spec = {
            'image_url': image_url,
            'svg_url': svg_url,
            'format': 'png' if image_url else ('svg' if svg_url else None)
        }
        if any(export_spec.values()):
            return export_spec
        return None

    @classmethod
    def _build_visibility(cls, obj: dict) -> bool:
        """推断图层是否可见。"""
        if 'visible' in obj:
            return bool(obj.get('visible'))
        if 'isVisible' in obj:
            return bool(obj.get('isVisible'))
        if 'hidden' in obj:
            return not bool(obj.get('hidden'))
        return True

    @classmethod
    def _build_locked(cls, obj: dict) -> bool:
        """推断图层是否锁定。"""
        if 'locked' in obj:
            return bool(obj.get('locked'))
        if 'isLocked' in obj:
            return bool(obj.get('isLocked'))
        return False

    @classmethod
    def _guess_layer_kind(cls, obj: dict, export_spec: Optional[dict], text_spec: Optional[dict], has_children: bool) -> str:
        """归一化图层类别。"""
        source_type = (obj.get('type') or obj.get('layerType') or obj.get('ddsType') or '').lower()
        layer_name = (obj.get('name') or '').lower()

        if 'text' in source_type or text_spec:
            return 'text'
        if has_children or 'group' in source_type or 'artboard' in source_type:
            return 'group'
        if 'icon' in source_type or 'icon' in layer_name:
            return 'icon'
        if 'bitmap' in source_type or 'image' in source_type or obj.get('ddsImage'):
            return 'image'
        if export_spec and ('shape' in source_type or 'vector' in source_type or 'path' in source_type):
            return 'icon'
        if 'shape' in source_type or 'vector' in source_type or 'path' in source_type:
            return 'shape'
        if export_spec:
            return 'image'
        return 'unknown'

    @classmethod
    def _build_layer_dedupe_key(cls, layer: dict) -> str:
        """为图层构建稳定的去重键。"""
        if layer.get('id'):
            return str(layer['id'])

        position = layer.get('position') or {}
        size = layer.get('size') or {}
        return "|".join([
            layer.get('layer_path') or '',
            layer.get('source_type') or '',
            str(position.get('x')),
            str(position.get('y')),
            str(size.get('width')),
            str(size.get('height')),
        ])

    @classmethod
    def _build_layer_entry(cls, obj: dict, parent_name: Optional[str], layer_path: str) -> Optional[dict]:
        """将蓝湖图层对象标准化为统一结构。"""
        if not isinstance(obj, dict):
            return None

        source_type = obj.get('type') or obj.get('layerType') or obj.get('ddsType')
        name = obj.get('name') or ''
        has_children = bool(obj.get('layers') or obj.get('children'))
        export_spec = cls._build_export_spec(obj)
        text_spec = cls._build_text_spec(obj)
        position = cls._extract_position(obj)
        size = cls._extract_size(obj)

        is_layer = any([
            obj.get('id'),
            name,
            source_type,
            has_children,
            export_spec,
            text_spec,
            position,
            size
        ])
        if not is_layer:
            return None

        return {
            'id': obj.get('id'),
            'name': name,
            'kind': cls._guess_layer_kind(obj, export_spec, text_spec, has_children),
            'source_type': source_type or 'unknown',
            'layer_path': layer_path,
            'parent_name': parent_name,
            'visible': cls._build_visibility(obj),
            'locked': cls._build_locked(obj),
            'position': position,
            'size': size,
            'opacity': cls._safe_number(obj.get('opacity')),
            'rotation': cls._safe_number(obj.get('rotation')),
            'style': cls._build_style_spec(obj),
            'text': text_spec,
            'export': export_spec
        }

    def _walk_design_layers(
        self,
        obj: Any,
        layers: List[dict],
        seen_keys: set,
        parent_name: Optional[str] = None,
        parent_path: str = ""
    ):
        """递归提取图层并做去重。"""
        if not isinstance(obj, dict):
            return

        current_name = obj.get('name') or ''
        current_path = f"{parent_path}/{current_name}" if parent_path and current_name else (current_name or parent_path)
        layer_entry = self._build_layer_entry(obj, parent_name, current_path)

        next_parent_name = parent_name
        next_parent_path = parent_path
        if layer_entry:
            dedupe_key = self._build_layer_dedupe_key(layer_entry)
            if dedupe_key not in seen_keys:
                seen_keys.add(dedupe_key)
                layers.append(layer_entry)
            next_parent_name = current_name or parent_name
            next_parent_path = current_path or parent_path

        for key in ['layers', 'children']:
            value = obj.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._walk_design_layers(item, layers, seen_keys, next_parent_name, next_parent_path)

        # 兼容旧结构下的嵌套对象，但跳过明显的样式字段，避免误把 metadata 当图层。
        skip_keys = {
            'image', 'ddsImage', 'textStyle', 'fills', 'borders', 'strokes', 'shadows',
            'frame', 'bounds', 'text', 'attributedString', 'content', 'string'
        }
        for key, value in obj.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict) and value is not obj:
                self._walk_design_layers(value, layers, seen_keys, next_parent_name, next_parent_path)
            elif isinstance(value, list) and key not in {'layers', 'children'}:
                for item in value:
                    if isinstance(item, dict):
                        self._walk_design_layers(item, layers, seen_keys, next_parent_name, next_parent_path)

    def _extract_standardized_layers(self, sketch_data: dict) -> List[dict]:
        """从设计 JSON 中提取标准化图层列表。"""
        layers: List[dict] = []
        seen_keys = set()

        artboard = sketch_data.get('artboard')
        if isinstance(artboard, dict):
            self._walk_design_layers(artboard, layers, seen_keys)

        info_list = sketch_data.get('info')
        if isinstance(info_list, list):
            for item in info_list:
                if isinstance(item, dict):
                    self._walk_design_layers(item, layers, seen_keys)

        if not layers:
            self._walk_design_layers(sketch_data, layers, seen_keys)

        return layers

    @staticmethod
    def _build_design_summary(layers: List[dict]) -> dict:
        """生成设计规格摘要。"""
        from collections import Counter

        kind_counter = Counter(layer.get('kind', 'unknown') for layer in layers)
        exportable_layers = sum(1 for layer in layers if layer.get('export'))

        return {
            'total_layers': len(layers),
            'exportable_layers': exportable_layers,
            'text_layers': kind_counter.get('text', 0),
            'layer_kind_counts': dict(kind_counter)
        }

    @classmethod
    def _detect_layout_direction(cls, siblings: List[dict]) -> str:
        """分析同级元素的排列方式：horizontal / vertical / stack / free。"""
        if len(siblings) <= 1:
            return 'single'

        rects = []
        for s in siblings:
            r = cls._layer_rect(s)
            if r:
                rects.append(r)
        if len(rects) <= 1:
            return 'single'

        ys = [r['top'] for r in rects]
        xs = [r['left'] for r in rects]
        heights = [r['height'] for r in rects]
        widths = [r['width'] for r in rects]

        y_range = max(ys) - min(ys)
        x_range = max(xs) - min(xs)
        avg_h = sum(heights) / len(heights) if heights else 1
        avg_w = sum(widths) / len(widths) if widths else 1

        # 检查重叠：如果大部分元素互相重叠，则是 stack
        overlap_count = 0
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                ri, rj = rects[i], rects[j]
                h_overlap = min(ri['right'], rj['right']) - max(ri['left'], rj['left'])
                v_overlap = min(ri['bottom'], rj['bottom']) - max(ri['top'], rj['top'])
                if h_overlap > 0 and v_overlap > 0:
                    overlap_count += 1
        total_pairs = len(rects) * (len(rects) - 1) / 2
        if total_pairs > 0 and overlap_count / total_pairs > 0.5:
            return 'stack'

        if avg_h > 0 and y_range < avg_h * 0.4:
            return 'horizontal'
        if avg_w > 0 and x_range < avg_w * 0.4:
            return 'vertical'
        return 'free'

    def _build_sibling_spacings(self, layers: List[dict]) -> List[dict]:
        """按容器分组同级图层，计算兄弟间距和布局方向。

        优先用 parent_name 分组；当大部分图层 parent_name 为 None 时，
        回退到几何包含关系分组。
        """
        from collections import defaultdict

        meaningful_layers = [
            layer for layer in layers
            if self._is_meaningful_named_layer(layer) and self._layer_rect(layer)
        ]

        # 检查 parent_name 是否有效
        with_parent = sum(1 for l in meaningful_layers if l.get('parent_name'))
        use_geometry = with_parent < len(meaningful_layers) * 0.3

        if use_geometry:
            groups = self._group_siblings_by_geometry(meaningful_layers)
        else:
            raw_groups = defaultdict(list)
            for layer in meaningful_layers:
                parent = layer.get('parent_name') or '__root__'
                raw_groups[parent].append(layer)
            groups = [(k if k != '__root__' else None, None, v) for k, v in raw_groups.items()]

        results = []
        for parent_name, parent_path, siblings in groups:
            if len(siblings) < 2:
                continue

            direction = self._detect_layout_direction(siblings)

            if direction == 'horizontal':
                siblings_sorted = sorted(siblings, key=lambda s: (s.get('position') or {}).get('x', 0))
                children = []
                for i, s in enumerate(siblings_sorted):
                    gap = None
                    if i < len(siblings_sorted) - 1:
                        cur_rect = self._layer_rect(s)
                        next_rect = self._layer_rect(siblings_sorted[i + 1])
                        if cur_rect and next_rect:
                            gap = self._safe_number(next_rect['left'] - cur_rect['right'])
                    children.append({'name': s.get('name'), 'kind': s.get('kind'), 'gap_to_next': gap})
            elif direction in ('vertical', 'free'):
                siblings_sorted = sorted(siblings, key=lambda s: (s.get('position') or {}).get('y', 0))
                children = []
                for i, s in enumerate(siblings_sorted):
                    gap = None
                    if i < len(siblings_sorted) - 1:
                        cur_rect = self._layer_rect(s)
                        next_rect = self._layer_rect(siblings_sorted[i + 1])
                        if cur_rect and next_rect:
                            gap = self._safe_number(next_rect['top'] - cur_rect['bottom'])
                    children.append({'name': s.get('name'), 'kind': s.get('kind'), 'gap_to_next': gap})
            else:
                children = [{'name': s.get('name'), 'kind': s.get('kind'), 'gap_to_next': None} for s in siblings]

            results.append({
                'parent_name': parent_name,
                'parent_path': parent_path,
                'layout_direction': direction,
                'child_count': len(children),
                'children': children
            })

        return results

    def _group_siblings_by_geometry(self, layers: List[dict]) -> List[tuple]:
        """用几何包含关系将图层分组为容器→子元素。

        返回 [(parent_name, parent_path, [children_layers]), ...]
        """
        container_kinds = {'group', 'unknown'}
        rects = []
        for layer in layers:
            r = self._layer_rect(layer)
            if r:
                rects.append((layer, r, r['width'] * r['height']))

        # 找出容器图层（group 类型或面积较大）
        avg_area = sum(a for _, _, a in rects) / len(rects) if rects else 0
        containers = [
            (l, r, a) for l, r, a in rects
            if l.get('kind') in container_kinds and a > avg_area * 0.5
        ]
        containers.sort(key=lambda x: x[2])  # 小容器优先

        assigned = {}  # layer_id → container_name
        groups = {}    # container_name → [layers]

        for layer, rect, area in rects:
            lid = id(layer)
            # 找最小包含容器
            for c_layer, c_rect, c_area in containers:
                if id(c_layer) == lid:
                    continue
                if c_area <= area:
                    continue
                if self._contains_rect(c_rect, rect):
                    c_name = c_layer.get('name', '')
                    assigned[lid] = c_name
                    if c_name not in groups:
                        groups[c_name] = []
                    groups[c_name].append(layer)
                    break

        result = []
        for c_name, children in groups.items():
            if len(children) >= 2:
                result.append((c_name, None, children))

        return result

    @classmethod
    def _build_layout_tree(cls, layers: List[dict]) -> dict:
        """将扁平图层列表重建为嵌套层级树。

        优先使用 layer_path 层级关系；当 layer_path 无层级（Sketch 扁平格式）时，
        回退到几何包含关系推断父子。
        """
        meaningful = [l for l in layers if l.get('name') and cls._layer_rect(l)]
        if not meaningful:
            return {'name': '__root__', 'children': []}

        # 检查 layer_path 是否有真正的层级（含 / 且不是日期格式）
        has_hierarchy = any(
            '/' in (l.get('layer_path') or '') and
            not (l.get('layer_path') or '').replace('/', '').replace(' ', '').isdigit()
            for l in meaningful
        )

        if has_hierarchy:
            return cls._build_tree_from_paths(meaningful)
        else:
            return cls._build_tree_from_geometry(meaningful)

    @classmethod
    def _build_tree_from_paths(cls, layers: List[dict]) -> dict:
        """从 layer_path 构建层级树。"""
        path_map = {}
        for layer in layers:
            path = layer.get('layer_path', '')
            name = layer.get('name', '')
            if not name:
                continue
            node = {
                'name': name,
                'kind': layer.get('kind'),
                'position': layer.get('position'),
                'size': layer.get('size'),
                'children': []
            }
            path_map[path] = node

        root_children = []
        for path, node in path_map.items():
            if '/' in path:
                parent_path = path.rsplit('/', 1)[0]
                parent_node = path_map.get(parent_path)
                if parent_node:
                    parent_node['children'].append(node)
                    continue
            root_children.append(node)

        def _clean(n):
            if not n.get('children'):
                n.pop('children', None)
            else:
                for c in n['children']:
                    _clean(c)

        for n in root_children:
            _clean(n)

        return {'name': '__root__', 'children': root_children}

    @classmethod
    def _build_tree_from_geometry(cls, layers: List[dict]) -> dict:
        """从几何包含关系推断层级树（Sketch 扁平格式回退）。

        只对 group/unknown 类型的容器图层建立父子关系，
        避免把所有小元素都挂到大背景上。
        """
        # 按面积从大到小排序
        rects = []
        for layer in layers:
            r = cls._layer_rect(layer)
            if r:
                rects.append((layer, r, r['width'] * r['height']))

        rects.sort(key=lambda x: -x[2])

        # 为每个图层找最小包含容器（仅 group 类型可作为容器）
        container_kinds = {'group', 'unknown'}
        nodes = {}
        for layer, rect, area in rects:
            name = layer.get('name', '')
            nodes[id(layer)] = {
                'name': name,
                'kind': layer.get('kind'),
                'position': layer.get('position'),
                'size': layer.get('size'),
                'children': [],
                '_layer_id': id(layer),
                '_rect': rect,
                '_area': area,
            }

        # 按面积从小到大，为每个图层找最小容器
        assigned = set()
        rects_small_first = sorted(rects, key=lambda x: x[2])
        for layer, rect, area in rects_small_first:
            lid = id(layer)
            best_parent = None
            best_area = None
            for p_layer, p_rect, p_area in rects:
                pid = id(p_layer)
                if pid == lid:
                    continue
                if p_area <= area:
                    continue
                # 容器必须是 group 类型或面积显著大于子元素
                if p_layer.get('kind') not in container_kinds and p_area < area * 3:
                    continue
                if cls._contains_rect(p_rect, rect):
                    if best_area is None or p_area < best_area:
                        best_parent = pid
                        best_area = p_area

            if best_parent and best_parent in nodes:
                nodes[best_parent]['children'].append(nodes[lid])
                assigned.add(lid)

        root_children = [n for lid, n in nodes.items() if lid not in assigned]

        # 清理内部字段
        def _clean(n):
            n.pop('_layer_id', None)
            n.pop('_rect', None)
            n.pop('_area', None)
            if not n.get('children'):
                n.pop('children', None)
            else:
                for c in n['children']:
                    _clean(c)

        for n in root_children:
            _clean(n)

        return {'name': '__root__', 'children': root_children}

    def _build_text_container_paddings(self, layers: List[dict]) -> List[dict]:
        """为文本图层推导其最近容器的内边距。"""
        meaningful_layers = [
            layer for layer in layers
            if self._is_meaningful_named_layer(layer) and self._layer_rect(layer)
        ]
        text_layers = [layer for layer in meaningful_layers if layer.get('kind') == 'text']
        container_candidates = [layer for layer in meaningful_layers if layer.get('kind') != 'text']

        paddings = []
        for text_layer in text_layers:
            text_rect = self._layer_rect(text_layer)
            text_area = text_rect['width'] * text_rect['height']
            best_container = None
            best_rect = None
            best_area = None

            for candidate in container_candidates:
                if candidate.get('id') == text_layer.get('id') and candidate.get('id'):
                    continue
                candidate_rect = self._layer_rect(candidate)
                if not self._contains_rect(candidate_rect, text_rect):
                    continue

                candidate_area = candidate_rect['width'] * candidate_rect['height']
                if candidate_area <= text_area:
                    continue

                if best_area is None or candidate_area < best_area:
                    best_container = candidate
                    best_rect = candidate_rect
                    best_area = candidate_area

            if not best_container:
                continue

            paddings.append({
                'text_layer_id': text_layer.get('id'),
                'text_layer_name': text_layer.get('name'),
                'text_layer_path': text_layer.get('layer_path'),
                'container_id': best_container.get('id'),
                'container_name': best_container.get('name'),
                'container_kind': best_container.get('kind'),
                'container_path': best_container.get('layer_path'),
                'padding': {
                    'left': self._safe_number(text_rect['left'] - best_rect['left']),
                    'right': self._safe_number(best_rect['right'] - text_rect['right']),
                    'top': self._safe_number(text_rect['top'] - best_rect['top']),
                    'bottom': self._safe_number(best_rect['bottom'] - text_rect['bottom']),
                }
            })

        return paddings

    def _build_nearest_neighbor_measurements(self, layers: List[dict]) -> List[dict]:
        """为命名图层推导最近邻图层间距（排除父子关系）。"""
        meaningful_layers = [
            layer for layer in layers
            if self._is_meaningful_named_layer(layer) and self._layer_rect(layer)
        ]

        # 预计算包含关系集合，用于排除父子配对
        containment_pairs = set()  # (child_id, parent_id) 表示 child 在 parent 内
        for i, layer_a in enumerate(meaningful_layers):
            rect_a = self._layer_rect(layer_a)
            area_a = rect_a['width'] * rect_a['height']
            for j, layer_b in enumerate(meaningful_layers):
                if i == j:
                    continue
                rect_b = self._layer_rect(layer_b)
                area_b = rect_b['width'] * rect_b['height']
                # 只标记面积差异显著的包含关系（面积比 > 2x）
                if self._contains_rect(rect_b, rect_a) and area_b > area_a * 2:
                    containment_pairs.add((i, j))

        nearest_neighbors = []
        for si, source_layer in enumerate(meaningful_layers):
            source_rect = self._layer_rect(source_layer)
            best_target = None
            best_metrics = None
            best_distance = None
            best_ti = None

            for ti, target_layer in enumerate(meaningful_layers):
                if target_layer is source_layer:
                    continue
                if source_layer.get('id') and source_layer.get('id') == target_layer.get('id'):
                    continue

                # 跳过父子关系（layer_path 前缀 或 几何包含）
                source_path = source_layer.get('layer_path', '')
                target_path = target_layer.get('layer_path', '')
                if source_path and target_path:
                    if source_path.startswith(target_path + '/') or target_path.startswith(source_path + '/'):
                        continue
                if (si, ti) in containment_pairs or (ti, si) in containment_pairs:
                    continue

                metrics = self._measure_rect_relationship(source_rect, self._layer_rect(target_layer))
                distance = metrics['edge_distance']
                if distance is None:
                    continue

                if best_distance is None or distance < best_distance:
                    best_target = target_layer
                    best_metrics = metrics
                    best_distance = distance
                    best_ti = ti

            if not best_target or not best_metrics:
                continue

            nearest_neighbors.append({
                'layer_id': source_layer.get('id'),
                'layer_name': source_layer.get('name'),
                'layer_kind': source_layer.get('kind'),
                'target_id': best_target.get('id'),
                'target_name': best_target.get('name'),
                'target_kind': best_target.get('kind'),
                **best_metrics
            })

        return nearest_neighbors

    def _build_icon_text_measurements(self, layers: List[dict]) -> List[dict]:
        """为小型图标/视觉元素推导最近文本图层间距。"""
        meaningful_layers = [
            layer for layer in layers
            if self._is_meaningful_named_layer(layer) and self._layer_rect(layer)
        ]
        text_layers = [layer for layer in meaningful_layers if layer.get('kind') == 'text']
        icon_layers = [layer for layer in meaningful_layers if self._is_icon_measurement_candidate(layer)]

        icon_text_distances = []
        for icon_layer in icon_layers:
            icon_rect = self._layer_rect(icon_layer)
            best_text_layer = None
            best_metrics = None
            best_distance = None

            for text_layer in text_layers:
                if icon_layer.get('id') and icon_layer.get('id') == text_layer.get('id'):
                    continue

                metrics = self._measure_rect_relationship(icon_rect, self._layer_rect(text_layer))
                distance = metrics['edge_distance']
                if distance is None:
                    continue

                if best_distance is None or distance < best_distance:
                    best_text_layer = text_layer
                    best_metrics = metrics
                    best_distance = distance

            if not best_text_layer or not best_metrics:
                continue

            icon_text_distances.append({
                'icon_layer_id': icon_layer.get('id'),
                'icon_layer_name': icon_layer.get('name'),
                'icon_layer_kind': icon_layer.get('kind'),
                'text_layer_id': best_text_layer.get('id'),
                'text_layer_name': best_text_layer.get('name'),
                'text_layer_kind': best_text_layer.get('kind'),
                **best_metrics
            })

        return icon_text_distances

    def _build_measurements(self, layers: List[dict]) -> dict:
        """构建图层间距和容器 padding 等自动测量结果。"""
        return {
            'text_container_paddings': self._build_text_container_paddings(layers),
            'nearest_neighbors': self._build_nearest_neighbor_measurements(layers),
            'icon_text_distances': self._build_icon_text_measurements(layers),
            'sibling_spacings': self._build_sibling_spacings(layers),
        }

    @classmethod
    def _convert_measurements_to_dp(cls, measurements: Optional[dict], scale: float = None) -> Optional[dict]:
        if not isinstance(measurements, dict):
            return measurements

        converted = copy.deepcopy(measurements)
        for key in ['text_container_paddings', 'nearest_neighbors', 'icon_text_distances']:
            for item in converted.get(key) or []:
                if 'padding' in item and isinstance(item['padding'], dict):
                    for side in ['left', 'right', 'top', 'bottom']:
                        item['padding'][side] = cls._to_dp(item['padding'].get(side), scale)
                for metric_key in ['horizontal_gap', 'vertical_gap', 'edge_distance']:
                    if metric_key in item:
                        item[metric_key] = cls._to_dp(item.get(metric_key), scale)

        # sibling_spacings 的 gap_to_next 也需要转 dp
        for group in converted.get('sibling_spacings') or []:
            for child in group.get('children') or []:
                if child.get('gap_to_next') is not None:
                    child['gap_to_next'] = cls._to_dp(child['gap_to_next'], scale)

        converted['unit'] = 'dp'
        converted['scale_factor'] = round(scale, 4) if scale else round(ANNOTATION_DP_SCALE, 3)
        converted['rule'] = f'round(px * {converted["scale_factor"]})'
        return converted

    @classmethod
    def _convert_annotations_to_dp(cls, annotations: dict) -> dict:
        converted = copy.deepcopy(annotations)

        # 从设计稿原始宽度推断缩放系数
        raw_canvas = converted.get('canvas_size') or {}
        design_width = raw_canvas.get('width')
        scale = cls._infer_dp_scale(design_width)

        converted['unit'] = 'dp'
        converted['conversion'] = {
            'source_unit': 'px',
            'target_unit': 'dp',
            'design_width_px': design_width,
            'scale_factor': round(scale, 4),
            'rule': f'round(px * {round(scale, 4)})'
        }
        converted['canvas_size'] = cls._convert_size_to_dp(converted.get('canvas_size'), scale)

        for layer in converted.get('layers') or []:
            layer['position'] = cls._convert_position_to_dp(layer.get('position'), scale)
            layer['size'] = cls._convert_size_to_dp(layer.get('size'), scale)
            layer['style'] = cls._convert_style_spec_to_dp(layer.get('style'), scale)
            layer['text'] = cls._convert_text_spec_to_dp(layer.get('text'), scale)

        converted['measurements'] = cls._convert_measurements_to_dp(converted.get('measurements'), scale)
        return converted

    async def _get_raw_design_annotations_info(self, image_id: str, team_id: str, project_id: str) -> dict:
        """获取原始 px 坐标系下的完整图层规格。"""
        payload = await self._fetch_design_payload(image_id, team_id, project_id)
        design = payload['design']
        latest_version = payload['latest_version']
        sketch_data = payload['sketch_data']
        layers = self._extract_standardized_layers(sketch_data)

        # artboard frame 是设计稿的真实 px 尺寸
        # Figma: sketch_data.artboard.frame.width
        # Sketch: sketch_data.info[0].width (artboard-group entry)
        artboard_frame = sketch_data.get('artboard', {}).get('frame', {})
        artboard_width = artboard_frame.get('width')
        artboard_height = artboard_frame.get('height')

        if not artboard_width:
            # Sketch 格式: info 列表第一项是 artboard-group
            info_list = sketch_data.get('info')
            if isinstance(info_list, list) and info_list:
                first = info_list[0] if isinstance(info_list[0], dict) else {}
                artboard_width = first.get('width') or artboard_width
                artboard_height = first.get('height') or artboard_height

        artboard_width = artboard_width or design.get('width')
        artboard_height = artboard_height or design.get('height')

        return {
            'status': 'success',
            'design_id': str(image_id),
            'design_name': design.get('name'),
            'version': latest_version.get('version_info'),
            'canvas_size': {
                'width': artboard_width,
                'height': artboard_height
            },
            'summary': self._build_design_summary(layers),
            'layout_tree': self._build_layout_tree(layers),
            'layers': layers,
            'measurements': self._build_measurements(layers)
        }

    async def get_design_annotations_info(self, image_id: str, team_id: str, project_id: str) -> dict:
        """获取设计图的完整图层规格，并将几何尺寸转换为 dp。"""
        raw_annotations = await self._get_raw_design_annotations_info(image_id, team_id, project_id)
        return self._convert_annotations_to_dp(raw_annotations)

    async def get_design_slices_info(self, image_id: str, team_id: str, project_id: str,
                                     include_metadata: bool = True) -> dict:
        """
        获取设计图的所有切图信息（仅返回元数据和下载地址，不下载文件）

        Args:
            image_id: 设计图ID
            team_id: 团队ID
            project_id: 项目ID
            include_metadata: 是否包含详细元数据（位置、颜色、样式等）

        Returns:
            包含切图列表和详细信息的字典
        """
        annotations = await self._get_raw_design_annotations_info(image_id, team_id, project_id)
        slices = []

        for layer in annotations['layers']:
            export_spec = layer.get('export')
            if not export_spec or not (export_spec.get('image_url') or export_spec.get('svg_url')):
                continue

            size = layer.get('size') or {}
            width = size.get('width')
            height = size.get('height')
            size_str = f"{width}x{height}" if width is not None and height is not None else "unknown"

            slice_info = {
                'id': layer.get('id'),
                'name': layer.get('name'),
                'type': layer.get('source_type'),
                'download_url': export_spec.get('image_url') or export_spec.get('svg_url'),
                'size': size_str,
                'format': export_spec.get('format'),
                'position': layer.get('position'),
                'parent_name': layer.get('parent_name'),
                'layer_path': layer.get('layer_path')
            }

            if include_metadata:
                metadata = {
                    'fills': layer.get('style', {}).get('fills'),
                    'borders': layer.get('style', {}).get('borders'),
                    'opacity': layer.get('opacity'),
                    'rotation': layer.get('rotation'),
                    'text_style': layer.get('text'),
                    'shadows': layer.get('style', {}).get('shadows'),
                    'border_radius': layer.get('style', {}).get('border_radius'),
                    'border_radius_raw': layer.get('style', {}).get('border_radius_raw'),
                    'border_radius_detail_raw': layer.get('style', {}).get('border_radius_detail_raw')
                }
                metadata = {key: value for key, value in metadata.items() if value not in (None, [], {}, '')}
                if metadata:
                    slice_info['metadata'] = metadata

            slices.append(slice_info)

        return {
            'design_id': annotations['design_id'],
            'design_name': annotations['design_name'],
            'version': annotations['version'],
            'canvas_size': annotations['canvas_size'],
            'total_slices': len(slices),
            'slices': slices
        }

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


def fix_html_files(directory: str):
    """修复HTML文件"""
    html_files = list(Path(directory).glob("*.html"))

    for html_path in html_files:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        soup = BeautifulSoup(content, 'html.parser')

        # 替换data-src
        for tag in soup.find_all(['img', 'script']):
            if tag.has_attr('data-src'):
                tag['src'] = tag['data-src']
                del tag['data-src']

        for tag in soup.find_all('link'):
            if tag.has_attr('data-src'):
                tag['href'] = tag['data-src']
                del tag['data-src']

        # 移除body隐藏样式
        body = soup.find('body')
        if body and body.has_attr('style'):
            style = body['style']
            style = re.sub(r'display\s*:\s*none\s*;?', '', style)
            style = re.sub(r'opacity\s*:\s*0\s*;?', '', style)
            style = style.strip()
            if style:
                body['style'] = style
            else:
                del body['style']

        # 移除蓝湖脚本
        for script in soup.find_all('script'):
            if script.string and 'alistatic.lanhuapp.com' in script.string:
                script.decompose()

        # 添加映射函数
        head = soup.find('head')
        if head:
            mapping_script = soup.new_tag('script')
            mapping_script.string = '''
// 蓝湖Axure映射数据处理函数
function lanhu_Axure_Mapping_Data(data) {
    return data;
}
'''
            first_script = head.find('script')
            if first_script:
                first_script.insert_before(mapping_script)
            else:
                head.append(mapping_script)

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))


async def screenshot_page_internal(resource_dir: str, page_names: List[str], output_dir: str,
                                   return_base64: bool = True, version_id: str = None) -> List[dict]:
    """内部截图函数（同时提取页面文本），支持智能缓存"""
    import http.server
    import socketserver
    import threading
    import time

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 缓存元数据文件
    cache_meta_path = output_path / ".screenshot_cache.json"
    cache_meta = {}
    if cache_meta_path.exists():
        try:
            with open(cache_meta_path, 'r', encoding='utf-8') as f:
                cache_meta = json.load(f)
        except Exception:
            cache_meta = {}
    
    # 检查哪些页面需要重新截图
    cached_version = cache_meta.get('version_id')
    pages_to_render = []
    cached_results = []
    
    for page_name in page_names:
        safe_name = re.sub(r'[^\w\s-]', '_', page_name)
        screenshot_file = output_path / f"{safe_name}.png"
        text_file = output_path / f"{safe_name}.txt"
        
        # 如果版本相同且文件存在，复用缓存
        if (version_id and cached_version == version_id and 
            screenshot_file.exists()):
            # 读取缓存的文本内容
            page_text = ""
            if text_file.exists():
                try:
                    page_text = text_file.read_text(encoding='utf-8')
                except Exception:
                    page_text = "(Cached - text not available)"
            
            cached_results.append({
                'page_name': page_name,
                'success': True,
                'screenshot_path': str(screenshot_file),
                'page_text': page_text if page_text else "(Cached result)",
                'size': f"{screenshot_file.stat().st_size / 1024:.1f}KB",
                'from_cache': True
            })
        else:
            pages_to_render.append(page_name)
    
    results = list(cached_results)
    
    # 如果所有页面都有缓存，直接返回
    if not pages_to_render:
        return results
    
    # 启动HTTP服务器（只有需要渲染时才启动）
    import random
    port = random.randint(8800, 8900)
    abs_dir = os.path.abspath(resource_dir)
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(
        *args, directory=abs_dir, **kwargs
    )
    httpd = socketserver.TCPServer(("", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # viewport 只影响初始窗口大小，不影响 full_page=True 的截图范围
        page = await browser.new_page(viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT})

        for page_name in pages_to_render:
            try:
                # 查找HTML文件
                html_file = None
                for f in Path(resource_dir).glob("*.html"):
                    if f.stem == page_name:
                        html_file = f.name
                        break

                if not html_file:
                    results.append({
                        'page_name': page_name,
                        'success': False,
                        'error': f'Page {page_name} does not exist'
                    })
                    continue

                # 访问页面
                url = f"http://localhost:{port}/{html_file}"
                await page.goto(url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(2000)

                # Extract page text content (optimized for Axure)
                page_text = await page.evaluate('''() => {
                    let sections = [];

                    // 1. Extract red annotation/warning text (product key notes)
                    const redTexts = Array.from(document.querySelectorAll('*')).filter(el => {
                        const style = window.getComputedStyle(el);
                        const color = style.color;
                        // Detect red text (rgb(255,0,0) or #ff0000, etc.)
                        return color && (
                            color.includes('rgb(255, 0, 0)') || 
                            color.includes('rgb(255,0,0)') ||
                            color === 'red'
                        );
                    });

                    if (redTexts.length > 0) {
                        const redContent = redTexts
                            .map(el => el.textContent.trim())
                            .filter(t => t.length > 0 && t.length < 200)
                            .filter((v, i, a) => a.indexOf(v) === i); // dedupe
                        if (redContent.length > 0) {
                            sections.push("[Important Tips/Warnings]\\n" + redContent.join("\\n"));
                        }
                    }

                    // 2. Extract Axure shape/flowchart node text
                    const axureShapes = document.querySelectorAll('[id^="u"], .ax_shape, .shape, [class*="shape"]');
                    const shapeTexts = [];
                    axureShapes.forEach(el => {
                        const text = el.textContent.trim();
                        // Only text with appropriate length (avoid overly long paragraphs)
                        if (text && text.length > 0 && text.length < 100) {
                            shapeTexts.push(text);
                        }
                    });

                    if (shapeTexts.length > 5) { // If many shape texts extracted, likely a flowchart
                        const uniqueShapes = [...new Set(shapeTexts)];
                        sections.push("[Flowchart/Component Text]\\n" + uniqueShapes.slice(0, 20).join(" | ")); // max 20
                    }

                    // 3. Extract all visible text (most complete content)
                    const bodyText = document.body.innerText || '';
                    if (bodyText.trim()) {
                        sections.push("[Full Page Text]\\n" + bodyText.trim());
                    }

                    // 4. If nothing extracted
                    if (sections.length === 0) {
                        return "⚠️ Page text is empty or cannot be extracted (please refer to visual output)";
                    }

                    return sections.join("\\n\\n");
                }''')

                # 截图
                safe_name = re.sub(r'[^\w\s-]', '_', page_name)
                screenshot_path = output_path / f"{safe_name}.png"
                text_path = output_path / f"{safe_name}.txt"

                # 获取截图字节
                screenshot_bytes = await page.screenshot(full_page=True)

                # 保存截图到文件
                screenshot_path.write_bytes(screenshot_bytes)
                
                # 保存文本到文件（用于缓存）
                try:
                    text_path.write_text(page_text, encoding='utf-8')
                except Exception:
                    pass

                result = {
                    'page_name': page_name,
                    'success': True,
                    'screenshot_path': str(screenshot_path),
                    'page_text': page_text,
                    'size': f"{len(screenshot_bytes) / 1024:.1f}KB",
                    'from_cache': False
                }

                # 如果需要返回base64
                if return_base64:
                    result['base64'] = base64.b64encode(screenshot_bytes).decode('utf-8')
                    result['mime_type'] = 'image/png'

                results.append(result)
            except Exception as e:
                results.append({
                    'page_name': page_name,
                    'success': False,
                    'error': str(e)
                })

        await browser.close()

    # 停止服务器
    httpd.shutdown()
    httpd.server_close()
    
    # 更新缓存元数据
    if version_id:
        cache_meta['version_id'] = version_id
        cache_meta['cached_pages'] = page_names
        try:
            with open(cache_meta_path, 'w', encoding='utf-8') as f:
                json.dump(cache_meta, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    return results


@mcp.tool()
async def lanhu_resolve_invite_link(
    invite_url: Annotated[str, "Lanhu invite link. Example: https://lanhuapp.com/link/#/invite?sid=xxx"]
) -> dict:
    """
    Resolve Lanhu invite/share link to actual project URL
    
    USE THIS WHEN: User provides invite link (lanhuapp.com/link/#/invite?sid=xxx)
    
    Purpose: Convert invite link to usable project URL with tid/pid/docId parameters
    
    Returns:
        Resolved URL and parsed parameters
    """
    try:
        # 解析Cookie字符串为playwright格式
        cookies = []
        for cookie_str in COOKIE.split('; '):
            if '=' in cookie_str:
                name, value = cookie_str.split('=', 1)
                cookies.append({
                    'name': name,
                    'value': value,
                    'domain': '.lanhuapp.com',
                    'path': '/'
                })
        
        # 使用playwright来处理前端重定向
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            # 添加cookies
            if cookies:
                await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # 访问邀请链接，等待重定向完成
            await page.goto(invite_url, wait_until='networkidle', timeout=30000)
            
            # 等待一下确保重定向完成
            await page.wait_for_timeout(2000)
            
            # 获取最终URL
            final_url = page.url
            
            await browser.close()
            
            # 解析最终URL
            extractor = LanhuExtractor()
            try:
                params = extractor.parse_url(final_url)
                
                return {
                    "status": "success",
                    "invite_url": invite_url,
                    "resolved_url": final_url,
                    "parsed_params": params,
                    "usage_tip": "You can now use this resolved_url with other lanhu tools (lanhu_get_pages, lanhu_get_designs, etc.)"
                }
            except Exception as e:
                return {
                    "status": "partial_success",
                    "invite_url": invite_url,
                    "resolved_url": final_url,
                    "parse_error": str(e),
                    "message": "URL resolved but parsing failed. You can try using the resolved_url directly."
                }
            finally:
                await extractor.close()
                
    except Exception as e:
        return {
            "status": "error",
            "invite_url": invite_url,
            "error": str(e),
            "message": "Failed to resolve invite link. Please check if the link is valid."
        }


def _get_analysis_mode_options_by_role(user_role: str) -> str:
    """
    根据用户角色生成分析模式选项（调整推荐顺序）
    
    Args:
        user_role: 用户角色
    
    Returns:
        格式化的选项文本
    """
    # 归一化角色
    normalized_role = normalize_role(user_role)
    
    # 定义三种模式的完整描述
    developer_option = """1️⃣ 【开发视角】- 详细技术文档
   适合：开发人员看需求，准备写代码
   输出内容：
   - 详细字段规则表（必填、类型、长度、校验规则、提示文案）
   - 业务规则清单（判断条件、异常处理、数据流向）
   - 全局流程图（包含所有分支、判断、异常处理）
   - 接口依赖说明、数据库设计建议"""
    
    tester_option = """2️⃣ 【测试视角】- 测试用例和验证点
   适合：测试人员写测试用例
   输出内容：
   - 正向测试场景（前置条件→步骤→期望结果）
   - 异常测试场景（边界值、异常情况、错误提示）
   - 字段校验规则表（含测试边界值）
   - 状态变化测试点、联调测试清单"""
    
    explorer_option = """3️⃣ 【快速探索】- 全局评审视角
   适合：需求评审会议、快速了解需求
   输出内容：
   - 模块核心功能概览（3-5个关键点）
   - 模块依赖关系图、数据流向图
   - 开发顺序建议、风险点识别
   - 前后端分工参考"""
    
    # 判断角色类型，调整推荐顺序
    # 开发相关角色：后端、前端、客户端、开发
    if normalized_role in ["后端", "前端", "客户端", "开发"]:
        # 开发视角排第一
        return f"""
{developer_option}

{tester_option}

{explorer_option}
"""
    
    # 测试相关角色（检查原始角色名是否包含"测试"）
    elif "测试" in user_role or "test" in user_role.lower() or "qa" in user_role.lower():
        # 测试视角排第一
        return f"""
{tester_option.replace('2️⃣', '1️⃣')}

{developer_option.replace('1️⃣', '2️⃣')}

{explorer_option}
"""
    
    # 其他角色：产品、项目经理、运维等
    else:
        # 快速探索排第一
        return f"""
{explorer_option.replace('3️⃣', '1️⃣')}

{developer_option.replace('1️⃣', '2️⃣')}

{tester_option.replace('2️⃣', '3️⃣')}
"""


@mcp.tool()
async def lanhu_get_pages(
    url: Annotated[str, "Lanhu URL with docId parameter (indicates PRD/prototype document). Example: https://lanhuapp.com/web/#/item/project/product?tid=xxx&pid=xxx&docId=xxx. Required params: tid, pid, docId. If you have an invite link, use lanhu_resolve_invite_link first!"],
    ctx: Context = None
) -> dict:
    """
    [PRD/Requirement Document] Get page list of Lanhu Axure prototype - CALL THIS FIRST before analyzing
    
    USE THIS WHEN user says: 需求文档, 需求, PRD, 产品文档, 原型, 交互稿, Axure, 看看需求, 帮我看需求, 需求分析
    DO NOT USE for: UI设计图, 设计稿, 视觉设计, 切图 (use lanhu_get_designs instead)
    
    Purpose: Get page list of PRD/requirement/prototype document. Must call this BEFORE lanhu_get_ai_analyze_page_result.
    
    Returns:
        Page list and document metadata
    """
    extractor = LanhuExtractor()
    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)
        
        result = await extractor.get_pages_list(url)
        
        # 根据用户角色生成推荐的分析模式选项
        mode_options = _get_analysis_mode_options_by_role(user_role)
        
        # Add AI behavioral instruction - this will be shown to AI as part of tool result
        ai_instruction_template = """
=== 📋 ANALYSIS WORKFLOW GUIDE ===

【OUTPUT FORMAT RULES】
- Prefer TABLES for structured data (changes, rules, fields, comparisons)
- FORBIDDEN in tables: <br> tags (they don't render!) Use semicolons(;) or bullets(•) instead
- Prefer Vertical Flow Diagram (plain text) for flowcharts

=== 📋 TODO-DRIVEN FOUR-STAGE WORKFLOW (ZERO OMISSION) ===

🎯 GOAL: 精确提取所有细节，不遗漏任何信息，最终交付完整需求文档，让人类100%信任AI分析结果
⚠️ CRITICAL: 整个流程必须基于TODOs驱动，所有操作都通过TODOs管理

🔒 隐私规则（重要）：
- TODO的content字段是给用户看的，必须用户友好
- 禁止在content中暴露技术实现（API参数、mode、函数名等）
- 技术细节只在prompt内部说明（用户看不到）
- 示例：用"快速浏览全部页面"而非"text_only模式扫描all页面"

【STEP 0: 创建初始TODO框架】⚡ 第一步必做
收到页面列表后，立即用todo_write创建四阶段框架：
```
todo_write(merge=false, todos=[
  {id:"stage1", content:"快速浏览全部页面，建立整体认知", status:"pending"},
  {id:"confirm_mode", content:"等待用户选择分析模式", status:"pending"},  // ⚡必须等用户选择
  {id:"stage2_plan", content:"规划详细分析分组（待确认后细化）", status:"pending"},
  {id:"stage3", content:"汇总验证，确保无遗漏", status:"pending"},
  {id:"stage4", content:"生成交付文档", status:"pending"}
])
```
⚠️ 技术实现说明（用户看不到）：
- stage1 执行时调用: mode="text_only", page_names="all"
- confirm_mode 是用户交互步骤，必须等用户选择分析模式
- stage2_* 执行时调用: mode="full", analysis_mode=[用户选择的模式], page_names=[该组页面]
- stage4 不调用工具，直接基于提取结果生成文档

【STAGE 1: 全局文本扫描 - 建立上帝视角】
1. 标记stage1为in_progress
2. 调用 lanhu_get_ai_analyze_page_result(page_names="all", mode="text_only")
3. 快速阅读文本，输出结构化分析（必须用表格）：
   | 模块名 | 包含页面 | 核心功能 | 业务流程 |
   |--------|---------|---------|---------|
   | 用户认证 | 登录,注册,找回密码 | 用户认证 | 登录→首页 |
4. **设计分组策略**（基于业务逻辑）
5. 标记stage1为completed
6. **⚡【必须】询问用户选择分析模式**（标记confirm_mode为in_progress）：
   ⚠️ 用户必须选择分析模式，否则不能继续！
   ```
   全部页面已浏览完毕。
   
   📊 发现以下模块：
   [列出分组表格，标注每组页面数]
   
   请选择分析角度：
   {MODE_OPTIONS_PLACEHOLDER}
   
   也可以自定义需求，比如"简单看看"、"只看数据流向"等。
   
   ⚠️ 请告知您的选择和要分析的模块，以便继续分析工作。
   ```
   
   ⚠️ 等待用户回复后，标记confirm_mode为completed，记住用户选择的analysis_mode，再执行步骤7
   
7. **⚡反向更新TODOs**（关键步骤）：
   根据用户选择的分析模式更新TODO描述：
```
todo_write(merge=true, todos=[
  {id:"stage2_plan", status:"cancelled"},  // 取消占位TODO
  {id:"stage2_1", content:"[模式名]分析：用户认证模块（3页）", status:"pending"},
  {id:"stage2_2", content:"[模式名]分析：订单管理模块（3页）", status:"pending"},
  // ... 根据STAGE1结果和用户指令动态生成
  // ⚠️ [模式名] = 开发视角/测试视角/快速探索
  // ⚠️ 如果用户只要求看指定模块，则只创建对应模块的TODOs
])
```

【STAGE 2: 分组深度分析 - 根据分析模式提取】
逐个执行stage2_*的TODOs：
1. 标记当前TODO为in_progress
2. 调用 lanhu_get_ai_analyze_page_result(page_names=[该组页面], mode="full", analysis_mode=[用户选择的模式])
   ⚠️ analysis_mode 必须使用用户在 confirm_mode 阶段选择的模式：
   - "developer" = 开发视角
   - "tester" = 测试视角
   - "explorer" = 快速探索

3. **根据分析模式输出不同内容**：
   工具返回会包含对应模式的 prompt 指引，按照指引输出即可。
   
   三种模式的核心区别：
   
   【开发视角】提取所有细节，供开发写代码：
   - 功能清单表（功能、输入、输出、规则、异常）
   - 字段规则表（必填、类型、长度、校验、提示）
   - 全局关联（数据依赖、输出、跳转）
   - AI理解与建议（对不清晰的地方）
   
   【测试视角】提取测试场景，供测试写用例：
   - 正向场景（前置条件→步骤→期望结果）
   - 异常场景（触发条件→期望结果）
   - 字段校验规则表（含测试边界值）
   - 状态变化表
   - 联调测试点
   
   【快速探索】提取核心功能，供需求评审：
   - 模块核心功能（3-5个点，一句话描述）
   - 依赖关系识别
   - 关键特征标注（外部接口、支付、审批等）
   - 评审讨论点

4. **所有模式都必须输出的：变更类型识别**
   ```
   🔍 变更类型识别：
   - 类型：🆕新增 / 🔄修改 / ❓未明确
   - 判断依据：[引用文档关键证据]
   - 结论：[一句话说明]
   ```

5. 标记当前TODO为completed
6. 继续下一个stage2_* TODO

【STAGE 3: 反向验证 - 确保零遗漏】
1. 标记stage3为in_progress
2. **汇总STAGE2所有结果，根据分析模式验证不同内容**：
   
   【开发视角】验证：
   - 功能点是否完整？字段是否齐全？
   - 业务规则是否清晰？异常处理是否覆盖？
   
   【测试视角】验证：
   - 测试场景是否覆盖核心功能？
   - 异常场景是否完整？边界值是否标注？
   
   【快速探索】验证：
   - 模块划分是否合理？依赖关系是否清晰？
   - 变更类型是否都已识别？
   
3. **汇总变更类型统计**（所有模式都要）：
   - 🆕 全新功能：X个模块
   - 🔄 功能修改：Y个模块
   - ❓ 未明确：Z个模块（列出需确认）
   
4. 生成"待确认清单"（汇总所有⚠️的项）
5. 标记stage3为completed

【STAGE 4: 生成交付文档 - 根据分析模式输出】⚠️ 必做阶段
1. 标记stage4为in_progress
2. **根据分析模式生成对应交付物**（工具返回的 prompt 中有详细格式）：

   【开发视角】输出：详细需求文档 + 全局流程图
   ```
   # 需求文档总结
   
   ## 📊 文档概览
   - 总页面数、模块数、变更类型统计、待确认项数
   
   ## 🎯 需求性质分析
   - 新增/修改统计表 + 判断依据
   
   ## 🌍 全局业务流程图（⚡核心交付物）
   - 包含所有模块的完整细节
   - 所有判断条件、分支、异常处理
   - 用文字流程图（Vertical Flow Diagram）
   
   ## 模块X：XXX模块
   ### 功能清单（表格）
   ### 字段规则（表格）
   ### 模块总结
   
   ## ⚠️ 待确认事项
   ```
   
   【测试视角】输出：测试计划文档
   ```
   # 测试计划文档
   
   ## 📊 测试概览
   - 模块数、测试场景数（正向X个，异常Y个）
   - 变更类型统计（🆕全量测试 / 🔄回归测试）
   
   ## 🎯 需求性质分析（影响测试范围）
   
   ## 测试用例清单（按模块）
   ### 模块X：XXX
   #### 正向场景（P0）
   #### 异常场景（P1）
   #### 字段校验表
   
   ## 📋 测试数据准备清单
   ## 🔄 回归测试提示
   ## ❓ 测试疑问汇总
   ```
   
   【快速探索】输出：需求评审文档（像PPT）
   ```
   # 需求评审 - XXX功能
   
   ## 📊 文档概览（1分钟了解全局）
   ## 🎯 需求性质分析（新增/修改统计 + 判断依据）
   ## 📦 模块清单表
   | 序号 | 模块名 | 变更类型 | 核心功能点 | 依赖模块 | 页面数 |
   
   ## 🔄 数据流向图（展示模块间依赖关系）
   ## 📅 开发顺序建议（基于依赖关系）
   ## 🔗 关键依赖关系说明
   ## ⚠️ 风险和待确认事项
   ## 💼 前后端分工参考（仅罗列，不估工时）
   ## 📋 评审会讨论要点
   ## ✅ 评审后行动项
   ```
   
3. **输出完成提示**（根据分析模式调整话术）：
   【开发视角】
   "详细需求文档已整理完毕，可供开发参考。"
   
   【测试视角】
   "测试计划已整理完毕，可供测试团队使用。"
   
   【快速探索】
   "需求评审文档已整理完毕，可用于评审会议。"

4. 标记stage4为completed

【输出规范】
 ❌ 禁止省略细节 ❌ 不确定禁止臆测

【TODO管理规则 - 核心】
✅ 收到页面列表后立即创建5个TODO（含confirm_mode）
✅ STAGE1完成后必须询问用户选择分析模式（confirm_mode）
✅ 用户选择分析模式后，记住analysis_mode，再更新stage2_*的TODOs
✅ 所有执行必须基于TODOs（先标记in_progress，完成后标记completed）
✅ STAGE2调用时必须传入用户选择的analysis_mode参数
✅ STAGE4必须在STAGE3完成后执行（生成文档，不调用工具）
✅ 禁止脱离TODO系统执行任何阶段

⚠️ TODO content字段规则（用户可见）：
  - 使用用户友好的描述："[模式名]分析：XX模块（N页）"
  - 模式名 = 开发视角/测试视角/快速探索
  - 禁止暴露技术细节：mode/API参数/函数名等
  - 示例正确："开发视角分析：用户认证模块（3页）"
  - 示例错误："STAGE2-developer-full模式" ❌

⚠️ 分析模式必须由用户选择：
  - 如果用户未选择分析模式，拒绝继续（confirm_mode保持pending）
  - 用户可以说"开发"/"测试"/"快速探索"或自定义需求
  - AI理解用户意图后映射到对应的analysis_mode

❌ 禁止跳过TODO创建 ❌ 禁止跳过confirm_mode ❌ 禁止不更新TODO状态 ❌ 禁止跳过STAGE4
    - Prefer Vertical Flow Diagram (plain text) for flowcharts
=== END OF WORKFLOW GUIDE ===
"""
        
        # 替换占位符并设置最终的指令
        result['__AI_INSTRUCTION__'] = ai_instruction_template.replace('{MODE_OPTIONS_PLACEHOLDER}', mode_options)
        
        # Add AI suggestion when there are many pages (>10)
        total_pages = result.get('total_pages', 0)
        if total_pages > 10:
            result['ai_suggestion'] = {
                'notice': f'This document contains {total_pages} pages, recommend FOUR-STAGE analysis',
                'recommendation': 'Use FOUR-STAGE workflow to ensure ZERO omission and deliver complete document',
                'next_action': 'Immediately call lanhu_get_ai_analyze_page_result(page_names="all", mode="text_only") for STAGE 1 global scan',
                'workflow_reminder': 'STAGE 1 (text scan) → Design TODOs → STAGE 2 (detailed analysis) → STAGE 3 (validation) → STAGE 4 (generate document + flowcharts)',
                'language_note': 'Respond in Chinese when talking to user'
            }
        else:
            # 少于10页也建议使用四阶段（确保零遗漏）
            result['ai_suggestion'] = {
                'notice': f'Document has {total_pages} pages',
                'recommendation': 'Still recommend FOUR-STAGE workflow for precision and complete deliverable',
                'next_action': 'Call lanhu_get_ai_analyze_page_result(page_names="all", mode="text_only") for STAGE 1',
                'language_note': 'Respond in Chinese when talking to user'
            }
        
        return result
    finally:
        await extractor.close()


# ============================================
# 分析模式 Prompt 生成函数
# ============================================

def _get_stage2_prompt_developer() -> str:
    """获取开发视角的 Stage 2 元认知验证 prompt"""
    return """
🧠 元认知验证（开发视角）

**🔍 变更类型识别**：
- 类型：🆕新增 / 🔄修改 / ❓未明确
- 判断依据：
  • [引用文档原文关键句，如"全新功能"/"在现有XX基础上"/"优化"]
  • [描述文档结构特征：是从0介绍还是对比新旧]
- 结论：[一句话说明]

**📋 本组核心N点**（按实际情况，不固定数量）：
1. [核心功能点1]：具体描述业务逻辑和规则
2. [核心功能点2]：...
...

**📊 功能清单表**：
| 功能点 | 描述 | 输入 | 输出 | 业务规则 | 异常处理 |
|--------|------|------|------|----------|----------|

**📋 字段规则表**（如果页面有表单/字段）：
| 字段名 | 必填 | 类型 | 长度/格式 | 校验规则 | 错误提示 |
|--------|------|------|-----------|----------|----------|

**🔗 与全局关联**（按需输出，有则写）：
• 数据依赖：依赖「XX模块」的XX数据/状态
• 数据输出：数据流向「XX模块」用于XX
• 交互跳转：完成后跳转/触发「XX模块」
• 状态同步：与「XX模块」的XX状态保持一致

**⚠️ 遗漏/矛盾检查**（按需输出）：
• ⚠️ [不清晰的地方]：具体描述
• ⚠️ [潜在矛盾]：描述发现的逻辑矛盾
• 🎨 [UI与文字冲突]：对比UI和文字说明的不一致
• ✅ [已确认清晰]：关键逻辑已明确

**🤖 AI理解与建议**（对不清晰的地方，按需输出）：
💡 [对XX的理解]：
   • 需求原文：[引用]
   • AI理解：[推测]
   • 推理依据：[说明]
   • 建议：[给产品/开发的建议]
"""


def _get_stage2_prompt_tester() -> str:
    """获取测试视角的 Stage 2 元认知验证 prompt"""
    return """
🧠 元认知验证（测试视角）

**🔍 变更类型识别**：
- 类型：🆕新增 / 🔄修改 / ❓未明确
- 判断依据：[引用文档关键证据]
- 测试影响：🆕全量测试 / 🔄回归+增量测试

**📋 测试场景提取**：

### ✅ 正向场景（P0核心功能）
**场景1：[场景名称]**
- 前置条件：[列出]
- 操作步骤：
  1. [步骤1]
  2. [步骤2]
  ...
- 期望结果：[具体描述]
- 数据准备：[需要什么测试数据]

**场景2：[场景名称]**
...

### ⚠️ 异常场景（P1边界和异常）
**异常1：[场景名称]**
- 触发条件：[什么情况下]
- 操作步骤：[...]
- 期望结果：[错误提示/页面反应]

**异常2：[场景名称]**
...

**📋 字段校验规则表**：
| 字段名 | 必填 | 长度/格式 | 校验规则 | 错误提示文案 | 测试边界值 |
|--------|------|-----------|----------|-------------|-----------|

**🔄 状态变化表**：
| 操作 | 操作前状态 | 操作后状态 | 界面变化 |
|------|-----------|-----------|---------|

**⚠️ 特殊测试点**：
- 并发场景：[哪些操作可能并发]
- 权限验证：[哪些操作需要权限]
- 数据边界：[数据量大时的表现]

**🔗 联调测试点**（与其他模块的交互）：
- 依赖「XX模块」：[测试时需要先准备什么]
- 影响「XX模块」：[操作后需要验证哪里]

**❓ 测试疑问**（需产品/开发澄清）：
- ⚠️ [哪里不清晰，无法编写测试用例]
"""


def _get_stage2_prompt_explorer() -> str:
    """获取快速探索视角的 Stage 2 元认知验证 prompt"""
    return """
🧠 元认知验证（快速探索视角）

**🔍 变更类型识别**：
- 类型：🆕新增 / 🔄修改 / ❓未明确
- 判断依据：
  • [引用文档原文关键句]
  • [指出关键信号词："全新"/"现有"/"优化"等]
- 结论：[一句话说明]

**📦 模块核心功能**（3-5个功能点，不深入细节）：
1. [功能点1]：[一句话描述]
2. [功能点2]：[一句话描述]
3. [功能点3]：[一句话描述]
...

**🔗 依赖关系识别**：
- 依赖输入：需要「XX模块」提供[具体什么数据/状态]
- 输出影响：数据会流向「XX模块」用于[什么用途]
- 依赖强度：强依赖（必须先完成）/ 弱依赖（可独立开发）

**💡 关键特征标注**（客观事实，不评价）：
- 涉及外部接口：[是/否，哪些]
- 涉及支付流程：[是/否]
- 涉及审批流程：[是/否，几级]
- 涉及文件上传：[是/否]

**⚠️ 需求问题**（影响评审决策）：
- 逻辑不清晰：[具体哪里]
- 逻辑矛盾：[哪里矛盾]
- 缺失信息：[缺什么]

**🎯 评审讨论点**（供会议讨论）：
- 给产品：[需要澄清的问题]
- 给开发：[需要技术评估的点]
- 给测试：[测试环境/数据准备问题]
"""


def _get_stage4_prompt_developer() -> str:
    """获取开发视角的 Stage 4 交付物 prompt"""
    return """
【STAGE 4 输出要求 - 开发视角】

输出结构：
1. # 需求文档总结
2. ## 📊 文档概览（页面数、模块数、变更类型统计、待确认项数）
3. ## 🎯 需求性质分析（新增/修改统计表 + 判断依据）
4. ## 🌍 全局业务流程图（⚡核心交付物）
   - 包含所有模块的完整细节
   - 所有判断条件、分支、异常处理
   - 所有字段校验规则和数据流转
   - 模块间的联系和数据传递
   - 用文字流程图（Vertical Flow Diagram）
5. ## 模块X：XXX模块
   ### 功能清单（表格）
   ### 字段规则（表格）
   ### 模块总结（列举式，不画单独流程图）
6. ## ⚠️ 待确认事项（所有疑问汇总）

质量标准：开发看完能写代码，测试看完能写用例，0遗漏
"""


def _get_stage4_prompt_tester() -> str:
    """获取测试视角的 Stage 4 交付物 prompt"""
    return """
【STAGE 4 输出要求 - 测试视角】

输出结构：
1. # 测试计划文档
2. ## 📊 测试概览
   - 模块数、测试场景数（正向X个，异常Y个）
   - 变更类型统计（🆕全量测试 / 🔄回归测试）
3. ## 🎯 需求性质分析（影响测试范围）
4. ## 测试用例清单（按模块）
   ### 模块X：XXX
   #### 正向场景（P0）
   - 场景1：前置条件 → 步骤 → 期望结果
   - 场景2：...
   #### 异常场景（P1）
   - 异常1：触发条件 → 期望结果
   #### 字段校验表
   | 字段 | 必填 | 规则 | 错误提示 | 边界值测试 |
5. ## 📋 测试数据准备清单
6. ## 🔄 回归测试提示（如有修改类型模块）
7. ## ❓ 测试疑问汇总（需澄清才能写用例）

质量标准：测试人员拿到后可直接写用例，知道测什么、怎么测
"""


def _get_stage4_prompt_explorer() -> str:
    """获取快速探索视角的 Stage 4 交付物 prompt"""
    return """
【STAGE 4 输出要求 - 快速探索/需求评审视角】

输出结构（像评审会PPT）：
1. # 需求评审 - XXX功能
2. ## 📊 文档概览（1分钟了解全局）
   - 总页面数、模块数
   - 需求性质统计（新增X个/修改Y个）
3. ## 🎯 需求性质分析
   | 变更类型 | 模块数 | 模块列表 | 判断依据 |
4. ## 📦 模块清单表
   | 序号 | 模块名 | 变更类型 | 核心功能点(3-5个) | 依赖模块 | 页面数 |
5. ## 🔄 数据流向图（文字或ASCII图）
   - 展示模块间依赖关系
   - 数据传递方向
6. ## 📅 开发顺序建议（基于依赖关系）
   - 第一批（无依赖）：...
   - 第二批（依赖第一批）：...
   - 可并行：...
7. ## 🔗 关键依赖关系说明
   | 模块 | 依赖什么 | 依赖原因 | 影响 |
8. ## ⚠️ 风险和待确认事项
   - 需求不清晰：...
   - 逻辑矛盾：...
   - 外部依赖：...
9. ## 💼 前后端分工参考（仅罗列，不估工时）
10. ## 📋 评审会讨论要点
    - 给产品：...
    - 给开发：...
    - 给测试：...
11. ## ✅ 评审后行动项

禁止：评估工时、评估复杂度、做主观评价
只做：陈述事实、展示关系、列出问题
"""


def _get_analysis_mode_prompt(analysis_mode: str) -> dict:
    """
    根据分析模式获取对应的 prompt
    
    Args:
        analysis_mode: 分析模式 (developer/tester/explorer)
    
    Returns:
        包含 stage2_prompt 和 stage4_prompt 的字典
    """
    if analysis_mode == "tester":
        return {
            "mode_name": "测试视角",
            "mode_desc": "提取测试场景、校验规则、异常清单",
            "stage2_prompt": _get_stage2_prompt_tester(),
            "stage4_prompt": _get_stage4_prompt_tester()
        }
    elif analysis_mode == "explorer":
        return {
            "mode_name": "快速探索",
            "mode_desc": "提取核心功能、依赖关系、评审要点",
            "stage2_prompt": _get_stage2_prompt_explorer(),
            "stage4_prompt": _get_stage4_prompt_explorer()
        }
    else:  # developer (default)
        return {
            "mode_name": "开发视角",
            "mode_desc": "提取所有细节、字段规则、完整流程",
            "stage2_prompt": _get_stage2_prompt_developer(),
            "stage4_prompt": _get_stage4_prompt_developer()
        }


@mcp.tool()
async def lanhu_get_ai_analyze_page_result(
        url: Annotated[str, "Lanhu URL with docId parameter (indicates PRD/prototype document). Example: https://lanhuapp.com/web/#/item/project/product?tid=xxx&pid=xxx&docId=xxx. If you have an invite link, use lanhu_resolve_invite_link first!"],
        page_names: Annotated[Union[str, List[str]], "Page name(s) to analyze. Use 'all' for all pages, single name like '退款流程', or list like ['退款流程', '用户中心']. Get exact names from lanhu_get_pages first!"],
        mode: Annotated[str, "Analysis mode: 'text_only' (fast global scan, text only for overview) or 'full' (detailed analysis with images+text). Default: 'full'"] = "full",
        analysis_mode: Annotated[str, "Analysis perspective (MUST be chosen by user after STAGE 1): 'developer' (detailed for coding), 'tester' (test scenarios/validation), 'explorer' (quick overview for review). Default: 'developer'"] = "developer",
        ctx: Context = None
) -> List[Union[str, Image]]:
    """
    [PRD/Requirement Document] Analyze Lanhu Axure prototype pages - GET VISUAL CONTENT
    
    USE THIS WHEN user says: 需求文档, 需求, PRD, 产品文档, 原型, 交互稿, Axure, 看看需求, 帮我看需求, 分析需求, 需求分析
    DO NOT USE for: UI设计图, 设计稿, 视觉设计, 切图 (use lanhu_get_ai_analyze_design_result instead)
    
    FOUR-STAGE WORKFLOW (ZERO OMISSION):
    1. STAGE 1: Call with mode="text_only" and page_names="all" for global text scan
       - Purpose: Build god's view, understand structure, design grouping strategy
       - Output: Text only (fast)
       - ⚠️ IMPORTANT: After STAGE 1, MUST ask user to choose analysis_mode!
    
    2. STAGE 2: Call with mode="full" for each group (output format varies by analysis_mode)
       - developer: Extract ALL details (fields, rules, flows) - for coding
       - tester: Extract test scenarios, validation points, field rules - for test cases
       - explorer: Extract core functions only (3-5 points) - for requirement review
    
    3. STAGE 3: Reverse validation (format varies by analysis_mode)
    
    4. STAGE 4: Generate deliverable (format varies by analysis_mode)
       - developer: Detailed requirement doc + global flowchart
       - tester: Test plan + test case list + field validation table
       - explorer: Review PPT-style doc + module table + dependency diagram
    
    Returns:
        - mode="text_only": Text content only (for fast global scan)
        - mode="full": Visual + text (format determined by analysis_mode)
    """
    extractor = LanhuExtractor()

    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)
        
        # 解析URL获取文档ID
        params = extractor.parse_url(url)
        doc_id = params['doc_id']

        # 设置输出目录（内部实现，自动管理）
        resource_dir = str(DATA_DIR / f"axure_extract_{doc_id[:8]}")
        output_dir = str(DATA_DIR / f"axure_extract_{doc_id[:8]}_screenshots")

        # 下载资源（支持智能缓存）
        download_result = await extractor.download_resources(url, resource_dir)

        # 如果是新下载或更新，修复HTML
        if download_result['status'] in ['downloaded', 'updated']:
            fix_html_files(resource_dir)

        # 获取页面列表
        pages_info = await extractor.get_pages_list(url)
        all_pages = pages_info['pages']

        # 处理page_names参数 - 构建name到filename的映射
        page_map = {p['name']: p['filename'].replace('.html', '') for p in all_pages}

        if isinstance(page_names, str):
            if page_names.lower() == 'all':
                target_pages = [p['filename'].replace('.html', '') for p in all_pages]
                target_page_names = [p['name'] for p in all_pages]
            else:
                # 如果是页面显示名，转换为文件名
                if page_names in page_map:
                    target_pages = [page_map[page_names]]
                    target_page_names = [page_names]
                else:
                    # 直接作为文件名使用
                    target_pages = [page_names]
                    target_page_names = [page_names]
        else:
            # 列表形式
            target_pages = []
            target_page_names = []
            for pn in page_names:
                if pn in page_map:
                    target_pages.append(page_map[pn])
                    target_page_names.append(pn)
                else:
                    target_pages.append(pn)
                    target_page_names.append(pn)

        # 截图（不需要返回base64了，直接保存文件）
        # 传入version_id用于智能缓存
        version_id = download_result.get('version_id', '')
        results = await screenshot_page_internal(resource_dir, target_pages, output_dir, return_base64=False, version_id=version_id)

        # 构建响应
        cached_count = sum(1 for r in results if r.get('from_cache'))
        summary = {
            'total_requested': len(target_pages),
            'successful': sum(1 for r in results if r['success']),
            'failed': sum(1 for r in results if not r['success']),
        }

        # 提取成功的结果
        success_results = [r for r in results if r['success']]

        # 构建返回内容列表（图文穿插）
        content = []

        # Add summary header - 简化显示，只告知是否命中缓存
        all_from_cache = cached_count == len(target_pages) and cached_count > 0
        cache_hint = "⚡" if all_from_cache else "✓"

        # Build reverse mapping from filename to display name
        filename_to_display = {p['filename'].replace('.html', ''): p['name'] for p in all_pages}

        # 根据mode决定输出格式
        is_text_only = (mode == "text_only")
        mode_indicator = "📝 TEXT_ONLY MODE" if is_text_only else "📸 FULL MODE"
        
        header_text = f"{cache_hint} {mode_indicator} | Version: {download_result['version_id'][:8]}...\n"
        header_text += f"📊 Total {summary['successful']}/{summary['total_requested']} pages\n\n"
        
        if is_text_only:
            # TEXT_ONLY模式的提示（STAGE 1全局扫描）
            header_text += "=" * 60 + "\n"
            header_text += "📝 STAGE 1: GLOBAL TEXT SCAN (Building God's View)\n"
            header_text += "=" * 60 + "\n"
            header_text += "🎯 Your Mission:\n"
            header_text += "  1. Quickly read ALL page texts below\n"
            header_text += "  2. Identify document structure (modules, flows, entities)\n"
            header_text += "  3. Output structured analysis (MUST use Markdown table)\n"
            header_text += "  4. Design grouping strategy based on business logic\n"
            header_text += "  5. Create TODOs for STAGE 2 detailed analysis\n\n"
            header_text += "⚠️ Important:\n"
            header_text += "  • This is text-only mode for fast overview\n"
            header_text += "  • No visual outputs in this stage\n"
            header_text += "  • Focus on understanding structure, not extracting details\n"
            header_text += "  • Details will be extracted in STAGE 2 (with images)\n"
            header_text += "=" * 60 + "\n"
        else:
            # FULL模式的提示（STAGE 2详细分析）
            # 获取分析模式对应的 prompt
            mode_prompts = _get_analysis_mode_prompt(analysis_mode)
            
            header_text += "=" * 60 + "\n"
            header_text += f"🤖 STAGE 2 分析模式：【{mode_prompts['mode_name']}】\n"
            header_text += f"📋 {mode_prompts['mode_desc']}\n"
            header_text += "=" * 60 + "\n"
            header_text += "📸 理解原则：视觉输出为主，文本为辅\n"
            header_text += "  • 视觉输出包含完整UI、流程图、交互细节\n"
            header_text += "  • 文本提供关键信息提取但可能不完整\n"
            header_text += "  • 建议：先看图理解整体，再用文本快速定位关键点\n\n"
            
            # 添加当前分析模式的 Stage 2 prompt
            header_text += "=" * 60 + "\n"
            header_text += f"🐕 二狗工作指引（{mode_prompts['mode_name']}）\n"
            header_text += "=" * 60 + "\n"
            header_text += "分析完本组页面后，必须按以下格式输出：\n"
            header_text += mode_prompts['stage2_prompt']
            header_text += "\n" + "=" * 60 + "\n"
            
            # 添加 Stage 4 输出提示（供 AI 记住）
            header_text += "\n📝 提醒：STAGE 4 交付物格式（完成所有分组后使用）：\n"
            header_text += mode_prompts['stage4_prompt']
            header_text += "\n" + "=" * 60 + "\n\n"
        header_text += "📋 Return Format (due to MCP limitations):\n"
        header_text += "  1️⃣ [ABOVE] All visual outputs displayed in page order (top to bottom)\n"
        header_text += "  2️⃣ [BELOW] Corresponding document text content (top to bottom)\n\n"
        header_text += "📌 Image-Text Mapping:\n"
        if success_results:
            display_name = filename_to_display.get(success_results[0]['page_name'], success_results[0]['page_name'])
            header_text += f"  • Image 1 ↔ Page 1 text: {display_name}\n"
        if len(success_results) > 1:
            display_name = filename_to_display.get(success_results[1]['page_name'], success_results[1]['page_name'])
            header_text += f"  • Image 2 ↔ Page 2 text: {display_name}\n"
        if len(success_results) > 2:
            display_name = filename_to_display.get(success_results[2]['page_name'], success_results[2]['page_name'])
            header_text += f"  • Image 3 ↔ Page 3 text: {display_name}\n"
        if len(success_results) > 3:
            display_name = filename_to_display.get(success_results[3]['page_name'], success_results[3]['page_name'])
            header_text += f"  • Image 4 ↔ Page 4 text: {display_name}\n"
        if len(success_results) > 4:
            header_text += f"  • ... Total {len(success_results)} pages, and so on\n"
        header_text += "\n💡 Please match visual outputs above with text below to understand each page's requirements\n"
        header_text += "=" * 60 + "\n"
        
        # 如果是首次查看完整文档（TEXT_ONLY模式），添加STAGE1的工作指引
        if isinstance(page_names, str) and page_names.lower() == 'all' and is_text_only:
            header_text += "\n" + "🐕 " + "=" * 58 + "\n"
            header_text += "二狗工作指引（STAGE 1全局扫描）\n"
            header_text += "=" * 60 + "\n"
            header_text += "📋 本阶段任务（建立上帝视角）：\n\n"
            header_text += "1️⃣ 快速阅读所有页面文本\n"
            header_text += "2️⃣ 输出文档结构表（模块、页面、功能）\n"
            header_text += "3️⃣ 识别业务关联关系\n"
            header_text += "4️⃣ 设计合理分组策略（基于业务逻辑）\n"
            header_text += "5️⃣ ⚡【必须】询问用户选择分析模式\n"
            header_text += "6️⃣ 反向更新TODOs（细化STAGE2分组任务）\n\n"
            header_text += "=" * 60 + "\n"
            header_text += "⚠️ 【重要】完成扫描后必须询问用户选择分析模式：\n"
            header_text += "=" * 60 + "\n"
            # 根据用户角色生成推荐的分析模式选项
            user_name_local, user_role_local = get_user_info(ctx) if ctx else ('匿名', '未知')
            mode_options_local = _get_analysis_mode_options_by_role(user_role_local)
            
            header_text += "全部页面已浏览完毕。\n\n"
            header_text += "📊 发现以下模块：\n"
            header_text += "[此处输出模块表格]\n\n"
            header_text += "请选择分析角度：\n"
            header_text += mode_options_local + "\n"
            header_text += '也可以自定义需求，比如"简单看看"、"只看数据流向"等。\n\n'
            header_text += "⚠️ 请告知您的选择，以便继续分析工作。\n"
            header_text += "=" * 60 + "\n"
        
        content.append(header_text)

        # 根据mode决定是否添加截图
        if not is_text_only:
            # FULL模式：先添加所有截图
            for r in success_results:
                if 'screenshot_path' in r:
                    content.append(Image(path=r['screenshot_path']))

        # Add all text content (格式根据mode不同)
        if is_text_only:
            # TEXT_ONLY模式：文本是主要内容
            text_section = "\n" + "=" * 60 + "\n"
            text_section += "📝 ALL PAGE TEXTS (For Global Understanding)\n"
            text_section += "=" * 60 + "\n"
            text_section += "💡 Read these texts to understand document structure\n"
            text_section += "💡 Identify modules, flows, and business logic\n"
            text_section += "💡 Then design reasonable grouping strategy for STAGE 2\n"
            text_section += "=" * 60 + "\n"
        else:
            # FULL模式：文本是辅助内容
            text_section = "\n" + "=" * 60 + "\n"
            text_section += "📝 Document Text Content (Supplementary, visual outputs above are primary)\n"
            text_section += "=" * 60 + "\n"
            text_section += "⚠️ Important: Text may be incomplete, for complex flowcharts/tables refer to visual outputs\n"
            text_section += "💡 Text Purpose: Quick keyword search, find specific info, understand text descriptions\n"
            text_section += "=" * 60 + "\n"
        content.append(text_section)

        for idx, r in enumerate(success_results, 1):
            display_name = filename_to_display.get(r['page_name'], r['page_name'])

            page_text = f"\n{'─' * 60}\n"
            page_text += f"📄 Page {idx}: {display_name}\n"
            page_text += f"{'─' * 60}\n"

            if 'page_text' in r and r['page_text']:
                page_text += r['page_text'] + "\n"
            else:
                page_text += "⚠️ No text content extracted (please refer to corresponding visual output above)\n"

            content.append(page_text)

        # Show failed pages (if any)
        failed_pages = [r for r in results if not r['success']]
        if failed_pages:
            failure_text = f"\n{'=' * 50}\n"
            failure_text += f"⚠️ Failed {len(failed_pages)} pages:\n"
            for r in failed_pages:
                failure_text += f"  ✗ {r['page_name']}: {r.get('error', 'Unknown')}\n"
            content.append(failure_text)

        return content
    finally:
        await extractor.close()


async def _get_sectors(extractor: LanhuExtractor, project_id: str) -> dict:
    """获取项目的分组(sector)信息，返回 image_id → sector_name 映射和分组列表"""
    try:
        response = await extractor.client.get(
            f"{BASE_URL}/api/project/project_sectors?project_id={project_id}"
        )
        extractor._check_auth(response)
        if response.status_code != 200:
            return {'sectors': [], 'image_sector_map': {}}
        data = response.json()
        if data.get('code') != '00000':
            return {'sectors': [], 'image_sector_map': {}}

        sectors_raw = data.get('data', {}).get('sectors', [])
        image_sector_map = {}
        sectors = []
        for sector in sectors_raw:
            name = sector.get('name', '')
            image_ids = sector.get('images', [])
            sectors.append({
                'id': sector.get('id'),
                'name': name,
                'image_count': len(image_ids),
                'image_ids': image_ids,
            })
            for img_id in image_ids:
                image_sector_map[img_id] = name

        return {'sectors': sectors, 'image_sector_map': image_sector_map}
    except Exception:
        return {'sectors': [], 'image_sector_map': {}}


async def _get_designs_internal(extractor: LanhuExtractor, url: str) -> dict:
    """内部函数：获取设计图列表"""
    # 解析URL获取参数
    params = extractor.parse_url(url)

    # 并行获取设计图列表和分组信息
    import asyncio as _asyncio
    designs_task = _fetch_design_images(extractor, params)
    sectors_task = _get_sectors(extractor, params['project_id'])
    designs_result, sectors_result = await _asyncio.gather(designs_task, sectors_task)

    if designs_result.get('status') == 'error':
        return designs_result

    # 将分组信息注入到每个设计图
    image_sector_map = sectors_result['image_sector_map']
    for design in designs_result['designs']:
        design['sector'] = image_sector_map.get(design['image_id'])

    designs_result['sectors'] = sectors_result['sectors']
    return designs_result


async def _fetch_design_images(extractor: LanhuExtractor, params: dict) -> dict:
    """获取设计图列表（纯数据获取）"""
    # 构建获取设计图列表的API URL
    api_url = (
        f"https://lanhuapp.com/api/project/images"
        f"?project_id={params['project_id']}"
        f"&team_id={params['team_id']}"
        f"&dds_status=1&position=1&show_cb_src=1&comment=1"
    )

    # 发送请求
    response = await extractor.client.get(api_url)
    extractor._check_auth(response)
    response.raise_for_status()
    data = response.json()

    if data.get('code') != '00000':
        return {
            'status': 'error',
            'message': data.get('msg', 'Unknown error')
        }

    # 提取设计图信息
    project_data = data.get('data', {})
    images = project_data.get('images', [])

    from collections import Counter
    name_counter = Counter((img.get('name') or '').strip() for img in images)

    design_list = []
    for idx, img in enumerate(images, 1):
        design_name = img.get('name')
        duplicate_count = name_counter.get((design_name or '').strip(), 0)
        design_list.append({
            'index': idx,
            'id': img.get('id'),
            'image_id': str(img.get('id')) if img.get('id') is not None else None,
            'name': design_name,
            'width': img.get('width'),
            'height': img.get('height'),
            'url': img.get('url'),
            'has_comment': img.get('has_comment', False),
            'update_time': img.get('update_time'),
            'has_duplicate_name': duplicate_count > 1,
            'duplicate_name_count': duplicate_count
        })

    return {
        'status': 'success',
        'project_name': project_data.get('name'),
        'total_designs': len(design_list),
        'designs': design_list
    }


def _safe_design_filename(design_name: str, image_id: str) -> str:
    """为设计图保存生成稳定文件名，避免重名覆盖。"""
    safe_name = re.sub(r'[^\w\s-]', '_', design_name or 'design').strip() or 'design'
    safe_name = re.sub(r'\s+', '_', safe_name)
    short_id = str(image_id)[:8]
    return f"{safe_name}__{short_id}.png"


def _normalize_requested_image_ids(image_ids: Union[str, List[str]]) -> Union[str, List[str]]:
    """将 image_id 请求参数标准化。"""
    if isinstance(image_ids, str):
        if image_ids.lower() == 'all':
            return 'all'
        image_ids = [image_ids]

    normalized: List[str] = []
    for image_id in image_ids:
        if image_id is None:
            continue
        image_id_str = str(image_id).strip()
        if image_id_str and image_id_str not in normalized:
            normalized.append(image_id_str)
    return normalized


def _build_design_candidates(designs: List[dict]) -> List[dict]:
    """构建统一的设计图候选列表。"""
    return [
        {
            'image_id': design.get('image_id') or str(design.get('id')),
            'name': design.get('name'),
            'has_duplicate_name': design.get('has_duplicate_name', False),
            'duplicate_name_count': design.get('duplicate_name_count', 1)
        }
        for design in designs
    ]


async def _resolve_target_designs(
    extractor: LanhuExtractor,
    url: str,
    image_ids: Union[str, List[str]]
) -> dict:
    """按 image_id 解析目标设计图，并统一处理候选与错误。"""
    params = extractor.parse_url(url)
    designs_data = await _get_designs_internal(extractor, url)

    if designs_data.get('status') != 'success':
        return {
            'status': 'error',
            'message': designs_data.get('message', 'Failed to get designs'),
            'available_designs': []
        }

    designs = designs_data.get('designs', [])
    available_designs = _build_design_candidates(designs)
    normalized_image_ids = _normalize_requested_image_ids(image_ids)
    embedded_image_id = str(params.get('doc_id')).strip() if params.get('doc_id') else None

    if normalized_image_ids == 'all':
        return {
            'status': 'success',
            'params': params,
            'designs_data': designs_data,
            'target_designs': designs
        }

    if not normalized_image_ids:
        return {
            'status': 'error',
            'message': 'image_id 不能为空',
            'available_designs': available_designs
        }

    if embedded_image_id and embedded_image_id not in normalized_image_ids:
        return {
            'status': 'error',
            'message': f"URL 中的 image_id ({embedded_image_id}) 与请求参数不一致",
            'available_designs': available_designs
        }

    design_map = {}
    for design in designs:
        design_id = design.get('image_id') or str(design.get('id'))
        if design_id:
            design_map[str(design_id)] = design

    missing_ids = [image_id for image_id in normalized_image_ids if image_id not in design_map]
    if missing_ids:
        return {
            'status': 'error',
            'message': f"找不到 image_id 为 {', '.join(missing_ids)} 的画板",
            'requested_image_ids': normalized_image_ids,
            'available_designs': available_designs
        }

    return {
        'status': 'success',
        'params': params,
        'designs_data': designs_data,
        'target_designs': [design_map[image_id] for image_id in normalized_image_ids]
    }


@mcp.tool()
async def lanhu_get_designs(
    url: Annotated[str, "Lanhu URL WITHOUT docId (indicates UI design project, not PRD). Example: https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx. Required params: tid, pid (NO docId)"],
    ctx: Context = None
) -> dict:
    """
    [UI Design] Get Lanhu UI design image list - CALL THIS FIRST before analyzing designs
    
    USE THIS WHEN user says: UI设计图, 设计图, 设计稿, 视觉设计, UI稿, 看看设计, 帮我看设计图, 设计评审
    DO NOT USE for: 需求文档, PRD, 原型, 交互稿, Axure (use lanhu_get_pages instead)
    DO NOT USE for: 切图, 图标, 素材 (use lanhu_get_design_slices instead)
    
    Purpose: Get list of UI design images from designers. Must call this BEFORE lanhu_get_ai_analyze_design_result.
    
    Returns:
        Design image list and project metadata
    """
    extractor = LanhuExtractor()
    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)
        
        result = await _get_designs_internal(extractor, url)
        
        # Add AI suggestion when there are many designs (>8)
        if result['status'] == 'success':
            total_designs = result.get('total_designs', 0)
            if total_designs > 8:
                result['ai_suggestion'] = {
                    'notice': f'This project contains {total_designs} design images, which is quite a lot',
                    'recommendation': 'Ask user whether to download all designs or specific ones first.',
                    'user_prompt_template': f'该项目包含 {total_designs} 个设计图。请选择：\n1. 下载全部 {total_designs} 个设计图（完整查看所有UI）\n2. 下载关键设计图（请指定需要的 image_id）',
                    'language_note': 'Respond in Chinese when talking to user'
                }
        
        return result
    finally:
        await extractor.close()


@mcp.tool()
async def lanhu_get_ai_analyze_design_result(
        url: Annotated[str, "Lanhu URL WITHOUT docId (indicates UI design project). Example: https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx"],
        image_ids: Annotated[Union[str, List[str]], "Design image_id(s) to analyze. Use 'all' for all designs, single id like '123456', or list like ['123456', '789012']. Get exact image_id from lanhu_get_designs first!"],
        ctx: Context = None
) -> List[Union[str, Image]]:
    """
    [UI Design] Analyze Lanhu UI design images - GET VISUAL CONTENT
    
    USE THIS WHEN user says: UI设计图, 设计图, 设计稿, 视觉设计, UI稿, 看看设计, 帮我看设计图, 设计评审
    DO NOT USE for: 需求文档, PRD, 原型, 交互稿, Axure (use lanhu_get_ai_analyze_page_result instead)
    DO NOT USE for: 切图, 图标, 素材 (use lanhu_get_design_slices instead)
    
    WORKFLOW: First call lanhu_get_designs to get design list, then call this with exact image_id(s).
    
    Returns:
        Visual representation of UI design images
    """
    extractor = LanhuExtractor()
    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)
        
        resolved = await _resolve_target_designs(extractor, url, image_ids)
        if resolved['status'] != 'success':
            available_lines = [
                f"  • {item['name']} (image_id={item['image_id']})"
                for item in resolved.get('available_designs', [])
            ]
            message = resolved.get('message', 'Failed to resolve design targets')
            if available_lines:
                message += "\n\nAvailable designs:\n" + "\n".join(available_lines)
            return [f"⚠️ {message}"]

        params = resolved['params']
        designs_data = resolved['designs_data']
        target_designs = resolved['target_designs']

        # 设置输出目录（内部实现，自动管理）
        output_dir = DATA_DIR / 'lanhu_designs' / params['project_id']
        output_dir.mkdir(parents=True, exist_ok=True)

        # 下载设计图
        results = []
        for design in target_designs:
            try:
                # 获取原图URL（去掉OSS处理参数）
                img_url = design['url'].split('?')[0]

                # 下载图片
                response = await extractor.client.get(img_url)
                response.raise_for_status()

                # 保存文件
                filename = _safe_design_filename(design['name'], design['image_id'])
                filepath = output_dir / filename

                with open(filepath, 'wb') as f:
                    f.write(response.content)

                results.append({
                    'success': True,
                    'design_name': design['name'],
                    'image_id': design['image_id'],
                    'screenshot_path': str(filepath)
                })
            except Exception as e:
                results.append({
                    'success': False,
                    'design_name': design['name'],
                    'image_id': design.get('image_id'),
                    'error': str(e)
                })

        # Build return content
        content = []

        # Add summary text
        summary_text = f"📊 Design Download\n"
        summary_text += f"📁 Project: {designs_data['project_name']}\n"
        summary_text += f"✓ {len([r for r in results if r['success']])}/{len(results)} designs\n\n"

        # Show design list
        summary_text += "📋 Design List (display order from top to bottom):\n"
        success_results = [r for r in results if r['success']]
        for idx, r in enumerate(success_results, 1):
            summary_text += f"{idx}. {r['design_name']} (image_id={r['image_id']})\n"

        # Show failed designs
        failed_results = [r for r in results if not r['success']]
        if failed_results:
            summary_text += f"\n⚠️ Failed {len(failed_results)} designs:\n"
            for r in failed_results:
                summary_text += f"  ✗ {r['design_name']} (image_id={r.get('image_id')}): {r.get('error', 'Unknown')}\n"

        content.append(summary_text)

        # 添加成功的截图
        for r in results:
            if r['success'] and 'screenshot_path' in r:
                content.append(Image(path=r['screenshot_path']))

        return content
    finally:
        await extractor.close()


@mcp.tool()
async def lanhu_get_designs_by_sector(
        url: Annotated[str, "Lanhu URL WITHOUT docId (indicates UI design project). Example: https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx"],
        sector_name: Annotated[str, "分组名称，传 'all' 分析所有分组，或传具体名称如 '一键借款弹窗'。从 lanhu_get_designs 结果的 sectors 列表获取准确名称"],
        ctx: Context = None
) -> List[Union[str, Image]]:
    """
    [UI Design] Get Lanhu UI design images by sector/group - VIEW DESIGNS BY GROUP

    USE THIS WHEN user says: 按分组查看设计图, 某个分组的设计图, 查看分组, 设计图分组, sector
    DO NOT USE for: 需求文档, PRD, 原型, 交互稿, Axure (use lanhu_get_ai_analyze_page_result instead)
    DO NOT USE for: 切图, 图标, 素材 (use lanhu_get_design_slices instead)

    WORKFLOW: First call lanhu_get_designs to see available sectors, then call this with sector_name.

    Returns:
        Visual representation of UI design images organized by sector/group
    """
    extractor = LanhuExtractor()
    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)

        # 获取全部设计图（已含 sector 信息）
        resolved = await _resolve_target_designs(extractor, url, 'all')
        if resolved['status'] != 'success':
            return [f"⚠️ {resolved.get('message', 'Failed to get designs')}"]

        params = resolved['params']
        designs_data = resolved['designs_data']
        all_designs = resolved['target_designs']

        # 按 sector 分组
        sector_groups: dict[str, list] = {}
        for design in all_designs:
            s = design.get('sector') or '未分组'
            sector_groups.setdefault(s, []).append(design)

        available_sectors = [f"  • {name}（{len(designs)}个设计图）" for name, designs in sector_groups.items()]

        # 确定目标分组
        if sector_name == 'all':
            target_sectors = sector_groups
        else:
            # 精确匹配
            if sector_name in sector_groups:
                target_sectors = {sector_name: sector_groups[sector_name]}
            else:
                # 模糊匹配：包含关系
                matched = {k: v for k, v in sector_groups.items() if sector_name in k or k in sector_name}
                if matched:
                    target_sectors = matched
                else:
                    return [
                        f"⚠️ 找不到分组「{sector_name}」\n\n"
                        f"可用分组：\n" + "\n".join(available_sectors)
                    ]

        # 设置输出目录
        output_dir = DATA_DIR / 'lanhu_designs' / params['project_id']
        output_dir.mkdir(parents=True, exist_ok=True)

        content: List[Union[str, Image]] = []

        # 添加总览
        total_designs = sum(len(d) for d in target_sectors.values())
        summary = f"📊 Design by Sector\n"
        summary += f"📁 Project: {designs_data['project_name']}\n"
        summary += f"📂 Sectors: {len(target_sectors)} | Designs: {total_designs}\n"
        content.append(summary)

        # 按分组下载并返回
        for s_name, designs in target_sectors.items():
            content.append(f"\n=== 分组：{s_name}（{len(designs)}个设计图）===")

            for design in designs:
                try:
                    img_url = design['url'].split('?')[0]
                    response = await extractor.client.get(img_url)
                    response.raise_for_status()

                    filename = _safe_design_filename(design['name'], design['image_id'])
                    filepath = output_dir / filename

                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    content.append(Image(path=str(filepath)))
                except Exception as e:
                    content.append(f"  ⚠️ {design['name']} (image_id={design.get('image_id')}): {e}")

        return content
    finally:
        await extractor.close()


@mcp.tool()
async def lanhu_search_designs(
        url: Annotated[str, "Lanhu URL WITHOUT docId (indicates UI design project). Example: https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx"],
        keyword: Annotated[str, "搜索关键词，模糊匹配设计图名称。例如 '借款'、'首页'、'订单'"],
        ctx: Context = None
) -> List[Union[str, Image]]:
    """
    [UI Design] Search and view Lanhu UI design images by name keyword

    USE THIS WHEN user says: 搜索设计图, 查找设计图, 找一下xx的设计图, 有没有xx相关的设计, 名字包含xx的设计图
    DO NOT USE for: 需求文档, PRD, 原型, 交互稿, Axure (use lanhu_get_ai_analyze_page_result instead)
    DO NOT USE for: 切图, 图标, 素材 (use lanhu_get_design_slices instead)

    WORKFLOW: Call this directly with a keyword to search and view matching designs.

    Returns:
        Matching design images with names containing the keyword
    """
    extractor = LanhuExtractor()
    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)

        # 获取全部设计图
        resolved = await _resolve_target_designs(extractor, url, 'all')
        if resolved['status'] != 'success':
            return [f"⚠️ {resolved.get('message', 'Failed to get designs')}"]

        params = resolved['params']
        designs_data = resolved['designs_data']
        all_designs = resolved['target_designs']

        # 按关键词模糊匹配名称
        keyword_lower = keyword.lower()
        matched = [d for d in all_designs if keyword_lower in (d.get('name') or '').lower()]

        if not matched:
            # 列出所有设计图名称供参考
            all_names = sorted(set(d.get('name') or '(unnamed)' for d in all_designs))
            sample = all_names[:20]
            hint = "\n".join(f"  • {n}" for n in sample)
            more = f"\n  ... 共 {len(all_names)} 个设计图" if len(all_names) > 20 else ""
            return [f"⚠️ 没有找到名称包含「{keyword}」的设计图\n\n部分设计图名称：\n{hint}{more}"]

        # 设置输出目录
        output_dir = DATA_DIR / 'lanhu_designs' / params['project_id']
        output_dir.mkdir(parents=True, exist_ok=True)

        content: List[Union[str, Image]] = []

        # 总览
        summary = f"🔍 Search: \"{keyword}\"\n"
        summary += f"📁 Project: {designs_data['project_name']}\n"
        summary += f"✓ Found {len(matched)} matching design(s)\n\n"
        summary += "📋 Matches:\n"
        for idx, d in enumerate(matched, 1):
            sector_info = f" [{d.get('sector')}]" if d.get('sector') else ""
            summary += f"{idx}. {d['name']}{sector_info} (image_id={d['image_id']})\n"
        content.append(summary)

        # 下载并返回图片
        for design in matched:
            try:
                img_url = design['url'].split('?')[0]
                response = await extractor.client.get(img_url)
                response.raise_for_status()

                filename = _safe_design_filename(design['name'], design['image_id'])
                filepath = output_dir / filename

                with open(filepath, 'wb') as f:
                    f.write(response.content)

                content.append(Image(path=str(filepath)))
            except Exception as e:
                content.append(f"  ⚠️ {design['name']} (image_id={design.get('image_id')}): {e}")

        return content
    finally:
        await extractor.close()


@mcp.tool()
async def lanhu_get_design_annotations(
        url: Annotated[str, "Lanhu URL for design project or a board URL with image_id. Example: https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx or https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx&image_id=123456"],
        image_id: Annotated[str, "Exact design image_id. Must match the image_id returned by lanhu_get_designs."],
        ctx: Context = None
) -> dict:
    """
    [UI Design] Get structured annotations/specs for a specific Lanhu design board

    USE THIS WHEN user says: 标注, 设计规格, 文本样式, icon尺寸, 图层信息, 设计说明, 样式明细
    DO NOT USE for: 需求文档, PRD, 原型 (use lanhu_get_pages instead)
    DO NOT USE for: 直接看设计图 (use lanhu_get_ai_analyze_design_result instead)

    WORKFLOW: First call lanhu_get_designs to get design list, then call this with exact image_id.

    Returns:
        Structured annotations with full layer specs for the selected board.
        Geometry, typography dimensions, and spacing measurements are converted to integer dp
        using round(px * 411 / 750), and measurements include nearest-neighbor/icon-text/container padding info.
    """
    extractor = LanhuExtractor()
    try:
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)

        resolved = await _resolve_target_designs(extractor, url, image_id)
        if resolved['status'] != 'success':
            return resolved

        params = resolved['params']
        target_design = resolved['target_designs'][0]
        annotations = await extractor.get_design_annotations_info(
            image_id=target_design['image_id'],
            team_id=params['team_id'],
            project_id=params['project_id']
        )
        annotations['requested_image_id'] = str(image_id)
        return annotations
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    finally:
        await extractor.close()


@mcp.tool()
async def lanhu_get_design_slices(
        url: Annotated[str, "Lanhu URL WITHOUT docId (indicates UI design project). Example: https://lanhuapp.com/web/#/item/project/stage?tid=xxx&pid=xxx"],
        image_id: Annotated[str, "Exact design image_id (single board only, NOT 'all'). Example: '123456'. Must match the image_id from lanhu_get_designs."],
        include_metadata: Annotated[bool, "Include color, opacity, shadow info"] = True,
        ctx: Context = None
) -> dict:
    """
    [UI Slices/Assets] Get slice/asset info from Lanhu design for download
    
    USE THIS WHEN user says: 切图, 下载切图, 图标, icon, 素材, 资源, 导出切图, 下载素材, 获取图标
    DO NOT USE for: 需求文档, PRD, 原型 (use lanhu_get_pages instead)
    DO NOT USE for: 看设计图, 设计评审 (use lanhu_get_designs instead)
    
    WORKFLOW: First call lanhu_get_designs to get design list, then call this with exact image_id to get slices from a specific board.
    
    Returns:
        Slice list with download URLs, AI will handle smart naming and batch download
    """
    extractor = LanhuExtractor()
    try:
        # 记录协作者
        user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
        project_id = get_project_id_from_url(url)
        if project_id:
            store = MessageStore(project_id)
            store.record_collaborator(user_name, user_role)
        
        resolved = await _resolve_target_designs(extractor, url, image_id)
        if resolved['status'] != 'success':
            return resolved

        params = resolved['params']
        target_design = resolved['target_designs'][0]

        slices_data = await extractor.get_design_slices_info(
            image_id=target_design['image_id'],
            team_id=params['team_id'],
            project_id=params['project_id'],
            include_metadata=include_metadata
        )

        # 5. Add AI workflow guide
        ai_workflow_guide = {
            "instructions": "🤖 AI assistant must follow this workflow to process slice download tasks",
            "language_requirement": "⚠️ IMPORTANT: Always respond to user in Chinese (中文回复)",
            "workflow_steps": [
                {
                    "step": 1,
                    "title": "Create TODO Task Plan",
                    "tasks": [
                        "Analyze project structure (read package.json, pom.xml, requirements.txt, etc.)",
                        "Identify project type (React/Vue/Flutter/iOS/Android/Plain Frontend, etc.)",
                        "Determine slice storage directory (e.g., src/assets/images/)",
                        "Plan slice grouping strategy (by feature module, UI component, etc.)"
                    ]
                },
                {
                    "step": 2,
                    "title": "Smart Directory Selection Rules",
                    "rules": [
                        "Priority 1: If user explicitly specified output_dir → use user-specified path",
                        "Priority 2: If project has standard assets directory → use project convention (e.g., src/assets/images/slices/)",
                        "Priority 3: If generic project → use design_slices/{design_name}/"
                    ],
                    "common_project_structures": {
                        "React/Vue": ["src/assets/", "public/images/"],
                        "Flutter": ["assets/images/"],
                        "iOS": ["Assets.xcassets/"],
                        "Android": ["res/drawable/", "res/mipmap/"],
                        "Plain Frontend": ["images/", "assets/"]
                    }
                },
                {
                    "step": 3,
                    "title": "Smart Naming Strategy",
                    "description": "Generate semantic filenames based on layer_path, parent_name, size",
                    "examples": [
                        {
                            "layer_path": "TopStatusBar/Battery/Border",
                            "size": "26x14",
                            "suggested_name": "status_bar_battery_border_26x14.png"
                        },
                        {
                            "layer_path": "Button/Background",
                            "size": "200x50",
                            "suggested_name": "button_background_200x50.png"
                        }
                    ],
                    "naming_patterns": {
                        "icons": "icon_xxx.png",
                        "backgrounds": "bg_xxx.png",
                        "buttons": "btn_xxx.png"
                    }
                },
                {
                    "step": 4,
                    "title": "Environment Detection and Download Solution Selection",
                    "principle": "AI must first detect current system environment and available tools, then autonomously select the best download solution",
                    "priority_rules": [
                        "Priority 1: Use system built-in download tools (curl/PowerShell/wget, etc.)",
                        "Priority 2: If system tools unavailable, detect programming language environment (python/node, etc.)",
                        "Priority 3: Create temporary script as last resort"
                    ],
                    "detection_steps": [
                        "Step 1: Detect operating system type (Windows/macOS/Linux)",
                        "Step 2: Sequentially detect available download tools",
                        "Step 3: Autonomously select optimal solution based on detection results",
                        "Step 4: Execute download task",
                        "Step 5: Clean up temporary files (if any)"
                    ],
                    "common_tools_by_platform": {
                        "Windows": {
                            "built_in": ["PowerShell Invoke-WebRequest", "certutil"],
                            "optional": ["curl (Win10 1803+ built-in)", "python", "node"]
                        },
                        "macOS": {
                            "built_in": ["curl"],
                            "optional": ["python", "wget", "node"]
                        },
                        "Linux": {
                            "built_in": ["curl", "wget"],
                            "optional": ["python", "node"]
                        }
                    },
                    "important_principles": [
                        "⚠️ Do not assume any tool is available, must detect first",
                        "⚠️ Prefer system built-in tools, avoid third-party dependencies",
                        "⚠️ Do not use fixed code templates or example code",
                        "⚠️ Dynamically generate commands or scripts based on actual environment",
                        "⚠️ Control concurrency when batch downloading",
                        "⚠️ Must clean up temporary files after completion"
                    ]
                }
            ],
            "execution_workflow": {
                "description": "Complete workflow that AI must autonomously complete",
                "steps": [
                    "Step 1: Call lanhu_get_design_slices(url, image_id) to get slice info",
                    "Step 2: Create TODO task plan (use todo_write tool)",
                    "Step 3: Detect current operating system type",
                    "Step 4: Detect available download tools by priority",
                    "Step 5: Identify project type and determine output directory",
                    "Step 6: Generate smart filenames based on slice info",
                    "Step 7: Select optimal download solution based on detection results",
                    "Step 8: Execute batch download task",
                    "Step 9: Verify download results",
                    "Step 10: Clean up temporary files and complete TODO"
                ]
            },
            "important_notes": [
                "🎯 AI must proactively complete the entire workflow, don't just return info and wait for user action",
                "📋 AI must use todo_write tool to create task plan, ensure orderly progress",
                "🔍 AI must detect environment and tool availability first, then select download solution",
                "⭐ AI must prefer system built-in tools, avoid third-party dependencies",
                "🚫 AI must not use fixed code examples, must dynamically generate commands based on actual environment",
                "✨ AI must smartly select output directory based on project structure, don't blindly use default path",
                "🏷️ AI must generate semantic filenames based on slice's layer_path and parent_name",
                "💻 AI must select corresponding download tools for different OS (Windows/macOS/Linux)",
                "🧹 AI must clean up temporary files after completion (if any)",
                "🗣️ AI must always respond to user in Chinese (中文回复)"
            ]
        }

        return {
            'status': 'success',
            'requested_image_id': str(image_id),
            **slices_data,
            'ai_workflow_guide': ai_workflow_guide
        }

    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }
    finally:
        await extractor.close()


# ==================== 团队留言板功能 ====================

@mcp.tool()
async def lanhu_say(
        url: Annotated[str, "蓝湖URL（含tid和pid）。例: https://lanhuapp.com/web/#/item/project/product?tid=xxx&pid=xxx&docId=xxx。会自动提取项目和文档信息"],
        summary: Annotated[str, "留言标题/概要"],
        content: Annotated[str, "留言详细内容"],
        mentions: Annotated[Optional[List[str]], "⚠️@提醒人名。必须是具体人名，例如: 张三/李四/王五/赵六等。禁止使用角色名(后端/前端等)！"] = None,
        message_type: Annotated[Optional[str], "留言类型。可选: normal(普通留言), task(查询任务-仅限查询操作,禁止修改代码), question(需要回答的问题), urgent(紧急通知), knowledge(知识库-长期保存的经验知识)。默认: normal"] = None,
        ctx: Context = None
) -> dict:
    """
    Post message to team message board
    
    USE THIS WHEN user says: 有话说, 留言, 发消息, 通知团队, 告诉xxx, @张三, @李四, 共享给xxx, 分享给xxx, 发给xxx, 写给xxx, 转发给xxx
    
    Message type description:
    - normal: Normal message/notification (default)
    - task: Query task - Only for query operations (query code, query database, query TODO, etc.), NO code modification
    - question: Question message - Needs answer from others
    - urgent: Urgent message - Needs immediate attention
    - knowledge: Knowledge base - Long-term preserved experience, pitfalls, notes, best practices
    
    Security restrictions:
    task type can only be used for query operations, including:
    - Query code location, code logic
    - Query database table structure, data
    - Query test methods, test coverage
    - Query TODO, comments
    - Forbidden: Modify code, delete files, execute commands, commit code
    
    Knowledge use cases:
    - Pitfalls encountered and solutions
    - Testing notes
    - Development experience and best practices
    - Common FAQ
    - Technical decision records
    
    Purpose: Post message to project message board, can @ specific person to send Feishu notification
    
    Returns:
        Post result, including message ID and details
    """
    # 获取用户信息
    user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
    
    # 获取project_id
    project_id = get_project_id_from_url(url)
    if not project_id:
        return {"status": "error", "message": "无法从URL解析project_id"}
    
    # 获取元数据（自动，带缓存）
    metadata = await _fetch_metadata_from_url(url)
    
    # 验证message_type
    valid_types = ['normal', 'task', 'question', 'urgent', 'knowledge']
    if message_type and message_type not in valid_types:
        return {
            "status": "error",
            "message": f"无效的留言类型: {message_type}",
            "valid_types": valid_types
        }
    
    # 默认为normal
    if not message_type:
        message_type = 'normal'
    
    # 验证mentions（只能@具体人名）
    if mentions:
        invalid_names = [name for name in mentions if name not in MENTION_ROLES]
        if invalid_names:
            return {
                "status": "error", 
                "message": f"无效的人名: {invalid_names}。只能@具体人名，不能使用角色名！",
                "valid_names": MENTION_ROLES
            }
    
    # 保存消息
    store = MessageStore(project_id)
    store.record_collaborator(user_name, user_role)
    
    # 保存项目元数据到store（如果首次获取到）
    if metadata.get('project_name') and not store._data.get('project_name'):
        store._data['project_name'] = metadata['project_name']
    if metadata.get('folder_name') and not store._data.get('folder_name'):
        store._data['folder_name'] = metadata['folder_name']
    store._save()
    
    message = store.save_message(
        summary=summary,
        content=content,
        author_name=user_name,
        author_role=user_role,
        mentions=mentions or [],
        message_type=message_type,  # 新增：留言类型
        # 标准元数据（10个字段）
        project_name=metadata.get('project_name'),
        folder_name=metadata.get('folder_name'),
        doc_id=metadata.get('doc_id'),
        doc_name=metadata.get('doc_name'),
        doc_type=metadata.get('doc_type'),
        doc_version=metadata.get('doc_version'),
        doc_updated_at=metadata.get('doc_updated_at'),
        doc_url=metadata.get('doc_url')
    )
    
    # 发送飞书通知（无论是否@人都发送）
    try:
        await send_feishu_notification(
            summary=summary,
            content=content,
            author_name=user_name,
            author_role=user_role,
            mentions=mentions or [],
            message_type=message_type,
            project_name=metadata.get('project_name'),
            doc_name=metadata.get('doc_name'),
            doc_url=metadata.get('doc_url')
        )
    except Exception as e:
        # 飞书通知失败不影响留言发布
        print(f"⚠️ 飞书通知发送失败（不影响留言发布）: {e}")
    
    return {
        "status": "success",
        "message": "留言发布成功",
        "data": {
            "id": message["id"],
            "summary": message["summary"],
            "message_type": message["message_type"],  # 新增：留言类型
            "mentions": message["mentions"],
            "author_name": message["author_name"],
            "author_role": message["author_role"],
            "created_at": message["created_at"],
            # 完整的10个元数据字段
            "project_id": project_id,
            "project_name": message.get("project_name"),
            "folder_name": message.get("folder_name"),
            "doc_id": message.get("doc_id"),
            "doc_name": message.get("doc_name"),
            "doc_type": message.get("doc_type"),
            "doc_version": message.get("doc_version"),
            "doc_updated_at": message.get("doc_updated_at"),
            "doc_url": message.get("doc_url")
        }
    }


@mcp.tool()
async def lanhu_say_list(
    url: Annotated[Optional[str], "蓝湖URL或'all'。不传或传'all'=查询所有项目；传具体URL=查询单个项目"] = None,
    filter_type: Annotated[Optional[str], "筛选留言类型: normal/task/question/urgent/knowledge。不传则返回所有类型"] = None,
    search_regex: Annotated[Optional[str], "正则表达式搜索（在summary和content中匹配）。例: '测试|退款|坑'。建议使用以避免返回过多消息"] = None,
    limit: Annotated[Any, "限制返回消息数量（防止上下文爆炸）。不传则不限制"] = None,
    ctx: Context = None
) -> dict:
    """
    Get message list with filtering and search
    
    USE THIS WHEN user says: 查看留言, 有什么消息, 谁@我了, 留言列表, 消息列表
    
    Supports two modes:
    1. Provide specific URL: Query messages in that project
    2. url='all' or url=None: Query messages in all projects (global mode)
    
    Important: To prevent AI context overflow, it is recommended:
    1. Use filter_type to filter by type
    2. Use search_regex for further filtering (regex, AI can generate itself)
    3. Use limit to limit the number of returned messages
    4. Unless user explicitly requests "view all", filters must be used
    
    Example:
    - Query all knowledge: filter_type="knowledge"
    - Search containing "test" or "refund": search_regex="test|refund"
    - Query tasks and containing "database": filter_type="task", search_regex="database"
    - Limit to 10 latest: limit=10
    
    Purpose: Get message board message summary list, supports type filtering, regex search and quantity limit
    
    Returns:
        Message list, including mentions_me count
    """
    # 获取用户信息
    user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
    
    # 验证filter_type
    if filter_type:
        valid_types = ['normal', 'task', 'question', 'urgent', 'knowledge']
        if filter_type not in valid_types:
            return {
                "status": "error",
                "message": f"无效的类型: {filter_type}",
                "valid_types": valid_types
            }
    
    # 编译正则表达式（如果提供）
    import re
    regex_pattern = None
    if search_regex:
        try:
            regex_pattern = re.compile(search_regex, re.IGNORECASE)
        except re.error as e:
            return {
                "status": "error",
                "message": f"无效的正则表达式: {search_regex}",
                "error": str(e)
            }
    
    # 处理limit参数 - 自动转换为整数
    if limit is not None:
        try:
            limit = int(limit)
            if limit <= 0:
                return {"status": "error", "message": "limit 必须是正整数"}
        except (ValueError, TypeError):
            return {"status": "error", "message": f"limit 类型错误，期望整数，实际类型: {type(limit).__name__}"}
    
    # 全局查询模式
    if not url or url.lower() == 'all':
        store = MessageStore(project_id=None)
        groups = store.get_all_messages_grouped(user_role=user_role, user_name=user_name)
        
        # 应用筛选和搜索
        filtered_groups = []
        total_messages_before_filter = sum(g['message_count'] for g in groups)
        
        for group in groups:
            filtered_messages = []
            for msg in group['messages']:
                # 类型筛选
                if filter_type and msg.get('message_type') != filter_type:
                    continue
                
                # 正则搜索
                if regex_pattern:
                    text = f"{msg.get('summary', '')} {msg.get('content', '')}"
                    if not regex_pattern.search(text):
                        continue
                
                filtered_messages.append(msg)
            
            # 如果该组有匹配的消息
            if filtered_messages:
                group_copy = group.copy()
                group_copy['messages'] = filtered_messages
                group_copy['message_count'] = len(filtered_messages)
                group_copy['mentions_me_count'] = sum(1 for m in filtered_messages if m.get('mentions_me'))
                filtered_groups.append(group_copy)
        
        # 应用limit（限制消息总数）
        if limit and limit > 0:
            limited_groups = []
            remaining_limit = limit
            for group in filtered_groups:
                if remaining_limit <= 0:
                    break
                group_copy = group.copy()
                group_copy['messages'] = group['messages'][:remaining_limit]
                group_copy['message_count'] = len(group_copy['messages'])
                limited_groups.append(group_copy)
                remaining_limit -= group_copy['message_count']
            filtered_groups = limited_groups
        
        # 统计
        total_messages = sum(g['message_count'] for g in filtered_groups)
        total_mentions_me = sum(g['mentions_me_count'] for g in filtered_groups)
        total_projects = len(set(g.get('project_id') for g in filtered_groups if g.get('project_id')))
        
        # 检查是否需要警告（无筛选且消息过多）
        warning_message = None
        if not filter_type and not search_regex and not limit and total_messages_before_filter > 100:
            warning_message = f"⚠️ 发现{total_messages_before_filter}条留言，建议使用筛选条件避免上下文溢出。使用 filter_type 或 search_regex 或 limit 参数"
        
        result = {
            "status": "success",
            "mode": "global",
            "current_user": {"name": user_name, "role": user_role},
            "total_messages": total_messages,
            "total_groups": len(filtered_groups),
            "total_projects": total_projects,
            "mentions_me_count": total_mentions_me,
            "groups": filtered_groups
        }
        
        if warning_message:
            result["warning"] = warning_message
        
        if filter_type or search_regex:
            result["filter_info"] = {
                "filter_type": filter_type,
                "search_regex": search_regex,
                "total_before_filter": total_messages_before_filter,
                "total_after_filter": total_messages
            }
        
        return result
    
    # 单项目查询模式
    project_id = get_project_id_from_url(url)
    if not project_id:
        return {"status": "error", "message": "无法从URL解析project_id"}
    
    # 获取消息列表
    store = MessageStore(project_id)
    store.record_collaborator(user_name, user_role)
    messages = store.get_messages(user_role=user_role)
    
    # 应用筛选和搜索
    total_messages_before_filter = len(messages)
    filtered_messages = []
    
    for msg in messages:
        # 类型筛选
        if filter_type and msg.get('message_type') != filter_type:
            continue
        
        # 正则搜索
        if regex_pattern:
            text = f"{msg.get('summary', '')} {msg.get('content', '')}"
            if not regex_pattern.search(text):
                continue
        
        filtered_messages.append(msg)
    
    # 应用limit
    if limit and limit > 0:
        filtered_messages = filtered_messages[:limit]
    
    # 统计@自己的消息数
    mentions_me_count = sum(1 for msg in filtered_messages if msg.get("mentions_me"))
    
    # 按文档分组（减少token）
    from collections import defaultdict
    groups_dict = defaultdict(list)
    
    for msg in filtered_messages:
        doc_id = msg.get('doc_id', 'no_doc')
        groups_dict[doc_id].append(msg)
    
    # 构建分组结果
    groups = []
    meta_fields = {
        'project_id', 'project_name', 'folder_name',
        'doc_id', 'doc_name', 'doc_type', 'doc_version',
        'doc_updated_at', 'doc_url'
    }
    
    for doc_id, doc_messages in groups_dict.items():
        if not doc_messages:
            continue
        
        # 提取元数据（组内共享）
        first_msg = doc_messages[0]
        
        group = {
            # 元数据（只出现一次）
            "doc_id": first_msg.get('doc_id'),
            "doc_name": first_msg.get('doc_name'),
            "doc_type": first_msg.get('doc_type'),
            "doc_version": first_msg.get('doc_version'),
            "doc_updated_at": first_msg.get('doc_updated_at'),
            "doc_url": first_msg.get('doc_url'),
            
            # 统计
            "message_count": len(doc_messages),
            "mentions_me_count": sum(1 for m in doc_messages if m.get("mentions_me")),
            
            # 精简消息列表（移除元数据）
            "messages": [_clean_message_dict({k: v for k, v in m.items() if k not in meta_fields}, user_name) for m in doc_messages]
        }
        
        groups.append(group)
    
    # 按组内最新消息时间排序
    groups.sort(
        key=lambda g: max((m.get('created_at', '') for m in g['messages']), default=''),
        reverse=True
    )
    
    # 检查是否需要警告
    warning_message = None
    if not filter_type and not search_regex and not limit and total_messages_before_filter > 50:
        warning_message = f"⚠️ 该项目有{total_messages_before_filter}条留言，建议使用筛选条件避免上下文溢出"
    
    result = {
        "status": "success",
        "mode": "single_project",
        "project_id": project_id,
        "project_name": store._data.get('project_name'),
        "folder_name": store._data.get('folder_name'),
        "current_user": {"name": user_name, "role": user_role},
        "total_messages": len(filtered_messages),
        "total_groups": len(groups),
        "mentions_me_count": mentions_me_count,
        "groups": groups
    }
    
    if warning_message:
        result["warning"] = warning_message
    
    if filter_type or search_regex:
        result["filter_info"] = {
            "filter_type": filter_type,
            "search_regex": search_regex,
            "total_before_filter": total_messages_before_filter,
            "total_after_filter": len(filtered_messages)
        }
    
    return result


@mcp.tool()
async def lanhu_say_detail(
        message_ids: Annotated[Any, "消息ID。单个数字或数组。例: 1 或 [1,2,3]"],
        url: Annotated[Optional[str], "蓝湖URL。传URL则自动解析项目ID；不传则需手动提供project_id参数"] = None,
        project_id: Annotated[Optional[str], "项目ID。仅在不传url时需要，用于全局查询模式"] = None,
        ctx: Context = None
) -> dict:
    """
    Get message detail (supports batch query)
    
    USE THIS WHEN user says: 查看详情, 看看内容, 详细内容, 消息详情
    
    Two modes:
    1. Provide url: Parse project_id from url, query messages in that project
    2. url='all'/None + project_id: Global mode, need to manually specify project_id
    
    Purpose: Get full content of messages by message ID
    
    Returns:
        Message detail list with full content
    """
    # 获取用户信息
    user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
    
    # 确定project_id
    if url and url.lower() != 'all':
        target_project_id = get_project_id_from_url(url)
    elif project_id:
        target_project_id = project_id
    else:
        return {"status": "error", "message": "请提供url或project_id"}
    
    if not target_project_id:
        return {"status": "error", "message": "无法获取project_id"}
    
    # 处理message_ids参数 - 自动转换单个数字为数组
    if isinstance(message_ids, (int, float)):
        message_ids = [int(message_ids)]
    elif isinstance(message_ids, list):
        # 确保列表中的元素都是整数
        try:
            message_ids = [int(mid) for mid in message_ids]
        except (ValueError, TypeError):
            return {"status": "error", "message": "message_ids 必须是整数或整数数组"}
    else:
        return {"status": "error", "message": f"message_ids 类型错误，期望整数或数组，实际类型: {type(message_ids).__name__}"}
    
    # 获取消息详情
    store = MessageStore(target_project_id)
    store.record_collaborator(user_name, user_role)
    
    messages = []
    not_found = []
    
    for msg_id in message_ids:
        msg = store.get_message_by_id(msg_id, user_role=user_role)
        if msg:
            messages.append(msg)
        else:
            not_found.append(msg_id)
    
    return {
        "status": "success",
        "total": len(messages),
        "messages": messages,
        "not_found": not_found
    }


@mcp.tool()
async def lanhu_say_edit(
        url: Annotated[str, "蓝湖URL（含tid和pid）"],
        message_id: Annotated[Any, "要编辑的消息ID"],
        summary: Annotated[Optional[str], "新标题（可选，不传则不修改）"] = None,
        content: Annotated[Optional[str], "新内容（可选，不传则不修改）"] = None,
        mentions: Annotated[Optional[List[str]], "新@列表（可选，不传则不修改）"] = None,
        ctx: Context = None
) -> dict:
    """
    Edit message
    
    USE THIS WHEN user says: 编辑留言, 修改消息, 更新内容
    
    Purpose: Edit published message, will record editor and edit time
    
    Returns:
        Updated message details
    """
    # 获取用户信息
    user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
    
    # 获取project_id
    project_id = get_project_id_from_url(url)
    if not project_id:
        return {"status": "error", "message": "无法从URL解析project_id"}
    
    # 处理message_id参数 - 自动转换为整数
    try:
        message_id = int(message_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": f"message_id 类型错误，期望整数，实际类型: {type(message_id).__name__}"}
    
    # 验证mentions（只能@具体人名）
    if mentions:
        invalid_names = [name for name in mentions if name not in MENTION_ROLES]
        if invalid_names:
            return {
                "status": "error", 
                "message": f"无效的人名: {invalid_names}。只能@具体人名，不能使用角色名！",
                "valid_names": MENTION_ROLES
            }
    
    # 检查是否有更新内容
    if summary is None and content is None and mentions is None:
        return {"status": "error", "message": "请至少提供一个要更新的字段"}
    
    # 更新消息
    store = MessageStore(project_id)
    store.record_collaborator(user_name, user_role)
    
    updated_msg = store.update_message(
        msg_id=message_id,
        editor_name=user_name,
        editor_role=user_role,
        summary=summary,
        content=content,
        mentions=mentions
    )
    
    if not updated_msg:
        return {"status": "error", "message": "消息不存在", "message_id": message_id}
    
    # 发送飞书编辑通知
    try:
        # 获取元数据
        metadata = await _fetch_metadata_from_url(url)
        
        await send_feishu_notification(
            summary=f"🔄 [已编辑] {updated_msg.get('summary', '')}",
            content=updated_msg.get('content', ''),
            author_name=f"{user_name}(编辑)",
            author_role=user_role,
            mentions=updated_msg.get('mentions', []),
            message_type=updated_msg.get('message_type', 'normal'),
            project_name=metadata.get('project_name'),
            doc_name=metadata.get('doc_name'),
            doc_url=metadata.get('doc_url')
        )
    except Exception as e:
        print(f"⚠️ 飞书编辑通知发送失败（不影响编辑）: {e}")
    
    return {
        "status": "success",
        "message": "消息更新成功",
        "data": updated_msg
    }


@mcp.tool()
async def lanhu_say_delete(
        url: Annotated[str, "蓝湖URL（含tid和pid）"],
        message_id: Annotated[Any, "要删除的消息ID"],
        ctx: Context = None
) -> dict:
    """
    Delete message
    
    USE THIS WHEN user says: 删除留言, 删除消息, 移除
    
    Purpose: Delete published message
    
    Returns:
        Delete result
    """
    # 获取用户信息
    user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
    
    # 获取project_id
    project_id = get_project_id_from_url(url)
    if not project_id:
        return {"status": "error", "message": "无法从URL解析project_id"}
    
    # 处理message_id参数 - 自动转换为整数
    try:
        message_id = int(message_id)
    except (ValueError, TypeError):
        return {"status": "error", "message": f"message_id 类型错误，期望整数，实际类型: {type(message_id).__name__}"}
    
    # 删除消息
    store = MessageStore(project_id)
    store.record_collaborator(user_name, user_role)
    
    success = store.delete_message(message_id)
    
    if not success:
        return {"status": "error", "message": "消息不存在", "message_id": message_id}
    
    return {
        "status": "success",
        "message": "消息删除成功",
        "deleted_id": message_id,
        "deleted_by_name": user_name,
        "deleted_by_role": user_role
    }


@mcp.tool()
async def lanhu_get_members(
    url: Annotated[str, "蓝湖URL（含tid和pid）"],
    ctx: Context = None
) -> dict:
    """
    Get project collaborators list
    
    USE THIS WHEN user says: 谁参与了, 协作者, 团队成员, 有哪些人
    
    Purpose: Get list of team members who have used Lanhu MCP tools to access this project
    
    Returns:
        Collaborator list with first and last access time
    """
    # 获取用户信息
    user_name, user_role = get_user_info(ctx) if ctx else ('匿名', '未知')
    
    # 获取project_id
    project_id = get_project_id_from_url(url)
    if not project_id:
        return {"status": "error", "message": "无法从URL解析project_id"}
    
    # 获取协作者列表
    store = MessageStore(project_id)
    store.record_collaborator(user_name, user_role)
    collaborators = store.get_collaborators()
    
    return {
        "status": "success",
        "project_id": project_id,
        "total": len(collaborators),
        "collaborators": collaborators
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
