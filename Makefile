.DEFAULT_GOAL := help

ARGS ?=
CLI_GOAL_ARGS := $(filter-out cli,$(MAKECMDGOALS))
CLI_RUN_ARGS := $(if $(ARGS),$(ARGS),$(CLI_GOAL_ARGS))

.PHONY: help postgres up down cli logs ps build config

help:
	@awk 'BEGIN {FS = ":.*## "; print "Targets:"} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

postgres: ## Start only the postgres service.
	doppler run -- docker compose up -d postgres

up: ## Start all compose services in the background.
	doppler run -- docker compose up -d

down: ## Stop and remove compose services.
	doppler run -- docker compose down

cli: ## Run the CLI service. Usage: make cli ARGS="--help"
	doppler run -- docker compose run --rm cli $(CLI_RUN_ARGS)

logs: ## Follow compose logs.
	doppler run -- docker compose logs -f

ps: ## Show compose service status.
	doppler run -- docker compose ps

build: ## Build compose images.
	doppler run -- docker compose build

config: ## Print the resolved compose config.
	doppler run -- docker compose config

%:
	@:
