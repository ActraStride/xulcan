"""Model Catalog - A unified directory of LLM identifiers for Xulcan Blueprints.

This module provides constants for IntelliSense and IDE autocomplete.
It does NOT restrict Xulcan; you can always pass a custom string directly
to the AgentBlueprint if a model is not listed here.
"""

class GoogleModels:
    """Official identifiers for Google Gemini via Google GenAI SDK."""
    # Production
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    GEMINI_1_5_FLASH_8B = "gemini-1.5-flash-8b"
    # Experimental / Reasoning
    GEMINI_2_0_FLASH_THINKING = "gemini-2.0-flash-thinking-exp"

class OpenAIModels:
    """Official identifiers for OpenAI API."""
    # Omnimodel (Standard)
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_TURBO = "gpt-4-turbo"
    # Reasoning (o-series)
    O1 = "o1"
    O1_MINI = "o1-mini"
    O3_MINI = "o3-mini"

class AnthropicModels:
    """Official identifiers for Anthropic Claude API."""
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet-latest"
    CLAUDE_3_5_HAIKU = "claude-3-5-haiku-latest"
    CLAUDE_3_OPUS = "claude-3-opus-latest"
    # Legacy specific versions if strict reproduction is needed
    CLAUDE_3_5_SONNET_20241022 = "claude-3-5-sonnet-20241022"

class XaiModels:
    """Official identifiers for xAI (Grok) API."""
    GROK_2 = "grok-2-latest"
    GROK_BETA = "grok-beta"
    GROK_VISION = "grok-2-vision-latest"

class LocalOllamaModels:
    """Standard tags for Local models running on Ollama."""
    
    class DeepSeek:
        R1_1_5B = "deepseek-r1:1.5b"  # Fast local reasoning
        R1_7B = "deepseek-r1:7b"      # Sweet spot for 8GB VRAM
        R1_14B = "deepseek-r1:14b"
        R1_32B = "deepseek-r1:32b"    # The RunPod 24GB King
        CODER_V2 = "deepseek-coder-v2"
        
    class Qwen:
        QWEN_0_5B = "qwen2.5:0.5b"    # Swarm worker / Router
        QWEN_7B = "qwen2.5:7b"
        CODER_7B = "qwen2.5-coder:7b" # Tier 1 Tool Calling for 8GB VRAM
        CODER_32B = "qwen2.5-coder:32b"
        QWEN_72B = "qwen2.5:72b"      # The Open Source Titan

    class Llama:
        LLAMA_3_2_1B = "llama3.2:1b"
        LLAMA_3_2_3B = "llama3.2:3b"
        LLAMA_3_1_8B = "llama3.1:8b"
        LLAMA_3_3_70B = "llama3.3:70b" # Tier 1 logic, requires 48GB+ VRAM
        
    class Utility:
        PHI_4 = "phi4"                # Microsoft's dense logic model
        COMMAND_R = "command-r"       # Cohere's RAG & Tool expert
        MISTRAL = "mistral"
        MIXTRAL_8x7B = "mixtral:8x7b" # Fast MoE

class GroqModels:
    """Identifiers for the ultra-fast LPU inference engine (Groq API)."""
    LLAMA_3_3_70B = "llama-3.3-70b-versatile"
    DEEPSEEK_R1_70B = "deepseek-r1-distill-llama-70b"
    QWEN_CODER_32B = "qwen-2.5-coder-32b"
    MIXTRAL_8X7B = "mixtral-8x7b-32768"

class OpenRouterModels:
    """Common identifiers for OpenRouter (The Universal Aggregator)."""
    ANTHROPIC_SONNET = "anthropic/claude-3.5-sonnet"
    OPENAI_GPT_4O = "openai/gpt-4o"
    GOOGLE_GEMINI_FLASH = "google/gemini-2.5-flash"
    DEEPSEEK_R1 = "deepseek/deepseek-r1"
    LIQUID_LFM_40B = "liquid/lfm-40b"

# ==========================================
# UNIFIED EXPORT
# ==========================================
class ModelCatalog:
    """
    Main catalog to access all curated Xulcan models.
    Type `ModelCatalog.` in your IDE to explore providers.
    """
    Google = GoogleModels
    OpenAI = OpenAIModels
    Anthropic = AnthropicModels
    xAI = XaiModels
    Ollama = LocalOllamaModels
    Groq = GroqModels
    OpenRouter = OpenRouterModels