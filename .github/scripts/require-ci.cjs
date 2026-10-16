// Shared by release and publish: require passing CI on the exact commit.
module.exports = async function requireCI({
  github, context, core, sha, wait = false,
  timeoutMs = 15 * 60 * 1000, pollMs = 10 * 1000,
  now = Date.now, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
}) {
  const deadline = now() + timeoutMs;
  const { owner, repo } = context.repo;
  const branch = context.payload.repository.default_branch;
  while (true) {
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner, repo, workflow_id: "ci.yml", head_sha: sha, branch,
      event: "push", per_page: 100,
    });
    // Ignore fork runs and require the newest CI run, so a failed or
    // in-progress rerun cannot be hidden by an older passing run.
    const runs = data.workflow_runs
      .filter(run => run.head_sha === sha
        && run.head_branch === branch
        && run.event === "push"
        && run.head_repository?.full_name === `${owner}/${repo}`)
      .sort((a, b) => b.id - a.id);
    const run = runs[0];
    if (run?.status === "completed") {
      if (run.conclusion !== "success") {
        throw new Error(`CI did not pass for ${sha}: ${run.conclusion} (${run.html_url})`);
      }
      core.info(`CI passed for ${sha}: ${run.html_url}`);
      return;
    }
    if (!wait || now() >= deadline) {
      throw new Error(`No completed, successful CI run for ${sha} on ${branch}`);
    }
    core.info(`Waiting for CI on ${sha} (${run?.status ?? "not started"})`);
    await sleep(Math.min(pollMs, Math.max(0, deadline - now())));
  }
};
