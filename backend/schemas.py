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
    rule_package_id: int | None = None
    rule_package_version: str = ""
    last_validated_at: str | None = None
    last_validation_status: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class RuleConfigIn(BaseModel):
    """规则包中单条规则的配置。"""

    code: str
    enabled: bool = True
    params: dict = Field(default_factory=dict)


class RulePackageCreate(BaseModel):
    name: str = ""
    version: str = ""
    remark: str = ""
    base_id: int | None = None  # 从哪个规则包克隆规则，缺省用内置默认


class RulePackageUpdate(BaseModel):
    name: str | None = None
    version: str | None = None
    remark: str | None = None
    effective_date: str | None = None
    rules: list[RuleConfigIn] | None = None


class RulePackagePublish(BaseModel):
    effective_date: str  # YYYY-MM-DD，允许未来日期（到期自动生效）
