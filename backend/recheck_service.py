"""历史标签批量重检服务。

- 以某个已发布规则包的不可变快照重检标签；
- 每条标签与「重检前最近一次留痕」逐条规则对比差异；
- 重检在后台线程中运行，每个线程打开独立 DB 会话，与在线校验互不干扰。
"""
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    Label,
    RecheckBatch,
    RecheckItem,
    RulePackage,
    ValidationRecord,
)
from rule_catalog import CATALOG_BY_CODE
from rule_engine import RuleEngine

STATUS_FLOW = {"pass": 0, "warning": 1, "fail": 2}


def diff_results(old: dict | None, new: dict) -> dict:
    """按规则 code 对齐两份校验结果，返回结构化差异。

    status_flow 仅在整体结论变化时出现：-1 变好 / 0 不变 / 1 变差。
    """
    old_map = {r["code"]: r for r in (old or {}).get("results", [])}
    new_map = {r["code"]: r for r in new.get("results", [])}
    changes = []

    for code in sorted(set(old_map) | set(new_map)):
        before, after = old_map.get(code), new_map.get(code)
        catalog = CATALOG_BY_CODE.get(code, {})
        name = catalog.get("name", code)

        if before is None:
            changes.append({
                "code": code, "name": name, "type": "added",
                "category": after["category"],
                "old_status": None, "new_status": after["status"],
                "old_message": None, "new_message": after["message"],
            })
        elif after is None:
            changes.append({
                "code": code, "name": name, "type": "removed",
                "category": before["category"],
                "old_status": before["status"], "new_status": None,
                "old_message": before["message"], "new_message": None,
            })
        elif before["status"] != after["status"] or before["message"] != after["message"]:
            changes.append({
                "code": code, "name": name,
                "type": "status" if before["status"] != after["status"] else "message",
                "category": after["category"],
                "old_status": before["status"], "new_status": after["status"],
                "old_message": before["message"], "new_message": after["message"],
            })

    old_status = (old or {}).get("status")
    new_status = new.get("status")
    flow = None
    if old_status is not None:
        flow = STATUS_FLOW[new_status] - STATUS_FLOW[old_status]

    return {
        "old_status": old_status,
        "new_status": new_status,
        "status_flow": flow,
        "changes": changes,
        "change_count": len(changes),
    }


def create_recheck_batch(db: Session, *, package_id: int,
                         baseline_package_id: int | None,
                         label_ids: list[int] | None) -> RecheckBatch:
    pkg = db.get(RulePackage, package_id)
    if pkg is None or pkg.status != "published":
        raise ValueError("重检目标必须是已发布的规则包")

    baseline_version = None
    if baseline_package_id is not None:
        baseline = db.get(RulePackage, baseline_package_id)
        if baseline is None or baseline.status not in ("published", "archived"):
            raise ValueError("基准规则包不存在或未发布")
        baseline_version = baseline.version

    stmt = select(Label)
    if label_ids:
        stmt = stmt.where(Label.id.in_(label_ids))
    labels = db.scalars(stmt.order_by(Label.id)).all()
    total = len(labels)
    if total == 0:
        raise ValueError("没有可重检的标签")

    batch = RecheckBatch(
        package_id=pkg.id,
        package_version=pkg.version,
        baseline_package_id=baseline_package_id,
        baseline_version=baseline_version,
        status="pending",
        total=total,
        scope_json=json.dumps(label_ids or [], ensure_ascii=False),
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


def run_recheck_batch(batch_id: int, session_factory) -> None:
    """后台执行入口：独立会话 + 一次性载入规则快照，保证运行期间不受发布影响。"""
    db: Session = session_factory()
    try:
        batch = db.get(RecheckBatch, batch_id)
        if batch is None:
            return
        batch.status = "running"
        batch.started_at = datetime.utcnow()
        db.commit()

        pkg = db.get(RulePackage, batch.package_id)
        engine = RuleEngine(pkg.config)  # 快照载入内存，后续发布/编辑均与本次无关

        try:
            scope = json.loads(batch.scope_json or "[]")
        except json.JSONDecodeError:
            scope = []
        stmt = select(Label).order_by(Label.id)
        if scope:
            stmt = stmt.where(Label.id.in_(scope))
        targets = db.scalars(stmt).all()
        changed_total = 0

        for label in targets:
            latest_record = db.scalar(
                select(ValidationRecord).where(ValidationRecord.label_id == label.id)
                .order_by(ValidationRecord.created_at.desc(), ValidationRecord.id.desc())
                .limit(1)
            )
            # 显式指定基准包时，取该标签在基准包下的最近一次留痕
            old_record = latest_record
            if batch.baseline_package_id is not None:
                old_record = db.scalar(
                    select(ValidationRecord)
                    .where(
                        ValidationRecord.label_id == label.id,
                        ValidationRecord.package_id == batch.baseline_package_id,
                    )
                    .order_by(ValidationRecord.created_at.desc(), ValidationRecord.id.desc())
                    .limit(1)
                ) or latest_record

            new_result = engine.validate(label.to_dict())
            new_record = ValidationRecord(
                label_id=label.id,
                package_id=pkg.id,
                package_version=pkg.version,
                trigger="recheck",
                status=new_result["status"],
                result_json=json.dumps(new_result, ensure_ascii=False),
            )
            db.add(new_record)
            db.flush()

            old_result = old_record.result if old_record else None
            diff = diff_results(old_result, new_result)
            changed = diff["change_count"] > 0
            changed_total += 1 if changed else 0

            item = RecheckItem(
                batch_id=batch.id,
                label_id=label.id,
                label_name=label.product_name or f"标签 #{label.id}",
                old_status=diff["old_status"],
                new_status=diff["new_status"],
                changed=changed,
                diff_json=json.dumps(diff, ensure_ascii=False),
                new_result_json=json.dumps(new_result, ensure_ascii=False),
                old_result_json=json.dumps(old_result or {}, ensure_ascii=False),
                new_record_id=new_record.id,
            )
            db.add(item)
            batch.processed += 1
            batch.changed_count = changed_total
            db.commit()  # 每条提交一次，前端可轮询进度，中断也能保留已完成部分

        batch.status = "completed"
        batch.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 任务级兜底，错误落库供前端展示
        db.rollback()
        batch = db.get(RecheckBatch, batch_id)
        if batch is not None:
            batch.status = "failed"
            batch.error_message = str(exc)
            batch.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
