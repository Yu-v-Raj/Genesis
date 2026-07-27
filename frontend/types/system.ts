// Raw shapes returned by the Genesis System API.
// These describe the wire format only — UI-facing view models
// (StatusCardData, ServiceItem, etc.) live alongside their components
// and are produced by the hook, not by this file.

export interface HealthApiResponse {
  status: string;
  version: string;
  uptime: number;
}

export interface RuntimeApiResponse {
  state: string;
}

interface SystemResourceApiItem {
  name: string;
  description: string;
  status: string;
}

export type ServiceApiItem = SystemResourceApiItem;

export interface ServicesApiResponse {
  services: ServiceApiItem[];
}

export type ToolApiItem = SystemResourceApiItem;

export interface ToolsApiResponse {
  tools: ToolApiItem[];
}

export type PluginApiItem = SystemResourceApiItem;

export interface PluginsApiResponse {
  plugins: PluginApiItem[];
}

export type MemoryProviderApiItem = SystemResourceApiItem;

export interface MemoryApiResponse {
  providers: MemoryProviderApiItem[];
}

export type WorkflowApiItem = SystemResourceApiItem;

export interface WorkflowsApiResponse {
  workflows: WorkflowApiItem[];
}
