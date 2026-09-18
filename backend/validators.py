"""标签校验引擎。

依据 GB 7718《预包装食品标签通则》与 GB 28050《预包装食品营养标签通则》
的核心要求，对标签数据做四类检查：

- field     字段完整性：强制标示内容是否齐全、格式是否正确
- unit      单位规范：净含量、保质期、营养成分单位是否规范
- nutrition 营养成分：核心营养素齐全性、能量折算核对、修约要求
- allergen  过敏原提示：扫描配料表中的常见致敏物质并检查提示语
"""
import re
from calendar import monthrange
from datetime import date, timedelta

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

# 能量折算系数 (kJ/g)，GB 28050 问答
ENERGY_FACTORS = {"protein_g": 17, "fat_g": 37, "carbohydrate_g": 17}

NET_CONTENT_UNITS = {"g", "kg", "ml", "l", "mL", "L", "克", "千克", "毫升", "升"}
SHELF_LIFE_UNITS = {"天", "日", "个月", "月", "年"}

# GB 7718 推荐标示的致敏物质（8 类）及常见扩展项
ALLERGEN_KEYWORDS: dict[str, list[str]] = {
    "含有麸质的谷物": ["小麦", "大麦", "黑麦", "燕麦", "麸质", "面粉", "麦芽"],
    "甲壳纲类动物": ["虾", "蟹", "龙虾", "磷虾"],
    "鱼类": ["鱼露", "鱼粉", "鳕鱼", "三文鱼", "金枪鱼", "带鱼", "鲣鱼", "鱼"],
    "蛋类": ["鸡蛋", "鸭蛋", "鹌鹑蛋", "蛋黄", "蛋清", "蛋粉", "全蛋"],
    "花生": ["花生"],
    "大豆": ["大豆", "黄豆", "豆粕", "酱油", "豆酱", "豆腐", "豆浆", "豆粉", "卵磷脂"],
    "乳及乳制品": ["牛奶", "牛乳", "羊奶", "奶粉", "奶酪", "奶油", "乳糖", "乳清", "炼乳", "酸奶", "乳酪"],
    "坚果": ["核桃", "杏仁", "腰果", "榛子", "开心果", "夏威夷果", "巴旦木", "松子", "碧根果", "板栗"],
    "芝麻": ["芝麻"],
    "芹菜": ["芹菜"],
    "芥末": ["芥末"],
    "亚硫酸盐": ["亚硫酸", "二氧化硫", "焦亚硫酸"],
}

LICENSE_RE = re.compile(r"^SC\d{14}$")
STANDARD_RE = re.compile(r"^(GB|GB/T|QB|QB/T|SB|SB/T|NY/T|Q/[A-Z0-9]{2,12})\s*\d+", re.IGNORECASE)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def detect_allergens(ingredients: list[str]) -> dict[str, list[str]]:
    """扫描配料表，返回 {过敏原类别: [命中的配料]}。"""
    found: dict[str, list[str]] = {}
    for ingredient in ingredients:
        for category, keywords in ALLERGEN_KEYWORDS.items():
            if any(kw in ingredient for kw in keywords):
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


def validate_label(data: dict) -> dict:
    """执行全部校验，返回结构化结果。"""
    results: list[dict] = []

    def add(category: str, code: str, status: str, message: str):
        results.append({"category": category, "code": code, "status": status, "message": message})

    def ok(cat, code, msg):
        add(cat, code, "pass", msg)

    def warn(cat, code, msg):
        add(cat, code, "warning", msg)

    def err(cat, code, msg):
        add(cat, code, "error", msg)

    # ---------------- 1. 字段完整性 ----------------
    required_text = [
        ("product_name", "食品名称"),
        ("manufacturer", "生产者名称"),
        ("address", "生产者地址"),
        ("storage_condition", "贮存条件"),
    ]
    for field, label in required_text:
        if (data.get(field) or "").strip():
            ok("field", f"{field}_required", f"{label}已填写")
        else:
            err("field", f"{field}_required", f"缺少强制标示内容：{label}")

    ingredients = [s.strip() for s in (data.get("ingredients") or []) if s and s.strip()]
    if ingredients:
        ok("field", "ingredients_required", f"配料表已填写（共 {len(ingredients)} 项）")
    else:
        err("field", "ingredients_required", "缺少强制标示内容：配料表")

    if data.get("net_content_value") is None:
        err("field", "net_content_required", "缺少强制标示内容：净含量")
    elif data["net_content_value"] <= 0:
        err("field", "net_content_positive", "净含量必须大于 0")
    else:
        ok("field", "net_content_required", "净含量已填写")

    if data.get("shelf_life_value") is None:
        err("field", "shelf_life_required", "缺少强制标示内容：保质期")
    elif data["shelf_life_value"] <= 0:
        err("field", "shelf_life_positive", "保质期必须大于 0")
    else:
        ok("field", "shelf_life_required", "保质期已填写")

    # 生产日期
    prod_date: date | None = None
    raw_date = (data.get("production_date") or "").strip()
    if not raw_date:
        warn("field", "production_date_required", "未填写生产日期（实际标签可以“见喷码”形式标示）")
    elif not DATE_RE.match(raw_date):
        err("field", "production_date_format", f"生产日期格式应为 YYYY-MM-DD，当前为：{raw_date}")
    else:
        try:
            prod_date = date.fromisoformat(raw_date)
            if prod_date > date.today():
                warn("field", "production_date_future", "生产日期晚于今天，请确认是否填写有误")
            else:
                ok("field", "production_date_format", "生产日期格式正确")
        except ValueError:
            err("field", "production_date_format", f"生产日期不是有效日期：{raw_date}")

    # 食品生产许可证编号：SC + 14 位数字
    license_no = (data.get("license_no") or "").strip()
    if not license_no:
        err("field", "license_required", "缺少强制标示内容：食品生产许可证编号")
    elif not LICENSE_RE.match(license_no):
        err("field", "license_format", "生产许可证编号格式应为 SC + 14 位数字，如 SC10632011500123")
    else:
        ok("field", "license_format", "生产许可证编号格式正确")

    # 产品标准号（推荐）
    standard_no = (data.get("standard_no") or "").strip()
    if not standard_no:
        warn("field", "standard_recommended", "建议填写产品标准号（如 GB/T 20980）")
    elif not STANDARD_RE.match(standard_no):
        warn("field", "standard_format", "产品标准号格式存疑，常见形式如 GB/T 20980、Q/XXX 0001S")
    else:
        ok("field", "standard_format", "产品标准号格式正确")

    # ---------------- 2. 单位规范 ----------------
    nc_unit = (data.get("net_content_unit") or "").strip()
    if nc_unit not in NET_CONTENT_UNITS:
        err("unit", "net_content_unit", f"净含量单位“{nc_unit or '（空）'}”不规范，应为 g、kg、mL 或 L")
    else:
        ok("unit", "net_content_unit", "净含量单位规范")
        value = data.get("net_content_value")
        if value is not None and value >= 1000 and nc_unit in ("g", "克"):
            warn("unit", "net_content_unit_scale", "净含量 ≥ 1000g 时应使用 kg 作为计量单位")
        if value is not None and value >= 1000 and nc_unit in ("ml", "mL", "毫升"):
            warn("unit", "net_content_unit_scale", "净含量 ≥ 1000mL 时应使用 L 作为计量单位")

    sl_unit = (data.get("shelf_life_unit") or "").strip()
    if sl_unit not in SHELF_LIFE_UNITS:
        err("unit", "shelf_life_unit", f"保质期单位“{sl_unit or '（空）'}”不规范，应为 天、个月 或 年")
    else:
        ok("unit", "shelf_life_unit", "保质期单位规范")
        value = data.get("shelf_life_value")
        if value is not None and sl_unit in ("天", "日") and value >= 365:
            warn("unit", "shelf_life_unit_scale", "保质期超过一年，建议使用“个月”或“年”表示")

    # ---------------- 3. 营养成分 ----------------
    nutrients = {key: data.get(key) for key, _, _ in NUTRIENT_META}
    missing = [label for key, label, _ in NUTRIENT_META if nutrients[key] is None]
    if missing:
        err("nutrition", "core_nutrients", "营养成分表缺少核心营养素（1+4）：" + "、".join(missing))
    else:
        ok("nutrition", "core_nutrients", "核心营养素（能量、蛋白质、脂肪、碳水化合物、钠）齐全")

    for key, label, _ in NUTRIENT_META:
        value = nutrients[key]
        if value is not None and value < 0:
            err("nutrition", f"{key}_negative", f"{label}含量不能为负数")

    # 修约：能量、钠应标示为整数
    if nutrients["energy_kj"] is not None and nutrients["energy_kj"] % 1 != 0:
        warn("nutrition", "energy_rounding", "能量的标示值应按 GB 28050 修约为整数（kJ）")
    if nutrients["sodium_mg"] is not None and nutrients["sodium_mg"] % 1 != 0:
        warn("nutrition", "sodium_rounding", "钠的标示值应按 GB 28050 修约为整数（mg）")

    # 能量折算核对：蛋白质×17 + 脂肪×37 + 碳水化合物×17
    if all(nutrients[k] is not None for k in ("energy_kj", "protein_g", "fat_g", "carbohydrate_g")):
        calc = (
            nutrients["protein_g"] * ENERGY_FACTORS["protein_g"]
            + nutrients["fat_g"] * ENERGY_FACTORS["fat_g"]
            + nutrients["carbohydrate_g"] * ENERGY_FACTORS["carbohydrate_g"]
        )
        declared = nutrients["energy_kj"]
        if calc > 0:
            ratio = declared / calc
            if ratio > 1.25 or ratio < 0.75:
                warn(
                    "nutrition",
                    "energy_cross_check",
                    f"标示能量 {declared:g}kJ 与三大营养素折算值约 {calc:.0f}kJ 偏差超过 25%，请核对",
                )
            else:
                ok("nutrition", "energy_cross_check", f"能量与三大营养素折算值（约 {calc:.0f}kJ）基本一致")

    if nutrients["sodium_mg"] is not None and nutrients["sodium_mg"] > NRV["sodium_mg"]:
        warn("nutrition", "sodium_high", "每 100g/mL 钠含量已超过 NRV（2000mg），属于高钠食品，请确认数据无误")

    # ---------------- 4. 过敏原提示 ----------------
    detected = detect_allergens(ingredients)
    statement = (data.get("allergen_statement") or "").strip()
    if detected:
        names = "、".join(detected.keys())
        if statement:
            ok("allergen", "allergen_statement", f"检测到致敏物质（{names}），已填写提示语")
        else:
            warn(
                "allergen",
                "allergen_statement",
                f"配料中检测到常见致敏物质：{names}，建议按 GB 7718 添加致敏物质提示",
            )
    else:
        ok("allergen", "allergen_scan", "配料表中未检测到常见致敏物质")

    # ---------------- 汇总 ----------------
    errors = sum(1 for r in results if r["status"] == "error")
    warnings = sum(1 for r in results if r["status"] == "warning")
    passed = sum(1 for r in results if r["status"] == "pass")
    status = "fail" if errors else ("warning" if warnings else "pass")

    # 营养成分表（含 NRV%），供预览直接使用
    nutrition_table = []
    for key, label, unit in NUTRIENT_META:
        value = nutrients[key]
        nrv_pct = round(value / NRV[key] * 100) if value is not None else None
        nutrition_table.append({"key": key, "name": label, "unit": unit, "value": value, "nrv": nrv_pct})

    expiry_date = None
    if prod_date and data.get("shelf_life_value") and sl_unit in SHELF_LIFE_UNITS:
        expiry = compute_expiry(prod_date, data["shelf_life_value"], sl_unit)
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
