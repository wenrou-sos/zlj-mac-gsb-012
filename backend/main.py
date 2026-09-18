"""FastAPI 入口：标签 CRUD + 校验 + 规则包版本管理 + 批量重检，生产模式托管前端。"""
import json
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import (
    Label,
    RecheckBatch,
    RecheckItem,
    RulePackage,
    ValidationRecord,
)
from recheck_service import create_recheck_batch, run_recheck_batch
from rule_catalog import catalog_payload, default_config
from rule_engine import RuleEngine
import rule_service
from schemas import (
    LabelIn,
    LabelOut,
    PackageDraftIn,
    PackagePublishIn,
    PackageUpdateIn,
    RecheckCreateIn,
    RuleSettingPatch,
)

app = FastAPI(title="食品包装标签校验平台", version="2.0.0")

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


def latest_validation_map(db: Session, label_ids: list[int]) -> dict[int, ValidationRecord]:
    if not label_ids:
        return {}
    rows = db.scalars(
        select(ValidationRecord).where(ValidationRecord.label_id.in_(label_ids)).order_by(
            ValidationRecord.label_id, ValidationRecord.created_at.desc(), ValidationRecord.id.desc()
        )
    ).all()
    latest: dict[int, ValidationRecord] = {}
    for row in rows:  # 已按 label + 时间倒序，首次出现即最近一条
        latest.setdefault(row.label_id, row)
    return latest


def run_and_persist_validation(db: Session, label: Label, pkg: RulePackage,
                               trigger: str) -> tuple[dict, ValidationRecord]:
    """以指定规则包快照执行校验并留痕。返回值同时带上规则版本戳。"""
    result = RuleEngine(pkg.config).validate(label.to_dict())
    record = ValidationRecord(
        label_id=label.id,
        package_id=pkg.id,
        package_version=pkg.version,
        trigger=trigger,
        status=result["status"],
        result_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(record)
    db.flush()
    result["rule_package"] = rule_service.package_ref(pkg)
    result["record_id"] = record.id
    return result, record


# ---------------- 基础 ----------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------- 规则目录 ----------------
@app.get("/api/rule-catalog")
def get_rule_catalog():
    """内置规则目录、参数编辑器 schema、默认配置（草稿编辑器初始化用）。"""
    return catalog_payload()


# ---------------- 规则包 ----------------
@app.get("/api/rule-packages")
def list_packages(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(RulePackage).order_by(
        RulePackage.family, RulePackage.version.desc()
    )
    if status:
        stmt = stmt.where(RulePackage.status == status)
    return [pkg.to_dict() for pkg in db.scalars(stmt).all()]


@app.get("/api/rule-packages/effective")
def effective_package(db: Session = Depends(get_db)):
    """当前生效中的规则包（供界面展示“当前执行版本”）。"""
    try:
        return rule_service.resolve_package(db, None).to_dict()
    except LookupError:
        raise HTTPException(status_code=404, detail="尚无已发布的规则包")


@app.post("/api/rule-packages/draft", status_code=201)
def create_draft(payload: PackageDraftIn, db: Session = Depends(get_db)):
    try:
        pkg = rule_service.create_draft(
            db,
            name=payload.name,
            description=payload.description,
            effective_date=payload.effective_date,
            based_on_package_id=payload.based_on_package_id,
            family=payload.family,
        )
        db.commit()
        db.refresh(pkg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return pkg.to_dict()


@app.get("/api/rule-packages/{package_id}")
def get_package(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(RulePackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="规则包不存在")
    return pkg.to_dict()


@app.put("/api/rule-packages/{package_id}")
def update_package(package_id: int, payload: PackageUpdateIn, db: Session = Depends(get_db)):
    pkg = db.get(RulePackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="规则包不存在")
    if pkg.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿状态的规则包可以修改")

    if payload.name is not None:
        pkg.name = payload.name
    if payload.description is not None:
        pkg.description = payload.description
    if payload.effective_date is not None:
        try:
            date.fromisoformat(payload.effective_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="生效日期格式应为 YYYY-MM-DD")
        pkg.effective_date = payload.effective_date
    if payload.config is not None:
        error = rule_service.validate_config(payload.config)
        if error:
            raise HTTPException(status_code=400, detail=error)
        pkg.config_json = json.dumps(payload.config, ensure_ascii=False)
    db.commit()
    db.refresh(pkg)
    return pkg.to_dict()


@app.patch("/api/rule-packages/{package_id}/rules/{code}")
def patch_rule(package_id: int, code: str, patch: RuleSettingPatch,
               db: Session = Depends(get_db)):
    """单条规则启停 / 严重级别 / 参数（仅草稿）。"""
    pkg = db.get(RulePackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="规则包不存在")
    if pkg.status != "draft":
        raise HTTPException(status_code=409, detail="只有草稿状态的规则包可以修改")

    config = pkg.config
    rules = config.setdefault("rules", {})
    if code not in default_config()["rules"]:
        raise HTTPException(status_code=404, detail=f"规则 {code} 不在目录中")
    setting = rules.setdefault(code, {"enabled": True, "severity": None, "params": {}})

    if patch.enabled is not None:
        setting["enabled"] = patch.enabled
    if patch.severity is not None:
        setting["severity"] = patch.severity
    if patch.params is not None:
        setting.setdefault("params", {}).update(patch.params)
    error = rule_service.validate_config(config)
    if error:
        raise HTTPException(status_code=400, detail=error)
    pkg.config_json = json.dumps(config, ensure_ascii=False)
    db.commit()
    db.refresh(pkg)
    return pkg.to_dict()


@app.post("/api/rule-packages/{package_id}/publish")
def publish_package(package_id: int, payload: PackagePublishIn, db: Session = Depends(get_db)):
    pkg = db.get(RulePackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="规则包不存在")
    error = rule_service.validate_config(pkg.config)
    if error:
        raise HTTPException(status_code=400, detail=f"配置校验未通过：{error}")
    try:
        rule_service.publish_package(db, pkg, payload.effective_date)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.refresh(pkg)
    return pkg.to_dict()


@app.post("/api/rule-packages/{package_id}/archive")
def archive_package(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(RulePackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="规则包不存在")
    if pkg.status != "published":
        raise HTTPException(status_code=409, detail="只有已发布的规则包可以归档")
    pkg.status = "archived"
    db.commit()
    db.refresh(pkg)
    return pkg.to_dict()


@app.delete("/api/rule-packages/{package_id}", status_code=204)
def delete_package(package_id: int, db: Session = Depends(get_db)):
    pkg = db.get(RulePackage, package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="规则包不存在")
    if pkg.status != "draft":
        raise HTTPException(status_code=409, detail="只能删除草稿；已发布版本作为审计快照保留")
    used = db.scalar(select(ValidationRecord).where(ValidationRecord.package_id == pkg.id).limit(1))
    if used:
        raise HTTPException(status_code=409, detail="该草稿已产生校验留痕，不能删除")
    db.delete(pkg)
    db.commit()


# ---------------- 校验 ----------------
@app.post("/api/validate")
def validate(payload: LabelIn, package_id: int | None = Query(default=None),
             db: Session = Depends(get_db)):
    """实时校验（不落库、不留痕）。默认用当前生效规则包，可指定草稿包试用。"""
    try:
        pkg = rule_service.resolve_package(db, package_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    result = RuleEngine(pkg.config).validate(payload.model_dump())
    result["rule_package"] = rule_service.package_ref(pkg)
    return result


@app.get("/api/labels", response_model=list[LabelOut])
def list_labels(db: Session = Depends(get_db)):
    labels = db.scalars(select(Label).order_by(Label.updated_at.desc())).all()
    latest_map = latest_validation_map(db, [lb.id for lb in labels])
    return [lb.to_dict(latest_map.get(lb.id)) for lb in labels]


@app.post("/api/labels", response_model=LabelOut, status_code=201)
def create_label(payload: LabelIn, db: Session = Depends(get_db)):
    label = apply_payload(Label(), payload)
    db.add(label)
    db.flush()
    # 保存即按当前生效规则包校验并留痕（标签从第一版起就有规则版本记录）
    pkg = rule_service.resolve_package(db, None)
    run_and_persist_validation(db, label, pkg, trigger="save")
    db.commit()
    db.refresh(label)
    latest = latest_validation_map(db, [label.id]).get(label.id)
    return label.to_dict(latest)


@app.get("/api/labels/{label_id}", response_model=LabelOut)
def get_label(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    latest = latest_validation_map(db, [label.id]).get(label.id)
    return label.to_dict(latest)


@app.put("/api/labels/{label_id}", response_model=LabelOut)
def update_label(label_id: int, payload: LabelIn, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    apply_payload(label, payload)
    db.flush()
    pkg = rule_service.resolve_package(db, None)
    run_and_persist_validation(db, label, pkg, trigger="save")
    db.commit()
    db.refresh(label)
    latest = latest_validation_map(db, [label.id]).get(label.id)
    return label.to_dict(latest)


@app.delete("/api/labels/{label_id}", status_code=204)
def delete_label(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(label)  # 校验留痕随级联删除；重检明细保留历史快照不受影响
    db.commit()


@app.get("/api/labels/{label_id}/validate")
def validate_saved(label_id: int, package_id: int | None = Query(default=None),
                   persist: bool = Query(default=True), db: Session = Depends(get_db)):
    """校验已保存标签。默认留痕（trigger=manual），可指定任意包（含草稿）试用。"""
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    try:
        pkg = rule_service.resolve_package(db, package_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not persist:
        result = RuleEngine(pkg.config).validate(label.to_dict())
        result["rule_package"] = rule_service.package_ref(pkg)
        return result
    result, _ = run_and_persist_validation(db, label, pkg, trigger="manual")
    db.commit()
    return result


@app.get("/api/labels/{label_id}/validations")
def list_validations(label_id: int, db: Session = Depends(get_db)):
    """标签的校验留痕历史（含每次使用的规则版本）。"""
    if not db.get(Label, label_id):
        raise HTTPException(status_code=404, detail="标签不存在")
    records = db.scalars(
        select(ValidationRecord).where(ValidationRecord.label_id == label_id)
        .order_by(ValidationRecord.created_at.desc(), ValidationRecord.id.desc())
    ).all()
    return [r.to_dict() for r in records]


# ---------------- 批量重检 ----------------
@app.post("/api/rechecks", status_code=201)
def create_recheck(payload: RecheckCreateIn, db: Session = Depends(get_db)):
    try:
        batch = create_recheck_batch(
            db,
            package_id=payload.package_id,
            baseline_package_id=payload.baseline_package_id,
            label_ids=payload.label_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # 后台线程独立会话执行；快照已在任务内载入，发布新包不影响本次重检
    import threading

    thread = threading.Thread(
        target=run_recheck_batch, args=(batch.id, SessionLocal), daemon=True
    )
    thread.start()
    db.refresh(batch)
    return batch.to_dict()


@app.get("/api/rechecks")
def list_rechecks(db: Session = Depends(get_db)):
    batches = db.scalars(select(RecheckBatch).order_by(RecheckBatch.created_at.desc())).all()
    return [b.to_dict() for b in batches]


@app.get("/api/rechecks/{batch_id}")
def get_recheck(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(RecheckBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="重检任务不存在")
    return batch.to_dict(include_items=True)


# ---------------- 启动种子 ----------------
@app.on_event("startup")
def seed_data():
    """初始化内置规则包 v1（已发布、当天生效）、示例标签，并为存量标签补留痕。"""
    db = SessionLocal()
    try:
        if not db.scalar(select(RulePackage).limit(1)):
            today = date.today().isoformat()
            from datetime import datetime

            pkg = RulePackage(
                family="GB_CORE",
                name="GB 7718 / GB 28050 核心校验规则",
                description="平台内置的食品标签核心校验规则（字段完整性、单位规范、营养成分、过敏原）。",
                version=1,
                status="published",
                config_json=json.dumps(default_config(), ensure_ascii=False),
                effective_date=today,
                published_at=datetime.utcnow(),
            )
            db.add(pkg)
            db.commit()
            db.refresh(pkg)

        # 为没有任何留痕的存量标签补一次当前生效版本的校验记录
        pkg = rule_service.resolve_package(db, None)
        labels_with_records = set(db.scalars(
            select(ValidationRecord.label_id).distinct()
        ).all())
        for label in db.scalars(select(Label).order_by(Label.id)).all():
            if label.id not in labels_with_records:
                run_and_persist_validation(db, label, pkg, trigger="save")
        db.commit()

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
        label = apply_payload(Label(), demo)
        db.add(label)
        db.flush()
        run_and_persist_validation(db, label, pkg, trigger="save")
        db.commit()
    finally:
        db.close()


# 生产模式：托管前端构建产物（Docker 镜像中由 Dockerfile 拷贝到 backend/static）
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
