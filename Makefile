# Makefile for KLoROS test orchestration
.PHONY: fast_all last_failed new_first promotion e2e_smoke help
.PHONY: spica-spawn spica-phase spica-validate spica-promote-intra spica-judge

# Test paths
UNIT_TARGETS := tests src/dream/tests
E2E_TARGETS := kloros-e2e/tests/e2e
FAST_FILTER := -k "not slow and not e2e"
VENV := /home/kloros/.venv/bin

# SPICA paths
SPICA_INST := /home/kloros/experiments/spica/instances
PY := $(VENV)/python

help:
	@echo "KLoROS Test Targets:"
	@echo "  fast_all      - Run all fast unit/integration tests in parallel"
	@echo "  last_failed   - Re-run only last failed tests"
	@echo "  new_first     - Run new/modified tests first"
	@echo "  promotion     - Run promotion policy tests"
	@echo "  e2e_smoke     - Run e2e smoke tests (non-slow)"
	@echo ""
	@echo "SPICA Tournament Targets:"
	@echo "  spica-spawn          - Spawn test SPICA instances"
	@echo "  spica-phase          - Run PHASE tournament on instances"
	@echo "  spica-validate       - Validate schemas and run tests"
	@echo "  spica-promote-intra  - Promote within instance (requires ID=<spica-id>)"
	@echo "  spica-judge          - Select winner and build promotion bundle"
	@echo ""
	@echo "Environment variables:"
	@echo "  FAST_FILTER='not slow and not e2e' - Test filter expression"
	@echo "  PYTEST_TIMEOUT=90                  - Test timeout in seconds"

fast_all:
	$(VENV)/pytest $(UNIT_TARGETS) $(FAST_FILTER) -n auto --durations=25 --maxfail=1

last_failed:
	$(VENV)/pytest --lf -n auto --maxfail=1

new_first:
	$(VENV)/pytest --nf $(UNIT_TARGETS) -n auto --maxfail=1

promotion:
	@PYTEST_FILTER="not slow and not e2e" PYTEST_TIMEOUT=90 $(VENV)/python scripts/run_promotion_tests.py

e2e_smoke:
	@if [ -f scripts/run-e2e.sh ]; then \
		bash scripts/run-e2e.sh; \
	else \
		echo "E2E runner not found at scripts/run-e2e.sh"; \
		$(VENV)/pytest $(E2E_TARGETS) -v --tb=line -k "not browser and not slow"; \
	fi

# SPICA Tournament targets
spica-spawn:
	@cd /home/kloros && $(PY) -c "from src.integrations.spica_spawn import spawn_instance; \
print(spawn_instance({'tau_persona': 0.01}, notes='Test instance A')); \
print(spawn_instance({'tau_persona': 0.03}, notes='Test instance B')); \
print(spawn_instance({'tau_persona': 0.05}, notes='Test instance C'))"

spica-phase:
	@cd /home/kloros && $(PY) -c "import glob, json; from src.integrations.phase_adapter import submit_tournament; \
inst = sorted(glob.glob('$(SPICA_INST)/spica-*')); \
print('{\"error\": \"No instances found\"}' if not inst else json.dumps(submit_tournament(inst, 'qa.rag.gold', {'epochs': 2, 'slices_per_epoch': 4, 'replicas_per_slice': 8}), indent=2))"

spica-validate:
	@cd /home/kloros/experiments/spica && $(PY) template/scripts/validate_schemas.py

spica-promote-intra:
	@if [ -z "$(ID)" ]; then \
		echo "Error: ID not set. Usage: make spica-promote-intra ID=spica-xxxxxxxx"; \
		exit 1; \
	fi
	@cd $(SPICA_INST)/$(ID) && SPICA_INTRA_PROMOTE=1 $(PY) ../../template/tools/promote_intra.py

spica-judge:
	@cd /home/kloros && $(PY) -c "import json, os; from src.dream.spica_admit import choose_winner, build_promotion_bundle; \
t = json.load(open('tournament.json')); \
w = choose_winner(t); \
os.environ.setdefault('DREAM_PROMOTION_HMAC_KEY', 'devkey'); \
print(build_promotion_bundle(w, t, '/home/kloros/artifacts/dream/promotions'))"
