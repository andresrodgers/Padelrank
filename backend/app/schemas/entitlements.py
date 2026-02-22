from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


PlanCode = Literal["FREE", "RIVIO_PLUS"]


class EntitlementOut(BaseModel):
    plan_code: PlanCode
    ads_enabled: bool
    activated_at: datetime
    expires_at: datetime | None = None


class EntitlementFeatureSetOut(BaseModel):
    analytics_kpis: list[str] = Field(default_factory=list)
    analytics_series: list[str] = Field(default_factory=list)
    export_enabled: bool = False
    ads_enabled: bool = True


class EntitlementContractOut(BaseModel):
    current: EntitlementOut
    basic: EntitlementFeatureSetOut
    plus: EntitlementFeatureSetOut
    effective: EntitlementFeatureSetOut


class PlanDefinitionOut(BaseModel):
    plan_code: PlanCode
    display_name: str
    description: str
    features: EntitlementFeatureSetOut


class PlanCatalogOut(BaseModel):
    current_plan: PlanCode
    plans: list[PlanDefinitionOut] = Field(default_factory=list)


class EntitlementSimulateIn(BaseModel):
    plan_code: PlanCode
    duration_days: int | None = Field(default=None, ge=1, le=3650)
