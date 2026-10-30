from fastapi import APIRouter, Depends
from sqlmodel import SQLModel

from app.api.deps import require_roles
from app.models import Role

router = APIRouter(prefix="/metrics", tags=["metrics"])


class MetricsPublic(SQLModel):
    demo: bool = True
    active_users: int
    completed_tasks: int


@router.get("/", dependencies=[Depends(require_roles(Role.ADMIN, Role.MANAGER))])
def read_metrics() -> MetricsPublic:
    return MetricsPublic(active_users=24, completed_tasks=128)
