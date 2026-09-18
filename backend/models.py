"""SQLAlchemy 模型：标签、规则包、校验记录与批量重检任务。"""
import json
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

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

    # 最近一次校验使用的规则版本（冗余自 Validation，便于列表展示与追溯）
    rule_package_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_package_version: Mapped[str] = mapped_column(String(50), default="")
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_validation_status: Mapped[str] = mapped_column(String(20), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    @property
    def ingredients(self) -> list[str]:
        try:
            return json.loads(self.ingredients_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self) -> dict:
        return {
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
            "rule_package_id": self.rule_package_id,
            "rule_package_version": self.rule_package_version,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "last_validation_status": self.last_validation_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RulePackage(Base):
    """法规规则包。已发布的包不可变：发布即冻结规则快照，
    保证执行中的校验与历史校验记录始终可复现。"""

    __tablename__ = "rule_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    version: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft / published
    effective_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    remark: Mapped[str] = mapped_column(Text, default="")
    rules_json: Mapped[str] = mapped_column(Text, default="[]")  # [{code, enabled, params}]

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def rules(self) -> list[dict]:
        try:
            return json.loads(self.rules_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self, with_rules: bool = False, active_id: int | None = None) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "effective_date": self.effective_date,
            "remark": self.remark,
            "is_active": self.id == active_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }
        if with_rules:
            data["rules"] = self.rules
        return data


class Validation(Base):
    """一次校验的留痕：标签在某规则版本下的完整结果快照。"""

    __tablename__ = "validations"

    id: Mapped[int] = mapped_column(primary_key=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id"), index=True)
    package_id: Mapped[int] = mapped_column(Integer)
    package_version: Mapped[str] = mapped_column(String(50), default="")
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # save / manual / batch / init
    status: Mapped[str] = mapped_column(String(20), default="")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    results_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def summary(self) -> dict:
        try:
            return json.loads(self.summary_json or "{}")
        except json.JSONDecodeError:
            return {}

    @property
    def results(self) -> list[dict]:
        try:
            return json.loads(self.results_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self, with_results: bool = False) -> dict:
        data = {
            "id": self.id,
            "label_id": self.label_id,
            "package_id": self.package_id,
            "package_version": self.package_version,
            "trigger": self.trigger,
            "status": self.status,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if with_results:
            data["results"] = self.results
        return data


class RecheckJob(Base):
    """批量重检任务：用某个已发布规则包重跑全部历史标签。"""

    __tablename__ = "recheck_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(Integer)
    package_version: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(20), default="running")  # running / done / failed
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    changed: Mapped[int] = mapped_column(Integer, default=0)  # 新旧结论有差异的标签数
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "package_id": self.package_id,
            "package_version": self.package_version,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "changed": self.changed,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class RecheckItem(Base):
    """单个标签的重检结果与新旧差异。"""

    __tablename__ = "recheck_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("recheck_jobs.id"), index=True)
    label_id: Mapped[int] = mapped_column(Integer)
    label_name: Mapped[str] = mapped_column(String(200), default="")
    old_validation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_validation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_package_version: Mapped[str] = mapped_column(String(50), default="")
    old_status: Mapped[str] = mapped_column(String(20), default="")
    new_status: Mapped[str] = mapped_column(String(20), default="")
    diff_json: Mapped[str] = mapped_column(Text, default="[]")

    @property
    def diff(self) -> list[dict]:
        try:
            return json.loads(self.diff_json or "[]")
        except json.JSONDecodeError:
            return []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "label_id": self.label_id,
            "label_name": self.label_name,
            "old_validation_id": self.old_validation_id,
            "new_validation_id": self.new_validation_id,
            "old_package_version": self.old_package_version,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "diff": self.diff,
        }
