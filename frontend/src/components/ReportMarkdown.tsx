import ReactMarkdown from "react-markdown";

import { CitationHover } from "./CitationHover";
import type { Citation } from "../types";

export function ReportMarkdown({
  content,
  citations,
}: {
  content: string;
  citations: Citation[];
}) {
  return (
    <article className="card prose prose-slate max-w-none">
      <ReactMarkdown>{content}</ReactMarkdown>
      {citations.length > 0 ? (
        <footer className="mt-6 border-t border-slate-100 pt-4">
          <h3 className="text-sm font-medium text-slate-600">引用来源</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {citations.map((item, index) => (
              <CitationHover key={`${item.chunk_id}-${index}`} citation={item} index={index + 1} />
            ))}
          </div>
        </footer>
      ) : null}
    </article>
  );
}
