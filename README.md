# 🏥 智能预问诊与数据枢纽 Agent

基于 **Python + LangGraph + Pydantic** 的临床预问诊系统，复现 Dify 工作流的完整功能。该系统通过意图识别、多分支路由和结构化数据提取，实现智能导诊、初诊处理和复诊管理。

## 📋 系统架构概述

```
用户输入
    ↓
【导诊预过滤】- 4 分类意图识别
    ├─ 类1【急危重症】 → 紧急提醒 → 结束
    ├─ 类2【初诊/复杂症状】 → 初诊分支 → 信息完整性判定 → 追问/报告
    ├─ 类3【慢病复诊/续方】 → 复诊分支 → 信息完整性判定 → 追问/凭证
    └─ 类4【非业务】 → 提示 → 结束

初诊分支流程：
  信息提取 → 数据治理 → 完整性判定
    ├─ 不完整 → 生成追问（含 RAG 指南）
    └─ 完整 → 生成临床决策报告（3 轨）

复诊分支流程：
  信息提取 → 数据治理 → 完整性判定
    ├─ 不完整 → 动态追问（5 种情况对应）
    └─ 完整 → 输出续方凭证
```

## 🚀 快速开始

### 1. 环境配置

```bash
# 克隆或下载项目
cd clinical_consulting_agent

# 创建虚拟环境（推荐）
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key

**方案A：使用环境变量**

```powershell
# PowerShell（Windows）
$env:TONGYI_API_KEY = 'your-api-key-here'
$env:OPENAI_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/'

# 或创建 .env 文件
# 复制 .env.example 为 .env，然后填入真实的 API Key
```

**方案B：在代码中直接指定**

```python
from main import ConsultationAgent

agent = ConsultationAgent(
    model_name="qwen-max-latest",
    api_key="your-api-key-here",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/"
)
```

### 3. 运行演示

```bash
python main.py
```

## 📂 项目结构

```
clinical_consulting_agent/
├── schemas.py              # Pydantic 数据模型定义
├── llm_config.py           # LLM 初始化和配置
├── nodes.py                # 工作流节点实现
├── workflow.py             # LangGraph 工作流图构建
├── main.py                 # 主程序入口和 Agent 类
├── requirements.txt        # 依赖列表
├── .env.example            # 环境变量示例
└── README.md               # 本文件
```

## 🔧 核心模块说明

### 1. **schemas.py** - 数据模型

定义了所有的数据结构，确保类型安全和序列化：

- `PatientBaselineInfo`: 患者基础信息
- `InitialConsultationExtraction`: 初诊提取结果
- `DataValidationResult`: 数据验证结果
- `FollowupConsultationExtraction`: 复诊提取结果
- `ConsultationState`: 整个工作流的状态对象

### 2. **llm_config.py** - LLM 配置

- `initialize_llm()`: 初始化 LLM 客户端
- `get_llm()`: 获取全局 LLM 实例（单例）
- 支持 OpenAI 兼容接口（通义千问、Claude 等）

### 3. **nodes.py** - 工作流节点

实现了各个处理节点：

**分类与分流：**
- `node_question_classifier()`: 意图识别（4 分类）

**初诊分支：**
- `node_initial_extraction()`: 全维临床信息提取
- `node_initial_data_validation()`: 数据治理与验证
- `router_initial_completeness()`: 完整性判定路由
- `node_initial_followup_question()`: 生成追问
- `node_initial_decision_report()`: 生成临床决策报告

**复诊分支：**
- `node_followup_extraction()`: 复诊信息提取
- `node_followup_data_validation()`: 复诊数据治理
- `router_followup_completeness()`: 完整性判定
- `node_followup_incomplete()`: 输出追问
- `node_followup_complete()`: 输出续方凭证

**特殊分支：**
- `node_critical_response()`: 紧急医疗提示
- `node_non_business_response()`: 非业务提示

### 4. **workflow.py** - LangGraph 工作流

- `create_consultation_graph()`: 构建完整的 DAG 工作流图
- 配置了所有节点间的边和条件路由
- `visualize_graph()`: 可视化工作流（需要 graphviz）

### 5. **main.py** - 主程序

- `ConsultationAgent` 类：Agent 主类，提供接口
  - `run_consultation()`: 异步运行咨询（推荐）
  - `run_consultation_sync()`: 同步运行咨询
- 包含完整的演示脚本和测试用例

## 💡 使用示例

### 基础使用

```python
import asyncio
from main import ConsultationAgent

async def main():
    # 初始化 Agent
    agent = ConsultationAgent(model_name="qwen-max-latest")
    
    # 运行咨询
    response = await agent.run_consultation(
        user_query="我最近三天一直在咳嗽，嗓子也疼",
        turn_count=1,
        verbose=True
    )
    
    print(response)

asyncio.run(main())
```

### 多轮对话

```python
async def multi_turn_consultation():
    agent = ConsultationAgent()
    
    # 第一轮：初诊
    response1 = await agent.run_consultation(
        user_query="我最近很疲劳，总是想睡觉",
        turn_count=1,
        verbose=True
    )
    print(f"Agent: {response1}\n")
    
    # 第二轮：追问的答复
    response2 = await agent.run_consultation(
        user_query="大概一周了，没有其他症状",
        turn_count=2,
        verbose=True
    )
    print(f"Agent: {response2}\n")

asyncio.run(multi_turn_consultation())
```

### 同步版本（不支持异步环境）

```python
from main import ConsultationAgent

agent = ConsultationAgent()

response = agent.run_consultation_sync(
    user_query="我胃疼已经两天了",
    verbose=True
)

print(response)
```

## 🎯 工作流逻辑详解

### 导诊预过滤（类别分类）

使用 LLM 的结构化输出，对用户输入进行 4 分类：

| 类别 | 触发条件 | 处理方案 |
|------|--------|--------|
| **1-急危重症** | 明确的致命性生理指征 | 直接输出紧急提示，结束 |
| **2-初诊/复杂** | 新患者、症状描述、简短碎片 | 进入初诊分支 |
| **3-复诊/续方** | 明确要求开药、复诊既往病 | 进入复诊分支 |
| **4-非业务** | 闲聊、系统测试等 | 输出提示，结束 |

### 初诊分支 - 三维核对算法

**三维核对（缺失项判定）：**
1. **维度1**：症状与部位（哪里痛、哪里不适）
2. **维度2**：发作/持续时间（多久了、何时开始）
3. **维度3**：诱发因素/伴随症状（吃错东西、受凉等）

**判定规则**：
- ✅ 三维齐备 → 信息完整 → 生成报告
- ❌ 缺少任一维 → 信息不完整 → 生成追问

**初诊报告 - 3 轨输出：**
1. **临床决策端**：标准化基线、现病史、既往史
2. **科研初筛端**：4 组临床试验匹配（代谢/消化/呼吸/眼科）
3. **患者端**：建议就诊科室、就医指引

### 复诊分支 - 5 种追问情景

| 情景 | 条件 | 追问 |
|------|------|------|
| **情景1** | 药名和疾病均无 | "请问您具体需要续开什么药物？" |
| **情景2** | 仅有病名，无药名和指标 | "请问您具体需要续开哪种药？最近指标如何？" |
| **情景3** | 有病和指标，无药名 | "请问您具体需要开哪一种药？" |
| **情景4** | 有药名，无指标 | "请问您最近症状控制得怎么样？" |
| **情景5** | 药名+指标齐备 | 无追问，输出续方凭证 |

## 🔐 免责声明处理

系统在所有最终输出中自动附加：

```
【免责声明：本服务仅通过大模型提供预问诊及科研初筛信息采集，不属于医疗诊断】
```

## 📝 扩展和定制

### 修改分类规则

编辑 `nodes.py` 中的 `QUESTION_CLASSIFIER_PROMPT` 常量。

### 修改追问话术

编辑 `CLINICAL_FOLLOWUP_PROMPT` 和 `FOLLOWUP_EXTRACTION_PROMPT`。

### 添加 RAG 知识库

在 `node_initial_followup_question()` 中集成向量数据库查询：

```python
from langchain.retrievers import VectorStoreRetriever

async def node_initial_followup_question(state):
    # ... 现有代码 ...
    
    # 检索临床指南
    context = retriever.get_relevant_documents(state.initial_validation.chief_complaint)
    
    # 将 context 融合到 prompt 中
    prompt = CLINICAL_FOLLOWUP_PROMPT.format(
        chief_complaint=...,
        missing_msg=...,
        rag_context=context
    )
```

### 支持多语言

修改 `llm_config.py` 的提示词为多语言版本，或使用 LLM 的多语言能力。

## 🐛 常见问题

### Q: 如何修改 LLM 模型？

A: 在初始化时指定 `model_name` 参数：

```python
agent = ConsultationAgent(model_name="gpt-4")  # 使用 GPT-4
agent = ConsultationAgent(model_name="qwen-plus")  # 使用通义 Plus
```

### Q: 如何禁用免责声明？

A: 在 `nodes.py` 中修改 `DISCLAIMER` 常量或在各节点中注释掉相关行。

### Q: 支持流式输出吗？

A: 当前实现是完整输出。可通过修改 `llm.ainvoke()` 为 `llm.astream()` 实现流式。

### Q: 如何调试工作流？

A: 使用 `verbose=True` 参数运行，会输出中间状态：

```python
response = await agent.run_consultation(
    user_query="...",
    verbose=True  # 打印详细日志
)
```

## 📚 依赖库说明

| 库 | 版本 | 用途 |
|----|-----|------|
| `langchain` | 0.3.1+ | LLM 框架 |
| `langgraph` | 0.2.50+ | 工作流图编排 |
| `pydantic` | 2.6.4+ | 数据模型验证 |
| `openai` | 1.35.13+ | OpenAI API 客户端 |
| `python-dotenv` | 1.0.0+ | 环境变量管理 |

## 📄 许可证

本项目仅供学习和研究使用。

## 👨‍💼 技术支持

如有问题，请检查：
1. ✅ API Key 是否正确配置
2. ✅ 网络连接是否正常
3. ✅ 依赖包是否完整安装
4. ✅ 运行 `verbose=True` 查看详细日志

---

**最后更新**: 2026年3月26日
