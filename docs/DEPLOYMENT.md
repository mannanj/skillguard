# Deploying the landing site (Cloudflare Worker + custom domain)

How `skillguard.sh` is wired, and the recipe for doing it again (new domain, new project, or disaster recovery). Proven 2026-06-03.

## Architecture

- **Cloudflare Worker** named `skillguard`, config at [`landing/wrangler.jsonc`](../landing/wrangler.jsonc)
- Static assets served from `landing/public/` via the Workers **assets binding** (no build step)
- A tiny fetch handler ([`landing/src/index.js`](../landing/src/index.js)) layered in front for redirects
- Custom domains `skillguard.sh` + `www.skillguard.sh` attached as Worker routes

## The config that matters

```jsonc
{
  "name": "skillguard",
  "main": "src/index.js",
  "compatibility_date": "2026-06-03",
  "assets": {
    "directory": "./public",
    "binding": "ASSETS",
    // Invoke the worker before the asset layer so the www→apex 301 fires on "/"
    "run_worker_first": true
  },
  "routes": [
    { "pattern": "skillguard.sh", "custom_domain": true },
    { "pattern": "www.skillguard.sh", "custom_domain": true }
  ]
}
```

## Deploy

```bash
cd landing
wrangler deploy
```

That's the whole thing. With `custom_domain: true` routes, `wrangler deploy` auto-creates the apex + www A/AAAA records and TLS certs on the zone — **no manual DNS step**. Prerequisite: the zone must already exist in the Cloudflare account with nameservers delegated at the registrar (`skillguard.sh` → `gabe`/`rosemary.ns.cloudflare.com`; account `hello@mannan.is`).

## Worker routing logic

Order matters in `src/index.js`:

1. `/install` or `/install.sh` → 302 to `https://raw.githubusercontent.com/mannanj/skillguard/main/install.sh` (powers `curl -fsSL https://skillguard.sh/install | sh`)
2. `www.skillguard.sh/*` → 301 to the same path on the apex (canonical host)
3. Everything else → `env.ASSETS.fetch(request)` (static files)

## Gotchas (each cost real debugging time)

### 1. Static assets serve *before* the worker by default

Without `run_worker_first`, any path matching a static file (`/` → `index.html`) is served by the asset layer and the fetch handler **never runs**. Symptom is deceptive partial behavior: non-asset paths like `/install` redirect fine, but the www→apex 301 silently doesn't fire on `/`. Fix: `"run_worker_first": true` (every request becomes a billed Worker invocation instead of free asset serving — negligible for a landing page).

### 2. Stale negative DNS cache after fresh domain wiring

If the domain was ever looked up *before* the zone went live, local resolvers (including the router) cache the "domain doesn't exist" answer for up to ~1 hour. The site looks dead locally while serving fine globally. Never judge a fresh domain from the local resolver — verify against public DNS and the edge directly (below). Local fix on macOS:

```bash
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
```

(The router's own cache just has to expire, or switch the machine's DNS to `1.1.1.1` temporarily.)

## Post-deploy verification

```bash
# 1. Delegation reaches Cloudflare's nameservers
dig +trace skillguard.sh NS

# 2. Records exist on the authoritative NS (bypasses every cache)
dig +short skillguard.sh A @gabe.ns.cloudflare.com
dig +short www.skillguard.sh A @gabe.ns.cloudflare.com

# 3. Endpoints behave (forced resolution — immune to local DNS state)
CF_IP=$(dig +short skillguard.sh A @1.1.1.1 | head -1)
curl -s -o /dev/null --resolve skillguard.sh:443:$CF_IP      -w "apex:    %{http_code}\n"                    https://skillguard.sh/
curl -s -o /dev/null --resolve www.skillguard.sh:443:$CF_IP  -w "www:     %{http_code} -> %{redirect_url}\n" https://www.skillguard.sh/
curl -s -o /dev/null --resolve skillguard.sh:443:$CF_IP      -w "install: %{http_code} -> %{redirect_url}\n" https://skillguard.sh/install
```

Expected: apex `200`, www `301 -> https://skillguard.sh/`, install `302 -> https://raw.githubusercontent.com/mannanj/skillguard/main/install.sh`.

## Rollback

```bash
cd landing
wrangler deployments list   # find the prior version
wrangler rollback           # or: wrangler rollback <VERSION_ID>
```
