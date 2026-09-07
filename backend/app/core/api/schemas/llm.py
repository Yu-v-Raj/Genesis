"""Pydantic REST contracts for the provider-neutral LLM Runtime."""

from pydantic import BaseModel, Field

from backend.app.core.llm_runtime.domain.models import (
    GenerationConfig,
    LLMModel,
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ToolDefinition,
)


class MessageRequest(BaseModel):
    role: MessageRole
    content: str
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_domain(self) -> Message:
        return Message(role=self.role, content=self.content, metadata=self.metadata)


class ModelRequest(BaseModel):
    provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)

    def to_domain(self) -> LLMModel:
        return LLMModel(provider=self.provider, model_name=self.model_name)


class GenerationRequest(BaseModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)

    def to_domain(self) -> GenerationConfig:
        return GenerationConfig(temperature=self.temperature, max_tokens=self.max_tokens)


class ToolDefinitionRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters: dict[str, object] = Field(default_factory=dict)

    def to_domain(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class GenerateRequest(BaseModel):
    model: ModelRequest
    messages: list[MessageRequest] = Field(min_length=1)
    generation: GenerationRequest = Field(default_factory=GenerationRequest)
    tools: list[ToolDefinitionRequest] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_domain(self) -> LLMRequest:
        return LLMRequest(
            model=self.model.to_domain(),
            messages=tuple(message.to_domain() for message in self.messages),
            generation=self.generation.to_domain(),
            tools=tuple(tool.to_domain() for tool in self.tools),
            metadata=self.metadata,
        )


class ModelResponse(BaseModel):
    provider: str
    model_name: str
    capabilities: list[str]
    metadata: dict[str, object]

    @classmethod
    def from_domain(cls, model: LLMModel) -> "ModelResponse":
        return cls(provider=model.provider, model_name=model.model_name, capabilities=sorted(model.capabilities), metadata=dict(model.metadata))


class ProviderListResponse(BaseModel):
    providers: list[str]


class ModelListResponse(BaseModel):
    models: list[ModelResponse]


class UsageResponse(BaseModel):
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class ToolCallResponse(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, object]


class GenerateResponse(BaseModel):
    content: str | None
    model: ModelResponse
    finish_reason: str | None
    usage: UsageResponse
    tool_calls: list[ToolCallResponse]
    metadata: dict[str, object]

    @classmethod
    def from_domain(cls, response: LLMResponse) -> "GenerateResponse":
        return cls(content=response.content, model=ModelResponse.from_domain(response.model), finish_reason=response.finish_reason, usage=UsageResponse(input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens, total_tokens=response.usage.total_tokens), tool_calls=[ToolCallResponse(call_id=call.call_id, name=call.name, arguments=dict(call.arguments)) for call in response.tool_calls], metadata=dict(response.metadata))
