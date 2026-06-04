"""
数据结构定义 - 使用 Pydantic 确保类型安全和序列化
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class PatientBaselineInfo(BaseModel):
    """患者基础信息提取结果"""
    std_gender: Literal["M", "F", "UNK"] = Field(default="UNK", description="性别标准化")
    std_history: str = Field(default="未提供（待补充）", description="既往史")
    age: int = Field(default=0, ge=0, description="年龄")
    chief_complaint: str = Field(description="主诉")


class InitialConsultationExtraction(BaseModel):
    """初诊信息提取 - LLM 输出"""
    std_gender: Optional[str] = Field(default=None, description="性别")
    std_history: Optional[str] = Field(default=None, description="既往史")
    missing_msg: Optional[str] = Field(default=None, description="缺失维度追问")
    age: Optional[int] = Field(default=None, description="年龄")
    chief_complaint: str = Field(description="主诉")


class DataValidationResult(BaseModel):
    """数据治理后的验证结果"""
    status: Literal["complete", "incomplete", "error"] = Field(description="数据完整性状态")
    missing_msg: str = Field(description="缺失项或完成标记")
    std_gender: str = Field(description="标准化性别")
    std_history: str = Field(description="标准化既往史")
    chief_complaint: str = Field(description="主诉")
    age: int = Field(description="年龄")


class ClinicalDecisionReport(BaseModel):
    """临床决策与科研初筛报告"""
    summary: str = Field(description="临床决策端摘要")
    ct_recommendation: str = Field(description="临床试验初筛结论")
    department_guide: str = Field(description="患者就诊指引")


class FollowupConsultationExtraction(BaseModel):
    """复诊信息提取 - LLM 输出"""
    target_medication: Optional[str] = Field(default=None, description="目标药物/疾病")
    recent_metrics: Optional[str] = Field(default=None, description="近期指标")
    missing_msg: Optional[str] = Field(default=None, description="缺失项追问")


class FollowupDataValidationResult(BaseModel):
    """复诊数据治理结果"""
    target_medication: str = Field(description="目标药物/疾病")
    recent_metrics: str = Field(description="近期指标")
    missing_msg: str = Field(description="缺失项追问或空")


# =================== 工作流状态对象 ===================

class ConsultationState(BaseModel):
    """整个咨询流程的状态对象"""
    # 基础信息
    user_query: str = Field(description="用户输入的原始问诊")
    query_classification: Optional[str] = Field(
        default=None, 
        description="导诊分类结果：critical, non_business, initial, followup"
    )
    
    # 初诊分支数据
    initial_extraction: Optional[InitialConsultationExtraction] = Field(
        default=None,
        description="初诊信息提取结果"
    )
    initial_validation: Optional[DataValidationResult] = Field(
        default=None,
        description="初诊数据验证结果"
    )
    
    # 复诊分支数据
    followup_extraction: Optional[FollowupConsultationExtraction] = Field(
        default=None,
        description="复诊信息提取结果"
    )
    followup_validation: Optional[FollowupDataValidationResult] = Field(
        default=None,
        description="复诊数据验证结果"
    )
    
    # 最终输出
    final_response: str = Field(default="", description="最终返回给用户的响应")
    
    # 元数据
    turn_count: int = Field(default=1, ge=1, description="对话轮数")
    requires_followup: bool = Field(default=False, description="是否需要继续追问")
    is_conversation_ended: bool = Field(default=False, description="对话是否已结束")
    
    # 🔄【新增】历史对话记录 - 用于多轮上下文维护
    conversation_history: List[dict] = Field(
        default_factory=list,
        description="历史对话列表，每项包含 {turn, role, content}"
    )
    accumulated_chief_complaint: Optional[str] = Field(
        default=None,
        description="累积的主诉信息（跨轮次合并）"
    )

    # 🔄【新增】追问止盈：记录已经问过的维度，避免重复追问
    asked_slots: List[str] = Field(
        default_factory=list,
        description="已追问的维度标记，如 ['pmh', 'allergy', 'inducement', 'associated', 'medication', 'metrics']"
    )


class QuestionClassificationResult(BaseModel):
    """问题分类结果"""
    classification: Literal["1", "2", "3", "4"] = Field(
        description="分类类别：1=急危重症, 2=初诊/复杂症状, 3=慢病复诊/续方, 4=非业务"
    )
    confidence: float = Field(ge=0, le=1, description="分类置信度")
    reasoning: str = Field(description="分类推理")
