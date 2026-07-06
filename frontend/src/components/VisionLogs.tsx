import { useEffect, useRef, useState } from "react";

interface Props {
  taskId: string | null;
  isRunning: boolean;
}

export default function VisionLogs({ taskId, isRunning }: Props) {
  const [logs, setLogs] = useState<string[]>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!taskId || !isRunning) {
      setLogs([]);
      return;
    }

    const eventSource = new EventSource(`/api/assets/index/${taskId}/logs`);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      setLogs((prev) => [...prev, event.data]);
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [taskId, isRunning]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  if (!isRunning || logs.length === 0) {
    return null;
  }

  return (
    <div className="mt-2 p-2 bg-[var(--color-void)] text-[var(--color-signal-green)] rounded text-xs font-mono max-h-40 overflow-y-auto">
      {logs.map((log, i) => (
        <div key={i}>{log}</div>
      ))}
      <div ref={logsEndRef} />
    </div>
  );
}
