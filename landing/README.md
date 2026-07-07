# SkillGuard landing

Self-contained static landing page for SkillGuard (inline CSS + JS, no build step).

Deploy: `wrangler deploy` from this directory. It is a Cloudflare Worker (`skillguard`) serving `public/` as static assets with `src/index.js` in front for the `/install` and host redirects, attached to `skillguard.sh` and `www.skillguard.sh` as custom domains. Full recipe, gotchas, and verification steps: [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).
