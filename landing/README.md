# SkillGuard landing

Self-contained static landing page for SkillGuard (inline CSS + JS, no build step).

Deploy: `wrangler deploy` from this directory — it's a Cloudflare Worker (`skillguard`) serving `public/` as static assets with `src/index.js` in front for the `/install` and www→apex redirects, attached to `skillguard.sh` + `www.skillguard.sh` as custom domains. Full recipe, gotchas, and verification steps: [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).
