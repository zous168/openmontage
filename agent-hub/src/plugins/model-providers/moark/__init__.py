"""模力方舟 (Gitee AI / moark.com) provider profile.

OpenAI-compatible chat completions at https://api.moark.com/v1.
Access tokens: https://moark.com/docs/organization/access-token
"""

from providers import register_provider
from providers.base import ProviderProfile

moark = ProviderProfile(
    name="moark",
    aliases=("gitee-ai", "gitee-ai-portal", "模力方舟"),
    display_name="模力方舟 (Gitee AI)",
    description="模力方舟 — Gitee AI OpenAI-compatible API (moark.com)",
    signup_url="https://moark.com/docs/organization/access-token",
    env_vars=("MOARK_API_KEY", "MOARK_BASE_URL"),
    base_url="https://api.moark.com/v1",
    default_aux_model="Qwen2.5-7B-Instruct",
    fallback_models=(
        "DeepSeek-R1",
        "DeepSeek-V3",
        "Qwen2.5-72B-Instruct",
        "Qwen2.5-7B-Instruct",
    ),
)

register_provider(moark)
