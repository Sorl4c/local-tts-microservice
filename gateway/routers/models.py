from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from schemas import ModelEntry, ModelListResponse
from service import TTSGatewayService

router = APIRouter(tags=["models"])


@router.get("/v1/models", response_model=ModelListResponse)
async def list_models(request: Request) -> ModelListResponse:
    service: TTSGatewayService = request.app.state.tts_service
    engines = list(service.adapters.items())

    model_lists = await asyncio.gather(*(adapter.list_models() for _, adapter in engines), return_exceptions=True)

    entries: list[ModelEntry] = []
    seen_ids: set[tuple[str, str]] = set()
    for (engine_name, _adapter), models in zip(engines, model_lists):
        if isinstance(models, Exception):
            continue

        for model in models:
            model_id = str(model.get("id", "")).strip() or f"{engine_name}-default"
            key = (engine_name, model_id)
            if key in seen_ids:
                continue
            seen_ids.add(key)
            entries.append(
                ModelEntry(
                    id=model_id,
                    owned_by=str(model.get("owned_by", "local")),
                    engine=engine_name,  # type: ignore[arg-type]
                    metadata={k: v for k, v in model.items() if k not in {"id", "object", "owned_by"}},
                )
            )

    entries.sort(key=lambda item: (item.engine, item.id))
    return ModelListResponse(data=entries)

