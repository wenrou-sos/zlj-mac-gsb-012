"""Pydantic 入参模型。所有字段可缺省，由校验引擎负责完整性检查。"""
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
