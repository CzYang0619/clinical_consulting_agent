## 🚀 快速启动指南

### 环境准备

1. **设置环境变量** (PowerShell)：
```powershell
$env:TONGYI_API_KEY = 'sk-9f480394f3874b2d98797649ffef405f'
$env:OPENAI_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
```

2. **安装依赖**：
```bash
pip install -r requirements.txt
```

### 运行方式

#### 方式1：运行演示脚本（推荐）
```bash
python run.py
```
自动设置环境变量并运行完整的演示测试

#### 方式2：交互式模式
```bash
python cli_interactive.py
```
实时输入症状，获取实时诊断建议

#### 方式3：直接调用 Agent
```python
from main import ConsultationAgent

agent = ConsultationAgent(model_name="qwen-plus")
response = agent.run_consultation("我感觉胸口疼", verbose=True)
print(response)
```

### 核心文件说明

| 文件 | 功能 |
|------|------|
| `main.py` | Agent 主类和演示脚本 |
| `nodes.py` | 工作流处理节点（11 个） |
| `workflow.py` | LangGraph 工作流定义 |
| `llm_config.py` | LLM 初始化和配置 |
| `schemas.py` | Pydantic 数据模型 |
| `cli_interactive.py` | 交互式命令行界面 |
| `run.py` | 启动脚本（自动设置环境） |

### 工作流流程

```
用户输入
   ↓
[分类节点] 判断为: critical / initial / followup / non_business
   ↓
   ├→ critical (急症) → 立即就医建议
   ├→ initial (初诊) → 症状提取 → 数据验证 → 临床决策 → 门诊指引
   ├→ followup (复诊) → 续方提取 → 数据验证 → 开具处方
   └→ non_business (非业务) → 友好拒绝
```

### 系统特点

✅ **4 分类路由** - 急症、初诊、复诊、非业务完整覆盖
✅ **结构化数据提取** - 症状、年龄、病史等自动解析
✅ **临床决策支持** - 科研初筛、试验匹配、就诊指引
✅ **多轮对话支持** - 动态追问、信息补全
✅ **完整错误处理** - 所有 LLM 调用均有 fallback
✅ **免责声明** - 明确标注非医疗诊断

### 常见问题

**Q: 如何更改 LLM 模型？**
A: 在 `cli_interactive.py` 第 28 行修改 `model_name` 参数

**Q: 如何自定义 API 密钥？**
A: 在 `run.py` 中修改环境变量或使用系统环境变量

**Q: 支持多轮对话吗？**
A: 支持！使用 `cli_interactive.py` 可进行多轮互动

---

**系统状态**: ✅ 生产就绪
