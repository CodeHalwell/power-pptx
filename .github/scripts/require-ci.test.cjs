const { test } = require("node:test");
const assert = require("node:assert/strict");
const requireCI = require("./require-ci.cjs");

const sha = "abc123";
const passing = {
  id: 10, head_sha: sha, head_branch: "master", event: "push",
  head_repository: { full_name: "owner/repo" },
  status: "completed", conclusion: "success", html_url: "https://example.test/ci/10",
};

function options(responses) {
  let index = 0;
  return {
    sha,
    context: { repo: { owner: "owner", repo: "repo" }, payload: { repository: { default_branch: "master" } } },
    core: { info() {} },
    github: { rest: { actions: { async listWorkflowRuns(args) {
      assert.equal(args.head_sha, sha);
      assert.equal(args.workflow_id, "ci.yml");
      return { data: { workflow_runs: responses[Math.min(index++, responses.length - 1)] } };
    } } } },
  };
}

test("accepts passing CI on the exact commit", async () => {
  await requireCI(options([[passing]]));
});

for (const replacement of [
  { head_sha: "another-commit" }, { head_branch: "develop" },
  { event: "pull_request" }, { head_repository: { full_name: "fork/repo" } },
]) {
  test(`rejects unrelated CI: ${JSON.stringify(replacement)}`, async () => {
    await assert.rejects(requireCI(options([[{ ...passing, ...replacement }]])), /No completed/);
  });
}

for (const conclusion of ["failure", "cancelled", "skipped", "timed_out"]) {
  test(`rejects ${conclusion} even if older CI passed`, async () => {
    await assert.rejects(requireCI(options([[
      passing, { ...passing, id: 11, conclusion },
    ]])), /CI did not pass/);
  });
}

test("waits for queued CI and then accepts its success", async () => {
  let time = 0;
  await requireCI({
    ...options([[], [{ ...passing, status: "in_progress" }], [passing]]),
    wait: true, now: () => time, sleep: async ms => { time += ms; },
  });
  assert.equal(time, 20000);
});

test("bounds the wait when CI never starts", async () => {
  let time = 0;
  await assert.rejects(requireCI({
    ...options([[]]), wait: true, timeoutMs: 5, pollMs: 2,
    now: () => time, sleep: async ms => { time += ms; },
  }), /No completed/);
  assert.equal(time, 5);
});
