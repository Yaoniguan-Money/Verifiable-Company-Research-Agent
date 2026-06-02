from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.feature_flags import ALLOWED_FLAGS, get_all_flags, reset_all, set_flag

router = APIRouter(prefix="/api/admin", tags=["admin"])


class FeatureFlagRead(BaseModel):
    name: str
    label: str
    description: str
    value: Any
    default: Any
    options: list[str] | None = None


class FeatureFlagsResponse(BaseModel):
    flags: list[FeatureFlagRead]


class UpdateFeatureFlagRequest(BaseModel):
    name: str
    value: Any


class UpdateFeatureFlagResponse(BaseModel):
    ok: bool
    name: str
    value: Any


class ResetFeatureFlagsResponse(BaseModel):
    ok: bool


@router.get("/flags", response_model=FeatureFlagsResponse)
def list_feature_flags() -> FeatureFlagsResponse:
    values = get_all_flags()
    flags = [
        FeatureFlagRead(
            name=name,
            label=str(meta["label"]),
            description=str(meta["description"]),
            value=values[name],
            default=meta["default"],
            options=meta.get("options"),
        )
        for name, meta in ALLOWED_FLAGS.items()
    ]
    return FeatureFlagsResponse(flags=flags)


@router.patch("/flags", response_model=UpdateFeatureFlagResponse)
def update_feature_flag(body: UpdateFeatureFlagRequest) -> UpdateFeatureFlagResponse:
    meta = ALLOWED_FLAGS.get(body.name)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown feature flag: {body.name}",
        )

    options = meta.get("options")
    if options is not None and body.value not in options:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid value for {body.name}. Allowed values: {', '.join(options)}",
        )

    if options is None and not isinstance(body.value, bool):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Feature flag {body.name} expects a boolean value.",
        )

    set_flag(body.name, body.value)
    return UpdateFeatureFlagResponse(ok=True, name=body.name, value=body.value)


@router.post("/flags/reset", response_model=ResetFeatureFlagsResponse)
def reset_feature_flags() -> ResetFeatureFlagsResponse:
    reset_all()
    return ResetFeatureFlagsResponse(ok=True)
