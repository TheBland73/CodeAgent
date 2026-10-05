from core.agent import run_agent

def main():
    task = """请帮我完成一个小调查：

1. 在 core/tools.py 里，search_code 函数用到了哪个辅助函数来定位 ripgrep 可执行文件？
2. 这个辅助函数的定义在第几行？
3. 它返回什么类型？

请先用工具检索确认，再告诉我答案。"""

    print("用户任务:")
    print(task)
    print()

    answer = run_agent(task, max_steps=8, verbose=True)

    print("\n" + "=" * 60)
    print("最终回答:")
    print("=" * 60)
    print(answer)


if __name__ == "__main__":
    main()