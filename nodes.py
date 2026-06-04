"""
节点处理函数 - 实现工作流中各个处理节点的逻辑
"""
import json
import re
from typing import Optional
from schemas import (
    ConsultationState,
    QuestionClassificationResult,
    InitialConsultationExtraction,
    DataValidationResult,
    FollowupConsultationExtraction,
    FollowupDataValidationResult,
    ClinicalDecisionReport,
)
from llm_config import get_llm


DISCLAIMER = "【免责声明：本服务仅通过大模型提供预问诊及科研初筛信息采集，不属于医疗诊断】"


def _extract_json_block(text: str) -> Optional[str]:
    """从模型输出中尽量稳健地提取一个 JSON 对象文本。

    约束：我们期望输出中只有一个主 JSON 块。
    策略：取第一个 '{' 到最后一个 '}' 之间的内容。
    """
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


# =================== 节点1: 导诊预过滤 ===================

QUESTION_CLASSIFIER_PROMPT = """
你是医疗导诊预过滤系统。请根据以下患者的输入，判断其属于哪一类。

分类标准：

【类1】急危重症：
患者明确描述了极其危重的致命性生理指征或红旗症状（如：突发剧烈且难以忍受的疼痛、大出血、意识丧失/改变、严重的呼吸或循环障碍、自杀、自伤、结束生命等）。包括情绪表达自杀意图或自伤行为。
⚠️【严格排他限制】：如果患者仅仅是情绪激动地表达身体极度不适，但未指明具体的高危部位，或描述极其模糊（如"快疼死了"、"救命"），请绝对不要归为急症！必须将其归类为【初诊/复杂症状】，由系统进行安全追问。

【类2】初诊/复杂症状：
患者试图进行医疗求助或生理状态登记（且未明确要求开药/续方）。包含以下任意情况：
- 描述任何身体不适、患病情况或既往病史。
- 仅提供基础生理信息（如年龄、性别等纯数据）。
- 表达模糊的痛苦、焦虑或不知所措（即使缺乏具体医学名词，或包含无意义语气词、乱码）。
- 【极度重要】：用极短的日常口语、肯定/否定词（如："没有"、"没有没有"、"是的"、"不知道"、"好"、"大概一天"）来回答上一轮关于症状的追问。
- 如果患者描述新出现的症状或首次求医，即使提到需要药物，也应归类为此类。
- ✅【强排他补充】：若患者在提到既往用药/停药后，明确询问“下一步怎么做/怎么办/如何处理/要不要调整方案”等需要重新评估的治疗决策问题，应优先归类为【类2】。

【类3】慢病复诊/续方：
患者明确表达了复诊常规疾病、开具处方或续购具体药物的诉求。包含关键词如“复诊”、“续方”、“开药”、“续购”、“上次开的药”、“再开”、“继续吃”等。或者当前对话大语境已经是开药/续方。
- 示例：正确 - "我来复诊糖尿病，需要续开二甲双胍"
- 示例：错误 - "我崴脚了，需要一些药物"（这是初诊，因为描述新症状）

【类4】非业务：
【仅限】完全脱离医疗问诊场景的输入。如纯粹的系统测试命令、毫无意义的日常闲聊（如询问天气、单纯打招呼等）。

请你输出 JSON 格式的结果，包含：
- classification: "1", "2", "3" 或 "4"
- confidence: 0.0-1.0 之间的置信度
- reasoning: 简短的推理说明

患者输入：
{user_input}
"""


def node_question_classifier(state: ConsultationState) -> ConsultationState:
    """
    节点1：导诊预过滤（意图分类）
    使用结构化输出分类患者问题
    """
    llm = get_llm()

    # ✅【多轮对话保护】如果上一轮已经判定为复诊/续方且正在追问，则本轮沿用复诊分支
    # 典型场景：第1轮=复诊但指标缺失 -> 系统追问；第2轮=补充指标（通常不再重复提药名）
    if state.turn_count > 1 and state.query_classification == "followup":
        return state

    user_input_stripped = state.user_query.strip()

    # ✅【安全兜底】仅对“明确管制药/安眠药/购药渠道”做早期拦截路由
    # ⚠️ 为避免误伤“提到管制药但在咨询不良反应/下一步怎么办”的初诊问题：
    # 只有当输入同时呈现出“开药/续方/买药”等意图时，才触发该前置路由。
    controlled_hint_patterns = [
        r"阿普唑仑|alprazolam|劳拉西泮|lorazepam|氯硝西泮|clonazepam|地西泮|diazepam|安定|吗啡|morphine|芬太尼|fentanyl|杜冷丁|可待因|苯二氮卓",
        r"安眠药|镇静|催眠",
        r"买药途径|怎么买|哪里买|代购|渠道"
    ]
    prescribing_intent_patterns = [
        r"开药|续方|续开|再开|处方|最大剂量|剂量|疗程|怎么买|哪里买|渠道|代购"
    ]
    has_controlled_hint = any(re.search(p, user_input_stripped, re.IGNORECASE) for p in controlled_hint_patterns)
    has_prescribing_intent = any(re.search(p, user_input_stripped, re.IGNORECASE) for p in prescribing_intent_patterns)
    if has_controlled_hint and has_prescribing_intent:
        state.query_classification = "followup"
        return state

    # 【前置检查】：识别无效的初始输入
    minimal_fragments = {"没有", "没", "没有没有", "是的", "好", "不知道", "不", "对", "嗯", "啊", ""}
    is_minimal_fragment = (
        user_input_stripped.lower() in minimal_fragments or
        (len(user_input_stripped) <= 2 and user_input_stripped not in ["我", "你", "他", "她"])
    )

    if is_minimal_fragment and state.turn_count == 1:
        state.query_classification = "initial"
        return state

    # 构建分类提示词
    prompt = QUESTION_CLASSIFIER_PROMPT.format(user_input=state.user_query)

    result = None
    try:
        response = llm.invoke(prompt)
        content = response.content

        json_text = _extract_json_block(content)
        if json_text:
            parsed = json.loads(json_text)
            result = QuestionClassificationResult(
                classification=str(parsed.get("classification", "2")),
                confidence=float(parsed.get("confidence", 0.5)),
                reasoning=str(parsed.get("reasoning", ""))
            )
        else:
            result = QuestionClassificationResult(
                classification="2",
                confidence=0.5,
                reasoning="无法解析响应，默认为初诊"
            )
    except (json.JSONDecodeError, ValueError) as e:
        result = QuestionClassificationResult(
            classification="2",
            confidence=0.5,
            reasoning=f"JSON解析失败，默认为初诊：{str(e)}"
        )
    except Exception as e:
        result = QuestionClassificationResult(
            classification="2",
            confidence=0.5,
            reasoning=f"处理失败，默认为初诊：{str(e)}"
        )

    state.query_classification = {
        "1": "critical",
        "2": "initial",
        "3": "followup",
        "4": "non_business"
    }.get(result.classification, "unknown")

    return state


# =================== 初诊分支节点 ===================

INITIAL_EXTRACTION_PROMPT = """
# Role
你是一个理性的临床数据结构化解析器（非诊断医生）。任务是综合【历史对话】和【最新回复】，提取并合并患者的结构化信息。

# Task (状态追踪 - 重要)
如果患者的最新回复是简短碎片（如"没有"、"昨天"、"不知道"），你必须去历史对话中捞取之前的症状。绝对不能让 chief_complaint 变成 null 或丢失历史信息！
如果用户明确回答“否认”或“没有”，则认为相应维度（如既往史、伴随症状）已确认，无需再问。

# Extraction Rules
1. std_gender: 提取性别（M/F/UNK），历史确认则保持。如果未提及，填 UNK。
2. std_history: 提取既往史，无则填 null，历史确认则保持。
3. missing_msg: 【执行严格的三维核对算法】
   检查当前合并后的病史，是否已经**同时包含**以下三个基础维度：
   - [维度1] 核心症状与部位（例如：哪里痛、哪里不舒服）
   - [维度2] 发作或持续时间（例如：多久了、何时开始的）
   - [维度3] 诱发因素或伴随症状（例如：吃错东西、受凉、是否伴有发热/呕吐，或患者明确回答"没有其他症状/没有没有"）
   
   如果三个维度均有信息（或用户明确否认），输出 null（信息齐备）。如果缺少任一维度，输出具体的缺失提示。
   
4. age: 提取纯数字年龄，无则 null，历史确认保持。
5. chief_complaint: 提取并合并核心主诉（包含部位、症状、时间、诱因等全部已收集信息的摘要）。如果无信息，填"未提及"。

# 历史对话上下文
【之前已收集的信息】
{history_context}

【最新患者输入】
{user_input}

# 输出要求
输出原生 JSON，包含上述5个字段。
"""


def node_initial_extraction(state: ConsultationState) -> ConsultationState:
    """
    初诊分支 - 节点2.1：全维临床信息提取
    【关键】支持多轮对话的历史信息合并
    """
    llm = get_llm()

    user_input_stripped = state.user_query.strip()
    minimal_fragments = {"没有", "没", "没有没有", "是的", "好", "不知道", "不", "对", "嗯", "啊", ""}
    is_minimal_fragment = (
        user_input_stripped.lower() in minimal_fragments or
        (len(user_input_stripped) <= 2 and user_input_stripped not in ["我", "你", "他", "她"])
    )

    # 🔄【新增】构建历史对话上下文
    history_context = ""
    if state.conversation_history:
        history_context = "【对话历史】\n"
        for item in state.conversation_history:
            role = "患者" if item.get("role") == "user" else "医生"
            content = item.get("content", "")
            history_context += f"  [{role}]: {content}\n"
    
    # 🔄【新增】检测是否为新问题（多轮对话中）
    is_new_problem = False
    if state.turn_count > 1:
        new_problem_indicators = ["我最近", "我现在", "我有", "我感觉", "我疼", "我头疼", "我肚子疼", "我胸口疼"]
        is_new_problem = any(indicator in user_input_stripped.lower() for indicator in new_problem_indicators)
    
    # 🔄【新增】如果有累积的主诉，也加入上下文（除非是新问题）
    if state.accumulated_chief_complaint and not is_new_problem:
        history_context += f"\n【已确认的症状汇总】：{state.accumulated_chief_complaint}\n"
    
    prompt = INITIAL_EXTRACTION_PROMPT.format(
        user_input=state.user_query,
        history_context=history_context if history_context else "（这是第一轮对话）"
    )
    
    result = None
    try:
        response = llm.invoke(prompt)
        content = response.content

        json_text = _extract_json_block(content)
        if json_text:
            parsed = json.loads(json_text)
            result = InitialConsultationExtraction(
                std_gender=parsed.get("std_gender"),
                std_history=parsed.get("std_history"),
                missing_msg=parsed.get("missing_msg"),
                age=parsed.get("age"),
                chief_complaint=parsed.get("chief_complaint", "")
            )
        else:
            # 无法解析时，强制进入不完整分支，避免“假性complete”
            result = InitialConsultationExtraction(
                chief_complaint=state.user_query,
                missing_msg="系统未能完全解析您的描述，请换个说法补充一下您的不适、出现时间及伴随症状。"
            )
    except (json.JSONDecodeError, ValueError):
        result = InitialConsultationExtraction(
            chief_complaint=state.user_query,
            missing_msg="系统未能完全解析您的描述，请换个说法补充一下您的不适、出现时间及伴随症状。"
        )
    except Exception as e:
        print(f"⚠️ node_initial_extraction 异常: {str(e)}")
        result = InitialConsultationExtraction(
            chief_complaint=state.user_query,
            missing_msg="系统未能完全解析您的描述，请换个说法补充一下您的不适、出现时间及伴随症状。"
        )

    # 【后置修复】：仅在“第一轮/无历史主诉”场景下，才对极短碎片强制标记不完整
    # 避免患者在多轮中按要求回答“没有/否认”时被误判，导致追问死循环。
    if is_minimal_fragment and state.turn_count == 1 and not state.accumulated_chief_complaint:
        result.missing_msg = "请详细描述您的不适症状、发作时间和伴随症状"
        result.chief_complaint = result.chief_complaint or "患者仅回复'没有'或极短碎片"

    if result.chief_complaint:
        state.accumulated_chief_complaint = result.chief_complaint

    state.initial_extraction = result

    return state


def node_initial_data_validation(state: ConsultationState) -> ConsultationState:
    """
    初诊分支 - 节点2.2：底层数据治理 (MEL)
    清洗和验证提取的数据
    """
    extraction = state.initial_extraction

    if not extraction:
        state.final_response = "系统解析出现异常，请重新描述。"
        return state

    def is_empty(val):
        """判断值是否为空"""
        return val is None or str(val).strip().lower() in ["null", "", "无", "none", "unknown"]

    def _mark_asked(slot: str):
        # ✅ 安全初始化：防止极端情况下 asked_slots 为 None 导致 append 崩溃
        if state.asked_slots is None:
            state.asked_slots = []
        if slot and slot not in state.asked_slots:
            state.asked_slots.append(slot)

    def _already_asked(slot: str) -> bool:
        return slot in (state.asked_slots or [])

    # 提取并清洗数据
    missing_raw = extraction.missing_msg
    missing_msg = None if is_empty(missing_raw) else str(missing_raw).strip()

    # 提取年龄（纯数字）
    age = 0
    age_raw = extraction.age
    if not is_empty(age_raw):
        match = re.search(r"\d+", str(age_raw))
        if match:
            age = int(match.group())

    # 标准化性别
    gender_raw = str(extraction.std_gender or "").strip().upper()
    std_gender = gender_raw if gender_raw in ["M", "F", "UNK"] else "UNK"

    # 标准化既往史：只有患者明确否认/提供时才写入；未回答则标记待补充
    history_raw = str(extraction.std_history or "").strip()
    if is_empty(history_raw):
        std_history = "未提供（待补充）"
    else:
        std_history = history_raw
        # 只要模型给到了既往史（包括“否认”类表述），认为已覆盖该维度
        _mark_asked("pmh")

    # --- 追问止盈策略（不改变原有逻辑，只避免重复问） ---
    # 1) 若上游已给 missing_msg，则不在此处覆盖它
    # 2) 若 missing_msg 为空，且既往史为空，则需要追问既往史
    #    但如果之前已经问过 pmh，则不再重复追问，避免死循环
    if not missing_msg and is_empty(history_raw):
        if not _already_asked("pmh"):
            missing_msg = "请补充既往史/慢性病史以及是否有长期用药或过敏史（如无请回复‘否认’）"
            _mark_asked("pmh")
        else:
            # 已经问过仍为空：放过，避免无限追问
            missing_msg = None

    # 构建验证结果
    status = "incomplete" if missing_msg else "complete"

    state.initial_validation = DataValidationResult(
        status=status,
        missing_msg=missing_msg if missing_msg else "核心信息已齐备",
        std_gender=std_gender,
        std_history=std_history,
        chief_complaint=extraction.chief_complaint or "未提及",
        age=age,
    )

    return state


# =================== 初诊路由判定 ===================

def router_initial_completeness(state: ConsultationState) -> str:
    """
    初诊信息完整性判定路由
    返回 "incomplete" 或 "complete"
    """
    if not state.initial_validation:
        return "incomplete"
    
    return "incomplete" if state.initial_validation.status == "incomplete" else "complete"


# =================== 初诊 - 信息不完整分支 ===================

CLINICAL_FOLLOWUP_PROMPT = """
# Role
你是一位严谨且有温度的专科主治医师。患者当前提供的核心问诊信息尚不完整，你需要向患者发起专业且具人文关怀的追问。

# Context
- 患者核心主诉：{chief_complaint}
- 必须补充的缺失核心维度：{missing_msg}

# Task
请生成一句自然、专业、贴近真实临床沟通场景的追问话术。

# Rules
1. 如果患者输入极其简短、包含乱码或带有痛苦/焦虑情绪（如"啊啊啊"、"不知道"），追问时必须先加入简短的安抚话语（如"请别着急，慢慢告诉我..."）。
2. 必须将【缺失核心维度】转化为易于患者理解的日常提问。
3. 话术要精炼，控制在 50-100 字以内。
4. 不要向患者解释你的意图。
5. 确保追问友好且不增加患者焦虑。
"""


def node_initial_followup_question(state: ConsultationState) -> ConsultationState:
    """
    初诊分支 - 信息不完整：生成追问
    """
    llm = get_llm()
    validation = state.initial_validation
    
    if not validation:
        state.final_response = "系统错误，无法继续。"
        return state
    
    prompt = CLINICAL_FOLLOWUP_PROMPT.format(
        chief_complaint=validation.chief_complaint,
        missing_msg=validation.missing_msg
    )
    
    response = llm.invoke(prompt)
    state.final_response = f"{response.content}\n\n{DISCLAIMER}"
    state.requires_followup = True
    
    return state


# =================== 初诊 - 信息完整分支 ===================

CLINICAL_DECISION_PROMPT = """
# Role
你是顶尖研究型医院的临床决策支持系统（CDSS）兼临床研究协调员（CRC）。
请基于以下清洗后的【标准化患者数据】。生成一份多维度的《数统与临床决策报告》。

# Input Data
- 标准化基线：{baseline}
- 现病史：{chief_complaint}
- 既往史 (PMH)：{history}

# Task
请严格按照以下格式输出三个部分：

### 👨‍⚕️ 【临床决策端】门诊预问诊摘要
- **标准化基线**：{baseline}
- **现病史**：[用精炼的医学术语总结现病史]
- **既往史 (PMH)**：[既往史信息]

### 🔬 【数统与科研端】临床试验（CT）静默初筛
[根据以下规则判定，若命中多个取最相关的一个：
- 规则 A【代谢组】：若 年龄>=18 且 既往史 包含 "高血压"/"糖尿病"
- 规则 B【消化组】：若 现病史 包含 "胃痛"/"腹泻"
- 规则 C【呼吸组】：若 现病史主要特征为原发性呼吸道感染或气道高反应（如以咳嗽/哮喘为主的呼吸道症状），且年龄 >= 12；若症状更符合心源性因素（如心衰引起的夜间咳/喘、下肢水肿伴呼吸困难等），应避免误归为呼吸组。
- 规则 D【眼科组】：若 现病史 包含 "视力"/"眼睛" 且 年龄 >= 50]

初筛结论：
- 若命中规则 A，输出："✅ 匹配《慢性代谢综合征队列研究》，建议向患者派发心血管内分泌组知情同意书"
- 若命中规则 B，输出："✅ 匹配《消化道微生态靶向干预临床试验》，建议向患者派发消化组知情同意书"
- 若命中规则 C，输出："✅ 匹配《成人/青少年气道高反应真实世界研究》，建议向患者派发呼吸组知情同意书"
- 若命中规则 D，输出："✅ 匹配《老年退行性眼病早期干预临床研究》，建议向患者派发眼科组知情同意书"
- 若以上全部不符合，输出："❌ 暂无高度匹配的运行中项目，已归入常规随访队列"

### 👥 【患者端】就诊指引
- 您的信息已结构化录入系统。请前往 [基于现病史推断的科室名称，如骨科、消化科等] 候诊。如突发剧烈不适请立即联系分诊台。
"""


def node_initial_decision_report(state: ConsultationState) -> ConsultationState:
    """
    初诊分支 - 信息完整：生成临床决策报告
    """
    llm = get_llm()
    validation = state.initial_validation

    if not validation:
        state.final_response = "系统错误，无法生成报告。"
        return state

    gender_label = {"M": "男", "F": "女", "UNK": "未知"}.get(validation.std_gender, "未知")
    age_str = f"{validation.age}岁" if validation.age > 0 else "未知"


    # 统一加上明确的标签前缀
    baseline_str = f"年龄: {age_str} | 性别: {gender_label}"

    prompt = CLINICAL_DECISION_PROMPT.format(
        baseline=baseline_str,
        chief_complaint=validation.chief_complaint,
        history=validation.std_history
    )

    response = llm.invoke(prompt)
    state.final_response = f"{response.content}\n\n{DISCLAIMER}"
    state.requires_followup = False
    state.is_conversation_ended = True

    return state


# =================== 复诊分支节点 ===================

FOLLOWUP_EXTRACTION_PROMPT = """
# Role
你是慢病复诊与续方信息提取引擎。任务是综合【历史对话】和【最新回复】，提取并合并患者的复诊信息。

# Task (状态追踪 - 重要)
如果患者的最新回复是简短碎片（如"7.2mmol/L"、"控制得还不错"），你必须去历史对话中捞取之前的疾病和药物信息。绝对不能让 target_medication 变成 null 或丢失历史信息！

# Extraction Rules
1. target_medication: 提取并合并患者复诊的【基础疾病名】以及想要开具的【具体目标药物名】。
   - 若仅有病名：填病名
   - 若仅有药名：填药名
   - 若两者皆有：合并填入（如"[疾病名]（[药物名]）"）
   - 若均未提及：从历史对话中查找并保持
   - 如果历史中已有信息，本轮未重复提及，则保持历史信息

2. recent_metrics: 患者提供的近期病情控制指标或生理反馈。合并历史和最新输入。如果无，填 null。
   - ✅ recent_metrics 不仅包括数值指标（如血压/血糖/体温），也包括口语化的主观反馈或用药后变化（例如："控制得还不错"、"还行"、"停药又犯"、"脚踝肿"、"出现不良反应"、"症状加重/缓解"）。

3. missing_msg: 根据合并后的完整信息动态生成追问逻辑：
   - 若 target_medication 为 null：提示"请问您具体需要续开什么药物？或者复诊什么疾病？"
   - 若只有病名没有具体药名，且 recent_metrics 为 null：提示"了解到您来复诊该疾病，请问您具体需要续开哪种药？另外最近的指标或症状控制得如何？"
   - 若只有病名没有药名，但 recent_metrics 已有内容：提示"您的指标/症状已记录，请问您具体需要开哪一种药？"
   - 若已有具体药名，但 recent_metrics 为 null：提示"了解到您需要开具该药物，为了确保用药安全，请问您最近症状控制得怎么样？"
   - 若药和指标都有：输出 null

# 历史对话上下文
【之前已收集的信息】
{history_context}

【最新患者输入】
{user_input}

# 输出要求
输出原生 JSON，包含上述3个字段。
"""


def node_followup_extraction(state: ConsultationState) -> ConsultationState:
    """
    复诊分支 - 节点3.1：复诊信息极简提取
    【关键】支持多轮对话的历史信息合并
    """
    llm = get_llm()

    # 🔄【新增】构建历史对话上下文
    history_context = ""
    if state.conversation_history:
        history_context = "【对话历史】\n"
        for item in state.conversation_history:
            role = "患者" if item.get("role") == "user" else "医生"
            content = item.get("content", "")
            history_context += f"  [{role}]: {content}\n"
    
    # 🔄【新增】如果有累积的主诉，也加入上下文
    if state.accumulated_chief_complaint:
        history_context += f"\n【已确认的症状汇总】：{state.accumulated_chief_complaint}\n"
    
    prompt = FOLLOWUP_EXTRACTION_PROMPT.format(
        user_input=state.user_query,
        history_context=history_context if history_context else "（这是第一轮对话）"
    )
    
    result = None
    try:
        response = llm.invoke(prompt)
        content = response.content

        json_text = _extract_json_block(content)
        if json_text:
            parsed = json.loads(json_text)
            result = FollowupConsultationExtraction(
                target_medication=parsed.get("target_medication"),
                recent_metrics=parsed.get("recent_metrics"),
                missing_msg=parsed.get("missing_msg")
            )
        else:
            # 解析不到 JSON：强制进入不完整分支，避免“假性 complete”输出空凭证
            result = FollowupConsultationExtraction(
                missing_msg="系统未能完整解析您的续方信息。请您说明需要续开的具体药物/疾病名称，以及最近的指标或症状控制情况（如无指标也请描述近期感受）。"
            )
    except (json.JSONDecodeError, ValueError):
        result = FollowupConsultationExtraction(
            missing_msg="系统未能完整解析您的续方信息。请您说明需要续开的具体药物/疾病名称，以及最近的指标或症状控制情况（如无指标也请描述近期感受）。"
        )
    except Exception as e:
        print(f"⚠️ node_followup_extraction 异常: {str(e)}")
        result = FollowupConsultationExtraction(
            missing_msg="系统未能完整解析您的续方信息。请您说明需要续开的具体药物/疾病名称，以及最近的指标或症状控制情况（如无指标也请描述近期感受）。"
        )

    # 🔄【去重】累积复诊信息（用于跨轮次保存），避免无限拼接重复片段
    if result.target_medication:
        if state.accumulated_chief_complaint:
            if result.target_medication not in state.accumulated_chief_complaint:
                state.accumulated_chief_complaint = f"{state.accumulated_chief_complaint} | {result.target_medication}"
        else:
            state.accumulated_chief_complaint = result.target_medication

    if result.recent_metrics:
        if state.accumulated_chief_complaint:
            if result.recent_metrics not in state.accumulated_chief_complaint:
                state.accumulated_chief_complaint = f"{state.accumulated_chief_complaint} | 指标：{result.recent_metrics}"
        else:
            state.accumulated_chief_complaint = f"指标：{result.recent_metrics}"

    state.followup_extraction = result

    return state


def node_followup_data_validation(state: ConsultationState) -> ConsultationState:
    """
    复诊分支 - 节点3.2：复诊数据治理
    """
    extraction = state.followup_extraction

    if not extraction:
        state.final_response = "系统解析出现异常，请重新描述。"
        return state

    def safe_get(val):
        return "" if val is None or str(val).strip().lower() in ["null", "", "无", "none"] else str(val).strip()

    target_med = safe_get(extraction.target_medication)

    # 检查是否为管制药
    controlled_drugs = ["阿普唑仑", "alprazolam", "芬太尼", "fentanyl", "吗啡", "morphine", "杜冷丁", "pethidine", "可待因", "codeine", "安定", "diazepam", "氯硝西泮", "clonazepam", "劳拉西泮", "lorazepam"]
    is_controlled = any(drug.lower() in target_med.lower() for drug in controlled_drugs)

    if is_controlled:
        # ✅ 关键：初始化 followup_validation，避免下游路由/节点因 validation 缺失触发“系统错误，无法继续”
        state.followup_validation = FollowupDataValidationResult(
            target_medication=target_med,
            recent_metrics=safe_get(extraction.recent_metrics),
            # 让 router_followup_completeness 走 complete，从而不会进入 followup_incomplete 覆盖 final_response
            missing_msg=""
        )
        state.final_response = f"此类药物（{target_med}）属于管制药品，无法通过线上方式开具。请前往医院专科门诊，由医生根据您的病情评估后开具处方。\n\n{DISCLAIMER}"
        state.requires_followup = False
        state.is_conversation_ended = True
        return state

    state.followup_validation = FollowupDataValidationResult(
        target_medication=target_med,
        recent_metrics=safe_get(extraction.recent_metrics),
        missing_msg=safe_get(extraction.missing_msg)
    )

    return state


# =================== 复诊路由判定 ===================

def router_followup_completeness(state: ConsultationState) -> str:
    """
    复诊信息完整性判定路由
    返回 "incomplete" 或 "complete"
    """
    if not state.followup_validation:
        return "incomplete"
    
    return "incomplete" if state.followup_validation.missing_msg else "complete"


# =================== 复诊 - 信息不完整分支 ===================

def node_followup_incomplete(state: ConsultationState) -> ConsultationState:
    """
    复诊分支 - 信息不完整：直接输出追问
    """
    validation = state.followup_validation
    
    if not validation:
        state.final_response = "系统错误，无法继续。"
        return state
    
    state.final_response = f"{validation.missing_msg}\n\n{DISCLAIMER}"
    state.requires_followup = True
    
    return state


# =================== 复诊 - 信息完整分支 ===================

def node_followup_complete(state: ConsultationState) -> ConsultationState:
    """
    复诊分支 - 信息完整：输出续方凭证
    """
    # ⚠️ 防御：上游若已明确终止（例如命中管制药拦截），绝不允许覆盖既有 final_response
    if getattr(state, "is_conversation_ended", False) and (state.final_response or "").strip():
        return state

    validation = state.followup_validation

    if not validation:
        state.final_response = "系统错误，无法生成凭证。"
        return state

    response_text = (
        f"您的续方需求（{validation.target_medication}）及近期指标（{validation.recent_metrics}）已记录，"
        f"正在为您流转至专科医生开具处方。\n\n{DISCLAIMER}"
    )

    state.final_response = response_text
    state.requires_followup = False
    state.is_conversation_ended = True

    return state


# =================== 紧急和非业务分支 ===================

def node_critical_response(state: ConsultationState) -> ConsultationState:
    """
    紧急医疗处理分支
    """
    state.final_response = f"""⚠️ 系统检测到您可能存在急危重症风险，请立即停止线上问诊，拨打 120 或前往最近的医院急诊科就医！

{DISCLAIMER}"""
    state.is_conversation_ended = True
    return state


def node_non_business_response(state: ConsultationState) -> ConsultationState:
    """
    非业务处理分支
    """
    state.final_response = f"""您好，我是预问诊助手，目前仅提供医疗问诊服务。为了更好地协助您，请详细描述您的不适症状（如症状内容、持续时间等）。

{DISCLAIMER}"""
    return state
