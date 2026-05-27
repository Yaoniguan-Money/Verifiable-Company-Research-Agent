import { useState } from "react";

import type { Citation } from "../types";

export function CitationHover({ citation, index }: { citation: Citation; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <sup className="cursor-help rounded bg-blue-100 px-1 text-xs text-accent">[{index}]</sup>
      {open ? (
        <span className="absolute left-0 top-5 z-20 w-72 rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-lg">
          <div className="font-medium text-ink">{citation.title}</div>
          <div className="mt-1 break-all text-slate-500">{citation.url || "无 URL"}</div>
          <div className="mt-1 text-slate-400">chunk: {citation.chunk_id}</div>
        </span>
      ) : null}
    </span>
  );
}
