from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from schemas import BackendHealth, HealthResponse
from service import TTSGatewayService

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz(request: Request) -> JSONResponse:
    service: TTSGatewayService = request.app.state.tts_service
    engines = list(service.adapters.items())

    checks = await asyncio.gather(*(adapter.health_check() for _, adapter in engines), return_exceptions=True)
    backend_items: list[BackendHealth] = []
    all_ok = True

    for (engine_name, _adapter), result in zip(engines, checks):
        if isinstance(result, Exception):
            all_ok = False
            backend_items.append(
                BackendHealth(engine=engine_name, healthy=False, detail=str(result))  # type: ignore[arg-type]
            )
            continue

        if not result.healthy:
            all_ok = False
        backend_items.append(
            BackendHealth(engine=engine_name, healthy=result.healthy, detail=result.detail)  # type: ignore[arg-type]
        )

    payload = HealthResponse(status="ok" if all_ok else "degraded", backends=backend_items)
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload.model_dump(),
    )

