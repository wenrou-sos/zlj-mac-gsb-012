"""SQLAlchemy 模型：标签记录。配料表以 JSON 字符串存储。"""
import json
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
