"""
ARCHITECTURE.md - 系统架构设计文档
详细说明 Agent 的设计思路、流程和实现细节
"""

# 🏥 预问诊 Agent - 系统架构设计文档

## 📐 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户输入(自然语言)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
         ┌───────────────────────────────────────┐
         │    【导诊预过滤】                     │
         │  Question Classifier (LLM)            │
         │  - 4分类意图识别                     │
         │  - 结构化输出                        │
         └──────────┬──┬──┬──┬──────────────────┘
                    │  │  │  │
        ┌───────────┘  │  │  └───────────┐
        │              │  │              │
        ▼              ▼  ▼              ▼
    【类1】         【类2】【类3】      【类4】
    急危重症         初诊  复诊         非业务
        │            │    │             │
        ▼            ▼    ▼             ▼
     紧急           初诊  复诊          非业务
     提醒           分支  分支          提醒
     └──────┐  ┌────┘    │    ┌────────┘
            │  │         │    │
            │  ▼         ▼    │
            │ ┌─────────────┐ │
            │ │  信息提取    │ │
            │ │  (LLM)      │ │
            │ └──────┬──────┘ │
            │        ▼        │
            │ ┌─────────────┐ │
            │ │ 数据治理     │ │
            │ │ (Python)    │ │
            │ └──────┬──────┘ │
            │        ▼        │
            │ ┌─────────────┐ │
            │ │完整性判定    │ │
            │ │ (If/Else)   │ │
            │ └─┬────────┬──┘ │
            │   │        │    │
            │   ▼        ▼    │
            │ 追问    完整    │
            │ │        │     │
            │ │        ▼     │
            │ │      报告     │
            │ │      /凭证    │
            └─┼────────┼─────┘
              │        │
              └────┬───┘
                   ▼
         ┌──────────────────┐
         │   最终响应        │
         │ + 免责声明       │
         └──────────────────┘
```

## 🏗️ 核心组件

### 1. 导诊预过滤 (Question Classifier)

**目的**: 对用户输入进行快速意图识别和分流

**实现方式**:
- 使用 LLM 的结构化输出 (Pydantic + Function Calling)
- 四分类输出: `QuestionClassificationResult`
  ```python
  class QuestionClassificationResult(BaseModel):
      classification: Literal["1", "2", "3", "4"]
      confidence: float
      reasoning: str
  ```

**分类规则**:

| 类别 | 标准 | 特征 | 处理 |
|------|------|------|------|
| **1** | 急危重症 | 明确的致命性指征 | 立即紧急提示 |
| **2** | 初诊/复杂 | 新患者、症状描述 | 进入初诊流程 |
| **3** | 复诊/续方 | 明确的开药/复诊诉求 | 进入复诊流程 |
| **4** | 非业务 | 闲聊、测试等 | 提示并结束 |

**关键逻辑**:
- ⚠️ 防误判: "救命"、"快疼死了"等表述必须进【类2】而非【类1】
- ⚠️ 医疗对话连续: 简短碎片回答（如"没有"）是对上一轮问题的应答，进【类2】

---

### 2. 初诊分支

#### 2.1 信息提取层 (node_initial_extraction)

**任务**: 从患者描述中提取结构化临床信息

**提取字段**:
```python
class InitialConsultationExtraction(BaseModel):
    std_gender: Optional[str]  # M/F/UNK
    std_history: Optional[str]  # 既往史
    age: Optional[int]  # 年龄
    chief_complaint: str  # 主诉
    missing_msg: Optional[str]  # 缺失维度
```

**三维核对算法** (Dimension Validation):

系统要求同时满足三个维度才认为信息齐备：

1. **维度1**: 症状与部位
   - 患者描述症状 AND 症状位置明确
   - 例: "咳嗽" (症状) + "嗓子/胸部" (部位)

2. **维度2**: 时间信息
   - 症状发作/持续时长明确
   - 例: "三天"、"昨天开始"、"一周"

3. **维度3**: 诱发因素或伴随症状
   - 患者提供诱因 OR 明确的伴随症状 OR 否认其他症状
   - 例: "受凉引起"、"伴有发热"、"没有其他症状"

**三维齐备 ✅** → 进入"完整"流程
**任一维缺失 ❌** → 进入"追问"流程

#### 2.2 数据治理层 (node_initial_data_validation)

**任务**: 清洗、验证、标准化提取的数据

**处理逻辑**:
```python
def clean_and_validate(extraction):
    # 1. 空值判定
    is_empty = lambda x: x is None or str(x).lower() in ["null", "", "无"]
    
    # 2. 类型转换
    age = extract_digits(extraction.age)
    gender = normalize_gender(extraction.std_gender)  # M/F/UNK
    
    # 3. 状态判定
    status = "complete" if not extraction.missing_msg else "incomplete"
    
    return DataValidationResult(
        status=status,
        missing_msg=extraction.missing_msg or "核心信息已齐备",
        std_gender=gender,
        std_history=extraction.std_history or "否认特殊既往史",
        chief_complaint=extraction.chief_complaint,
        age=age
    )
```

**输出**:
```python
class DataValidationResult(BaseModel):
    status: Literal["complete", "incomplete"]
    missing_msg: str
    std_gender: str
    std_history: str
    chief_complaint: str
    age: int
```

#### 2.3 路由判定层 (router_initial_completeness)

**条件**: 
- `status == "incomplete"` → 追问分支
- `status == "complete"` → 报告分支

#### 2.4 追问生成 (node_initial_followup_question)

**触发条件**: 信息不完整

**流程**:
1. 调用 RAG 检索临床追问指南 (可选)
2. 使用 LLM 生成人文关怀的口语化追问
3. 安抚患者并指出缺失维度

**提示词特点**:
- 温度: 检测患者情绪状态，适度安抚
- 连贯性: 基于历史对话自然顺延
- 口语化: 医学术语 → 日常用语
- 精炼: 控制在 50-100 字以内

#### 2.5 报告生成 (node_initial_decision_report)

**触发条件**: 信息完整

**生成的报告包含三个部分**:

##### 👨‍⚕️ 【临床决策端】门诊预问诊摘要
```
- 标准化基线: [年龄] | [性别]
- 现病史: [症状+部位+时间+诱因的临床总结]
- 既往史: [既往病史]
```

##### 🔬 【科研初筛端】临床试验匹配
基于规则判定患者是否匹配运行中的临床试验：

```python
rules = {
    "A-代谢组": {
        condition: age >= 18 AND ("高血压" in history OR "糖尿病" in history),
        output: "✅ 匹配《慢性代谢综合征队列研究》"
    },
    "B-消化组": {
        condition: "胃痛" in complaint OR "腹泻" in complaint,
        output: "✅ 匹配《消化道微生态靶向干预临床试验》"
    },
    "C-呼吸组": {
        condition: ("咳嗽" in complaint OR "哮喘" in complaint) AND age >= 12,
        output: "✅ 匹配《成人/青少年气道高反应真实世界研究》"
    },
    "D-眼科组": {
        condition: ("视力模糊" in complaint OR "眼睛痛" in complaint) AND age >= 50,
        output: "✅ 匹配《老年退行性眼病早期干预临床研究》"
    },
    "default": "❌ 暂无高度匹配的运行中项目，已归入常规随访队列"
}
```

##### 👥 【患者端】就诊指引
```
您的信息已结构化录入系统。请前往 [推断的科室] 候诊。
如突发剧烈不适请立即联系分诊台。
```

---

### 3. 复诊分支

#### 3.1 信息提取层 (node_followup_extraction)

**任务**: 提取患者的复诊需求、目标药物和近期指标

**提取字段**:
```python
class FollowupConsultationExtraction(BaseModel):
    target_medication: Optional[str]  # 疾病名+药物名的合并
    recent_metrics: Optional[str]  # 近期指标/控制状态
    missing_msg: Optional[str]  # 缺失追问
```

#### 3.2 动态追问逻辑（5种情景）

系统根据已收集信息的不同组合，动态生成精准的追问：

**情景 1: 彻底空白**
- 条件: `target_medication == null`
- 追问: "请问您具体需要续开什么药物？或者复诊什么疾病？"

**情景 2: 只有病名，缺药名和指标**
- 条件: `target_medication` 仅含疾病名 AND `recent_metrics == null`
- 追问: "了解到您来复诊该疾病，请问您具体需要续开哪种药？另外最近的指标或症状控制得如何？"

**情景 3: 有病和指标，唯独缺药名**
- 条件: `target_medication` 仅含疾病名 AND `recent_metrics` 有内容
- 追问: "您的指标/症状已记录，请问您具体需要开哪一种药？"

**情景 4: 有药名，唯独缺指标**
- 条件: `target_medication` 含具体药名 AND `recent_metrics == null`
- 追问: "了解到您需要开具该药物，为了确保用药安全，请问您最近症状控制得怎么样？（或相关的常规测量指标是多少？）"

**情景 5: 完美齐备**
- 条件: `target_medication` 含药名 AND `recent_metrics` 有内容
- 追问: `null` (无追问，直接进入完成流程)

#### 3.3 数据治理层 (node_followup_data_validation)

**处理逻辑**:
```python
def clean_followup_data(extraction):
    def safe_get(val):
        return "" if is_empty(val) else str(val).strip()
    
    return FollowupDataValidationResult(
        target_medication=safe_get(extraction.target_medication),
        recent_metrics=safe_get(extraction.recent_metrics),
        missing_msg=safe_get(extraction.missing_msg)
    )
```

#### 3.4 路由判定 (router_followup_completeness)

- `missing_msg` 不为空 → 追问分支
- `missing_msg` 为空 → 凭证分支

#### 3.5 追问输出 (node_followup_incomplete)

**输出**: 直接返回 `missing_msg` 的内容作为追问

#### 3.6 凭证输出 (node_followup_complete)

**输出**:
```
您的续方需求（[target_medication]）及近期指标（[recent_metrics]）已记录，
正在为您流转至专科医生开具处方。
```

---

## 🔄 工作流图编织 (LangGraph)

### 节点定义

```python
workflow = StateGraph(ConsultationState)

# 添加所有节点
workflow.add_node("question_classifier", node_question_classifier)
workflow.add_node("initial_extraction", node_initial_extraction)
workflow.add_node("initial_data_validation", node_initial_data_validation)
workflow.add_node("initial_followup_question", node_initial_followup_question)
workflow.add_node("initial_decision_report", node_initial_decision_report)
# ... 复诊分支节点 ...
workflow.add_node("critical_response", node_critical_response)
workflow.add_node("non_business_response", node_non_business_response)
```

### 边定义

```python
# 入口
workflow.set_entry_point("question_classifier")

# 第一层分流
workflow.add_conditional_edges(
    "question_classifier",
    lambda state: {
        "critical": "critical_response",
        "non_business": "non_business_response",
        "initial": "initial_extraction",
        "followup": "followup_extraction",
    }[state.query_classification]
)

# 初诊流程
workflow.add_edge("initial_extraction", "initial_data_validation")
workflow.add_conditional_edges(
    "initial_data_validation",
    router_initial_completeness,
    {
        "incomplete": "initial_followup_question",
        "complete": "initial_decision_report",
    }
)

# 复诊流程
workflow.add_edge("followup_extraction", "followup_data_validation")
workflow.add_conditional_edges(
    "followup_data_validation",
    router_followup_completeness,
    {
        "incomplete": "followup_incomplete",
        "complete": "followup_complete",
    }
)

# 结束节点
workflow.add_edge("initial_followup_question", END)
workflow.add_edge("initial_decision_report", END)
# ... 其他结束节点 ...
```

---

## 💾 状态对象 (ConsultationState)

```python
class ConsultationState(BaseModel):
    # 基础
    user_query: str  # 用户输入
    query_classification: Optional[str]  # 分类结果
    
    # 初诊分支
    initial_extraction: Optional[InitialConsultationExtraction]
    initial_validation: Optional[DataValidationResult]
    
    # 复诊分支
    followup_extraction: Optional[FollowupConsultationExtraction]
    followup_validation: Optional[FollowupDataValidationResult]
    
    # 输出
    final_response: str  # 最终响应
    
    # 元数据
    turn_count: int  # 对话轮数
    requires_followup: bool  # 是否需要追问
```

---

## 🔐 安全机制

### 1. 免责声明自动附加

所有最终输出都包含：
```
【免责声明：本服务仅通过大模型提供预问诊及科研初筛信息采集，不属于医疗诊断】
```

### 2. 紧急情况检测

如果分类为"急危重症"，立即:
- 输出紧急提示
- 建议拨打 120 或就医
- 终止后续处理

### 3. 防误判机制

- 情绪化表述（"救命"）不归类为急症
- 简短碎片回答识别为医疗对话连续
- 明确的诊断措辞才进入相应分支

---

## 🚀 执行流程示例

### 场景A: 初诊咨询（信息完整）

```
输入: "我从昨天开始头疼，前额部位疼痛，伴有发热，可能是受凉了"

步骤:
1. question_classifier → "initial"
2. initial_extraction → 
   {chief_complaint: "前额头疼伴发热1天，诱因受凉", 
    missing_msg: null, age: null, std_gender: "UNK"}
3. initial_data_validation →
   {status: "complete", age: 0, std_gender: "UNK"}
4. router_initial_completeness → "complete"
5. initial_decision_report →
   生成《临床决策报告》(3轨输出)
6. final_response = 报告内容 + 免责声明
```

### 场景B: 初诊咨询（信息不完整）

```
输入: "我疼得很厉害"

步骤:
1. question_classifier → "initial"
2. initial_extraction → 
   {chief_complaint: "疼痛", 
    missing_msg: "缺失部位、时间、伴随症状"}
3. initial_data_validation →
   {status: "incomplete"}
4. router_initial_completeness → "incomplete"
5. initial_followup_question →
   "请别着急，能否告诉我疼痛在哪个位置？已经疼多久了？"
6. final_response = 追问内容 + 免责声明
```

### 场景C: 复诊咨询

```
输入: "我需要续开高血压的药，最近血压110/70"

步骤:
1. question_classifier → "followup"
2. followup_extraction →
   {target_medication: "高血压患者", recent_metrics: "血压110/70",
    missing_msg: "请问具体需要开哪一种药？"}
3. followup_data_validation →
   {target_medication: "高血压患者", recent_metrics: "血压110/70",
    missing_msg: "请问具体需要开哪一种药？"}
4. router_followup_completeness → "incomplete"
5. followup_incomplete →
   "请问具体需要开哪一种药？"
6. final_response = 追问内容 + 免责声明
```

---

## 📈 扩展性考虑

### 1. 多语言支持

在 `nodes.py` 中的提示词加上语言参数：
```python
QUESTION_CLASSIFIER_PROMPT = """
{language_prompt}
患者输入: {user_input}
"""
```

### 2. RAG 集成

在追问生成前调用向量数据库：
```python
async def node_initial_followup_question(state):
    # 检索相关临床指南
    docs = await retriever.aget_relevant_documents(
        state.initial_validation.chief_complaint
    )
    # 将 docs 融合到 prompt
    prompt = format_prompt_with_context(prompt, docs)
    # ... 继续 LLM 调用
```

### 3. 多 LLM 支持

配置文件中指定不同节点使用不同模型：
```python
config = {
    "classifier": {"model": "gpt-3.5-turbo"},  # 快速
    "extractor": {"model": "gpt-4"},  # 精准
    "reporter": {"model": "gpt-4"},  # 详细
}
```

---

## 📊 性能优化

### 1. 异步执行

所有 LLM 调用使用 `async/await`：
```python
async def node_initial_extraction(state):
    result = await llm.ainvoke(prompt)
```

### 2. 缓存机制

对重复的分类或提取使用缓存。

### 3. 流式输出

支持流式返回，实时显示结果：
```python
async def stream_response(user_query: str):
    async for chunk in graph.astream(state):
        yield chunk
```

---

## 🧪 测试策略

1. **单元测试**: 各节点独立测试
2. **集成测试**: 完整工作流测试
3. **回归测试**: 边界情况和错误处理
4. **压力测试**: 并发请求处理

---

## 📝 总结

该架构通过以下特点实现了高效、安全、可扩展的预问诊系统：

✅ **清晰的分流逻辑**: 导诊预过滤确保用户被路由到正确的处理流程
✅ **三维信息验证**: 初诊的三维核对算法避免过度或不足问诊
✅ **动态追问策略**: 复诊的5情景追问确保精准收集信息
✅ **结构化输出**: Pydantic 确保数据类型安全和可序列化
✅ **安全机制**: 紧急情况检测和免责声明自动附加
✅ **异步设计**: 高效处理并发请求
✅ **可扩展架构**: 易于添加 RAG、多模型、多语言等功能
