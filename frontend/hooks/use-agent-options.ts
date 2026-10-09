"use client";

import { useCallback, useEffect, useState } from "react";

import { AgentService } from "@/services/agent.service";
import { ToolService } from "@/services/tool.service";
import type { LLMModelOption } from "@/types/agents";
import type { ToolDefinition } from "@/types/tools";

export interface AgentOptions {
  /** Null until loaded, so readiness never reports a model as missing prematurely. */
  models: LLMModelOption[] | null;
  tools: ToolDefinition[] | null;
  error: string | null;
  reload: () => Promise<void>;
}

/** Load the models and tools an Agent can be configured with from the live runtimes. */
export function useAgentOptions(): AgentOptions {
  const [models, setModels] = useState<LLMModelOption[] | null>(null);
  const [tools, setTools] = useState<ToolDefinition[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [modelList, toolList] = await Promise.all([AgentService.models(), ToolService.list()]);
      setModels(modelList.models);
      setTools(toolList.tools);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load Agent options.");
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void reload());
  }, [reload]);

  return { models, tools, error, reload };
}
