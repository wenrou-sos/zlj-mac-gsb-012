"""数据驱动的标签校验引擎。

与历史版本的区别：规则的启停、严重级别、阈值/正则/词表等全部来自
规则包版本快照（config），引擎本身无状态——每次校验都基于调用方传入的
config 快照在内存中执行。因此规则包发布/编辑草稿不会影响任何正在执行的校验。

配置结构见 rule_catalog.default_config()：
    {"params": <全局参数>, "rules": {code: {"enabled", "severity", "params"}}}
"""
import re
from calendar import monthrange
from copy import deepcopy
from datetime import date, timedelta

from rule_catalog import (
    CATALOG_BY_CODE,
    DEFAULT_GLOBAL_PARAMS,
    DEFAULT_NRV,
    NUTRIENT_META,
    default_config,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

NEGATIVE_CODES = {
    item["code"]: item["meta"]["nutrient_key"]
    for item in CATALOG_BY_CODE.values()
    if item.get("meta", {}).get("nutrient_key")
}


def detect_allergens(ingredients: list[str], keyword_map: dict[str, list[str]]) -> dict[str, list[str]]:
    """扫描配料表，返回 {过敏原类别: [命中的配料]}。"""
    found: dict[str, list[str]] = {}
    for ingredient in ingredients:
        for category, keywords in (keyword_map or {}).items():
            if any(kw in ingredient for kw in keywords or []):
                found.setdefault(category, [])
                if ingredient not in found[category]:
                    found[category].append(ingredient)
    return found


def compute_expiry(prod: date, value: int, unit: str) -> date | None:
    """由生产日期和保质期推算到期日。"""
    if unit in ("天", "日"):
        return prod + timedelta(days=value)
    if unit in ("个月", "月"):
        total = prod.month - 1 + value
        year, month = prod.year + total // 12, total % 12 + 1
        day = min(prod.day, monthrange(year, month)[1])
        return date(year, month, day)
    if unit == "年":
        try:
            return prod.replace(year=prod.year + value)
        except ValueError:  # 2 月 29 日
            return prod.replace(year=prod.year + value, day=28)
    return None


class RuleEngine:
    """按指定规则包快照执行校验。"""

    def __init__(self, config: dict | None = None):
        cfg = config or default_config()
        # 合并一层默认值，保证历史/精简配置缺字段时也能运行
        merged = default_config()
        merged["params"] = {**merged["params"], **(cfg.get("params") or {})}
        for code, setting in (cfg.get("rules") or {}).items():
            if code in merged["rules"]:
                merged["rules"][code] = {
                    "enabled": setting.get("enabled", True),
                    "severity": setting.get("severity")
                    or CATALOG_BY_CODE[code]["default_severity"],
                    "params": {**merged["rules"][code]["params"], **(setting.get("params") or {})},
                }
        self.global_params = deepcopy(merged["params"])
        self.rules = merged["rules"]

    # ---- 配置访问 ----
    def rule(self, code: str) -> dict | None:
        setting = self.rules.get(code)
        return setting if setting and setting.get("enabled", True) else None

    def rparam(self, code: str, key: str, default=None):
        setting = self.rules.get(code) or {}
        return (setting.get("params") or {}).get(key, default)

    @property
    def net_content_units(self) -> set[str]:
        return set(self.global_params.get("net_content_units") or DEFAULT_GLOBAL_PARAMS["net_content_units"])

    @property
    def shelf_life_units(self) -> set[str]:
        return set(self.global_params.get("shelf_life_units") or DEFAULT_GLOBAL_PARAMS["shelf_life_units"])

    @property
    def nrv(self) -> dict:
        nrv = dict(DEFAULT_NRV)
        nrv.update(self.global_params.get("nrv") or {})
        return nrv

    @property
    def energy_factors(self) -> dict:
        factors = dict(DEFAULT_GLOBAL_PARAMS["energy_factors"])
        factors.update(self.global_params.get("energy_factors") or {})
        return factors

    @property
    def allergen_keywords(self) -> dict[str, list[str]]:
        return self.global_params.get("allergen_keywords") or DEFAULT_GLOBAL_PARAMS["allergen_keywords"]

    # ---- 校验主流程 ----
    def validate(self, data: dict) -> dict:
        results: list[dict] = []

        def emit(code: str, status: str, message: str, extra: dict | None = None):
            catalog = CATALOG_BY_CODE.get(code)
            item = {
                "category": catalog["category"] if catalog else data.get("category", "field"),
                "code": code,
                "status": status,
                "message": message,
            }
            if extra:
                item.update(extra)
            results.append(item)

        def add(code: str, fired_status: str, msg: str, **kw):
            """按规则配置的严重级别输出；停用的规则直接跳过。"""
            setting = self.rule(code)
            if setting is None:
                return
            emit(code, setting["severity"] if fired_status != "pass" else "pass", msg, **kw)

        sl_unit = (data.get("shelf_life_unit") or "").strip()
        prod_date = self._check_field_rules(data, add)
        self._check_unit_rules(data, add, sl_unit)
        self._check_nutrition_rules(data, add)
        detected = self._check_allergen_rules(data, add)

        errors = sum(1 for r in results if r["status"] == "error")
        warnings = sum(1 for r in results if r["status"] == "warning")
        passed = sum(1 for r in results if r["status"] == "pass")
        status = "fail" if errors else ("warning" if warnings else "pass")

        nutrients = {key: data.get(key) for key, _, _ in NUTRIENT_META}
        nrv_table = self.nrv
        nutrition_table = []
        for key, label, unit in NUTRIENT_META:
            value = nutrients[key]
            nrv_pct = round(value / nrv_table[key] * 100) if value is not None else None
            nutrition_table.append({"key": key, "name": label, "unit": unit, "value": value, "nrv": nrv_pct})

        expiry_date = None
        if prod_date and data.get("shelf_life_value") and sl_unit in self.shelf_life_units:
            expiry = compute_expiry(prod_date, int(data["shelf_life_value"]), sl_unit)
            expiry_date = expiry.isoformat() if expiry else None

        return {
            "status": status,
            "summary": {"errors": errors, "warnings": warnings, "passed": passed},
            "results": results,
            "detected_allergens": sorted(detected.keys()),
            "allergen_details": {k: v for k, v in sorted(detected.items())},
            "nutrition_table": nutrition_table,
            "expiry_date": expiry_date,
        }

    # ---------------- 1. 字段完整性 ----------------
    def _check_field_rules(self, data: dict, add) -> date | None:
        required_text = [
            ("product_name_required", "product_name", "食品名称"),
            ("manufacturer_required", "manufacturer", "生产者名称"),
            ("address_required", "address", "生产者地址"),
            ("storage_condition_required", "storage_condition", "贮存条件"),
        ]
        for code, field, label in required_text:
            if (data.get(field) or "").strip():
                add(code, "pass", f"{label}已填写")
            else:
                add(code, "fail", f"缺少强制标示内容：{label}")

        ingredients = [s.strip() for s in (data.get("ingredients") or []) if s and s.strip()]
        if ingredients:
            add("ingredients_required", "pass", f"配料表已填写（共 {len(ingredients)} 项）")
        else:
            add("ingredients_required", "fail", "缺少强制标示内容：配料表")

        if data.get("net_content_value") is None:
            add("net_content_required", "fail", "缺少强制标示内容：净含量")
        elif data["net_content_value"] <= 0:
            add("net_content_required", "pass", "净含量已填写")
            add("net_content_positive", "fail", "净含量必须大于 0")
        else:
            add("net_content_required", "pass", "净含量已填写")

        if data.get("shelf_life_value") is None:
            add("shelf_life_required", "fail", "缺少强制标示内容：保质期")
        elif data["shelf_life_value"] <= 0:
            add("shelf_life_required", "pass", "保质期已填写")
            add("shelf_life_positive", "fail", "保质期必须大于 0")
        else:
            add("shelf_life_required", "pass", "保质期已填写")

        prod_date: date | None = None
        raw_date = (data.get("production_date") or "").strip()
        if not raw_date:
            add("production_date_required", "warn", "未填写生产日期（实际标签可以“见喷码”形式标示）")
        elif not DATE_RE.match(raw_date):
            add("production_date_required", "pass", "已填写生产日期")
            add("production_date_format", "fail",
                f"生产日期格式应为 YYYY-MM-DD，当前为：{raw_date}")
        else:
            add("production_date_required", "pass", "已填写生产日期")
            try:
                prod_date = date.fromisoformat(raw_date)
            except ValueError:
                add("production_date_format", "fail", f"生产日期不是有效日期：{raw_date}")
            else:
                add("production_date_format", "pass", "生产日期格式正确")
                if prod_date > date.today():
                    add("production_date_future", "warn", "生产日期晚于今天，请确认是否填写有误")

        license_no = (data.get("license_no") or "").strip()
        if not license_no:
            add("license_required", "fail", "缺少强制标示内容：食品生产许可证编号")
        else:
            add("license_required", "pass", "生产许可证编号已填写")
            pattern = self.rparam("license_format", "pattern", r"^SC\d{14}$")
            try:
                matched = re.compile(pattern).match(license_no) is not None
            except re.error:
                matched = re.compile(r"^SC\d{14}$").match(license_no) is not None
            example = self.rparam("license_format", "example", "SC10632011500123")
            if not matched:
                add("license_format", "fail",
                    f"生产许可证编号格式不符合规则要求，示例：{example}")
            else:
                add("license_format", "pass", "生产许可证编号格式正确")

        standard_no = (data.get("standard_no") or "").strip()
        if not standard_no:
            add("standard_recommended", "warn", "建议填写产品标准号（如 GB/T 20980）")
        else:
            add("standard_recommended", "pass", "产品标准号已填写")
            pattern = self.rparam("standard_format", "pattern", r"^GB")
            try:
                matched = re.compile(pattern, re.IGNORECASE).match(standard_no) is not None
            except re.error:
                matched = standard_no.upper().startswith(("GB", "Q/"))
            if not matched:
                add("standard_format", "warn", "产品标准号格式存疑，常见形式如 GB/T 20980、Q/XXX 0001S")
            else:
                add("standard_format", "pass", "产品标准号格式正确")

        return prod_date

    # ---------------- 2. 单位规范 ----------------
    def _check_unit_rules(self, data: dict, add, sl_unit: str):
        nc_unit = (data.get("net_content_unit") or "").strip()
        nc_value = data.get("net_content_value")
        if nc_unit not in self.net_content_units:
            add("net_content_unit", "fail",
                f"净含量单位“{nc_unit or '（空）'}”不在允许集合内：{('、'.join(sorted(self.net_content_units)))}")
        else:
            add("net_content_unit", "pass", "净含量单位规范")
            threshold = self.rparam("net_content_unit_scale", "threshold", 1000)
            if nc_value is not None and nc_value >= threshold and nc_unit in ("g", "克"):
                add("net_content_unit_scale", "warn",
                    f"净含量 ≥ {threshold:g}g 时应使用 kg 作为计量单位")
            elif nc_value is not None and nc_value >= threshold and nc_unit in ("ml", "mL", "毫升"):
                add("net_content_unit_scale", "warn",
                    f"净含量 ≥ {threshold:g}mL 时应使用 L 作为计量单位")

        sl_value = data.get("shelf_life_value")
        if sl_unit not in self.shelf_life_units:
            add("shelf_life_unit", "fail",
                f"保质期单位“{sl_unit or '（空）'}”不在允许集合内：{('、'.join(sorted(self.shelf_life_units)))}")
        else:
            add("shelf_life_unit", "pass", "保质期单位规范")
            threshold = self.rparam("shelf_life_unit_scale", "threshold", 365)
            if sl_value is not None and sl_unit in ("天", "日") and sl_value >= threshold:
                add("shelf_life_unit_scale", "warn", "保质期超过一年，建议使用“个月”或“年”表示")

    # ---------------- 3. 营养成分 ----------------
    def _check_nutrition_rules(self, data: dict, add):
        nutrients = {key: data.get(key) for key, _, _ in NUTRIENT_META}
        missing = [label for key, label, _ in NUTRIENT_META if nutrients[key] is None]
        if missing:
            add("core_nutrients", "fail", "营养成分表缺少核心营养素（1+4）：" + "、".join(missing))
        else:
            add("core_nutrients", "pass", "核心营养素（能量、蛋白质、脂肪、碳水化合物、钠）齐全")

        nutrient_labels = {key: label for key, label, _ in NUTRIENT_META}
        for code, key in NEGATIVE_CODES.items():
            value = nutrients.get(key)
            if value is not None and value < 0:
                add(code, "fail", f"{nutrient_labels[key]}含量不能为负数")

        if nutrients["energy_kj"] is not None and nutrients["energy_kj"] % 1 != 0:
            add("energy_rounding", "warn", "能量的标示值应按 GB 28050 修约为整数（kJ）")
        if nutrients["sodium_mg"] is not None and nutrients["sodium_mg"] % 1 != 0:
            add("sodium_rounding", "warn", "钠的标示值应按 GB 28050 修约为整数（mg）")

        factors = self.energy_factors
        if all(nutrients.get(k) is not None for k in ("energy_kj", "protein_g", "fat_g", "carbohydrate_g")):
            calc = (
                nutrients["protein_g"] * factors["protein_g"]
                + nutrients["fat_g"] * factors["fat_g"]
                + nutrients["carbohydrate_g"] * factors["carbohydrate_g"]
            )
            declared = nutrients["energy_kj"]
            if calc > 0:
                ratio = declared / calc
                tolerance = self.rparam("energy_cross_check", "tolerance", 0.25)
                if ratio > 1 + tolerance or ratio < 1 - tolerance:
                    pct = int(round(tolerance * 100))
                    add("energy_cross_check", "warn",
                        f"标示能量 {declared:g}kJ 与三大营养素折算值约 {calc:.0f}kJ 偏差超过 ±{pct}%，请核对")
                else:
                    add("energy_cross_check", "pass",
                        f"能量与三大营养素折算值（约 {calc:.0f}kJ）基本一致")

        sodium_threshold = self.rparam("sodium_high", "threshold_mg", self.nrv["sodium_mg"])
        if nutrients["sodium_mg"] is not None and nutrients["sodium_mg"] > sodium_threshold:
            add("sodium_high", "warn",
                f"每 100g/mL 钠含量已超过 {sodium_threshold:g}mg，属于高钠食品，请确认数据无误")

    # ---------------- 4. 过敏原提示 ----------------
    def _check_allergen_rules(self, data: dict, add) -> dict[str, list[str]]:
        ingredients = [s.strip() for s in (data.get("ingredients") or []) if s and s.strip()]
        detected = detect_allergens(ingredients, self.allergen_keywords)
        statement = (data.get("allergen_statement") or "").strip()
        if detected:
            names = "、".join(detected.keys())
            if statement:
                add("allergen_statement", "pass", f"检测到致敏物质（{names}），已填写提示语")
            else:
                add("allergen_statement", "warn",
                    f"配料中检测到常见致敏物质：{names}，建议按 GB 7718 添加致敏物质提示")
        else:
            add("allergen_scan", "pass", "配料表中未检测到常见致敏物质")
        return detected


def validate_label(data: dict, config: dict | None = None) -> dict:
    """兼容历史调用方式的便捷函数（使用内置默认规则配置）。"""
    return RuleEngine(config).validate(data)
