const GITHUB_API = "https://api.github.com";
const USER_AGENT = "three-papers-one-journal-trigger";

async function dispatchWorkflow(env, metadata = {}) {
  if (!env.GITHUB_TOKEN) {
    throw new Error("Missing GITHUB_TOKEN secret");
  }

  const repo = env.GITHUB_REPO || "hyc17666-cmd/Hyeechenhome";
  const workflow = env.GITHUB_WORKFLOW || "update-and-deploy.yml";
  const ref = env.GITHUB_REF || "main";
  const endpoint = `${GITHUB_API}/repos/${repo}/actions/workflows/${workflow}/dispatches`;

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": USER_AGENT,
    },
    body: JSON.stringify({
      ref,
      inputs: { trigger_source: "cloudflare-cron" },
    }),
  });

  const responseText = await response.text();
  if (response.status !== 204) {
    throw new Error(`GitHub workflow_dispatch failed: ${response.status} ${responseText}`);
  }

  return {
    ok: true,
    dispatched_at: new Date().toISOString(),
    repo,
    workflow,
    ref,
    ...metadata,
  };
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      dispatchWorkflow(env, {
        source: "cloudflare-cron",
        cron: controller.cron,
        scheduled_time: new Date(controller.scheduledTime).toISOString(),
      }).catch((error) => {
        console.error(error);
        throw error;
      }),
    );
  },

  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({ ok: true, service: USER_AGENT });
    }

    if (url.pathname !== "/trigger") {
      return new Response("Not found", { status: 404 });
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const authorization = request.headers.get("Authorization") || "";
    if (!env.TRIGGER_SECRET || authorization !== `Bearer ${env.TRIGGER_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    try {
      const result = await dispatchWorkflow(env, {
        source: "http-manual-test",
      });
      return Response.json(result);
    } catch (error) {
      console.error(error);
      return Response.json(
        { ok: false, error: String(error.message || error) },
        { status: 502 },
      );
    }
  },
};