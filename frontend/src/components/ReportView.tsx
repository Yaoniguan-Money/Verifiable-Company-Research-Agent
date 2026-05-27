import { useMemo } from "react";
import ReactMarkdown from "react-markdown";

import type { Citation, Report, ResearchTask } from "../types";

const SECTION_ALIASES: Record<string, string> = {
  要点: "核心发现",
  "附录：材料与核对说明": "附录",
  "附录（材料与处理说明）": "附录",
};

const PRIMARY_SECTIONS = ["总结", "核心发现", "补充背景"];
const HIDDEN_PRIMARY_WHEN_EMPTY = new Set(["补充背景"]);

interface ReportSection {
  heading: string;
  body: string;
}

function normalizeHeading(heading: string): string {
  const clean = heading.trim();
  return SECTION_ALIASES[clean] ?? clean;
}

function parseSections(markdown: string): {
  preface: string;
  sections: ReportSection[];
} {
  const lines = markdown.split("\n");
  const sections: ReportSection[] = [];
  let current: ReportSection | null = null;
  const prefaceLines: string[] = [];

  for (const line of lines) {
    const match = line.match(/^##\s+(.+?)\s*$/);
    if (match) {
      if (current) sections.push(current);
      current = { heading: normalizeHeading(match[1]), body: "" };
      continue;
    }
    if (current) {
      current.body += (current.body ? "\n" : "") + line;
    } else if (line.trim() && !line.startsWith("# ")) {
      prefaceLines.push(line);
    }
  }
  if (current) sections.push(current);
  return { preface: prefaceLines.join("\n").trim(), sections };
}

function pickSection(sections: ReportSection[], heading: string): ReportSection | null {
  return sections.find((s) => normalizeHeading(s.heading) === heading) ?? null;
}

function isEmptyOptionalSection(section: ReportSection): boolean {
  if (!HIDDEN_PRIMARY_WHEN_EMPTY.has(section.heading)) return false;
  const body = section.body.trim();
  return !body || /暂无|没有|无额外|未抽取/.test(body);
}

interface UniqueSource {
  url: string | null;
  title: string;
  count: number;
}

function dedupeCitations(citations: Citation[]): UniqueSource[] {
  const map = new Map<string, UniqueSource>();
  for (const c of citations) {
    const key = c.url || `${c.title}`;
    const existing = map.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      map.set(key, { url: c.url, title: c.title || "未命名来源", count: 1 });
    }
  }
  return [...map.values()];
}

function MarkdownBlock({ children }: { children: string }) {
  const trimmed = children.trim();
  if (!trimmed) return null;
  return (
    <div className="prose prose-slate max-w-none prose-headings:font-semibold prose-p:my-2 prose-li:my-0.5">
      <ReactMarkdown>{trimmed}</ReactMarkdown>
    </div>
  );
}

export function ReportView({
  task,
  report,
}: {
  task: ResearchTask | null;
  report: Report | null;
}) {
  const parsed = useMemo(
    () => (report ? parseSections(report.content) : { preface: "", sections: [] }),
    [report],
  );
  const summary = pickSection(parsed.sections, "总结");
  const primary = PRIMARY_SECTIONS.filter((h) => h !== "总结")
    .map((h) => pickSection(parsed.sections, h))
    .filter((s): s is ReportSection => Boolean(s && s.body.trim()))
    .filter((s) => !isEmptyOptionalSection(s));
  const secondary = parsed.sections.filter(
    (s) =>
      !PRIMARY_SECTIONS.includes(s.heading) &&
      !["公开资料来源", "免责声明"].includes(s.heading),
  );
  const uniqueSources = report ? dedupeCitations(report.citations) : [];

  if (!report) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-slate-500">报告尚未生成。</p>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <header className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs uppercase tracking-[0.18em] text-slate-400">
          {task?.company_name ?? "-"}
        </p>
        <h1 className="mt-1 text-xl font-semibold text-ink">
          {task?.question ?? report.title ?? "研究报告"}
        </h1>
        {summary?.body ? (
          <div className="mt-3 rounded-xl bg-slate-50 p-4 text-[15px] leading-7 text-slate-800">
            <MarkdownBlock>{summary.body}</MarkdownBlock>
          </div>
        ) : null}
      </header>

      {primary.length > 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {primary.map((section) => (
            <section key={section.heading} className="mb-4 last:mb-0">
              <h2 className="mb-2 text-base font-semibold text-ink">{section.heading}</h2>
              <MarkdownBlock>{section.body}</MarkdownBlock>
            </section>
          ))}
        </div>
      ) : null}

      {uniqueSources.length > 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-ink">来源</h2>
          <ul className="space-y-2 text-sm">
            {uniqueSources.map((src, idx) => (
              <li key={`${src.url ?? src.title}-${idx}`} className="flex items-start gap-3">
                <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-50 px-1.5 text-xs font-medium text-accent">
                  {idx + 1}
                </span>
                <div className="flex-1">
                  <div className="text-slate-800">{src.title}</div>
                  {src.url ? (
                    <a
                      className="break-all text-xs text-accent underline-offset-2 hover:underline"
                      href={src.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {src.url}
                    </a>
                  ) : (
                    <span className="text-xs text-slate-400">无 URL</span>
                  )}
                  {src.count > 1 ? (
                    <span className="ml-2 text-xs text-slate-400">引用 {src.count} 次</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {secondary.length > 0 ? (
        <details className="rounded-2xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
          <summary className="cursor-pointer select-none text-slate-600">
            报告细节（风险观察 / 附录 / 材料与处理说明）
          </summary>
          <div className="mt-3 space-y-4">
            {secondary.map((section) => (
              <section key={section.heading}>
                <h3 className="mb-1 font-medium text-slate-700">{section.heading}</h3>
                <MarkdownBlock>{section.body}</MarkdownBlock>
              </section>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

