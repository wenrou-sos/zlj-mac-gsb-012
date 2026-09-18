"""法规规则定义注册表。

每条规则包含：唯一编码、分类、中文名称、说明以及可配置参数的 schema。
规则包（RulePackage）库存储的是 [{code, enabled, params}] 快照，
校验引擎按快照逐条执行，从而实现规则的版本化、启停与参数化。

新增规则时：在 RULE_DEFINITIONS 中登记定义，并在 validators.py 的
RULE_CHECKS 中实现同名检查函数。
"""

# GB 7718 推荐标示的致敏物质（8 类）及常见扩展项（默认关键词，可在规则参数中调整）
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

CATEGORY_LABELS = {
    "field": "字段完整性",
    "unit": "单位规范",
    "nutrition": "营养成分",
    "allergen": "过敏原提示",
}

# 参数类型：number / boolean / text / json（json 类型以前端 JSON 文本框编辑）
RULE_DEFINITIONS: list[dict] = [
    # ---------------- 字段完整性 ----------------
    {
        "code": "product_name_required",
        "category": "field",
        "name": "食品名称必填",
        "description": "GB 7718 强制标示内容：应在标签醒目位置清晰标示食品名称。",
        "params": [],
    },
    {
        "code": "manufacturer_required",
        "category": "field",
        "name": "生产者名称必填",
        "description": "GB 7718 强制标示内容：应标示生产者的名称。",
        "params": [],
    },
    {
        "code": "address_required",
        "category": "field",
        "name": "生产者地址必填",
        "description": "GB 7718 强制标示内容：应标示生产者的地址。",
        "params": [],
    },
    {
        "code": "storage_condition_required",
        "category": "field",
        "name": "贮存条件必填",
        "description": "GB 7718 强制标示内容：应标示贮存条件。",
        "params": [],
    },
    {
        "code": "ingredients_required",
        "category": "field",
        "name": "配料表必填",
        "description": "GB 7718 强制标示内容：应标示配料表，按加入量递减顺序排列。",
        "params": [],
    },
    {
        "code": "net_content_required",
        "category": "field",
        "name": "净含量必填",
        "description": "GB 7718 强制标示内容：应标示净含量，且数值必须大于 0。",
        "params": [],
    },
    {
        "code": "shelf_life_required",
        "category": "field",
        "name": "保质期必填",
        "description": "GB 7718 强制标示内容：应标示保质期，且数值必须大于 0。",
        "params": [],
    },
    {
        "code": "production_date_format",
        "category": "field",
        "name": "生产日期格式",
        "description": "生产日期应按 YYYY-MM-DD 填写；未填写时可“见喷码”标示，仅提示。",
        "params": [
            {
                "key": "future_warning",
                "label": "生产日期晚于今天时告警",
                "type": "boolean",
                "default": True,
            },
        ],
    },
    {
        "code": "license_format",
        "category": "field",
        "name": "生产许可证编号",
        "description": "食品生产许可证编号格式应为 SC + 14 位数字。",
        "params": [
            {
                "key": "required",
                "label": "是否强制（关闭后缺失仅告警）",
                "type": "boolean",
                "default": True,
            },
            {
                "key": "pattern",
                "label": "编号格式正则",
                "type": "text",
                "default": r"^SC\d{14}$",
                "help": "用于校验编号的正则表达式，留空或无效时回退默认",
            },
        ],
    },
    {
        "code": "standard_no_format",
        "category": "field",
        "name": "产品标准号",
        "description": "产品标准号为推荐标示内容，常见形式如 GB/T 20980、Q/XXX 0001S。",
        "params": [
            {
                "key": "required",
                "label": "是否强制（开启后缺失记为错误）",
                "type": "boolean",
                "default": False,
            },
        ],
    },
    # ---------------- 单位规范 ----------------
    {
        "code": "net_content_unit",
        "category": "unit",
        "name": "净含量单位规范",
        "description": "净含量单位应为 g、kg、mL 或 L；超过阈值时建议换算为 kg / L。",
        "params": [
            {
                "key": "scale_threshold",
                "label": "换算阈值（g / mL）",
                "type": "number",
                "default": 1000,
                "min": 1,
                "step": 100,
                "help": "净含量达到该值时建议使用 kg / L 标示",
            },
        ],
    },
    {
        "code": "shelf_life_unit",
        "category": "unit",
        "name": "保质期单位规范",
        "description": "保质期单位应为 天、个月 或 年；以天标示超过阈值时建议换算。",
        "params": [
            {
                "key": "day_threshold",
                "label": "天数换算阈值",
                "type": "number",
                "default": 365,
                "min": 1,
                "step": 1,
                "help": "保质期（天）达到该值时建议使用“个月”或“年”",
            },
        ],
    },
    # ---------------- 营养成分 ----------------
    {
        "code": "core_nutrients",
        "category": "nutrition",
        "name": "核心营养素齐全",
        "description": "GB 28050 要求营养成分表至少标示“1+4”核心营养素：能量、蛋白质、脂肪、碳水化合物、钠。",
        "params": [
            {
                "key": "required",
                "label": "必填营养素",
                "type": "json",
                "default": ["energy_kj", "protein_g", "fat_g", "carbohydrate_g", "sodium_mg"],
                "help": "营养素字段名列表，可选：energy_kj / protein_g / fat_g / carbohydrate_g / sodium_mg",
            },
        ],
    },
    {
        "code": "nutrient_non_negative",
        "category": "nutrition",
        "name": "营养素含量非负",
        "description": "各营养素标示值不能为负数。",
        "params": [],
    },
    {
        "code": "rounding",
        "category": "nutrition",
        "name": "修约要求",
        "description": "能量、钠的标示值应按 GB 28050 修约为整数。",
        "params": [
            {
                "key": "integer_fields",
                "label": "要求整数的营养素",
                "type": "json",
                "default": ["energy_kj", "sodium_mg"],
                "help": "需要修约为整数的营养素字段名列表",
            },
        ],
    },
    {
        "code": "energy_cross_check",
        "category": "nutrition",
        "name": "能量折算核对",
        "description": "标示能量与三大营养素折算值（蛋白质×17 + 脂肪×37 + 碳水化合物×17）的偏差应在允许范围内。",
        "params": [
            {
                "key": "tolerance",
                "label": "允许偏差比例",
                "type": "number",
                "default": 0.25,
                "min": 0.01,
                "max": 1,
                "step": 0.05,
                "help": "如 0.25 表示偏差超过 ±25% 时告警",
            },
        ],
    },
    {
        "code": "sodium_high",
        "category": "nutrition",
        "name": "高钠提示",
        "description": "每 100g/mL 钠含量超过阈值时提示属于高钠食品。",
        "params": [
            {
                "key": "threshold",
                "label": "钠含量阈值（mg）",
                "type": "number",
                "default": 2000,
                "min": 1,
                "step": 100,
                "help": "默认为钠的 NRV（2000mg）",
            },
        ],
    },
    # ---------------- 过敏原提示 ----------------
    {
        "code": "allergen_scan",
        "category": "allergen",
        "name": "致敏物质扫描与提示",
        "description": "扫描配料表中的常见致敏物质，检出时建议按 GB 7718 添加致敏物质提示语。",
        "params": [
            {
                "key": "keywords",
                "label": "致敏物质关键词",
                "type": "json",
                "default": ALLERGEN_KEYWORDS,
                "help": "对象结构：{ 致敏物质类别: [关键词, ...] }",
            },
        ],
    },
]

DEFINITIONS_BY_CODE = {d["code"]: d for d in RULE_DEFINITIONS}


def default_params(definition: dict) -> dict:
    return {p["key"]: p["default"] for p in definition["params"]}


def default_rule_configs() -> list[dict]:
    """生成内置默认规则配置（全部启用、默认参数），用于初始化规则包。"""
    return [
        {"code": d["code"], "enabled": True, "params": default_params(d)}
        for d in RULE_DEFINITIONS
    ]
