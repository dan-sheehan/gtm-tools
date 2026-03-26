.PHONY: install start stop status test lint seed

install:
	python3 -m pip install -r requirements.txt

start:
	./hub start

stop:
	./hub stop

status:
	./hub status

test:
	python3 -m pytest tests/ -v

lint:
	python3 -m ruff check apps/

seed:
	@echo "Seeding sample data..."
	@curl -s -X POST http://localhost:3003/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  morning-brief: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  morning-brief: not running"
	@curl -s -X POST http://localhost:3010/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  pipeline: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  pipeline: not running"
	@curl -s -X POST http://localhost:3011/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  enrichment: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  enrichment: not running"
	@curl -s -X POST http://localhost:3012/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  icp-scorer: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  icp-scorer: not running"
	@curl -s -X POST http://localhost:3005/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  discovery: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  discovery: not running"
	@curl -s -X POST http://localhost:3006/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  competitive-intel: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  competitive-intel: not running"
	@curl -s -X POST http://localhost:3008/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  outbound-email: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  outbound-email: not running"
	@curl -s -X POST http://localhost:3004/api/seed | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  playbook: {d.get(\"status\", \"error\")}')" 2>/dev/null || echo "  playbook: not running"
	@echo "Done. Visit http://localhost:8000"
