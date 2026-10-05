# FIM Prompt 模板（用于参考和调试，实际调用时无需手动拼接）
FIM_TEMPLATE = "<｜fim▁begin｜>{prefix}<｜fim▁hole｜>{suffix}<｜fim▁end｜>"

def build_fim_prompt(prefix: str, suffix: str) -> str:
    """
    构建 FIM 格式的原始 prompt 字符串（主要用于调试和日志）。
    实际调用 API 时，直接传递 prefix 和 suffix 参数即可。
    """
    return FIM_TEMPLATE.format(prefix=prefix, suffix=suffix)