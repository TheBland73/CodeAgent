# test_retry.py
from core.llm import _retry_call

call_count = {"n": 0}

def flaky():
    call_count["n"] += 1
    if call_count["n"] < 3:
        import openai
        raise openai.APIConnectionError(request=None)
    return "success"

result = _retry_call(flaky, max_retries=3, base_delay=0.2)
print(f"结果: {result}, 总共尝试 {call_count['n']} 次")