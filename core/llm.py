#LLM
from openai import OpenAI
from core.config import settings
import time
import openai
from core.cache import fim_cache

# 可重试的异常类型（网络抖动、限流、服务端临时错误）
RETRYABLE_EXCEPTIONS = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.RateLimitError,
    openai.InternalServerError,
)

# 初始化客户端，复用连接，提升后续调用性能
client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL
)
#
# FIM 补全需要使用 Beta 端点，单独创建一个客户端
fim_client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/beta"  # 为beta路径
)


def call_chat(
        messages: list,
        model: str = None,
        stream: bool = False,
        temperature: float = 1.0,
) -> str:
    """
    封装 DeepSeek Chat API 调用。

    Args:
        messages: 对话消息列表，格式为 [{"role": "user", "content": "..."}]
        model: 使用的模型名称，默认使用配置中的 DEFAULT_MODEL
        stream: 是否启用流式响应，默认 False
        temperature: 采样温度，控制随机性

    Returns:
        模型的回复文本
    """

    # call_chat 内部
    response = _retry_call(lambda: client.chat.completions.create(
        model=model or settings.DEFAULT_MODEL,
        messages=messages,
        stream=stream,
        temperature=temperature,
    ))

    if stream:
        # 流式响应需要迭代器处理，此处暂时只返回简单提示
        return "流式模式暂未在此封装中实现，请直接使用 client。"

    return response.choices[0].message.content

def call_fim(
    prefix: str,
    suffix: str,
    model: str = None,
    max_tokens: int = 128,
    temperature: float = 0.2,
    use_cache: bool = True,
) -> str:
    """
    调用 DeepSeek FIM 补全 API（带缓存）。

    Args:
        prefix: 光标前的代码内容
        suffix: 光标后的代码内容
        model: 模型名称，默认使用配置中的 DEFAULT_MODEL
        max_tokens: 最大生成 token 数
        temperature: 采样温度，代码补全建议使用较低值 (0.2 左右)

    Returns:
        模型补全的中间代码文本
    """
    model = model or settings.DEFAULT_MODEL
    # 缓存 key 必须包含所有影响输出的参数：
    # 只按 prefix 缓存会返回错误结果，因为同一 prefix 配不同 suffix 应有不同补全
    if use_cache:
        cached = fim_cache.get(model, prefix, suffix, max_tokens, temperature)
        if cached is not None:
            print(f"[缓存] FIM 命中 (prefix={len(prefix)}字符, suffix={len(suffix)}字符)")
            return cached

    # call_fim 内部：请求 beta 端点的 FIM 补全
    response = _retry_call(lambda: fim_client.completions.create(
        model=model,
        prompt=prefix,
        suffix=suffix,
        max_tokens=max_tokens,
        temperature=temperature,
    ))
    result = response.choices[0].text or ""  # 模型可能返回空补全，统一成空串

    if use_cache:
        fim_cache.set(result, model, prefix, suffix, max_tokens, temperature)
    return result

def _retry_call(fn, max_retries: int = 3, base_delay: float = 1.0):
    """
    带指数退避的重试封装。

    Args:
        fn: 无参的可调用对象，内部发起一次 API 调用
        max_retries: 最大尝试次数（含首次）
        base_delay: 首次重试前的等待秒数，之后每次翻倍

    Returns:
        fn 的返回值

    Raises:
        最后一次尝试的异常（如果全部失败）
    """
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except RETRYABLE_EXCEPTIONS as e:
            last_exc = e
            if attempt == max_retries:
                break
            delay = base_delay * (2 ** (attempt - 1))
            print(f"[重试] 第 {attempt} 次失败: {type(e).__name__}, {delay:.1f}s 后重试...")
            time.sleep(delay)
    raise last_exc