"""规则包业务层：生效解析、发布、校验留痕与批量重检。

并发与一致性约定：
- 已发布的规则包不可变（发布即冻结规则快照），“发布”只做状态翻转，
  从不改写历史包的 rules_json；
- 每次校验在请求开始时解析一次生效包并固化为内存快照，之后纯内存执行，
  因此校验执行期间发布新包不会影响本次结果；
- 批量重检在任务启动时固定同一份快照，整个任务期间不受新发布影响。
"""
import json
import threading
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Label, RecheckItem, RecheckJob, RulePackage, Validation
from rules import RULE_DEFINITIONS, default_rule_configs
from validators import validate_label

STATUS_RANK = {"error": 3, "warning": 2, "pass": 1}
STATUS_TEXT = {"pass": "通过", "warning": "警告", "error": "错误"}
RULE_NAME_BY_CODE = {d["code"]: d["name"] for d in RULE_DEFINITIONS}


# ---------------------------------------------------------------------------
# 规则包解析与快照
# ---------------------------------------------------------------------------

def parse_rules(package: RulePackage) -> list[dict]:
    try:
        return json.loads(package.rules_json or "[]")
    except json.JSONDecodeError:
        return default_rule_configs()


def resolve_active_package(db: Session, on_date: date | None = None) -> RulePackage | None:
    """当前生效的规则包：已发布且生效日期不晚于当天，取最新者。"""
    today = (on_date or date.today()).isoformat()
    return db.scalars(
        select(RulePackage)
        .where(RulePackage.status == "published", RulePackage.effective_date <= today)
        .order_by(RulePackage.effective_date.desc(), RulePackage.id.desc())
    ).first()


def active_package_id(db: Session) -> int | None:
    package = resolve_active_package(db)
    return package.id if package else None


def snapshot_of(package: RulePackage) -> dict:
    """把规则包固化为可跨线程使用的内存快照。"""
    return {
        "id": package.id,
        "name": package.name,
        "version": package.version,
        "effective_date": package.effective_date,
        "rules": parse_rules(package),
    }


def validate_with_snapshot(data: dict, snapshot: dict | None) -> dict:
    """用给定快照校验；无快照（尚未发布任何规则包）时回退内置默认规则。"""
    result = validate_label(data, snapshot["rules"] if snapshot else None)
    result["rule_version"] = (
        {
            "id": snapshot["id"],
            "name": snapshot["name"],
            "version": snapshot["version"],
            "effective_date": snapshot["effective_date"],
        }
        if snapshot
        else None
    )
    return result


# ---------------------------------------------------------------------------
# 校验留痕
# ---------------------------------------------------------------------------

def record_validation(
    db: Session,
    label: Label,
    result: dict,
    snapshot: dict | None,
    trigger: str,
) -> Validation:
    """保存一次校验结果，并把所用规则版本回写到标签上。"""
    record = Validation(
        label_id=label.id,
        package_id=snapshot["id"] if snapshot else None,
        package_version=snapshot["version"] if snapshot else "内置默认",
        trigger=trigger,
        status=result["status"],
        summary_json=json.dumps(result["summary"], ensure_ascii=False),
        results_json=json.dumps(result["results"], ensure_ascii=False),
    )
    db.add(record)
    label.rule_package_id = record.package_id
    label.rule_package_version = record.package_version
    label.last_validation_status = record.status
    label.last_validated_at = datetime.utcnow()
    db.flush()
    return record


def latest_validation(db: Session, label_id: int) -> Validation | None:
    return db.scalars(
        select(Validation)
        .where(Validation.label_id == label_id)
        .order_by(Validation.id.desc())
    ).first()


# ---------------------------------------------------------------------------
# 结果差异
# ---------------------------------------------------------------------------

def diff_results(old_results: list[dict], new_results: list[dict]) -> list[dict]:
    """按检查项编码对齐新旧结果，产出差异列表。"""
    old_by_code = {r["code"]: r for r in old_results}
    new_by_code = {r["code"]: r for r in new_results}
    changes: list[dict] = []
    for code in list(dict.fromkeys([r["code"] for r in old_results] + [r["code"] for r in new_results])):
        old, new = old_by_code.get(code), new_by_code.get(code)
        source = new or old
        base = {
            "code": code,
            "category": source["category"],
            "rule": RULE_NAME_BY_CODE.get(source.get("rule") or code, code),
            "old_status": old["status"] if old else None,
            "new_status": new["status"] if new else None,
            "old_message": old["message"] if old else None,
            "new_message": new["message"] if new else None,
        }
        if old is None:
            changes.append({**base, "change": "added"})
        elif new is None:
            changes.append({**base, "change": "removed"})
        elif old["status"] != new["status"] or old["message"] != new["message"]:
            changes.append({**base, "change": "changed"})
    return changes


# ---------------------------------------------------------------------------
# 批量重检（后台线程）
# ---------------------------------------------------------------------------

def start_recheck_job(package_id: int) -> int:
    """以指定已发布规则包批量重检全部标签，返回任务 id。"""
    db = SessionLocal()
    try:
        package = db.get(RulePackage, package_id)
        if not package:
            raise ValueError("规则包不存在")
        if package.status != "published":
            raise ValueError("仅已发布的规则包可用于批量重检")
        # 任务启动即固定快照：执行期间发布新包不影响本次重检
        snapshot = snapshot_of(package)
        label_ids = list(db.scalars(select(Label.id).order_by(Label.id)))
        job = RecheckJob(
            package_id=package.id,
            package_version=package.version,
            status="running",
            total=len(label_ids),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    thread = threading.Thread(
        target=_run_recheck, args=(job_id, snapshot, label_ids), daemon=True,
        name=f"recheck-job-{job_id}",
    )
    thread.start()
    return job_id


def _run_recheck(job_id: int, snapshot: dict, label_ids: list[int]) -> None:
    db = SessionLocal()
    try:
        job = db.get(RecheckJob, job_id)
        for label_id in label_ids:
            label = db.get(Label, label_id)
            if not label:
                continue
            previous = latest_validation(db, label_id)
            result = validate_with_snapshot(label.to_dict(), snapshot)
            record = record_validation(db, label, result, snapshot, trigger="batch")

            old_results = previous.results if previous else []
            changes = diff_results(old_results, result["results"])
            db.add(RecheckItem(
                job_id=job_id,
                label_id=label_id,
                label_name=label.product_name or f"标签 #{label_id}",
                old_validation_id=previous.id if previous else None,
                new_validation_id=record.id,
                old_package_version=previous.package_version if previous else "",
                old_status=previous.status if previous else "",
                new_status=result["status"],
                diff_json=json.dumps(changes, ensure_ascii=False),
            ))
            job.completed += 1
            if changes or (previous and previous.status != result["status"]):
                job.changed += 1
            db.commit()  # 逐条提交，前端可实时看到进度
        job.status = "done"
        job.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 任务失败需落库而不是静默
        db.rollback()
        job = db.get(RecheckJob, job_id)
        if job:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
