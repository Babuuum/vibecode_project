from fastapi import APIRouter

from autocontent.api.schemas import HealthResponse
from autocontent.services import HealthService

api_router = APIRouter()
health_service = HealthService()


@api_router.get("/healthz", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    status = await health_service.get_status()
    return HealthResponse(status=status.status)
