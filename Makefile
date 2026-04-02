# Dan's World of AI Magic -- Makefile
# Usage:
#   make deploy         Full deploy (pull sources + rebuild + restart)
#   make build          Build all containers
#   make build-app APP=ticketmaker   Build one container
#   make up             Start all containers
#   make restart APP=ticketmaker     Restart one container
#   make logs APP=ticketmaker        Tail logs for one container
#   make status         Show container status
#   make health         Run health checks
#   make ps             Alias for status

.PHONY: deploy build build-app up down restart logs status health ps

# Load paths.env if it exists
ifneq (,$(wildcard ./paths.env))
include paths.env
export
endif

deploy:
	@echo "==> Pulling dans-world repo..."
	git pull origin main
	@echo "==> Syncing app sources..."
	./scripts/sync-sources.sh
	@echo "==> Building and starting containers..."
	docker compose up --build -d
	@echo "==> Deploy complete."
	docker compose ps

build:
	docker compose build

build-app:
ifndef APP
	$(error APP is required. Usage: make build-app APP=ticketmaker)
endif
	docker compose build $(APP)

up:
	docker compose up -d

down:
	docker compose down

restart:
ifndef APP
	$(error APP is required. Usage: make restart APP=ticketmaker)
endif
	docker compose restart $(APP)

logs:
ifndef APP
	docker compose logs -f --tail 50
else
	docker compose logs -f --tail 50 $(APP)
endif

status:
	docker compose ps

ps: status

health:
	./scripts/healthcheck.sh
