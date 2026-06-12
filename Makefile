# Convenience targets. Run from the repo root.

.PHONY: setup backend test frontend experiment smoke-llm skills

setup:  ## Create venv and install backend deps
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

backend:  ## Run the API (offline mock by default)
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload

test:  ## Run the backend test suite (offline)
	cd backend && . .venv/bin/activate && pytest -q

frontend:  ## Run the Next.js dev server
	cd frontend && npm install && npm run dev

experiment:  ## Run the reliability experiment harness
	cd backend && . .venv/bin/activate && python -m experiments.run --students 10 --problems 10

smoke-llm:  ## Test the configured LLM provider end-to-end (uses .env; may call a real model)
	cd backend && . .venv/bin/activate && python -m scripts.smoke_llm

skills:  ## List every supported skill, grouped by domain
	cd backend && . .venv/bin/activate && python -m scripts.list_skills
