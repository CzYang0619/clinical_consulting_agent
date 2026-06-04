#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动脚本 - 设置环境变量并运行主程序
"""
import os
import subprocess
import sys

# 设置环境变量
os.environ['TONGYI_API_KEY'] = 'sk-9f480394f3874b2d98797649ffef405f'
os.environ['OPENAI_BASE_URL'] = 'https://dashscope.aliyuncs.com/compatible-mode/v1'

# 运行主程序
if __name__ == '__main__':
    from main import main
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中止了程序。")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 程序出现错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
