.PHONY: install start stop status test lint

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
