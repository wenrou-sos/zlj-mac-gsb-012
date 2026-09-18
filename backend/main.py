"""FastAPI 入口：标签 CRUD + 校验接口，生产模式下托管前端静态文件。"""
import json
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import Label
from schemas import LabelIn, LabelOut
from validators import validate_label

app = FastAPI(title="食品包装标签校验平台", version="1.0.0")

# 开发模式下前端跑在 vite dev server，放开跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_payload(label: Label, payload: LabelIn) -> Label:
    data = payload.model_dump()
    data["ingredients_json"] = json.dumps(data.pop("ingredients"), ensure_ascii=False)
    for key, value in data.items():
        setattr(label, key, value)
    return label


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/validate")
def validate(payload: LabelIn):
    """校验标签数据（不落库），返回检查结果、过敏原和营养表。"""
    return validate_label(payload.model_dump())


@app.get("/api/labels", response_model=list[LabelOut])
def list_labels(db: Session = Depends(get_db)):
    labels = db.scalars(select(Label).order_by(Label.updated_at.desc())).all()
    return [label.to_dict() for label in labels]


@app.post("/api/labels", response_model=LabelOut, status_code=201)
def create_label(payload: LabelIn, db: Session = Depends(get_db)):
    label = apply_payload(Label(), payload)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label.to_dict()


@app.get("/api/labels/{label_id}", response_model=LabelOut)
def get_label(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    return label.to_dict()


@app.put("/api/labels/{label_id}", response_model=LabelOut)
def update_label(label_id: int, payload: LabelIn, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    apply_payload(label, payload)
    db.commit()
    db.refresh(label)
    return label.to_dict()


@app.delete("/api/labels/{label_id}", status_code=204)
def delete_label(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(label)
    db.commit()


@app.get("/api/labels/{label_id}/validate")
def validate_saved(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    return validate_label(label.to_dict())


@app.on_event("startup")
def seed_demo_data():
    """首次启动写入一条示例数据，便于演示。"""
    db = SessionLocal()
    try:
        if db.scalar(select(Label).limit(1)):
            return
        demo = LabelIn(
            product_name="全麦消化饼干",
            brand="谷香坊",
            net_content_value=500,
            net_content_unit="g",
            standard_no="GB/T 20980",
            ingredients=[
                "小麦粉", "白砂糖", "植物油", "全麦粉", "鸡蛋",
                "奶粉", "芝麻", "膨松剂(碳酸氢钠)", "食用盐",
            ],
            allergen_statement="本品含有麸质谷物、蛋类、乳及乳制品、芝麻。",
            energy_kj=1980,
            protein_g=8.2,
            fat_g=18.5,
            carbohydrate_g=62.3,
            sodium_mg=320,
            shelf_life_value=12,
            shelf_life_unit="个月",
            storage_condition="请置于阴凉干燥处，避免阳光直射",
            production_date="2026-09-01",
            manufacturer="谷香坊食品有限公司",
            address="江苏省苏州市工业园区示例路 88 号",
            license_no="SC10632011500123",
        )
        db.add(apply_payload(Label(), demo))
        db.commit()
    finally:
        db.close()


# 生产模式：托管前端构建产物（Docker 镜像中由 Dockerfile 拷贝到 backend/static）
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
