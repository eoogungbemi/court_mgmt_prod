#!/usr/bin/env bash
# =============================================================================
# deploy.sh — zero-to-live provisioning for one court instance
#
# First run:  bootstraps server, syncs code, generates secrets, starts stack,
#             seeds DB, sets DNS (optional), waits for HTTPS.
# Re-deploy:  --update flag skips bootstrap + secret generation; preserves .env
#
# Usage:
#   ./deploy.sh --court allegheny --domain court.alleghenycounty.us --ip 1.2.3.4
#   ./deploy.sh --court butler    --domain butler.courtmgmt.co      --ip 5.6.7.8 \
#               --gd-key fZ1W... --gd-secret RwVL...
#   ./deploy.sh --court allegheny --domain court.alleghenycounty.us --ip 1.2.3.4 \
#               --update
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; YEL='\033[1;33m'; GRN='\033[0;32m'
CYN='\033[0;36m'; BLD='\033[1m';    RST='\033[0m'

log()  { echo -e "${CYN}[deploy]${RST} $*"; }
step() { echo -e "\n${BLD}${CYN}──────────────────────────────────────────${RST}\n${BLD}${CYN}  $*${RST}\n${BLD}${CYN}──────────────────────────────────────────${RST}"; }
ok()   { echo -e "  ${GRN}✓${RST}  $*"; }
warn() { echo -e "  ${YEL}⚠${RST}  $*"; }
die()  { echo -e "\n${RED}✗  $*${RST}\n" >&2; exit 1; }

# ── Defaults ───────────────────────────────────────────────────────────────────
SSH_USER="root"
SSH_KEY=""
COURT_NAME=""
COURT_DISPLAY_NAME=""
DOMAIN=""
SERVER_IP=""
ADMIN_PASSWORD=""
SECRET_KEY=""
DB_PASSWORD=""
GD_KEY="${GODADDY_API_KEY:-}"
GD_SECRET="${GODADDY_API_SECRET:-}"
BASE_DOMAIN=""
UPDATE=false
SKIP_DNS=false
SKIP_SEED=false

# ── Usage ──────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF

${BLD}deploy.sh${RST} — provision a court instance from zero to live

${BLD}Usage:${RST}
  $0 --court NAME --domain DOMAIN --ip IP [OPTIONS]

${BLD}Required:${RST}
  --court   NAME     Short identifier, lowercase (e.g. allegheny, butler)
  --domain  DOMAIN   Full public domain (e.g. court.alleghenycounty.us)
  --ip      IP       Server IPv4 address

${BLD}Optional:${RST}
  --court-name NAME  Display name shown in the UI (default: "NAME County Juvenile Court")
  --ssh-user  USER   SSH login (default: root)
  --ssh-key   PATH   Path to SSH private key
  --admin-pw  PASS   Initial admin password  (default: auto-generated)
  --secret    KEY    JWT secret key           (default: auto-generated 64 chars)
  --db-pass   PASS   Postgres password        (default: auto-generated)
  --gd-key    KEY    GoDaddy API key   — also reads \$GODADDY_API_KEY
  --gd-secret SEC    GoDaddy API secret — also reads \$GODADDY_API_SECRET
  --base-domain DOM  Base domain for GoDaddy (default: last 2 parts of DOMAIN)
  --update           Re-deploy code; skips bootstrap & preserves .env/Caddyfile
  --skip-dns         Skip DNS setup even when GoDaddy creds are present
  --skip-seed        Skip DB seeding (use with --update when data exists)

${BLD}Examples:${RST}
  # First install with automatic DNS:
  $0 --court butler --domain butler.courtmgmt.co --ip 5.6.7.8 \\
     --gd-key fZ1Wm... --gd-secret RwVL...

  # Code-only update (preserves DB and secrets):
  $0 --court butler --domain butler.courtmgmt.co --ip 5.6.7.8 --update --skip-seed

  # From env vars (CI-friendly):
  GODADDY_API_KEY=... GODADDY_API_SECRET=... \\
  $0 --court butler --domain butler.courtmgmt.co --ip 5.6.7.8

EOF
  exit 0
}

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --court)       COURT_NAME="$2";        shift 2 ;;
    --court-name)  COURT_DISPLAY_NAME="$2"; shift 2 ;;
    --domain)      DOMAIN="$2";          shift 2 ;;
    --ip)          SERVER_IP="$2";       shift 2 ;;
    --ssh-user)    SSH_USER="$2";        shift 2 ;;
    --ssh-key)     SSH_KEY="$2";         shift 2 ;;
    --admin-pw)    ADMIN_PASSWORD="$2";  shift 2 ;;
    --secret)      SECRET_KEY="$2";      shift 2 ;;
    --db-pass)     DB_PASSWORD="$2";     shift 2 ;;
    --gd-key)      GD_KEY="$2";          shift 2 ;;
    --gd-secret)   GD_SECRET="$2";       shift 2 ;;
    --base-domain) BASE_DOMAIN="$2";     shift 2 ;;
    --update)      UPDATE=true;          shift   ;;
    --skip-dns)    SKIP_DNS=true;        shift   ;;
    --skip-seed)   SKIP_SEED=true;       shift   ;;
    --help|-h)     usage ;;
    *) die "Unknown option: $1  (run with --help)" ;;
  esac
done

# ── Validate ───────────────────────────────────────────────────────────────────
[[ -n "$COURT_NAME" ]] || die "--court is required"
[[ -n "$DOMAIN"     ]] || die "--domain is required"
[[ -n "$SERVER_IP"  ]] || die "--ip is required"
[[ "$COURT_NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]] \
  || die "--court must be lowercase alphanumeric (hyphens/underscores ok)"

APP_DIR="/opt/court-${COURT_NAME}"
COMPOSE_FILE="docker-compose.deploy.yml"
PROJECT="court-${COURT_NAME}"

# ── SSH / rsync helpers ────────────────────────────────────────────────────────
_ssh_opts=(-o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=15)
[[ -n "$SSH_KEY" ]] && _ssh_opts+=(-i "$SSH_KEY")

ssh_run() {
  ssh "${_ssh_opts[@]}" "${SSH_USER}@${SERVER_IP}" "$@"
}

# Run docker compose on the remote server
dc() {
  ssh_run bash -c "cd ${APP_DIR} && docker compose -f ${COMPOSE_FILE} -p ${PROJECT} $*"
}

gen_secret()   { openssl rand -hex 32; }
gen_password() { openssl rand -base64 18 | tr -dc 'A-Za-z0-9!@#%' | head -c 20; }

# =============================================================================
step "Checking local tools"
# =============================================================================
for cmd in ssh rsync curl openssl python3; do
  command -v "$cmd" &>/dev/null && ok "$cmd" || die "Required tool not found: $cmd"
done

# =============================================================================
step "Connecting to ${SSH_USER}@${SERVER_IP}"
# =============================================================================
ssh_run "echo '  SSH handshake OK'" || die "Cannot reach ${SERVER_IP} as ${SSH_USER}"

# =============================================================================
if [[ "$UPDATE" == false ]]; then
  step "Bootstrapping server (Docker, firewall, directories)"
# =============================================================================
  ssh_run bash -s <<'BOOTSTRAP'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

if ! command -v docker &>/dev/null; then
  echo "  Installing Docker CE..."
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg lsb-release
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
  echo "  Docker installed: $(docker --version)"
else
  echo "  Docker already present: $(docker --version)"
fi

# Allow web traffic if ufw is active
if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 22/tcp  2>/dev/null || true
  ufw allow 80/tcp  2>/dev/null || true
  ufw allow 443/tcp 2>/dev/null || true
  echo "  UFW rules ensured (22, 80, 443)"
fi
BOOTSTRAP
  ok "Server bootstrapped"
fi

ssh_run "mkdir -p ${APP_DIR}"

# =============================================================================
step "Syncing source code → ${SERVER_IP}:${APP_DIR}"
# =============================================================================
RSYNC_SSH="ssh ${_ssh_opts[*]}"
rsync -az --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='Caddyfile' \
  --exclude='*.egg-info' \
  --exclude='.venv' \
  --exclude='venv' \
  -e "$RSYNC_SSH" \
  "${SCRIPT_DIR}/" \
  "${SSH_USER}@${SERVER_IP}:${APP_DIR}/"
ok "Code synced"

# =============================================================================
if [[ "$UPDATE" == false ]]; then
  step "Generating secrets and writing .env + Caddyfile"
# =============================================================================
  [[ -z "$SECRET_KEY"          ]] && SECRET_KEY="$(gen_secret)"
  [[ -z "$DB_PASSWORD"         ]] && DB_PASSWORD="$(gen_secret)"
  [[ -z "$ADMIN_PASSWORD"      ]] && ADMIN_PASSWORD="$(gen_password)"
  [[ -z "$COURT_DISPLAY_NAME"  ]] && COURT_DISPLAY_NAME="${COURT_NAME^} County Juvenile Court"

  # Write .env — excluded from rsync so it is never overwritten by future deploys
  ssh_run tee "${APP_DIR}/.env" > /dev/null <<ENVFILE
# Generated by deploy.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Court: ${COURT_NAME} | Domain: ${DOMAIN} | Server: ${SERVER_IP}
# DO NOT EDIT — rerun deploy.sh to regenerate, or edit and restart the stack.

SECRET_KEY=${SECRET_KEY}
DATABASE_URL=postgresql://court:${DB_PASSWORD}@db:5432/court_mgmt
POSTGRES_DB=court_mgmt
POSTGRES_USER=court
POSTGRES_PASSWORD=${DB_PASSWORD}
ENVIRONMENT=production
ALLOWED_ORIGINS=https://${DOMAIN}
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PASSWORD}
COURT_DISPLAY_NAME=${COURT_DISPLAY_NAME}

# ── AI (optional — ETA estimates fall back to rule-based if unset) ──────────
ANTHROPIC_API_KEY=

# ── Observability (optional) ─────────────────────────────────────────────────
SENTRY_DSN=
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=court-${COURT_NAME}
LANGSMITH_TRACING=false
ENVFILE
  ok ".env written"

  # Write Caddyfile — also excluded from rsync
  ssh_run tee "${APP_DIR}/Caddyfile" > /dev/null <<CADDYFILE
# Managed by Caddy — TLS certificates obtained automatically via Let's Encrypt.
# Edit manually only if you need custom headers/auth; then reload with:
#   docker compose -p court-${COURT_NAME} exec caddy caddy reload --config /etc/caddy/Caddyfile
${DOMAIN} {
    # WebSocket connections route direct to FastAPI (Next.js can't proxy WS upgrades reliably)
    reverse_proxy /api/ws/* backend:8000

    # Everything else through Next.js, which re-proxies /api/* HTTP calls to the backend
    reverse_proxy frontend:3000
}
CADDYFILE
  ok "Caddyfile written"
else
  log "Skipping secret generation — existing .env and Caddyfile preserved"
fi

# =============================================================================
step "Building images and starting stack (project: ${PROJECT})"
# =============================================================================
# Pull base images in parallel to speed up build
dc "pull --quiet caddy postgres:16-alpine redis:7-alpine 2>/dev/null" || true
dc "build --pull"
dc "up -d --remove-orphans"
ok "Stack started"

# =============================================================================
step "Waiting for backend to pass health check"
# =============================================================================
log "Polling /health on ${SERVER_IP} …"
ATTEMPTS=36   # 6 minutes total (36 × 10s)
for i in $(seq 1 $ATTEMPTS); do
  STATUS=$(ssh_run "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null || echo 000")
  if [[ "$STATUS" == "200" ]]; then
    ok "Backend healthy (attempt ${i}/${ATTEMPTS})"
    break
  fi
  if [[ "$i" -eq "$ATTEMPTS" ]]; then
    warn "Backend not healthy after 6 minutes — check logs:"
    warn "  ssh ${SSH_USER}@${SERVER_IP} \"cd ${APP_DIR} && docker compose -p ${PROJECT} logs backend --tail=30\""
    die "Aborting — stack may still be starting; retry with --update once it's up"
  fi
  printf "."
  sleep 10
done

# =============================================================================
if [[ "$SKIP_SEED" == false ]]; then
  step "Database migrations and seeding"
# =============================================================================
  dc "exec -T backend sh -c 'PYTHONPATH=/app python db/seed.py'"
  ok "Base schema seeded (courtrooms, judges, lawyers)"

  if [[ "$UPDATE" == false ]]; then
    dc "exec -T backend sh -c 'PYTHONPATH=/app python db/demo_seed.py'"
    ok "Demo docket seeded (today's hearings with realistic statuses)"
  fi
else
  log "Skipping seed (--skip-seed)"
fi

# =============================================================================
if [[ "$SKIP_DNS" == false && -n "$GD_KEY" && -n "$GD_SECRET" ]]; then
  step "Setting DNS A record via GoDaddy API"
# =============================================================================
  if [[ -z "$BASE_DOMAIN" ]]; then
    # butler.courtmgmt.co → courtmgmt.co / butler
    BASE_DOMAIN=$(echo "$DOMAIN" | rev | cut -d. -f1-2 | rev)
    SUBDOMAIN=$(echo "$DOMAIN"   | rev | cut -d. -f3-  | rev)
    [[ -z "$SUBDOMAIN" ]] && die "Could not parse subdomain from '${DOMAIN}' — use --base-domain explicitly"
  else
    SUBDOMAIN="${DOMAIN%."${BASE_DOMAIN}"}"
  fi

  log "PUT ${SUBDOMAIN}.${BASE_DOMAIN} → ${SERVER_IP} (TTL 600)"
  HTTP_CODE=$(curl -s -o /tmp/_gd_resp.json -w "%{http_code}" \
    -X PUT \
    "https://api.godaddy.com/v1/domains/${BASE_DOMAIN}/records/A/${SUBDOMAIN}" \
    -H "Authorization: sso-key ${GD_KEY}:${GD_SECRET}" \
    -H "Content-Type: application/json" \
    -d "[{\"data\":\"${SERVER_IP}\",\"ttl\":600}]")

  if [[ "$HTTP_CODE" == "200" ]]; then
    ok "DNS A record set: ${DOMAIN} → ${SERVER_IP}"
  else
    warn "GoDaddy API returned HTTP ${HTTP_CODE}:"
    cat /tmp/_gd_resp.json 2>/dev/null || true
    warn "Set the DNS record manually, then rerun with --update --skip-dns"
  fi

  log "Waiting for DNS propagation (polling Google + Cloudflare DoH) …"
  DNS_OK=false
  for i in $(seq 1 30); do
    R1=$(curl -s "https://dns.google/resolve?name=${DOMAIN}&type=A" \
      | python3 -c "import sys,json; a=json.load(sys.stdin).get('Answer',[]); print(a[0]['data'] if a else '')" 2>/dev/null || echo "")
    R2=$(curl -s -H "Accept: application/dns-json" \
      "https://cloudflare-dns.com/dns-query?name=${DOMAIN}&type=A" \
      | python3 -c "import sys,json; a=json.load(sys.stdin).get('Answer',[]); print(a[0]['data'] if a else '')" 2>/dev/null || echo "")
    if [[ "$R1" == "$SERVER_IP" && "$R2" == "$SERVER_IP" ]]; then
      ok "DNS propagated to Google (${R1}) and Cloudflare (${R2})"
      DNS_OK=true
      break
    fi
    [[ "$i" -eq 30 ]] && warn "DNS propagation timed out — HTTPS setup may need a few extra minutes"
    printf "."
    sleep 10
  done
elif [[ "$SKIP_DNS" == false ]]; then
  warn "No GoDaddy credentials — skipping DNS (set --gd-key / --gd-secret or \$GODADDY_API_KEY)"
  warn "Point ${DOMAIN} → ${SERVER_IP} manually before HTTPS will work"
fi

# =============================================================================
step "Waiting for HTTPS (Caddy obtaining Let's Encrypt certificate)"
# =============================================================================
log "Caddy retries every ~2 min until the cert is issued …"
HTTPS_OK=false
for i in $(seq 1 42); do   # up to 7 minutes
  STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "https://${DOMAIN}/" 2>/dev/null || echo 000)
  if [[ "$STATUS" =~ ^(200|301|302|307)$ ]]; then
    ok "HTTPS live — HTTP ${STATUS}"
    HTTPS_OK=true
    break
  fi
  if [[ "$i" -eq 42 ]]; then
    warn "HTTPS not confirmed after 7 minutes — cert may still be issuing"
    warn "Check Caddy: ssh ${SSH_USER}@${SERVER_IP} \"docker logs ${PROJECT}-caddy-1 --tail=20\""
  fi
  printf "."
  sleep 10
done

# =============================================================================
step "Deployment complete"
# =============================================================================

# Read ADMIN_PASSWORD back from .env in case it was auto-generated
_ADMIN_PW=$(ssh_run "grep '^ADMIN_PASSWORD=' ${APP_DIR}/.env 2>/dev/null | cut -d= -f2" || echo "(see ${APP_DIR}/.env)")

echo ""
echo -e "${BLD}${GRN}╔══════════════════════════════════════════════════════════╗${RST}"
echo -e "${BLD}${GRN}║  ${RST}${BLD}Court instance ready${RST}${BLD}${GRN}                                    ║${RST}"
echo -e "${BLD}${GRN}╚══════════════════════════════════════════════════════════╝${RST}"
echo ""
echo -e "  ${BLD}Court:${RST}   ${COURT_NAME}"
echo -e "  ${BLD}URL:${RST}     https://${DOMAIN}"
echo -e "  ${BLD}Server:${RST}  ${SERVER_IP}  (${APP_DIR})"
echo ""

if [[ "$UPDATE" == false ]]; then
  echo -e "  ${BLD}Admin login:${RST}"
  echo -e "    URL:      https://${DOMAIN}/login"
  echo -e "    Username: admin"
  echo -e "    Password: ${_ADMIN_PW}"
  echo ""
  echo -e "  ${BLD}Demo accounts:${RST}"
  echo -e "    demo_admin    / Admin1234"
  echo -e "    demo_clerk    / Clerk1234"
  echo -e "    demo_judge    / Judge1234"
  echo -e "    demo_attorney / Attorney1234"
  echo ""
fi

echo -e "  ${BLD}Useful commands:${RST}"
echo -e "    # Live logs"
echo -e "    ssh ${SSH_USER}@${SERVER_IP} \\"
echo -e "      \"cd ${APP_DIR} && docker compose -p ${PROJECT} logs -f\""
echo ""
echo -e "    # Backend shell"
echo -e "    ssh ${SSH_USER}@${SERVER_IP} \\"
echo -e "      \"cd ${APP_DIR} && docker compose -p ${PROJECT} exec backend bash\""
echo ""
echo -e "    # Rolling update (after pushing code changes)"
echo -e "    ./deploy.sh --court ${COURT_NAME} --domain ${DOMAIN} --ip ${SERVER_IP} \\"
echo -e "                --update --skip-seed"
echo ""
echo -e "    # DB backup"
echo -e "    ssh ${SSH_USER}@${SERVER_IP} \"${APP_DIR}/scripts/backup.sh\""
echo ""
