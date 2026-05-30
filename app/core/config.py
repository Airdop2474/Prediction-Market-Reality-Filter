from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "deepseek-chat")

    # Base URL 可通过 .env 的 OPENAI_BASE_URL 覆盖
    # DeepSeek:  https://api.deepseek.com
    # DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1
    # OpenAI:    留空（使用 SDK 默认值）
    DASHSCOPE_BASE_URL: str = os.getenv(
        "OPENAI_BASE_URL",
        "https://api.deepseek.com",
    )

    GNEWS_MAX_RESULTS: int = int(os.getenv("GNEWS_MAX_RESULTS", "10"))
    MARKET_SCAN_LIMIT: int = int(os.getenv("MARKET_SCAN_LIMIT", "5"))
    MEMORY_FILE: str = os.getenv(
        "MEMORY_FILE",
        os.path.join(
            os.path.dirname(__file__), "..", "..", "agent_memory.json"
        ),
    )


settings = Settings()
