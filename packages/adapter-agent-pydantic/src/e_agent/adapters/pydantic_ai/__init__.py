"""Pydantic AI driver adapter (ADR 0004). The only package that imports pydantic_ai."""

from .driver import PydanticAiDriver, ToolSpec, ollama_model

__all__ = ["PydanticAiDriver", "ToolSpec", "ollama_model"]
