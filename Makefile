.PHONY: dev seed test eval langfuse langfuse-down deploy

dev:
	trap 'kill 0' INT TERM; uv run --env-file .env uvicorn app.main:app --reload --port 8000 & pnpm -C frontend dev & wait

seed:
	uv run python data/seed.py

test:
	uv run pytest -q

eval:
	PYTHONPATH=. uv run --env-file .env python evals/gate.py

langfuse:
	cd infra/langfuse && docker compose up -d
	until curl -sf http://localhost:3000/api/public/health >/dev/null; do sleep 2; done
	@echo "Langfuse: http://localhost:3000 (login in infra/langfuse/.env)"

langfuse-down:
	cd infra/langfuse && docker compose down

deploy:
	gcloud run deploy diagnostic-agent --source . --allow-unauthenticated

# --- devops: CI gates and local deploy (devops skill) ---
# Gates `make ci` runs, in order; CI runs the same list. Known: ruff hadolint actionlint test scan local-deploy.
# One-off override: make ci CI_GATES="ruff test"
CI_GATES = ruff hadolint actionlint test scan local-deploy
HADOLINT = hadolint/hadolint:v2.15.1@sha256:32dac94127fd60b7b7e3fbfc65e1383b9b5e25c9bfd7b8536de7a539fe68a12d
TRIVY = aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
ACTIONLINT = rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
IMAGE = diagnostic-agent:local
export IMAGE

.PHONY: ci ruff hadolint actionlint scan local-deploy image up smoke down

ci:
	@for gate in $(CI_GATES); do \
	    echo "== gate: $$gate"; \
	    $(MAKE) --no-print-directory $$gate || { echo "== FAILED gate: $$gate"; exit 1; }; \
	done; echo "== passed: $(CI_GATES)"

ruff:
	uv run ruff check .

hadolint:
	docker run --rm -i $(HADOLINT) hadolint --no-color - < Dockerfile

actionlint:
	docker run --rm -v "$(CURDIR):/repo" -w /repo $(ACTIONLINT) -color=false .github/workflows/*.yml

scan: image
	docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache -v $(CURDIR)/trivy-secret.yaml:/trivy-secret.yaml:ro $(TRIVY) image --secret-config /trivy-secret.yaml --quiet --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed $(IMAGE)

local-deploy:
	$(MAKE) --no-print-directory up && $(MAKE) --no-print-directory smoke; status=$$?; $(MAKE) --no-print-directory down; exit $$status

image:
	docker build -t $(IMAGE) .

up: image
	docker compose up -d --wait

smoke:
	scripts/smoke.sh http://localhost:8080

down:
	docker compose down
