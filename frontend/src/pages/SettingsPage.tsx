import { useCallback, useEffect, useState } from "react";

import { getFeatureFlags, resetFeatureFlags, updateFeatureFlag } from "../api";
import type { FeatureFlag } from "../types";

export function SettingsPage() {
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getFeatureFlags();
      setFlags(data.flags);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(name: string, current: unknown) {
    const next = !current;
    try {
      const res = await updateFeatureFlag(name, next);
      if (res.ok) {
        setFlags((prev) =>
          prev.map((f) => (f.name === name ? { ...f, value: next } : f)),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换失败");
    }
  }

  async function selectOption(name: string, option: string) {
    try {
      const res = await updateFeatureFlag(name, option);
      if (res.ok) {
        setFlags((prev) =>
          prev.map((f) => (f.name === name ? { ...f, value: option } : f)),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换失败");
    }
  }

  async function reset() {
    try {
      await resetFeatureFlags();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置失败");
    }
  }

  if (loading) {
    return <p className="text-sm text-slate-500">加载中...</p>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">
            Settings
          </p>
          <h1 className="text-3xl font-semibold">特性开关</h1>
          <p className="text-sm text-slate-600">
            切换即时生效并自动写入 .env，重启后保持。
          </p>
        </div>
        <button className="btn-primary" onClick={reset}>
          重置全部
        </button>
      </header>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="space-y-4">
        {flags.map((flag) => (
          <section key={flag.name} className="card space-y-2">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="font-medium">{flag.label}</h3>
                <p className="text-xs text-slate-500">{flag.description}</p>
                <p className="mt-1 font-mono text-xs text-slate-400">
                  {flag.name} · 默认 {String(flag.default)}
                </p>
              </div>
              {flag.options && flag.options.length > 0 ? (
                <div className="flex shrink-0 gap-2">
                  {flag.options.map((opt) => (
                    <button
                      key={opt}
                      className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                        String(flag.value) === opt
                          ? "border-accent bg-accent text-white"
                          : "border-slate-200 bg-white text-slate-600 hover:border-accent"
                      }`}
                      onClick={() => selectOption(flag.name, opt)}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full transition ${
                    flag.value ? "bg-accent" : "bg-slate-300"
                  }`}
                  onClick={() => toggle(flag.name, flag.value)}
                  aria-label={`切换 ${flag.label}`}
                >
                  <span
                    className={`inline-block h-5 w-5 rounded-full bg-white shadow transition ${
                      flag.value ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
              )}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
