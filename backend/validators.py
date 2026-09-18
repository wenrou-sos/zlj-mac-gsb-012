"""标签校验引擎。

依据 GB 7718《预包装食品标签通则》与 GB 28050《预包装食品营养标签通则》
的核心要求，对标签数据做四类检查（field / unit / nutrition / allergen）。

引擎本身不硬编码规则开关与阈值：调用方传入规则包快照
（[{code, enabled, params}]，见 rules.py），引擎逐条执行启用的规则。
不传规则配置时使用内置默认值，行为与初版一致。
"""
import re
from calendar import monthrange
from datetime import date, timedelta

from rules import ALLERGEN_KEYWORDS, RULE_DEFINITIONS, default_rule_configs

# GB 28050-2011 附录A：营养素参考值 (NRV)
NRV = {
    "energy_kj": 8400,
    "protein_g": 60,
    "fat_g": 60,
    "carbohydrate_g": 300,
    "sodium_mg": 2000,
}

NUTRIENT_META = [
    ("energy_kj", "能量", "千焦(kJ)"),
    ("protein_g", "蛋白质", "克(g)"),
    ("fat_g", "脂肪", "克(g)"),
    ("carbohydrate_g", "碳水化合物", "克(g)"),
    ("sodium_mg", "钠", "毫克(mg)"),
]
NUTRIENT_LABELS = {key: label for key, label, _ in NUTRIENT_META}

# 能量折算系数 (kJ/g)，GB 28050 问答
ENERGY_FACTORS = {"protein_g": 17, "fat_g": 37, "carbohydrate_g": 17}

NET_CONTENT_UNITS = {"g", "kg", "ml", "l", "mL", "L", "克", "千克", "毫升", "升"}
SHELF_LIFE_UNITS = {"天", "日", "个月", "月", "年"}

DEFAULT_LICENSE_PATTERN = r"^SC\d{14}$"
STANDARD_RE = re.compile(r"^(GB|GB/T|QB|QB/T|SB|SB/T|NY/T|Q/[A-Z0-9]{2,12})\s*\d+", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _pass(category: str, code: str, message: str) -> dict:
    return {"category": category, "code": code, "status": "pass", "message": message}


def _warn(category: str, code: str, message: str) -> dict:
    return {"category": category, "code": code, "status": "warning", "message": message}


def _err(category: str, code: str, message: str) -> dict:
    return {"category": category, "code": code, "status": "error", "message": message}


def detect_allergens(ingredients: list[str], keywords: dict | None = None) -> dict[str, list[str]]:
    """扫描配料表，返回 {过敏原类别: [命中的配料]}。关键词表可由规则参数覆盖。"""
    keywords = keywords or ALLERGEN_KEYWORDS
    found: dict[str, list[str]] = {}
    for ingredient in ingredients:
        for category, words in keywords.items():
            if any(kw and kw in ingredient for kw in words):
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


def _clean_ingredients(data: dict) -> list[str]:
    return [s.strip() for s in (data.get("ingredients") or []) if s and s.strip()]


# ---------------------------------------------------------------------------
# 规则实现：每个函数接收 (data, params, ctx)，返回检查结果列表。
# ctx 为规则间共享的上下文（如过敏原扫描结果），避免重复计算。
# ---------------------------------------------------------------------------

def _required_text_rule(field: str, label: str):
    def check(data, params, ctx):
        if (data.get(field) or "").strip():
            return [_pass("field", f"{field}_required", f"{label}已填写")]
        return [_err("field", f"{field}_required", f"缺少强制标示内容：{label}")]

    return check


def check_ingredients_required(data, params, ctx):
    ingredients = _clean_ingredients(data)
    if ingredients:
        return [_pass("field", "ingredients_required", f"配料表已填写（共 {len(ingredients)} 项）")]
    return [_err("field", "ingredients_required", "缺少强制标示内容：配料表")]


def check_net_content_required(data, params, ctx):
    value = data.get("net_content_value")
    if value is None:
        return [_err("field", "net_content_required", "缺少强制标示内容：净含量")]
    if value <= 0:
        return [_err("field", "net_content_positive", "净含量必须大于 0")]
    return [_pass("field", "net_content_required", "净含量已填写")]


def check_shelf_life_required(data, params, ctx):
    value = data.get("shelf_life_value")
    if value is None:
        return [_err("field", "shelf_life_required", "缺少强制标示内容：保质期")]
    if value <= 0:
        return [_err("field", "shelf_life_positive", "保质期必须大于 0")]
    return [_pass("field", "shelf_life_required", "保质期已填写")]


def check_production_date_format(data, params, ctx):
    raw = (data.get("production_date") or "").strip()
    if not raw:
        return [_warn("field", "production_date_required", "未填写生产日期（实际标签可以“见喷码”形式标示）")]
    if not DATE_RE.match(raw):
        return [_err("field", "production_date_format", f"生产日期格式应为 YYYY-MM-DD，当前为：{raw}")]
    try:
        prod = date.fromisoformat(raw)
    except ValueError:
        return [_err("field", "production_date_format", f"生产日期不是有效日期：{raw}")]
    if params.get("future_warning", True) and prod > date.today():
        return [_warn("field", "production_date_future", "生产日期晚于今天，请确认是否填写有误")]
    return [_pass("field", "production_date_format", "生产日期格式正确")]


def check_license_format(data, params, ctx):
    pattern = (params.get("pattern") or "").strip() or DEFAULT_LICENSE_PATTERN
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(DEFAULT_LICENSE_PATTERN)
    required = params.get("required", True)
    license_no = (data.get("license_no") or "").strip()
    if not license_no:
        if required:
            return [_err("field", "license_required", "缺少强制标示内容：食品生产许可证编号")]
        return [_warn("field", "license_required", "未填写食品生产许可证编号")]
    if not regex.match(license_no):
        return [_err("field", "license_format", "生产许可证编号格式应为 SC + 14 位数字，如 SC10632011500123")]
    return [_pass("field", "license_format", "生产许可证编号格式正确")]


def check_standard_no_format(data, params, ctx):
    required = params.get("required", False)
    standard_no = (data.get("standard_no") or "").strip()
    if not standard_no:
        if required:
            return [_err("field", "standard_recommended", "缺少强制标示内容：产品标准号")]
        return [_warn("field", "standard_recommended", "建议填写产品标准号（如 GB/T 20980）")]
    if not STANDARD_RE.match(standard_no):
        return [_warn("field", "standard_format", "产品标准号格式存疑，常见形式如 GB/T 20980、Q/XXX 0001S")]
    return [_pass("field", "standard_format", "产品标准号格式正确")]


def check_net_content_unit(data, params, ctx):
    unit = (data.get("net_content_unit") or "").strip()
    if unit not in NET_CONTENT_UNITS:
        return [_err("unit", "net_content_unit", f"净含量单位“{unit or '（空）'}”不规范，应为 g、kg、mL 或 L")]
    results = [_pass("unit", "net_content_unit", "净含量单位规范")]
    threshold = params.get("scale_threshold", 1000)
    value = data.get("net_content_value")
    if value is not None and threshold and value >= threshold:
        if unit in ("g", "克"):
            results.append(_warn("unit", "net_content_unit_scale", f"净含量 ≥ {threshold:g}g 时应使用 kg 作为计量单位"))
        elif unit in ("ml", "mL", "毫升"):
            results.append(_warn("unit", "net_content_unit_scale", f"净含量 ≥ {threshold:g}mL 时应使用 L 作为计量单位"))
    return results


def check_shelf_life_unit(data, params, ctx):
    unit = (data.get("shelf_life_unit") or "").strip()
    if unit not in SHELF_LIFE_UNITS:
        return [_err("unit", "shelf_life_unit", f"保质期单位“{unit or '（空）'}”不规范，应为 天、个月 或 年")]
    results = [_pass("unit", "shelf_life_unit", "保质期单位规范")]
    threshold = params.get("day_threshold", 365)
    value = data.get("shelf_life_value")
    if value is not None and threshold and unit in ("天", "日") and value >= threshold:
        results.append(_warn("unit", "shelf_life_unit_scale", "保质期超过一年，建议使用“个月”或“年”表示"))
    return results


def check_core_nutrients(data, params, ctx):
    required = params.get("required") or [key for key, _, _ in NUTRIENT_META]
    missing = [NUTRIENT_LABELS.get(key, key) for key in required if data.get(key) is None]
    if missing:
        return [_err("nutrition", "core_nutrients", "营养成分表缺少核心营养素（1+4）：" + "、".join(missing))]
    return [_pass("nutrition", "core_nutrients", "核心营养素（能量、蛋白质、脂肪、碳水化合物、钠）齐全")]


def check_nutrient_non_negative(data, params, ctx):
    results = []
    for key, label, _ in NUTRIENT_META:
        value = data.get(key)
        if value is not None and value < 0:
            results.append(_err("nutrition", f"{key}_negative", f"{label}含量不能为负数"))
    return results


def check_rounding(data, params, ctx):
    fields = params.get("integer_fields") or ["energy_kj", "sodium_mg"]
    results = []
    for key in fields:
        value = data.get(key)
        if value is not None and value % 1 != 0:
            label = NUTRIENT_LABELS.get(key, key)
            unit = "kJ" if key == "energy_kj" else ("mg" if key == "sodium_mg" else "")
            results.append(_warn("nutrition", f"{key}_rounding", f"{label}的标示值应按 GB 28050 修约为整数（{unit}）".rstrip("（）")))
    return results


def check_energy_cross_check(data, params, ctx):
    keys = ("energy_kj", "protein_g", "fat_g", "carbohydrate_g")
    if any(data.get(k) is None for k in keys):
        return []
    calc = (
        data["protein_g"] * ENERGY_FACTORS["protein_g"]
        + data["fat_g"] * ENERGY_FACTORS["fat_g"]
        + data["carbohydrate_g"] * ENERGY_FACTORS["carbohydrate_g"]
    )
    declared = data["energy_kj"]
    if calc <= 0:
        return []
    tolerance = params.get("tolerance", 0.25)
    ratio = declared / calc
    if ratio > 1 + tolerance or ratio < 1 - tolerance:
        return [_warn(
            "nutrition",
            "energy_cross_check",
            f"标示能量 {declared:g}kJ 与三大营养素折算值约 {calc:.0f}kJ 偏差超过 {tolerance:.0%}，请核对",
        )]
    return [_pass("nutrition", "energy_cross_check", f"能量与三大营养素折算值（约 {calc:.0f}kJ）基本一致")]


def check_sodium_high(data, params, ctx):
    sodium = data.get("sodium_mg")
    threshold = params.get("threshold", NRV["sodium_mg"])
    if sodium is not None and threshold and sodium > threshold:
        return [_warn("nutrition", "sodium_high", f"每 100g/mL 钠含量已超过 {threshold:g}mg，属于高钠食品，请确认数据无误")]
    return []


def check_allergen_scan(data, params, ctx):
    keywords = params.get("keywords") or ALLERGEN_KEYWORDS
    detected = detect_allergens(_clean_ingredients(data), keywords)
    ctx["detected_allergens"] = detected
    statement = (data.get("allergen_statement") or "").strip()
    if not detected:
        return [_pass("allergen", "allergen_scan", "配料表中未检测到常见致敏物质")]
    names = "、".join(detected.keys())
    if statement:
        return [_pass("allergen", "allergen_statement", f"检测到致敏物质（{names}），已填写提示语")]
    return [_warn(
        "allergen",
        "allergen_statement",
        f"配料中检测到常见致敏物质：{names}，建议按 GB 7718 添加致敏物质提示",
    )]


RULE_CHECKS = {
    "product_name_required": _required_text_rule("product_name", "食品名称"),
    "manufacturer_required": _required_text_rule("manufacturer", "生产者名称"),
    "address_required": _required_text_rule("address", "生产者地址"),
    "storage_condition_required": _required_text_rule("storage_condition", "贮存条件"),
    "ingredients_required": check_ingredients_required,
    "net_content_required": check_net_content_required,
    "shelf_life_required": check_shelf_life_required,
    "production_date_format": check_production_date_format,
    "license_format": check_license_format,
    "standard_no_format": check_standard_no_format,
    "net_content_unit": check_net_content_unit,
    "shelf_life_unit": check_shelf_life_unit,
    "core_nutrients": check_core_nutrients,
    "nutrient_non_negative": check_nutrient_non_negative,
    "rounding": check_rounding,
    "energy_cross_check": check_energy_cross_check,
    "sodium_high": check_sodium_high,
    "allergen_scan": check_allergen_scan,
}


def normalize_rule_configs(rule_configs: list[dict] | None) -> dict[str, dict]:
    """把规则包快照归一化为 {code: {enabled, params}}。

    以内置默认配置为底，包里的 enabled / params 逐项覆盖；
    未登记的规则编码会被忽略，保证引擎行为只取决于注册表。
    """
    merged: dict[str, dict] = {}
    overrides = {c.get("code"): c for c in (rule_configs or [])}
    for base in default_rule_configs():
        cfg = {"enabled": True, "params": dict(base["params"])}
        override = overrides.get(base["code"])
        if override:
            cfg["enabled"] = bool(override.get("enabled", True))
            for key, value in (override.get("params") or {}).items():
                if key in cfg["params"]:
                    cfg["params"][key] = value
        merged[base["code"]] = cfg
    return merged


def validate_label(data: dict, rule_configs: list[dict] | None = None) -> dict:
    """按规则配置执行全部启用的检查，返回结构化结果。"""
    configs = normalize_rule_configs(rule_configs)
    ctx: dict = {}
    results: list[dict] = []

    for definition in RULE_DEFINITIONS:
        cfg = configs[definition["code"]]
        if not cfg["enabled"]:
            continue
        for item in RULE_CHECKS[definition["code"]](data, cfg["params"], ctx):
            item["rule"] = definition["code"]  # 标注所属规则，便于差异对比时展示规则名
            results.append(item)

    # ---------------- 汇总 ----------------
    errors = sum(1 for r in results if r["status"] == "error")
    warnings = sum(1 for r in results if r["status"] == "warning")
    passed = sum(1 for r in results if r["status"] == "pass")
    status = "fail" if errors else ("warning" if warnings else "pass")

    # 营养成分表（含 NRV%），供预览直接使用（数据派生，不受规则启停影响）
    nutrition_table = []
    for key, label, unit in NUTRIENT_META:
        value = data.get(key)
        nrv_pct = round(value / NRV[key] * 100) if value is not None else None
        nutrition_table.append({"key": key, "name": label, "unit": unit, "value": value, "nrv": nrv_pct})

    # 过敏原检出与到期日推算同属数据派生：即使对应规则被停用，
    # 预览与一键填充仍可使用当前参数（或默认参数）的扫描结果。
    detected = ctx.get("detected_allergens")
    if detected is None:
        keywords = configs["allergen_scan"]["params"].get("keywords") or ALLERGEN_KEYWORDS
        detected = detect_allergens(_clean_ingredients(data), keywords)

    expiry_date = None
    raw_date = (data.get("production_date") or "").strip()
    sl_unit = (data.get("shelf_life_unit") or "").strip()
    if DATE_RE.match(raw_date) and data.get("shelf_life_value") and sl_unit in SHELF_LIFE_UNITS:
        try:
            prod_date = date.fromisoformat(raw_date)
            expiry = compute_expiry(prod_date, data["shelf_life_value"], sl_unit)
            expiry_date = expiry.isoformat() if expiry else None
        except ValueError:
            expiry_date = None

    return {
        "status": status,
        "summary": {"errors": errors, "warnings": warnings, "passed": passed},
        "results": results,
        "detected_allergens": sorted(detected.keys()),
        "allergen_details": {k: v for k, v in sorted(detected.items())},
        "nutrition_table": nutrition_table,
        "expiry_date": expiry_date,
    }
