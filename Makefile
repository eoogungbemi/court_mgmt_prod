# ── Allegheny County Juvenile Court — Court Management System ──────────────────
# Usage: make <target>
# Requires: docker, docker compose v2

COMPOSE      = docker compose
COMPOSE_PROD = docker compose -f docker-compose.prod.yml
BACKEND      = $(COMPOSE) exec backend
DOMAIN      ?= court.example.com

.PHONY: help dev dev-down prod prod-down \
        migrate seed logs logs-backend logs-frontend \
        shell-backend shell-db cert cert-renew \
        build build-prod clean

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  dev              Start dev stack (hot-reload)"
	@echo "  dev-down         Stop dev stack"
	@echo "  prod             Start production stack"
	@echo "  prod-down        Stop production stack"
	@echo "  migrate          Run Alembic migrations (dev)"
	@echo "  seed             Seed the database (dev)"
	@echo "  logs             Tail all dev logs"
	@echo "  logs-backend     Tail backend logs"
	@echo "  logs-frontend    Tail frontend logs"
	@echo "  shell-backend    Open shell in backend container"
	@echo "  shell-db         Open psql in db container"
	@echo "  cert             Issue Let's Encrypt cert (DOMAIN=your.domain)"
	@echo "  cert-renew       Force cert renewal"
	@echo "  build            Build dev images"
	@echo "  build-prod       Build production images"
	@echo "  clean            Remove volumes and containers"
	@echo ""

# ── Development ───────────────────────────────────────────────────────────────
dev:
	$(COMPOSE) up

dev-down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

# ── Production ────────────────────────────────────────────────────────────────
prod:
	$(COMPOSE_PROD) up -d

prod-down:
	$(COMPOSE_PROD) down

build-prod:
	$(COMPOSE_PROD) build

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	$(BACKEND) alembic upgrade head

seed:
	$(BACKEND) python -m db.seed

shell-backend:
	$(BACKEND) sh

shell-db:
	$(COMPOSE) exec db psql -U court -d court_mgmt

# ── Logs ─────────────────────────────────────────────────────────────────────
logs:
	$(COMPOSE) logs -f

logs-backend:
	$(COMPOSE) logs -f backend

logs-frontend:
	$(COMPOSE) logs -f frontend

# ── TLS Certificates ──────────────────────────────────────────────────────────
cert:
	@echo "Issuing Let's Encrypt cert for $(DOMAIN)..."
	$(COMPOSE_PROD) run --rm certbot certonly \
		--webroot -w /var/www/certbot \
		-d $(DOMAIN) \
		--email admin@$(DOMAIN) \
		--agree-tos --no-eff-email
	@echo "Replace 'court.example.com' in nginx/nginx.conf with $(DOMAIN), then restart nginx:"
	@echo "  $(COMPOSE_PROD) restart nginx"

cert-renew:
	$(COMPOSE_PROD) exec certbot certbot renew --force-renewal

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	$(COMPOSE) down -v --remove-orphans
