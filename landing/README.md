# Gandalf landing

Self-contained static landing page for Gandalf (inline CSS + JS, no build step).

Deploy: `wrangler deploy` from this directory. It is a Cloudflare Worker (`gandalf`) serving `public/` as static assets with `src/index.js` in front for the `/install` and www-to-apex redirects, attached to `gandalf.sh` and `www.gandalf.sh` as custom domains. Full recipe, gotchas, and verification steps: [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md).
