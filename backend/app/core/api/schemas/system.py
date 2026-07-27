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


class ServiceInfo(BaseModel):
    name: str
    description: str
    status: str


class ToolInfo(BaseModel):
    name: str
    description: str
    status: str


class PluginInfo(BaseModel):
    name: str
    description: str
    status: str


class MemoryProviderInfo(BaseModel):
    name: str
    description: str
    status: str


class WorkflowInfo(BaseModel):
    name: str
    description: str
    status: str


class SystemServicesResponse(BaseModel):
    services: list[ServiceInfo]


class SystemToolsResponse(BaseModel):
    tools: list[ToolInfo]


class SystemPluginsResponse(BaseModel):
    plugins: list[PluginInfo]


class SystemMemoryResponse(BaseModel):
    providers: list[MemoryProviderInfo]


class SystemWorkflowsResponse(BaseModel):
    workflows: list[WorkflowInfo]