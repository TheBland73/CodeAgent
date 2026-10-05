from core.llm import call_chat
# .\venv2\Scripts\Activate.ps1 环境激活
def main():
    print("正在发送测试消息...")
    reply = call_chat(
        messages=[{"role": "user", "content": "你好"}],
        temperature=0.7,
    )
    print("\n=== 模型回复 ===")
    print(reply)
    print("=================")

if __name__ == "__main__":
    main()