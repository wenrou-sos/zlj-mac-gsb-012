"""规则包领域服务：配置校验、草稿/发布流转、生效版本解析。"""
import json
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import RulePackage
from rule_catalog import CATALOG_BY_CODE, default_config

DATE_FMT = "%Y-%m-%d"
VALID_SEVERITIES = {"error", "warning", "pass"}


def validate_config(config: dict) -> str | None:
    """校验包配置合法性，返回错误信息；合法返回 None。"""
    if not isinstance(config, dict):
        return "配置必须是对象"
    if set(config.keys()) - {"params", "rules"}:
        return "配置只允许包含 params、rules 两个键"
    rules = config.get("rules")
    if not isinstance(rules, dict) or not rules:
        return "rules 必须是非空对象"
    unknown = set(rules) - set(CATALOG_BY_CODE)
    if unknown:
        return f"存在目录中未定义的规则 code：{', '.join(sorted(unknown))}"
    for code, setting in rules.items():
        if not isinstance(setting, dict):
            return f"规则 {code} 的配置必须是对象"
        severity = setting.get("severity")
        if severity is not None and severity not in VALID_SEVERITIES:
            return f"规则 {code} 的严重级别非法：{severity}"
        params = setting.get("params")
        if params is not None and not isinstance(params, dict):
            return f"规则 {code} 的 params 必须是对象"
        # 数值型参数必须可转 float 且非负（阈值类参数语义上不应为负）
        catalog = CATALOG_BY_CODE[code]
        for spec in catalog.get("params", []):
            if spec.get("type") == "number" and spec["key"] in (params or {}):
                raw = params[spec["key"]]
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    return f"规则 {code} 的参数 {spec['key']} 必须是数字"
                if spec.get("min") is not None and value < spec["min"]:
                    return f"规则 {code} 的参数 {spec['key']} 不能小于 {spec['min']}"
                params[spec["key"]] = value
    if "params" in config and not isinstance(config["params"], dict):
        return "全局参数 params 必须是对象"
    return None


def create_draft(db: Session, *, name: str | None, description: str,
                 effective_date: str | None, based_on_package_id: int | None,
                 family: str) -> RulePackage:
    """创建草稿。同一 family 同时只允许一个草稿。"""
    existing_draft = db.scalar(
        select(RulePackage).where(RulePackage.family == family, RulePackage.status == "draft")
    )
    if existing_draft:
        raise ValueError(f"系列 {family} 已存在草稿（v{existing_draft.version}），请先发布或删除")

    if based_on_package_id is not None:
        base = db.get(RulePackage, based_on_package_id)
        if base is None:
            raise ValueError("基准规则包不存在")
        if base.status != "published":
            raise ValueError("只能基于已发布的规则包创建草稿")
        if base.family != family:
            raise ValueError("基准规则包与草稿不属于同一系列")
        config = base.config
        base_name = base.name
    else:
        config = default_config()
        base_name = "GB 7718 / GB 28050 核心校验规则"
    latest = db.scalar(
        select(RulePackage).where(RulePackage.family == family)
        .order_by(RulePackage.version.desc()).limit(1)
    )
    version = (latest.version + 1) if latest else 1

    pkg = RulePackage(
        family=family,
        name=name or f"{base_name} 草稿",
        description=description,
        version=version,
        status="draft",
        config_json=json.dumps(config, ensure_ascii=False),
        effective_date=effective_date or date.today().isoformat(),
    )
    db.add(pkg)
    db.flush()
    return pkg


def publish_package(db: Session, pkg: RulePackage, effective_date_str: str | None) -> RulePackage:
    """发布草稿：固化快照、生效日期、时间戳。发布后配置不可再改。"""
    if pkg.status != "draft":
        raise ValueError("只有草稿状态的规则包可以发布")
    eff = effective_date_str or pkg.effective_date or date.today().isoformat()
    try:
        date.fromisoformat(eff)
    except ValueError:
        raise ValueError("生效日期格式应为 YYYY-MM-DD")

    pkg.status = "published"
    pkg.effective_date = eff
    pkg.published_at = datetime.utcnow()
    # 固化：以默认目录补齐为全量显式快照，使该版本自描述、不受未来目录变化影响
    cfg = default_config()
    cfg["params"] = {**cfg["params"], **(pkg.config.get("params") or {})}
    for code, setting in (pkg.config.get("rules") or {}).items():
        if code in cfg["rules"]:
            cfg["rules"][code] = {**cfg["rules"][code], **setting}
    pkg.config_json = json.dumps(cfg, ensure_ascii=False)
    db.flush()
    return pkg


def resolve_package(db: Session, package_id: int | None) -> RulePackage:
    """解析本次校验要使用的规则包。

    - 显式指定 package_id：草稿/已发布均可（便于草稿试用）；
    - 未指定：取「当前已生效」的已发布包中生效日期最新者；
      都未生效则取发布时间最新的已发布包；再没有则 404。
    """
    if package_id is not None:
        pkg = db.get(RulePackage, package_id)
        if pkg is None:
            raise LookupError("规则包不存在")
        if pkg.status == "archived":
            raise LookupError("规则包已归档，不能用于校验")
        return pkg

    today = date.today().isoformat()
    pkg = db.scalar(
        select(RulePackage)
        .where(RulePackage.status == "published", RulePackage.effective_date <= today)
        .order_by(RulePackage.effective_date.desc(), RulePackage.version.desc())
        .limit(1)
    )
    if pkg is None:
        pkg = db.scalar(
            select(RulePackage).where(RulePackage.status == "published")
            .order_by(RulePackage.published_at.desc().nullslast(), RulePackage.version.desc())
            .limit(1)
        )
    if pkg is None:
        raise LookupError("尚无已发布的规则包")
    return pkg


def package_ref(pkg: RulePackage) -> dict:
    """校验结果中附带的规则版本戳。"""
    return {
        "package_id": pkg.id,
        "package_version": pkg.version,
        "package_name": pkg.name,
        "package_status": pkg.status,
        "effective_date": pkg.effective_date or None,
    }
