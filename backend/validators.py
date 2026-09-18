"""向后兼容垫片。

校验逻辑已迁移到数据驱动的 rule_engine.RuleEngine（规则启停 / 严重级别 /
参数全部来自规则包版本快照）。此处保留历史调用入口，默认使用内置规则配置。
"""
from rule_engine import RuleEngine, compute_expiry, detect_allergens


def validate_label(data: dict, config: dict | None = None) -> dict:
    return RuleEngine(config).validate(data)


__all__ = ["validate_label", "RuleEngine", "detect_allergens", "compute_expiry"]
