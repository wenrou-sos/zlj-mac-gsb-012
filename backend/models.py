"""SQLAlchemy 模型。

- Label：标签记录（配料表以 JSON 字符串存储）
- RulePackage：可版本化的法规规则包（草稿 / 已发布，配置为不可变 JSON 快照）
- ValidationRecord：每次持久化校验的留痕（记录使用的规则包版本与完整结果）
- RecheckBatch / RecheckItem：新规则发布后对历史标签的批量重检任务与逐条差异
"""
import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 基本信息
    product_name: Mapped[str] = mapped_column(String(200), default="")
    brand: Mapped[str] = mapped_column(String(100), default="")
    net_content_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_content_unit: Mapped[str] = mapped_column(String(10), default="g")
    standard_no: Mapped[str] = mapped_column(String(50), default="")

    # 配料与过敏原
    ingredients_json: Mapped[str] = mapped_column(Text, default="[]")
    allergen_statement: Mapped[str] = mapped_column(Text, default="")

    # 营养成分（每 100g/mL）
    energy_kj: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbohydrate_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sodium_mg: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 保质期与贮存
    shelf_life_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shelf_life_unit: Mapped[str] = mapped_column(String(10), default="天")
    storage_condition: Mapped[str] = mapped_column(String(200), default="")
    production_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD

    # 生产信息
    manufacturer: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    license_no: Mapped[str] = mapped_column(String(20), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    validations: Mapped[list["ValidationRecord"]] = relationship(
        back_populates="label", cascade="all, delete-orphan"
    )

    @property
    def ingredients(self) -> list[str]:
        try:
            return json.loads(self.ingredients_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self, latest: "ValidationRecord | None" = None) -> dict:
        data = {
            "id": self.id,
            "product_name": self.product_name,
            "brand": self.brand,
            "net_content_value": self.net_content_value,
            "net_content_unit": self.net_content_unit,
            "standard_no": self.standard_no,
            "ingredients": self.ingredients,
            "allergen_statement": self.allergen_statement,
            "energy_kj": self.energy_kj,
            "protein_g": self.protein_g,
            "fat_g": self.fat_g,
            "carbohydrate_g": self.carbohydrate_g,
            "sodium_mg": self.sodium_mg,
            "shelf_life_value": self.shelf_life_value,
            "shelf_life_unit": self.shelf_life_unit,
            "storage_condition": self.storage_condition,
            "production_date": self.production_date,
            "manufacturer": self.manufacturer,
            "address": self.address,
            "license_no": self.license_no,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "latest_status": None,
            "latest_package_id": None,
            "latest_package_version": None,
            "latest_validated_at": None,
        }
        if latest is not None:
            data.update({
                "latest_status": latest.status,
                "latest_package_id": latest.package_id,
                "latest_package_version": latest.package_version,
                "latest_validated_at": latest.created_at.isoformat() if latest.created_at else None,
            })
        return data


class RulePackage(Base):
    """法规规则包。同一系列（family）通过自增 version 串成版本链。

    - draft：可任意修改配置、生效日期；同一 family 至多一个草稿
    - published：不可变快照，仅允许归档（archived）
    """
    __tablename__ = "rule_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    family: Mapped[str] = mapped_column(String(50), default="GB_CORE", index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft/published/archived
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    effective_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def config(self) -> dict:
        try:
            return json.loads(self.config_json or "{}")
        except json.JSONDecodeError:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "family": self.family,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "status": self.status,
            "config": self.config,
            "effective_date": self.effective_date or None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ValidationRecord(Base):
    """校验留痕：每条记录都钉死校验时使用的规则包版本与完整结果。"""
    __tablename__ = "validation_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id", ondelete="CASCADE"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("rule_packages.id"), index=True)
    package_version: Mapped[int] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(String(20), default="validate")  # save/manual/recheck

    status: Mapped[str] = mapped_column(String(20))
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    label: Mapped["Label"] = relationship(back_populates="validations")

    @property
    def result(self) -> dict:
        try:
            return json.loads(self.result_json or "{}")
        except json.JSONDecodeError:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label_id": self.label_id,
            "package_id": self.package_id,
            "package_version": self.package_version,
            "trigger": self.trigger,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RecheckBatch(Base):
    """批量重检任务：以某个已发布规则包快照重检历史标签。"""
    __tablename__ = "recheck_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("rule_packages.id"))
    package_version: Mapped[int] = mapped_column(Integer)
    baseline_package_id: Mapped[int | None] = mapped_column(
        ForeignKey("rule_packages.id"), nullable=True
    )
    baseline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    total: Mapped[int] = mapped_column(Integer, default=0)
    scope_json: Mapped[str] = mapped_column(Text, default="")  # 重检范围：[] 表示全部标签
    processed: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["RecheckItem"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )

    def to_dict(self, include_items: bool = False) -> dict:
        try:
            scope = json.loads(self.scope_json or "[]")
        except json.JSONDecodeError:
            scope = []
        data = {
            "id": self.id,
            "package_id": self.package_id,
            "package_version": self.package_version,
            "baseline_package_id": self.baseline_package_id,
            "baseline_version": self.baseline_version,
            "status": self.status,
            "total": self.total,
            "scope": scope,
            "processed": self.processed,
            "changed_count": self.changed_count,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }
        if include_items:
            data["items"] = [item.to_dict() for item in sorted(self.items, key=lambda i: i.id)]
        return data


class RecheckItem(Base):
    """批量重检单条结果：快照标签数据、新旧整体结论与逐条规则差异。"""
    __tablename__ = "recheck_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recheck_batches.id", ondelete="CASCADE"), index=True)
    label_id: Mapped[int] = mapped_column(Integer, index=True)
    label_name: Mapped[str] = mapped_column(String(200), default="")

    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), default="pass")
    changed: Mapped[bool] = mapped_column(default=False)
    diff_json: Mapped[str] = mapped_column(Text, default="[]")
    new_result_json: Mapped[str] = mapped_column(Text, default="{}")
    old_result_json: Mapped[str] = mapped_column(Text, default="{}")
    new_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    batch: Mapped["RecheckBatch"] = relationship(back_populates="items")

    def to_dict(self) -> dict:
        def loads(raw, fallback):
            try:
                return json.loads(raw or fallback)
            except json.JSONDecodeError:
                return json.loads(fallback)

        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "label_id": self.label_id,
            "label_name": self.label_name,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "changed": self.changed,
            "diff": loads(self.diff_json, "[]"),
            "new_result": loads(self.new_result_json, "{}"),
            "old_result": loads(self.old_result_json, "{}"),
            "new_record_id": self.new_record_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
