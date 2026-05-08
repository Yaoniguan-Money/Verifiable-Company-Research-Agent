import type { RegressionEvalCase, RegressionEvalSummary } from "../types";

const PUBLIC_REGRESSION_EVAL: RegressionEvalSummary = {
  case_count: 6,
  passed_count: 6,
  average_metric_coverage_ratio: 1.0,
  total_source_count: 6,
  total_fact_count: 117,
  cases: [
    {
      company_name: "sample_case_001",
      source_count: 1,
      fact_count: 22,
      metric_coverage_ratio: 1.0,
      missing_metric_groups: [],
      unexpected_metric_groups: [],
      passed: true,
    },
    {
      company_name: "sample_case_002",
      source_count: 1,
      fact_count: 16,
      metric_coverage_ratio: 1.0,
      missing_metric_groups: [],
      unexpected_metric_groups: [],
      passed: true,
    },
    {
      company_name: "sample_case_003",
      source_count: 1,
      fact_count: 22,
      metric_coverage_ratio: 1.0,
      missing_metric_groups: [],
      unexpected_metric_groups: ["revenue_segment"],
      passed: true,
    },
    {
      company_name: "sample_case_004",
      source_count: 1,
      fact_count: 22,
      metric_coverage_ratio: 1.0,
      missing_metric_groups: [],
      unexpected_metric_groups: [],
      passed: true,
    },
    {
      company_name: "sample_case_005",
      source_count: 1,
      fact_count: 22,
      metric_coverage_ratio: 1.0,
      missing_metric_groups: [],
      unexpected_metric_groups: [],
      passed: true,
    },
    {
      company_name: "sample_case_006",
      source_count: 1,
      fact_count: 13,
      metric_coverage_ratio: 1.0,
      missing_metric_groups: [],
      unexpected_metric_groups: [],
      passed: true,
    },
  ],
};

export function RegressionEvalPanel() {
  const summary = PUBLIC_REGRESSION_EVAL;

  return (
    <section className="panel regression-eval-panel">
      <div className="panel-heading-row">
        <div>
          <h2>公开资料回归评测结果</h2>
          <p className="hint-text">
            静态展示离线 fixture 回归评测摘要，用于核对抽取链路是否保持稳定。
          </p>
        </div>
        <span className="readonly-badge">只读 / 本地内置</span>
      </div>

      <p className="eval-boundary-text">
        该摘要不代表真实搜索质量，不代表生产级事实审计，也不用于投资决策。
      </p>

      <dl className="eval-summary-grid">
        <SummaryItem label="case_count" value={summary.case_count} />
        <SummaryItem label="passed_count" value={summary.passed_count} />
        <SummaryItem
          label="average_metric_coverage_ratio"
          value={formatRatio(summary.average_metric_coverage_ratio)}
        />
        <SummaryItem label="total_source_count" value={summary.total_source_count} />
        <SummaryItem label="total_fact_count" value={summary.total_fact_count} />
      </dl>

      <div className="table-scroll">
        <table className="eval-table">
          <thead>
            <tr>
              <th>company_name</th>
              <th>source_count</th>
              <th>fact_count</th>
              <th>metric_coverage_ratio</th>
              <th>missing_metric_groups</th>
              <th>unexpected_metric_groups</th>
              <th>passed</th>
            </tr>
          </thead>
          <tbody>
            {summary.cases.map((item) => (
              <RegressionEvalRow key={item.company_name} item={item} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SummaryItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function RegressionEvalRow({ item }: { item: RegressionEvalCase }) {
  return (
    <tr>
      <td>{item.company_name}</td>
      <td>{item.source_count}</td>
      <td>{item.fact_count}</td>
      <td>{formatRatio(item.metric_coverage_ratio)}</td>
      <td>{formatMetricGroups(item.missing_metric_groups)}</td>
      <td>{formatMetricGroups(item.unexpected_metric_groups)}</td>
      <td>{String(item.passed)}</td>
    </tr>
  );
}

function formatRatio(value: number) {
  return value.toFixed(4);
}

function formatMetricGroups(groups: string[]) {
  return groups.length ? groups.join(", ") : "-";
}
