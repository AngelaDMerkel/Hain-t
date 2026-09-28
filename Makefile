.PHONY: up down logs bridge test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f dro-utility

bridge:
	python3 bridge/dro_bridge.py --port auto --endpoint http://127.0.0.1:8080/api/live --poll-interval 0.25

test:
	python3 -m unittest discover -s tests -v
