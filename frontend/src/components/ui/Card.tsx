import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`.trim()}>{children}</div>;
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h2 className="mb-2 text-lg font-semibold text-ink">{children}</h2>;
}
