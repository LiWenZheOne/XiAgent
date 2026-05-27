import type { TaskNodeExecution } from "../../api/types";

export function imageChoicePreviewNode(): TaskNodeExecution {
  return {
    node_execution_id: "preview-image-choice",
    node_id: "preview_image_choice",
    node_ref: "system.user_choice.v1",
    status: "waiting",
    input_snapshot: {
      question: "选择一张候选图",
      candidates: [
        {
          id: "candidate-a",
          label: "候选 A",
          image_url: "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=480&q=80",
        },
        {
          id: "candidate-b",
          label: "候选 B",
          image_url: "https://images.unsplash.com/photo-1493246507139-91e8fad9978e?auto=format&fit=crop&w=480&q=80",
        },
        {
          id: "candidate-c",
          label: "候选 C",
          image_url: "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=480&q=80",
        },
      ],
    },
  };
}
