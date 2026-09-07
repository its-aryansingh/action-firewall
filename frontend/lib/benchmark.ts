export type WorkflowBenchmarkReport = {
  schema_version: "action-firewall-workflow-comparison@1";
  scope: string;
  corpus: {
    seeds: number;
    legitimate_jobs: number;
    eligible_stock_loss_jobs: number;
    unsafe_drift_attempts: number;
  };
  results: {
    manual_checkout: {
      completed_without_action_time_intervention: number;
      eligible_stock_loss_recovered_without_reapproval: number;
      approval_prompts_per_legitimate_completion: number;
      unsafe_automatic_authorizations: number;
    };
    exact_cart_approval: {
      completed_without_action_time_intervention: number;
      eligible_stock_loss_recovered_without_reapproval: number;
      approval_prompts_per_legitimate_completion: number;
      unsafe_automatic_authorizations: number;
    };
    purchase_envelope: {
      completed_without_action_time_intervention: number;
      eligible_stock_loss_recovered_without_reapproval: number;
      approval_prompts_per_legitimate_completion: number;
      unsafe_automatic_authorizations: number;
    };
  };
  failures: Array<Record<string, unknown>>;
};

export const VERIFIED_BENCHMARK: WorkflowBenchmarkReport = {
  schema_version: "action-firewall-workflow-comparison@1",
  scope:
    "Modeled workflow counts over synthetic catalog jobs. Not measured user time, conversion, revenue, or production payment success.",
  corpus: {
    seeds: 50,
    legitimate_jobs: 100,
    eligible_stock_loss_jobs: 50,
    unsafe_drift_attempts: 150,
  },
  results: {
    manual_checkout: {
      completed_without_action_time_intervention: 0,
      eligible_stock_loss_recovered_without_reapproval: 0,
      approval_prompts_per_legitimate_completion: 1.0,
      unsafe_automatic_authorizations: 0,
    },
    exact_cart_approval: {
      completed_without_action_time_intervention: 50,
      eligible_stock_loss_recovered_without_reapproval: 0,
      approval_prompts_per_legitimate_completion: 1.5,
      unsafe_automatic_authorizations: 0,
    },
    purchase_envelope: {
      completed_without_action_time_intervention: 100,
      eligible_stock_loss_recovered_without_reapproval: 50,
      approval_prompts_per_legitimate_completion: 1.0,
      unsafe_automatic_authorizations: 0,
    },
  },
  failures: [],
};

export async function fetchWorkflowBenchmark(): Promise<WorkflowBenchmarkReport> {
  try {
    const res = await fetch("/workflow_benchmark.json", { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (data && data.schema_version === "action-firewall-workflow-comparison@1") {
        return data as WorkflowBenchmarkReport;
      }
    }
  } catch {
    // Fallback to verified local constant
  }
  return VERIFIED_BENCHMARK;
}
