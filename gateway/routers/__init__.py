from routers.health import router as health_router
from routers.models import router as models_router
from routers.speech import router as speech_router

__all__ = ["speech_router", "models_router", "health_router"]

