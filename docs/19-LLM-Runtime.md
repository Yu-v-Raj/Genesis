# LLM Runtime

Genesis needs an LLM Runtime so Agents can use language models without knowing an SDK, API key format, or provider response shape. v0.9A provides that boundary only; it does not implement agent reasoning, planning, streaming, or tool-execution loops.

```text
Agent / future Agent Intelligence
            |
       LLMManager
            |
   LLMProviderRegistry
            |
     LLMProvider adapter
            |
      External LLM API
```

## Concepts

- **Provider** is the external service integration, such as OpenAI.
- **Model** is a provider-neutral `provider` + `model_name` record.
- **Message** has one of four normalized roles: `system`, `user`, `assistant`, or `tool`.
- **Request** contains a model, ordered messages, small portable generation settings (`temperature`, `max_tokens`), and metadata.
- **Response** contains generated content, normalized finish reason and usage, plus reserved normalized `tool_calls` for a future intelligence layer.

The OpenAI adapter owns SDK imports and response parsing. The manager and domain never receive OpenAI SDK objects. Provider failures are translated into stable Genesis exceptions, and API keys/prompt content are excluded from lifecycle events.

## Events

The existing EventBus carries `llm.requested`, `llm.completed`, and `llm.failed`. Their payloads contain only provider/model, duration, usage where supplied, and a failure type. They flow through the established observability and realtime pipeline.

## Configuration and API

`OPENAI_API_KEY` is loaded as a `SecretStr`; `OPENAI_MODEL` defaults to `gpt-4.1-mini`; `OPENAI_TIMEOUT_SECONDS` defaults to 30 seconds. The OpenAI SDK is a project dependency but is imported lazily, so a missing key or SDK returns a clear configuration error instead of breaking startup.

- `GET /api/llm/providers` lists registered adapters.
- `GET /api/llm/models` lists configured model records.
- `POST /api/llm/generate` accepts Genesis request schemas and returns normalized Genesis response schemas.

## Future work

Streaming can be added as another provider/runtime operation without changing request or response records. Tool calls are represented in `LLMResponse` but are deliberately not dispatched. A future Agent Intelligence layer will decide whether to call Tool, Memory, or Workflow Runtime, return tool results as `tool` messages, and request a final LLM response.
