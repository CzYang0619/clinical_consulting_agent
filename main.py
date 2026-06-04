"""
主程序入口 - 预问诊 Agent 执行脚本
"""
import sys
from typing import Optional, Tuple
from schemas import ConsultationState
from workflow import create_consultation_graph
from llm_config import initialize_llm


class ConsultationAgent:
    """预问诊咨询 Agent 主类"""
    
    def __init__(
        self,
        model_name: str = "qwen-max-latest",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        初始化 Agent
        
        Args:
            model_name: LLM 模型名称
            api_key: API Key（可选，会从环境变量读取）
            base_url: API 基础 URL（可选，会从环境变量读取）
        """
        # 初始化 LLM
        initialize_llm(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url
        )
        
        # 创建工作流图
        self.graph = create_consultation_graph()
        print(f"✅ 预问诊 Agent 已初始化，使用模型：{model_name}")
    
    def run_consultation(
        self,
        user_query: str,
        turn_count: int = 1,
        verbose: bool = False,
        previous_state: Optional[ConsultationState] = None
    ) -> Tuple[str, ConsultationState]:
        """
        运行单轮咨询
        
        Args:
            user_query: 用户的咨询问题
            turn_count: 对话轮数
            verbose: 是否打印中间步骤
            previous_state: 前一轮的状态（用于跨轮次维护信息）
        
        Returns:
            (最终的响应文本, 当前状态对象) 的元组
        """
        # 🔄【改进】基于前一个状态构建新状态
        if previous_state is not None:
            # 继承历史对话和累积信息
            state = ConsultationState(
                user_query=user_query,
                turn_count=turn_count,
                conversation_history=previous_state.conversation_history.copy() if previous_state.conversation_history else [],
                accumulated_chief_complaint=previous_state.accumulated_chief_complaint,
                # ✅ 继承上一轮分支判定，确保“复诊追问”的下一轮仍在复诊分支内
                query_classification=previous_state.query_classification,
                requires_followup=previous_state.requires_followup,
            )
            # 添加前一轮的医生回复到历史
            if previous_state.final_response:
                state.conversation_history.append({
                    "turn": turn_count - 1,
                    "role": "assistant",
                    "content": previous_state.final_response
                })
        else:
            # 第一轮，创建新的空状态
            state = ConsultationState(
                user_query=user_query,
                turn_count=turn_count
            )
        
        # 添加当前轮的用户输入到历史
        state.conversation_history.append({
            "turn": turn_count,
            "role": "user",
            "content": user_query
        })
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"👤 用户输入（第{turn_count}轮）：{user_query}")
            print(f"{'='*60}\n")
        
        try:
            # 执行工作流
            result_state = self.graph.invoke(state)
            
            # LangGraph 返回字典，需要转换或直接访问
            if isinstance(result_state, dict):
                final_response = result_state.get('final_response', '无法获取响应')
                # 🔄【改进】返回状态对象供下一轮使用
                result_state_obj = ConsultationState(**result_state) if isinstance(result_state, dict) else result_state
                if verbose:
                    print(f"\n📊 流程中间数据：")
                    print(f"  - 分类结果: {result_state.get('query_classification', 'unknown')}")
                    if result_state.get('initial_validation'):
                        print(f"  - 初诊验证: {result_state['initial_validation'].status}")
                    if result_state.get('followup_validation'):
                        print(f"  - 复诊验证: missing_msg='{result_state['followup_validation'].missing_msg}'")
                    print(f"\n🤖 Agent 响应：")
                return final_response, result_state_obj
            else:
                final_response = result_state.final_response
                if verbose:
                    print(f"\n📊 流程中间数据：")
                    print(f"  - 分类结果: {result_state.query_classification}")
                    if result_state.initial_validation:
                        print(f"  - 初诊验证: {result_state.initial_validation.status}")
                    if result_state.followup_validation:
                        print(f"  - 复诊验证: missing_msg='{result_state.followup_validation.missing_msg}'")
                    print(f"\n🤖 Agent 响应：")
                return final_response, result_state
        
        except Exception as e:
            error_msg = f"⚠️ 执行出现错误：{str(e)}"
            # 总是打印详细错误
            print(f"\n{'='*60}")
            print("❌ 详细错误信息：")
            print(f"{'='*60}")
            print(error_msg)
            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")
            return error_msg, state


def main():
    """
    主函数 - 演示脚本
    """
    print("\n" + "="*70)
    print("🏥 智能预问诊与数据枢纽 Agent - 演示脚本")
    print("="*70)
    
    # 初始化 Agent
    agent = ConsultationAgent(model_name="qwen-plus")
    
    # ==================== 测试用例 ====================
    
    test_cases = [
        {
            "name": "【类1】急危重症 - 胸痛",
            "query": "我现在感觉胸口突然剧烈疼痛，呼吸困难，感觉要死了！"
        },
        {
            "name": "【类2】初诊 - 感冒症状",
            "query": "最近三天开始咳嗽，嗓子疼，有点流鼻涕，吃过感冒药但还是没好。"
        },
        {
            "name": "【类3】复诊 - 高血压续方",
            "query": "我是高血压患者，上次开的硝苯地平已经吃完了，想要继续开药。最近血压控制得还不错，130/80 左右。"
        },
        {
            "name": "【类4】非业务 - 闲聊",
            "query": "你好，今天天气怎么样？"
        },
    ]
    
    print("\n开始测试各类场景...\n")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'─'*70}")
        print(f"测试 {i}: {test_case['name']}")
        print(f"{'─'*70}")
        
        response, state = agent.run_consultation(
            user_query=test_case["query"],
            turn_count=i,
            verbose=True
        )
        
        print(f"\n{response}\n")


    # ==================== 多轮对话测试 ====================
    
    print("\n" + "="*70)
    print("🔄 多轮对话测试 - 复诊续方场景")
    print("="*70)
    
    # 模拟多轮对话
    persistent_state = None
    
    # 第1轮：患者描述续方需求
    print("\n第1轮输入：我是2型糖尿病患者，用了半个月的二甲双胍已经吃完了需要续方。")
    response1, state1 = agent.run_consultation(
        user_query="我是2型糖尿病患者，用了半个月的二甲双胍已经吃完了需要续方。",
        turn_count=1,
        verbose=True,
        previous_state=persistent_state
    )
    print(f"\n🤖 Agent 响应：\n{response1}")
    persistent_state = state1
    
    # 第2轮：患者补充指标
    print("\n" + "-"*70)
    print("第2轮输入：最近检查空腹血糖7.2mmol/L，控制得还不错")
    response2, state2 = agent.run_consultation(
        user_query="最近检查空腹血糖7.2mmol/L，控制得还不错",
        turn_count=2,
        verbose=True,
        previous_state=persistent_state
    )
    print(f"\n🤖 Agent 响应：\n{response2}")
    persistent_state = state2
    
    print("\n✅ 多轮对话测试完成")
    print("="*70)
    
    print("="*70)
    print("✅ 演示完成！")
    print("="*70)


if __name__ == "__main__":
    # 检查 API 配置
    import os
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("TONGYI_API_KEY")):
        print("\n⚠️  注意：未检测到 API Key 环境变量")
        print("请设置以下任一环境变量：")
        print("  - OPENAI_API_KEY (用于 OpenAI 或兼容的 API)")
        print("  - TONGYI_API_KEY (用于通义千问)")
        print("  - OPENAI_BASE_URL (可选，指定 API 基础 URL)")
        print("\n例如在 PowerShell 中：")
        print("  $env:TONGYI_API_KEY = 'your-api-key'")
        print("  $env:OPENAI_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/'")
        print("\n" + "="*70 + "\n")
    
    # 运行演示
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中止了程序。")
    except Exception as e:
        print(f"\n❌ 程序出现错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
