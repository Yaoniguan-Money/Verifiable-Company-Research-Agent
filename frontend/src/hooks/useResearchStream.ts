import { useEffect, useState } from "react";

export type StreamEvent = {
  type: string;
  task_id?: string;
  step?: string;
  token?: string;
  report_id?: string;
  error?: string;
  timestamp?: string;
};

export function useResearchStream(taskId: string | null, enabled: boolean) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streamText, setStreamText] = useState("");

  useEffect(() => {
    if (!taskId || !enabled) {
      return;
    }
    const source = new EventSource(`/api/research/tasks/${taskId}/stream`);
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as StreamEvent;
        setEvents((prev) => [...prev, event]);
        if (event.type === "report.streaming" && event.token) {
          setStreamText((prev) => prev + event.token);
        }
      } catch {
        // 忽略非 JSON 心跳
      }
    };
    source.onerror = () => source.close();
    return () => source.close();
  }, [taskId, enabled]);

  return { events, streamText };
}
