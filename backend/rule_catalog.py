"""内置规则目录（Rule Catalog）。

每一条法规检查在此声明为一条「规则」：固定 code、分类、中文名、默认严重级别
与默认可调参数。规则包版本化时，包内配置以这里的目录为基准做覆盖；
RuleEngine 只认 code，因此新老版本之间可以逐条比对差异。

参数分两层：
- 全局参数（GLOBAL_PARAM_SCHEMA / DEFAULT_GLOBAL_PARAMS）：单位集合、NRV、
  能量折算系数、过敏原关键词表等多条规则共享的配置；
- 单规则参数（catalog 条目的 params）：正则、阈值等，仅该规则使用。
"""
from copy import deepcopy

# GB 28050-2011 附录A：营养素参考值 (NRV)
DEFAULT_NRV = {
    "energy_kj": 8400,
    "protein_g": 60,
    "fat_g": 60,
    "carbohydrate_g": 300,
    "sodium_mg": 2000,
}

# 能量折算系数 (kJ/g)，GB 28050 问答
DEFAULT_ENERGY_FACTORS = {"protein_g": 17, "fat_g": 37, "carbohydrate_g": 17}

NUTRIENT_META = [
    ("energy_kj", "能量", "千焦(kJ)"),
    ("protein_g", "蛋白质", "克(g)"),
    ("fat_g", "脂肪", "克(g)"),
    ("carbohydrate_g", "碳水化合物", "克(g)"),
    ("sodium_mg", "钠", "毫克(mg)"),
]

# GB 7718 推荐标示的致敏物质（8 类）及常见扩展项
DEFAULT_ALLERGEN_KEYWORDS: dict[str, list[str]] = {
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

DEFAULT_NET_CONTENT_UNITS = ["g", "kg", "ml", "l", "mL", "L", "克", "千克", "毫升", "升"]
DEFAULT_SHELF_LIFE_UNITS = ["天", "日", "个月", "月", "年"]

DEFAULT_LICENSE_PATTERN = r"^SC\d{14}$"
DEFAULT_STANDARD_PATTERN = r"^(GB|GB/T|QB|QB/T|SB|SB/T|NY/T|Q/[A-Z0-9]{2,12})\s*\d+"

# 参数编辑器描述（前端据此渲染全局参数表单）
GLOBAL_PARAM_SCHEMA = [
    {"key": "net_content_units", "label": "净含量允许单位", "type": "string_list",
     "help": "多个单位用逗号分隔，如 g、kg、mL、L、克、千克、毫升、升"},
    {"key": "shelf_life_units", "label": "保质期允许单位", "type": "string_list",
     "help": "多个单位用逗号分隔，如 天、日、个月、月、年"},
    {"group": "nrv", "label": "营养素参考值 NRV", "type": "number_group",
     "fields": [
         {"key": "energy_kj", "label": "能量 (kJ)"},
         {"key": "protein_g", "label": "蛋白质 (g)"},
         {"key": "fat_g", "label": "脂肪 (g)"},
         {"key": "carbohydrate_g", "label": "碳水化合物 (g)"},
         {"key": "sodium_mg", "label": "钠 (mg)"},
     ]},
    {"group": "energy_factors", "label": "能量折算系数 (kJ/g)", "type": "number_group",
     "fields": [
         {"key": "protein_g", "label": "蛋白质"},
         {"key": "fat_g", "label": "脂肪"},
         {"key": "carbohydrate_g", "label": "碳水化合物"},
     ]},
    {"key": "allergen_keywords", "label": "致敏物质关键词表", "type": "allergen_map",
     "help": "每行一类，格式：类别: 关键词1,关键词2"},
]

DEFAULT_GLOBAL_PARAMS = {
    "net_content_units": list(DEFAULT_NET_CONTENT_UNITS),
    "shelf_life_units": list(DEFAULT_SHELF_LIFE_UNITS),
    "nrv": dict(DEFAULT_NRV),
    "energy_factors": dict(DEFAULT_ENERGY_FACTORS),
    "allergen_keywords": {k: list(v) for k, v in DEFAULT_ALLERGEN_KEYWORDS.items()},
}


def _p(key, label, ptype="string", help_text="", step=None, minimum=None):
    return {"key": key, "label": label, "type": ptype, "help": help_text, "step": step, "min": minimum}


# 规则目录：顺序即界面展示顺序
RULE_CATALOG: list[dict] = [
    # ---------------- 字段完整性 ----------------
    {"code": "product_name_required", "category": "field", "name": "食品名称必填",
     "default_severity": "error", "description": "强制标示内容：食品名称"},
    {"code": "manufacturer_required", "category": "field", "name": "生产者名称必填",
     "default_severity": "error", "description": "强制标示内容：生产者名称"},
    {"code": "address_required", "category": "field", "name": "生产者地址必填",
     "default_severity": "error", "description": "强制标示内容：生产者地址"},
    {"code": "storage_condition_required", "category": "field", "name": "贮存条件必填",
     "default_severity": "error", "description": "强制标示内容：贮存条件"},
    {"code": "ingredients_required", "category": "field", "name": "配料表必填",
     "default_severity": "error", "description": "强制标示内容：配料表"},
    {"code": "net_content_required", "category": "field", "name": "净含量必填",
     "default_severity": "error", "description": "强制标示内容：净含量"},
    {"code": "net_content_positive", "category": "field", "name": "净含量必须为正数",
     "default_severity": "error", "description": "净含量数值需大于 0"},
    {"code": "shelf_life_required", "category": "field", "name": "保质期必填",
     "default_severity": "error", "description": "强制标示内容：保质期"},
    {"code": "shelf_life_positive", "category": "field", "name": "保质期必须为正数",
     "default_severity": "error", "description": "保质期数值需大于 0"},
    {"code": "production_date_required", "category": "field", "name": "生产日期标示提示",
     "default_severity": "warning", "description": "未填写生产日期时提示（允许以“见喷码”形式标示）"},
    {"code": "production_date_format", "category": "field", "name": "生产日期格式",
     "default_severity": "error", "description": "生产日期须为 YYYY-MM-DD 且为有效日期"},
    {"code": "production_date_future", "category": "field", "name": "生产日期晚于今天提示",
     "default_severity": "warning", "description": "生产日期为未来日期时给出警告"},
    {"code": "license_required", "category": "field", "name": "生产许可证编号必填",
     "default_severity": "error", "description": "强制标示内容：食品生产许可证编号"},
    {"code": "license_format", "category": "field", "name": "生产许可证编号格式",
     "default_severity": "error",
     "description": "默认要求 SC + 14 位数字，正则可按监管口径调整",
     "params": [
         _p("pattern", "编号正则"),
         _p("example", "示例编号"),
     ],
     "defaults": {"pattern": DEFAULT_LICENSE_PATTERN, "example": "SC10632011500123"}},
    {"code": "standard_recommended", "category": "field", "name": "产品标准号建议",
     "default_severity": "warning", "description": "未填写产品标准号时提示"},
    {"code": "standard_format", "category": "field", "name": "产品标准号格式",
     "default_severity": "warning",
     "description": "产品标准号常见形式如 GB/T 20980、Q/XXX 0001S，正则可调整",
     "params": [_p("pattern", "标准号正则")],
     "defaults": {"pattern": DEFAULT_STANDARD_PATTERN}},

    # ---------------- 单位规范 ----------------
    {"code": "net_content_unit", "category": "unit", "name": "净含量单位规范",
     "default_severity": "error", "description": "净含量单位须在全局参数允许的单位集合内"},
    {"code": "net_content_unit_scale", "category": "unit", "name": "净含量计量单位量级",
     "default_severity": "warning",
     "description": "净含量达到阈值时建议使用 kg / L 标示",
     "params": [_p("threshold", "换算阈值", "number", "达到该数值时建议换用大单位", step=1, minimum=0)],
     "defaults": {"threshold": 1000}},
    {"code": "shelf_life_unit", "category": "unit", "name": "保质期单位规范",
     "default_severity": "error", "description": "保质期单位须在全局参数允许的单位集合内"},
    {"code": "shelf_life_unit_scale", "category": "unit", "name": "保质期计量单位量级",
     "default_severity": "warning",
     "description": "保质期天数达到阈值时建议使用“个月”或“年”",
     "params": [_p("threshold", "天数阈值", "number", step=1, minimum=0)],
     "defaults": {"threshold": 365}},

    # ---------------- 营养成分 ----------------
    {"code": "core_nutrients", "category": "nutrition", "name": "核心营养素齐全（1+4）",
     "default_severity": "error",
     "description": "能量、蛋白质、脂肪、碳水化合物、钠必须全部标示"},
    {"code": "energy_negative", "category": "nutrition", "name": "能量非负",
     "default_severity": "error", "description": "能量标示值不能为负数", "meta": {"nutrient_key": "energy_kj"}},
    {"code": "protein_negative", "category": "nutrition", "name": "蛋白质非负",
     "default_severity": "error", "description": "蛋白质标示值不能为负数", "meta": {"nutrient_key": "protein_g"}},
    {"code": "fat_negative", "category": "nutrition", "name": "脂肪非负",
     "default_severity": "error", "description": "脂肪标示值不能为负数", "meta": {"nutrient_key": "fat_g"}},
    {"code": "carbohydrate_negative", "category": "nutrition", "name": "碳水化合物非负",
     "default_severity": "error", "description": "碳水化合物标示值不能为负数", "meta": {"nutrient_key": "carbohydrate_g"}},
    {"code": "sodium_negative", "category": "nutrition", "name": "钠非负",
     "default_severity": "error", "description": "钠标示值不能为负数", "meta": {"nutrient_key": "sodium_mg"}},
    {"code": "energy_rounding", "category": "nutrition", "name": "能量修约",
     "default_severity": "warning", "description": "能量应按 GB 28050 修约为整数（kJ）"},
    {"code": "sodium_rounding", "category": "nutrition", "name": "钠修约",
     "default_severity": "warning", "description": "钠应按 GB 28050 修约为整数（mg）"},
    {"code": "energy_cross_check", "category": "nutrition", "name": "能量折算核对",
     "default_severity": "warning",
     "description": "标示能量与蛋白质/脂肪/碳水折算值偏差超限时提示",
     "params": [_p("tolerance", "允许偏差比例", "number", "0.25 表示 ±25%", step=0.01, minimum=0)],
     "defaults": {"tolerance": 0.25}},
    {"code": "sodium_high", "category": "nutrition", "name": "高钠提示",
     "default_severity": "warning",
     "description": "每 100g/mL 钠含量超过阈值时提示为高钠食品",
     "params": [_p("threshold_mg", "钠阈值 (mg)", "number", step=1, minimum=0)],
     "defaults": {"threshold_mg": 2000}},

    # ---------------- 过敏原 ----------------
    {"code": "allergen_statement", "category": "allergen", "name": "致敏物质提示语",
     "default_severity": "warning",
     "description": "配料检出致敏物质但未填写提示语时警告，关键词表在全局参数中维护"},
    {"code": "allergen_scan", "category": "allergen", "name": "致敏物质扫描（信息项）",
     "default_severity": "warning",
     "description": "未检出致敏物质时给出通过信息；停用后不再输出该项"},
]

CATALOG_BY_CODE = {item["code"]: item for item in RULE_CATALOG}
CATEGORIES = [
    {"key": "field", "label": "字段完整性", "icon": "📋"},
    {"key": "unit", "label": "单位规范", "icon": "⚖️"},
    {"key": "nutrition", "label": "营养成分", "icon": "🥗"},
    {"key": "allergen", "label": "过敏原提示", "icon": "⚠️"},
]


def default_config() -> dict:
    """生成一份「全量显式」的默认包配置。

    发布后的规则包是自描述快照：即使未来代码内置默认值随新版国标调整，
    老版本包的校验结果仍由其自身配置决定。
    """
    return {
        "params": deepcopy(DEFAULT_GLOBAL_PARAMS),
        "rules": {
            item["code"]: {
                "enabled": True,
                "severity": item["default_severity"],
                "params": deepcopy(item.get("defaults", {})),
            }
            for item in RULE_CATALOG
        },
    }


def catalog_payload() -> dict:
    """GET /api/rule-catalog 的返回体。"""
    return {
        "categories": CATEGORIES,
        "rules": RULE_CATALOG,
        "global_params_schema": GLOBAL_PARAM_SCHEMA,
        "default_config": default_config(),
    }
