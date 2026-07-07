// SkillGuard landing worker: static assets plus a couple of friendly routes.
const GITHUB_REPO_API = "https://api.github.com/repos/mannanj/skillguard";
const GITHUB_REPO_CACHE_SECONDS = 60 * 60;

async function githubRepoResponse(request, ctx) {
  const cache = caches.default;
  const cacheKey = new Request(new URL(request.url).toString(), {
    method: "GET",
  });
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached;
  }

  let upstream;
  try {
    upstream = await fetch(GITHUB_REPO_API, {
      headers: {
        Accept: "application/vnd.github+json",
        "User-Agent": "skillguard.sh",
      },
    });
  } catch (_error) {
    return Response.json(
      { error: "github_unavailable" },
      {
        status: 502,
        headers: { "Cache-Control": "public, max-age=60" },
      },
    );
  }

  if (!upstream.ok) {
    return Response.json(
      { error: "github_unavailable" },
      {
        status: 502,
        headers: { "Cache-Control": "public, max-age=60" },
      },
    );
  }

  const repo = await upstream.json();
  const response = Response.json(
    {
      stargazers_count: repo.stargazers_count,
      html_url: repo.html_url,
    },
    {
      headers: {
        "Cache-Control": `public, max-age=300, s-maxage=${GITHUB_REPO_CACHE_SECONDS}`,
      },
    },
  );

  if (ctx && ctx.waitUntil) {
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
  } else {
    await cache.put(cacheKey, response.clone());
  }
  return response;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // `curl -fsSL https://skillguard.sh/install | sh`
    if (url.pathname === "/install" || url.pathname === "/install.sh") {
      return Response.redirect(
        "https://raw.githubusercontent.com/mannanj/skillguard/main/install.sh",
        302,
      );
    }

    if (url.pathname === "/api/github-repo") {
      return githubRepoResponse(request, ctx);
    }

    // Canonical host: collapse www to apex.
    if (url.hostname === "www.skillguard.sh") {
      url.hostname = "skillguard.sh";
      return Response.redirect(url.toString(), 301);
    }

    if (url.hostname === "gandalf.sh" || url.hostname === "www.gandalf.sh") {
      url.hostname = "skillguard.sh";
      return Response.redirect(url.toString(), 301);
    }

    return env.ASSETS.fetch(request);
  },
};
