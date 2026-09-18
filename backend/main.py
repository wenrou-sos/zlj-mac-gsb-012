"""FastAPI 入口：标签 CRUD + 校验 + 规则包版本管理 + 批量重检。"""
import json
import re
from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import Label, RecheckItem, RecheckJob, RulePackage, Validation
from rule_service import (
    active_package_id,
    latest_validation,
    parse_rules,
    record_validation,
    resolve_active_package,
    snapshot_of,
    start_recheck_job,
    validate_with_snapshot,
)
from rules import CATEGORY_LABELS, RULE_DEFINITIONS, default_rule_configs
from schemas import (
    LabelIn,
    LabelOut,
    RulePackageCreate,
    RulePackagePublish,
    RulePackageUpdate,
)
from validators import validate_label  # noqa: F401  保持原有导入路径兼容

app = FastAPI(title="食品包装标签校验平台", version="2.0.0")

# 开发模式下前端跑在 vite dev server，放开跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(engine)

DATE_FMT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def migrate_schema():
    """轻量迁移：为既有 labels 表补充规则版本相关列（新表由 create_all 创建）。"""
    new_columns = {
        "rule_package_id": "INTEGER",
        "rule_package_version": "VARCHAR(50) DEFAULT ''",
        "last_validated_at": "DATETIME",
        "last_validation_status": "VARCHAR(20) DEFAULT ''",
    }
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(labels)")}
        for column, ddl in new_columns.items():
            if column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE labels ADD COLUMN {column} {ddl}")
        conn.commit()


migrate_schema()


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


def validate_and_record(db: Session, label: Label, trigger: str) -> None:
    """用当前生效规则包校验标签并留痕（保存/手动校验时调用）。"""
    package = resolve_active_package(db)
    snapshot = snapshot_of(package) if package else None
    result = validate_with_snapshot(label.to_dict(), snapshot)
    record_validation(db, label, result, snapshot, trigger)


def get_package_or_404(db: Session, package_id: int) -> RulePackage:
    package = db.get(RulePackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="规则包不存在")
    return package


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/validate")
def validate(payload: LabelIn, package_id: int | None = None, db: Session = Depends(get_db)):
    """校验标签数据（不落库）。默认使用当前生效规则包，
    可通过 package_id 指定任意版本（用于草稿预览与版本对比）。"""
    if package_id is not None:
        package = get_package_or_404(db, package_id)
    else:
        package = resolve_active_package(db)
    snapshot = snapshot_of(package) if package else None
    return validate_with_snapshot(payload.model_dump(), snapshot)


# ---------------------------------------------------------------------------
# 标签
# ---------------------------------------------------------------------------

@app.get("/api/labels", response_model=list[LabelOut])
def list_labels(db: Session = Depends(get_db)):
    labels = db.scalars(select(Label).order_by(Label.updated_at.desc())).all()
    return [label.to_dict() for label in labels]


@app.post("/api/labels", response_model=LabelOut, status_code=201)
def create_label(payload: LabelIn, db: Session = Depends(get_db)):
    label = apply_payload(Label(), payload)
    db.add(label)
    db.flush()
    validate_and_record(db, label, trigger="save")
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
    validate_and_record(db, label, trigger="save")
    db.commit()
    db.refresh(label)
    return label.to_dict()


@app.delete("/api/labels/{label_id}", status_code=204)
def delete_label(label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.query(Validation).filter(Validation.label_id == label_id).delete()
    db.delete(label)
    db.commit()


@app.get("/api/labels/{label_id}/validate")
def validate_saved(label_id: int, db: Session = Depends(get_db)):
    """用当前生效规则包校验已保存的标签，并把结果与规则版本留痕。"""
    label = db.get(Label, label_id)
    if not label:
        raise HTTPException(status_code=404, detail="标签不存在")
    package = resolve_active_package(db)
    snapshot = snapshot_of(package) if package else None
    result = validate_with_snapshot(label.to_dict(), snapshot)
    record_validation(db, label, result, snapshot, trigger="manual")
    db.commit()
    return result


@app.get("/api/labels/{label_id}/validations")
def label_validations(label_id: int, db: Session = Depends(get_db)):
    """标签的校验历史（每次校验所用的规则版本与结论）。"""
    if not db.get(Label, label_id):
        raise HTTPException(status_code=404, detail="标签不存在")
    records = db.scalars(
        select(Validation)
        .where(Validation.label_id == label_id)
        .order_by(Validation.id.desc())
        .limit(50)
    ).all()
    return [r.to_dict() for r in records]


# ---------------------------------------------------------------------------
# 规则包
# ---------------------------------------------------------------------------

@app.get("/api/rule-definitions")
def rule_definitions():
    """全部规则定义（含参数 schema），供规则编辑器渲染。"""
    return {
        "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
        "definitions": RULE_DEFINITIONS,
    }


@app.get("/api/rule-packages")
def list_rule_packages(db: Session = Depends(get_db)):
    active_id = active_package_id(db)
    packages = db.scalars(select(RulePackage).order_by(RulePackage.id.desc())).all()
    return [p.to_dict(active_id=active_id) for p in packages]


@app.post("/api/rule-packages", status_code=201)
def create_rule_package(payload: RulePackageCreate, db: Session = Depends(get_db)):
    """新建草稿：默认克隆当前生效包（或 base_id 指定包）的规则。"""
    if payload.base_id is not None:
        base = get_package_or_404(db, payload.base_id)
        rules = parse_rules(base)
    else:
        active = resolve_active_package(db)
        rules = parse_rules(active) if active else default_rule_configs()

    count = db.scalar(select(func.count(RulePackage.id))) or 0
    package = RulePackage(
        name=payload.name.strip() or "GB 7718 / GB 28050 标签合规规则",
        version=payload.version.strip() or f"v{count + 1}.0",
        remark=payload.remark.strip(),
        status="draft",
        rules_json=json.dumps(rules, ensure_ascii=False),
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package.to_dict(with_rules=True, active_id=active_package_id(db))


@app.get("/api/rule-packages/{package_id}")
def get_rule_package(package_id: int, db: Session = Depends(get_db)):
    package = get_package_or_404(db, package_id)
    return package.to_dict(with_rules=True, active_id=active_package_id(db))


@app.put("/api/rule-packages/{package_id}")
def update_rule_package(package_id: int, payload: RulePackageUpdate, db: Session = Depends(get_db)):
    """更新草稿（名称、版本号、生效日期、规则启停与参数）。已发布包不可变。"""
    package = get_package_or_404(db, package_id)
    if package.status != "draft":
        raise HTTPException(status_code=409, detail="已发布的规则包不可修改，请新建草稿版本")

    if payload.name is not None:
        package.name = payload.name.strip() or package.name
    if payload.version is not None:
        package.version = payload.version.strip() or package.version
    if payload.remark is not None:
        package.remark = payload.remark.strip()
    if payload.effective_date is not None:
        if payload.effective_date and not DATE_FMT_RE.match(payload.effective_date):
            raise HTTPException(status_code=422, detail="生效日期格式应为 YYYY-MM-DD")
        package.effective_date = payload.effective_date
    if payload.rules is not None:
        known = {d["code"] for d in RULE_DEFINITIONS}
        unknown = [r.code for r in payload.rules if r.code not in known]
        if unknown:
            raise HTTPException(status_code=422, detail=f"未知规则编码：{'、'.join(unknown)}")
        package.rules_json = json.dumps(
            [r.model_dump() for r in payload.rules], ensure_ascii=False
        )
    db.commit()
    db.refresh(package)
    return package.to_dict(with_rules=True, active_id=active_package_id(db))


@app.post("/api/rule-packages/{package_id}/publish")
def publish_rule_package(package_id: int, payload: RulePackagePublish, db: Session = Depends(get_db)):
    """发布草稿：冻结规则快照并设定生效日期。

    发布只翻转状态，不改写任何历史数据；生效中的校验与重检任务
    持有各自启动时的快照，因此不受本次发布影响。
    """
    package = get_package_or_404(db, package_id)
    if package.status != "draft":
        raise HTTPException(status_code=409, detail="该规则包已发布")
    if not DATE_FMT_RE.match(payload.effective_date):
        raise HTTPException(status_code=422, detail="生效日期格式应为 YYYY-MM-DD")
    package.status = "published"
    package.effective_date = payload.effective_date
    package.published_at = datetime.utcnow()
    db.commit()
    db.refresh(package)
    return package.to_dict(with_rules=True, active_id=active_package_id(db))


@app.delete("/api/rule-packages/{package_id}", status_code=204)
def delete_rule_package(package_id: int, db: Session = Depends(get_db)):
    package = get_package_or_404(db, package_id)
    if package.status != "draft":
        raise HTTPException(status_code=409, detail="已发布的规则包不可删除（需保留用于追溯）")
    db.delete(package)
    db.commit()


@app.post("/api/rule-packages/{package_id}/recheck", status_code=202)
def recheck_with_package(package_id: int, db: Session = Depends(get_db)):
    """用该规则包批量重检全部历史标签（后台执行），返回任务 id。"""
    get_package_or_404(db, package_id)
    try:
        job_id = start_recheck_job(package_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# 重检任务
# ---------------------------------------------------------------------------

@app.get("/api/recheck-jobs")
def list_recheck_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(RecheckJob).order_by(RecheckJob.id.desc()).limit(20)).all()
    return [j.to_dict() for j in jobs]


@app.get("/api/recheck-jobs/{job_id}")
def get_recheck_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(RecheckJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="重检任务不存在")
    items = db.scalars(
        select(RecheckItem).where(RecheckItem.job_id == job_id).order_by(RecheckItem.id)
    ).all()
    return {**job.to_dict(), "items": [item.to_dict() for item in items]}


# ---------------------------------------------------------------------------
# 启动种子
# ---------------------------------------------------------------------------

@app.on_event("startup")
def seed_demo_data():
    """首次启动写入默认规则包与示例标签；为存量标签补录校验记录。"""
    db = SessionLocal()
    try:
        # 1) 默认规则包：内置规则全量启用，发布并置为当前生效
        if not db.scalar(select(RulePackage).limit(1)):
            db.add(RulePackage(
                name="GB 7718 / GB 28050 标签合规规则",
                version="v1.0",
                status="published",
                effective_date="2026-01-01",
                remark="内置默认规则包：字段完整性、单位规范、营养成分、过敏原提示四类检查。",
                rules_json=json.dumps(default_rule_configs(), ensure_ascii=False),
                published_at=datetime.utcnow(),
            ))
            db.commit()

        # 2) 示例标签
        if not db.scalar(select(Label).limit(1)):
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

        # 3) 存量标签补录：没有校验记录的标签按当前生效包补一次（trigger=init）
        snapshot = None
        package = resolve_active_package(db)
        if package:
            snapshot = snapshot_of(package)
        labels = db.scalars(select(Label).where(Label.rule_package_id.is_(None))).all()
        for label in labels:
            if latest_validation(db, label.id):
                continue
            result = validate_with_snapshot(label.to_dict(), snapshot)
            record_validation(db, label, result, snapshot, trigger="init")
        db.commit()
    finally:
        db.close()


# 生产模式：托管前端构建产物（Docker 镜像中由 Dockerfile 拷贝到 backend/static）
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
