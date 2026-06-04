"""
setup.py - 项目初始化脚本
检查依赖、配置环境、生成示例文件
"""
import os
import sys
import subprocess
from pathlib import Path


def check_python_version():
    """检查 Python 版本"""
    if sys.version_info < (3, 9):
        print(f"❌ Python 版本过低 ({sys.version_info.major}.{sys.version_info.minor})")
        print("   请升级至 Python 3.9+ (推荐 3.10+)")
        return False
    print(f"✅ Python 版本检查通过: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def check_and_install_dependencies():
    """检查并安装依赖"""
    print("\n" + "="*70)
    print("检查依赖包...")
    print("="*70)
    
    requirements = [
        "langchain>=0.3.1",
        "langgraph>=0.2.50",
        "pydantic>=2.6.4",
        "python-dotenv>=1.0.0",
        "openai>=1.35.13",
        "httpx>=0.27.0",
    ]
    
    try:
        import pkg_resources
        installed_packages = {pkg.key for pkg in pkg_resources.working_set}
        
        missing_packages = []
        for req in requirements:
            pkg_name = req.split(">=")[0].replace("-", "_").lower()
            if pkg_name not in installed_packages:
                missing_packages.append(req)
        
        if missing_packages:
            print(f"\n缺少依赖包: {missing_packages}")
            response = input("\n是否要自动安装缺失的依赖？(y/n): ").lower()
            
            if response == 'y':
                print("\n正在安装依赖...")
                for package in missing_packages:
                    print(f"  安装 {package}...", end=" ")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                    print("✅")
                print("\n✅ 所有依赖已安装")
                return True
            else:
                print("⚠️  请手动安装依赖: pip install -r requirements.txt")
                return False
        else:
            print("✅ 所有依赖都已安装")
            return True
    
    except Exception as e:
        print(f"❌ 检查依赖时出错: {e}")
        print("   请手动运行: pip install -r requirements.txt")
        return False


def create_env_file():
    """创建 .env 文件"""
    print("\n" + "="*70)
    print("配置 API 环境变量...")
    print("="*70)
    
    env_file = ".env"
    
    if os.path.exists(env_file):
        response = input(f"\n⚠️  {env_file} 已存在，是否覆盖？(y/n): ").lower()
        if response != 'y':
            print("⏭️  跳过创建 .env 文件")
            return True
    
    print("\n请选择要使用的 LLM 服务：")
    print("1. 通义千问 (Qwen) - 推荐")
    print("2. OpenAI (GPT-4, GPT-3.5 等)")
    print("3. 其他兼容 OpenAI 的 API")
    
    choice = input("\n请输入选项 (1-3): ").strip()
    
    env_content = ""
    
    if choice == "1":
        print("\n通义千问配置:")
        api_key = input("  请输入 TONGYI_API_KEY: ").strip()
        
        if api_key:
            env_content = f"""# ==================== 通义千问配置 ====================
TONGYI_API_KEY={api_key}
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/

# 模型名称选项: qwen-max-latest, qwen-max, qwen-plus
"""
            with open(env_file, "w") as f:
                f.write(env_content)
            print(f"✅ {env_file} 已创建")
            return True
        else:
            print("⚠️  未输入 API Key，跳过创建")
            return False
    
    elif choice == "2":
        print("\nOpenAI 配置:")
        api_key = input("  请输入 OPENAI_API_KEY: ").strip()
        
        if api_key:
            env_content = f"""# ==================== OpenAI 配置 ====================
OPENAI_API_KEY={api_key}
OPENAI_BASE_URL=https://api.openai.com/v1

# 模型名称选项: gpt-4, gpt-3.5-turbo, gpt-4-turbo
"""
            with open(env_file, "w") as f:
                f.write(env_content)
            print(f"✅ {env_file} 已创建")
            return True
        else:
            print("⚠️  未输入 API Key，跳过创建")
            return False
    
    elif choice == "3":
        print("\n其他 API 配置:")
        api_key = input("  请输入 API_KEY: ").strip()
        base_url = input("  请输入 BASE_URL (例: http://localhost:8000/v1): ").strip()
        
        if api_key and base_url:
            env_content = f"""# ==================== 自定义 API 配置 ====================
OPENAI_API_KEY={api_key}
OPENAI_BASE_URL={base_url}
"""
            with open(env_file, "w") as f:
                f.write(env_content)
            print(f"✅ {env_file} 已创建")
            return True
        else:
            print("⚠️  输入不完整，跳过创建")
            return False
    
    else:
        print("❌ 无效的选项")
        return False


def test_llm_connection():
    """测试 LLM 连接"""
    print("\n" + "="*70)
    print("测试 LLM 连接...")
    print("="*70 + "\n")
    
    try:
        from llm_config import get_llm
        
        print("正在初始化 LLM...", end=" ")
        llm = get_llm()
        print("✅\n")
        
        print("测试 LLM 调用...", end=" ")
        response = llm.invoke("你是谁？请简要回答。")
        print("✅\n")
        
        print("🤖 LLM 响应:")
        print(f"  {response.content[:100]}...\n")
        
        return True
    
    except Exception as e:
        print(f"❌\n\n连接失败: {e}")
        print("\n可能的原因:")
        print("  1. API Key 未配置或错误")
        print("  2. 网络连接问题")
        print("  3. API 服务暂时不可用")
        print("\n请检查 .env 文件的配置或网络连接")
        return False


def print_summary():
    """打印总结信息"""
    summary = """
╔══════════════════════════════════════════════════════════════════╗
║          🏥 预问诊 Agent - 初始化完成！                          ║
╚══════════════════════════════════════════════════════════════════╝

📚 接下来的步骤:

1️⃣  快速开始 (推荐)
    python cli_interactive.py
    
    这会启动交互式命令行界面，您可以直接对话

2️⃣  运行演示脚本
    python main.py
    
    这会运行几个预设的测试用例

3️⃣  集成测试
    python test_integration.py
    
    这会运行完整的系统集成测试

4️⃣  在代码中使用
    from main import ConsultationAgent
    import asyncio
    
    async def main():
        agent = ConsultationAgent()
        response = await agent.run_consultation("您的症状描述...")
        print(response)
    
    asyncio.run(main())

📖 更多信息请查看 README.md

⚠️  重要提示:
   - 本系统仅供学习和研究使用
   - 所有输出都包含医疗免责声明
   - 不能替代真实医疗诊断

╚══════════════════════════════════════════════════════════════════╝
"""
    print(summary)


def main():
    """主初始化流程"""
    print("\n" + "#"*70)
    print("# 🏥 预问诊 Agent 初始化脚本")
    print("#"*70)
    
    # 第一步：检查 Python 版本
    if not check_python_version():
        sys.exit(1)
    
    # 第二步：检查和安装依赖
    if not check_and_install_dependencies():
        sys.exit(1)
    
    # 第三步：创建 .env 文件
    if not create_env_file():
        print("\n⚠️  警告：未配置 API 环境变量")
        print("   请查看 .env.example 或手动创建 .env 文件")
    
    # 第四步：测试连接
    try:
        if not test_llm_connection():
            print("\n⚠️  LLM 连接测试失败，但您可以稍后重试")
    except Exception as e:
        print(f"\n⚠️  无法测试连接: {e}")
        print("   您可以稍后手动测试")
    
    # 打印总结
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n初始化已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 初始化出现错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
