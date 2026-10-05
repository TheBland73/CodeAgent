import os
from dotenv import load_dotenv
from pathlib import Path

# 显式加载 CodeAgent 项目根目录下的 .env
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

class Settings:
    # 从环境变量读取 API Key
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY")

    # DeepSeek 的 OpenAI 兼容 Base URL
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"

    # 选择当前的主流模型
    DEFAULT_MODEL: str = "deepseek-flash"

settings = Settings()

# 自动检测（简单）：如果API Key 未设置，则抛出异常
if not settings.DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY 未设置，请检查 .env 文件。")