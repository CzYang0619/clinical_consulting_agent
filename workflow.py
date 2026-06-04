"""
LangGraph 工作流图定义
实现完整的预问诊 Agent 路由逻辑
"""
from typing import Any
from langgraph.graph import StateGraph, END
from schemas import ConsultationState
from nodes import (
    node_question_classifier,
    # 初诊分支
    node_initial_extraction,
    node_initial_data_validation,
    router_initial_completeness,
    node_initial_followup_question,
    node_initial_decision_report,
    # 复诊分支
    node_followup_extraction,
    node_followup_data_validation,
    router_followup_completeness,
    node_followup_incomplete,
    node_followup_complete,
    # 紧急和非业务
    node_critical_response,
    node_non_business_response,
)


def create_consultation_graph() -> Any:
    """
    构建预问诊咨询工作流图
    
    工作流结构：
    1. 导诊预过滤 -> 分流到 4 个分支
    2. 初诊分支：提取 -> 验证 -> 判定完整性 -> 追问/生成报告
    3. 复诊分支：提取 -> 验证 -> 判定完整性 -> 追问/确认凭证
    4. 紧急分支：直接输出紧急提示
    5. 非业务分支：直接输出提示
    """
    workflow = StateGraph(ConsultationState)
    
    # =================== 添加节点 ===================
    
    # 第一层：导诊预过滤
    workflow.add_node("question_classifier", node_question_classifier)
    
    # 初诊分支：第二层
    workflow.add_node("initial_extraction", node_initial_extraction)
    
    # 初诊分支：第三层（数据治理）
    workflow.add_node("initial_data_validation", node_initial_data_validation)
    
    # 初诊分支：信息不完整 - 追问
    workflow.add_node("initial_followup_question", node_initial_followup_question)
    
    # 初诊分支：信息完整 - 生成报告
    workflow.add_node("initial_decision_report", node_initial_decision_report)
    
    # 复诊分支：第二层
    workflow.add_node("followup_extraction", node_followup_extraction)
    
    # 复诊分支：第三层（数据治理）
    workflow.add_node("followup_data_validation", node_followup_data_validation)
    
    # 复诊分支：信息不完整 - 追问
    workflow.add_node("followup_incomplete", node_followup_incomplete)
    
    # 复诊分支：信息完整 - 续方凭证
    workflow.add_node("followup_complete", node_followup_complete)
    
    # 紧急和非业务分支
    workflow.add_node("critical_response", node_critical_response)
    workflow.add_node("non_business_response", node_non_business_response)
    
    # =================== 配置边（路由关系） ===================
    
    # 起点 -> 导诊预过滤
    workflow.set_entry_point("question_classifier")
    
    # 导诊预过滤分流
    def route_after_classification(state: ConsultationState) -> str:
        """根据分类结果路由到不同的分支"""
        classification = state.query_classification

        if classification == "critical":
            return "critical_response"
        elif classification == "non_business":
            return "non_business_response"
        elif classification == "initial":
            return "initial_extraction"
        elif classification == "followup":
            return "followup_extraction"
        else:
            # 默认作为初诊处理（包含 unknown 等异常值）
            return "initial_extraction"

    workflow.add_conditional_edges(
        "question_classifier",
        route_after_classification,
        {
            "critical_response": "critical_response",
            "non_business_response": "non_business_response",
            "initial_extraction": "initial_extraction",
            "followup_extraction": "followup_extraction",
            # ✅ 显式兜底映射：当 route_after_classification 返回 initial_extraction（例如 unknown）时保证有边可走
            "unknown": "initial_extraction",
        }
    )
    
    # 紧急响应 -> 结束
    workflow.add_edge("critical_response", END)
    
    # 非业务响应 -> 结束
    workflow.add_edge("non_business_response", END)
    
    # ========== 初诊分支的流程 ==========
    workflow.add_edge("initial_extraction", "initial_data_validation")
    
    # 初诊数据验证后的路由
    workflow.add_conditional_edges(
        "initial_data_validation",
        router_initial_completeness,
        {
            "incomplete": "initial_followup_question",
            "complete": "initial_decision_report",
        }
    )
    
    # 初诊追问 -> 结束
    workflow.add_edge("initial_followup_question", END)
    
    # 初诊报告 -> 结束
    workflow.add_edge("initial_decision_report", END)
    
    # ========== 复诊分支的流程 ==========
    workflow.add_edge("followup_extraction", "followup_data_validation")
    
    # 复诊数据验证后的路由
    workflow.add_conditional_edges(
        "followup_data_validation",
        router_followup_completeness,
        {
            "incomplete": "followup_incomplete",
            "complete": "followup_complete",
        }
    )
    
    # 复诊追问 -> 结束
    workflow.add_edge("followup_incomplete", END)
    
    # 复诊完成 -> 结束
    workflow.add_edge("followup_complete", END)
    
    # 编译图
    graph = workflow.compile()
    
    return graph


def visualize_graph():
    """
    生成工作流图的可视化（需要 graphviz）
    """
    graph = create_consultation_graph()
    try:
        png_data = graph.get_graph().draw_mermaid_png()
        with open("consultation_graph.png", "wb") as f:
            f.write(png_data)
        print("✅ 工作流图已保存为 consultation_graph.png")
    except Exception as e:
        print(f"⚠️ 无法生成可视化图片：{e}")
        print("你可以使用 graph.get_graph().print_ascii() 查看 ASCII 表示")
