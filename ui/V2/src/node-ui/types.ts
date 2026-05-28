import type { ReactElement } from "react";
import type { TaskNodeExecution, WorkflowNodeSpec, WorkflowSnapshot, NodeUiControlConfig } from "../api/types";

export interface NodeUiControlProps {
  config: NodeUiControlConfig;
  node: TaskNodeExecution;
  nodeSpec?: WorkflowNodeSpec;
  snapshot?: WorkflowSnapshot | null;
  slot?: "input" | "output" | "interaction" | "detail";
  value?: unknown;
  title?: string;
  imageAltPrefix?: string;
  projectId?: string;
  busy?: boolean;
  preview?: boolean;
  onSubmit?: (output: Record<string, unknown>) => void;
}

export type NodeUiComponent = (props: NodeUiControlProps) => ReactElement;

export interface ImageChoiceItem {
  id: string;
  label: string;
  imageUrl: string;
  raw: Record<string, unknown>;
  index: number;
}
