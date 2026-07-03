from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    """
    Immutable configuration for a single model.
    frozen=True means no one can accidentally change these values.
    """
    model_id: str
    provider: str
    context_window: int
    max_output_tokens: int
    supports_streaming: bool
    supports_tool_calling: bool
    cost_per_1k_input_tokens: float
    cost_per_1k_output_tokens: float
    embedding_dimensions: int | None = None


MODEL_TABLE: dict[str, ModelConfig] = {

    "gemini-2.5-flash": ModelConfig(
        model_id="gemini-2.5-flash",
        provider="gemini",
        context_window=1_000_000,
        max_output_tokens=8192,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.000075,
        cost_per_1k_output_tokens=0.0003,
    ),
    "models/text-embedding-004": ModelConfig(
        model_id="models/text-embedding-004",
        provider="gemini",
        context_window=2048,
        max_output_tokens=0,
        supports_streaming=False,
        supports_tool_calling=False,
        cost_per_1k_input_tokens=0.00001,
        cost_per_1k_output_tokens=0.0,
        embedding_dimensions=768,
    ),

    # ── Amazon Bedrock Models (Production) ────────────────────
    "anthropic.claude-3-sonnet-20240229-v1:0": ModelConfig(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        provider="bedrock",
        context_window=200_000,
        max_output_tokens=4096,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.003,
        cost_per_1k_output_tokens=0.015,
    ),
    "anthropic.claude-3-haiku-20240307-v1:0": ModelConfig(
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        provider="bedrock",
        context_window=200_000,
        max_output_tokens=4096,
        supports_streaming=True,
        supports_tool_calling=True,
        cost_per_1k_input_tokens=0.00025,
        cost_per_1k_output_tokens=0.00125,
    ),
    "amazon.titan-embed-text-v2:0": ModelConfig(
        model_id="amazon.titan-embed-text-v2:0",
        provider="bedrock",
        context_window=8192,
        max_output_tokens=0,
        supports_streaming=False,
        supports_tool_calling=False,
        cost_per_1k_input_tokens=0.00002,
        cost_per_1k_output_tokens=0.0,
        embedding_dimensions=1024,
    ),
}


def get_model_config(model_id: str) -> ModelConfig:
    """
    Look up a model by ID.
    Raises a clear error if the model doesn't exist.
    """
    if model_id not in MODEL_TABLE:
        available = list(MODEL_TABLE.keys())
        raise ValueError(
            f"Unknown model: '{model_id}'.\n"
            f"Available models: {available}"
        )
    return MODEL_TABLE[model_id]