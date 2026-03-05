# Proyecto: SmartLock Tracking API

## Objetivo
API REST con FastAPI para gestionar smart locks en shipments globales.
Proyecto de práctica para aprender FastAPI + Pydantic + Async.

## Stack
- Python 3.11
- FastAPI + Pydantic v2
- Uvicorn
- En memoria por ahora (sin DB real)

## Modelos principales
- SmartLock: dispositivo físico con estado y ubicación
- SecurityEvent: evento reportado por un lock
- Shipment: contenedor con locks asignados

## Endpoints planificados
- POST /locks
- GET /locks/{lock_id}
- PATCH /locks/{lock_id}/status
- POST /events
- GET /events
- GET /shipments/{id}/health

## Contexto del developer
Senior Software Engineer, aprendiendo FastAPI en profundidad.
Foco en buenas prácticas: validaciones, dependency injection, response models separados.