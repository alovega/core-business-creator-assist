from __future__ import annotations

from dataclasses import dataclass

from flask import current_app


class AIProviderError(RuntimeError):
    """Raised when the configured AI provider cannot generate a reply."""


@dataclass(frozen=True)
class AIProviderResult:
    text: str
    request_id: str | None = None


class OpenAIReplyProvider:
    """Small provider adapter so the rest of the app is not tied to an SDK."""

    def generate(self, *, instructions: str, input_text: str) -> AIProviderResult:
        api_key = (current_app.config.get("AI_API_KEY") or "").strip()
        model = (current_app.config.get("AI_MODEL") or "").strip()

        if not api_key:
            raise AIProviderError("AI provider is not configured")
        if not model:
            raise AIProviderError("AI model is not configured")

        try:
            from openai import OpenAI, OpenAIError
        except ImportError as exc:
            raise AIProviderError("OpenAI SDK is not installed") from exc

        try:
            client = OpenAI(
                api_key=api_key,
                timeout=12.0,
                max_retries=1,
            )
            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=input_text,
                max_output_tokens=250,
                store=False,
            )
        except OpenAIError as exc:
            raise AIProviderError("AI provider request failed") from exc
        except Exception as exc:
            # Keep SDK/network implementation details out of API responses.
            raise AIProviderError("AI provider request failed") from exc

        text = (response.output_text or "").strip()
        if not text:
            raise AIProviderError("AI provider returned an empty reply")

        return AIProviderResult(
            text=text,
            request_id=getattr(response, "_request_id", None),
        )