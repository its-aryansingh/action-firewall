.PHONY: install backend frontend test seed demo

install:
	cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -q

seed:
	cd backend && python -m app.catalog

demo:
	cd backend && python scripts/demo.py
