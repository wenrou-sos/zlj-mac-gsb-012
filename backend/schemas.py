"""Pydantic 入参/出参模型。标签字段可缺省，由校验引擎负责完整性检查。"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class LabelIn(BaseModel):
    # 基本信息
    product_name: str = ""
    brand: str = ""
    net_content_value: float | None = None
    net_content_unit: str = "g"
    standard_no: str = ""

    # 配料与过敏原
    ingredients: list[str] = Field(default_factory=list)
    allergen_statement: str = ""

    # 营养成分（每 100g/mL）
    energy_kj: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbohydrate_g: float | None = None
    sodium_mg: float | None = None

    # 保质期与贮存
    shelf_life_value: int | None = None
    shelf_life_unit: str = "天"
    storage_condition: str = ""
    production_date: str = ""  # YYYY-MM-DD

    # 生产信息
    manufacturer: str = ""
    address: str = ""
    license_no: str = ""


class LabelOut(LabelIn):
    id: int
    created_at: str | None = None
    updated_at: str | None = None
    # 最近一次持久化校验的摘要（规则版本随标签一起返回）
    latest_status: str | None = None
    latest_package_id: int | None = None
    latest_package_version: int | None = None
    latest_validated_at: str | None = None


# ---------------- 规则包 ----------------
class RuleSettingPatch(BaseModel):
    enabled: bool | None = None
    severity: Literal["error", "warning", "pass"] | None = None
    params: dict[str, Any] | None = None


class PackageDraftIn(BaseModel):
    """创建草稿：可基于某个已发布包复制，或完全使用默认目录配置。"""
    name: str | None = None
    description: str = ""
    effective_date: str | None = None  # YYYY-MM-DD
    based_on_package_id: int | None = None
    family: str = "GB_CORE"


class PackageUpdateIn(BaseModel):
    """编辑草稿元信息 / 整体配置（仅草稿可改）。"""
    name: str | None = None
    description: str | None = None
    effective_date: str | None = None
    config: dict[str, Any] | None = None


class PackagePublishIn(BaseModel):
    effective_date: str | None = None  # 不传则取今天


# ---------------- 批量重检 ----------------
class RecheckCreateIn(BaseModel):
    package_id: int
    baseline_package_id: int | None = None  # 不传则自动取每条标签最近一次留痕所用版本
    label_ids: list[int] | None = None  # 不传则重检全部历史标签
