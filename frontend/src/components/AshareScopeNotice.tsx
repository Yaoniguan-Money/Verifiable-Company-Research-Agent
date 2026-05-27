/** 说明当前公开资料检索主要覆盖 A 股巨潮披露，避免用户误填港股/美股名称。 */
export function AshareScopeNotice({ className = "" }: { className?: string }) {
  return (
    <div
      className={`rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950 ${className}`.trim()}
      role="note"
    >
      <p className="font-medium">检索范围提示</p>
      <p className="mt-1 leading-relaxed text-amber-900/90">
        当前默认联网搜索主要对接<strong className="font-semibold">巨潮 A 股</strong>
        上市公司公告与年报（沪深主板、创业板、科创板）。请填写在 A 股上市的公司全称或常用简称。
      </p>
      <p className="mt-1 text-amber-800/85">
        纯港股、美股主体通常无法匹配公告来源，任务可能在收集资料阶段失败。
      </p>
    </div>
  );
}
