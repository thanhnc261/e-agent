# ADR 0021: LiteLLM as an explicit second model provider

Date: 2026-10-12. Status: Accepted (owner, 2026-10-14). Refines ADR 0001 (Ollama first, no silent cloud fallback).

## Context

The Pydantic AI driver accepts only Ollama (`DriverConfig.provider: Literal["ollama"]`,
`ollama_model()` refuses non-loopback endpoints and `-cloud` models). The owner asked to keep
Ollama as the default and also support LiteLLM, which exposes many model backends behind one
OpenAI-compatible proxy.

## Decision

- `DriverConfig.provider` becomes `Literal["ollama", "litellm"]`, default `"ollama"`.
- `litellm` uses Pydantic AI's `LiteLLMProvider` against a LiteLLM proxy whose URL comes from the
  environment variable named by `base_url_env` (default `E_AGENT_LITELLM_URL`, fallback
  `http://localhost:4000`). The endpoint must be loopback (`localhost`, `127.0.0.1`, `::1`) over
  http or https, with no userinfo, query or fragment, and the model name must be non-empty. The
  Ollama guard differs: it allows http only and also refuses `-cloud` and `:cloud` models.
- An API key, if the proxy needs one, comes from the environment variable named by `api_key_env`;
  the profile never contains the key, and the key never appears in errors, logs or evidence.
- The profile must name the provider explicitly to use LiteLLM. There is no fallback between
  providers: a missing model or an unreachable proxy rejects startup or fails the run.
- Evidence runtime metadata records `model_provider` next to `model`.

## Consequences

Which upstream model the proxy routes to (local or hosted) is configured in the operator's LiteLLM
proxy, outside e-agent; a hosted upstream is the operator's explicit choice, not a fallback, and
data-egress review for it belongs to that deployment. Model qualification evidence remains
per provider and model; a LiteLLM-routed model is not qualified by an Ollama run of a similar model.

## Verification

Unit tests for the endpoint guard and model construction; bootstrap tests that a `litellm` profile
builds a driver, that a missing model or a remote endpoint is rejected, and that the API key is read
from the named variable without being echoed.
