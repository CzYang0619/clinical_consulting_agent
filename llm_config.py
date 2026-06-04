"""
LLM 配置与初始化
支持 OpenAI 兼容接口（包括通义千问、Claude 等）
"""
import os
from typing import Optional
from langchain_openai import ChatOpenAI
from pydantic import BaseModel


def initialize_llm(
    model_name: str = "qwen-max-latest",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.2,
    top_p: float = 0.3,
) -> ChatOpenAI:
    """
    初始化 LLM 客户端
    
    Args:
        model_name: 模型名称（默认为通义千问）
        api_key: API Key（若不提供则从环境变量读取）
        base_url: API 基础 URL（若不提供则从环境变量读取）
        temperature: 温度参数
        top_p: top_p 参数
    
    Returns:
        ChatOpenAI 实例
    """
    global _global_llm
    
    # 从环境变量读取默认配置
    api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("TONGYI_API_KEY")
    base_url = base_url or os.getenv("OPENAI_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    
    if not api_key:
        raise ValueError(
            "API Key 未设置！请设置环境变量 OPENAI_API_KEY/TONGYI_API_KEY "
            "或直接在函数参数中传入 api_key"
        )
    
    _global_llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        top_p=top_p,
    )
    return _global_llm


# 全局 LLM 实例（延迟初始化）
_global_llm: Optional[ChatOpenAI] = None


def get_llm(
    model_name: str = "qwen-max-latest",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ChatOpenAI:
    """
    获取全局 LLM 实例（单例模式）
    """
    global _global_llm
    if _global_llm is None:
        _global_llm = initialize_llm(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url
        )
    return _global_llm


def reset_llm():
    """重置 LLM 实例"""
    global _global_llm
    _global_llm = None
