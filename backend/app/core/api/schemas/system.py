"""Pydantic response models for read-only Genesis system endpoints."""

from pydantic import BaseModel


class SystemHealthResponse(BaseModel):
    """Current process health and version information."""

    status: str
    version: str
    uptime: float


class SystemRuntimeResponse(BaseModel):
    """Current Genesis runtime lifecycle state."""

    state: str


class SystemServicesResponse(BaseModel):
    """Registered Core service names."""

    services: list[str]


class SystemToolsResponse(BaseModel):
    """Registered tool names."""

    tools: list[str]


class SystemPluginsResponse(BaseModel):
    """Registered plugin names."""

    plugins: list[str]


class SystemMemoryResponse(BaseModel):
    """Registered memory provider names."""

    providers: list[str]


class SystemWorkflowsResponse(BaseModel):
    """Registered workflow names."""

    workflows: list[str]
