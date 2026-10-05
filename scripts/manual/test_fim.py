from core.llm import call_fim

def main():
    prefix = "def add(a, b):\n    "
    suffix = "\n    return result"

    print("=== 前缀 ===")
    print(repr(prefix))
    print("=== 后缀 ===")
    print(repr(suffix))
    print("\n正在请求补全...")

    completion = call_fim(prefix=prefix, suffix=suffix)

    print("\n=== 模型补全内容 ===")
    print(completion)
    print("=====================")

    full_code = prefix + completion + suffix
    print("\n=== 拼接后的完整代码 ===")
    print(full_code)

if __name__ == "__main__":
    main()