<script setup>
defineProps({
  form: { type: Object, required: true },
  detectedAllergens: { type: Array, default: () => [] },
})
defineEmits(['fill-allergen'])

const netContentUnits = ['g', 'kg', 'mL', 'L']
const shelfLifeUnits = ['天', '个月', '年']
</script>

<template>
  <div class="form">
    <section>
      <h2><span class="num">1</span>基本信息</h2>
      <div class="grid">
        <label class="span2">
          食品名称 <i class="req">*</i>
          <input v-model.trim="form.product_name" placeholder="如：全麦消化饼干" />
        </label>
        <label>
          品牌
          <input v-model.trim="form.brand" placeholder="如：谷香坊" />
        </label>
        <label>
          产品标准号
          <input v-model.trim="form.standard_no" placeholder="如：GB/T 20980" />
        </label>
        <label>
          净含量 <i class="req">*</i>
          <div class="inline">
            <input v-model.number="form.net_content_value" type="number" min="0" step="any" placeholder="500" />
            <select v-model="form.net_content_unit">
              <option v-for="u in netContentUnits" :key="u" :value="u">{{ u }}</option>
            </select>
          </div>
        </label>
      </div>
    </section>

    <section>
      <h2><span class="num">2</span>配料表 <i class="req">*</i></h2>
      <textarea
        v-model="form.ingredients_text"
        rows="3"
        placeholder="按加入量递减顺序填写，用顿号或逗号分隔，如：小麦粉、白砂糖、植物油、鸡蛋"
      ></textarea>
      <p class="hint">配料将自动扫描常见致敏物质（麸质、蛋、乳、花生、大豆、坚果等）</p>
    </section>

    <section>
      <h2><span class="num">3</span>营养成分 <span class="sub">每 100g / 100mL</span></h2>
      <div class="grid nutrition">
        <label>
          能量 (kJ) <i class="req">*</i>
          <input v-model.number="form.energy_kj" type="number" min="0" step="any" placeholder="1980" />
        </label>
        <label>
          蛋白质 (g) <i class="req">*</i>
          <input v-model.number="form.protein_g" type="number" min="0" step="any" placeholder="8.2" />
        </label>
        <label>
          脂肪 (g) <i class="req">*</i>
          <input v-model.number="form.fat_g" type="number" min="0" step="any" placeholder="18.5" />
        </label>
        <label>
          碳水化合物 (g) <i class="req">*</i>
          <input v-model.number="form.carbohydrate_g" type="number" min="0" step="any" placeholder="62.3" />
        </label>
        <label>
          钠 (mg) <i class="req">*</i>
          <input v-model.number="form.sodium_mg" type="number" min="0" step="any" placeholder="320" />
        </label>
      </div>
    </section>

    <section>
      <h2><span class="num">4</span>保质期与贮存</h2>
      <div class="grid">
        <label>
          保质期 <i class="req">*</i>
          <div class="inline">
            <input v-model.number="form.shelf_life_value" type="number" min="0" step="1" placeholder="12" />
            <select v-model="form.shelf_life_unit">
              <option v-for="u in shelfLifeUnits" :key="u" :value="u">{{ u }}</option>
            </select>
          </div>
        </label>
        <label>
          生产日期
          <input v-model="form.production_date" type="date" />
        </label>
        <label class="span2">
          贮存条件 <i class="req">*</i>
          <input v-model.trim="form.storage_condition" placeholder="如：请置于阴凉干燥处，避免阳光直射" />
        </label>
      </div>
    </section>

    <section>
      <h2><span class="num">5</span>生产信息</h2>
      <div class="grid">
        <label>
          生产者名称 <i class="req">*</i>
          <input v-model.trim="form.manufacturer" placeholder="如：某某食品有限公司" />
        </label>
        <label>
          生产许可证编号 <i class="req">*</i>
          <input v-model.trim="form.license_no" placeholder="SC + 14 位数字" />
        </label>
        <label class="span2">
          生产者地址 <i class="req">*</i>
          <input v-model.trim="form.address" placeholder="如：江苏省苏州市工业园区示例路 88 号" />
        </label>
      </div>
    </section>

    <section>
      <h2>
        <span class="num">6</span>致敏物质提示
        <button
          v-if="detectedAllergens.length"
          class="fill-btn"
          type="button"
          @click="$emit('fill-allergen')"
        >
          一键填充（已检出 {{ detectedAllergens.length }} 类）
        </button>
      </h2>
      <textarea
        v-model.trim="form.allergen_statement"
        rows="2"
        placeholder="如：本品含有麸质谷物、蛋类、乳及乳制品。"
      ></textarea>
      <p v-if="detectedAllergens.length" class="hint warn">
        配料中检出：{{ detectedAllergens.join('、') }}
      </p>
    </section>
  </div>
</template>

<style scoped>
.form section {
  padding: 14px 0;
  border-bottom: 1px dashed var(--border);
}
.form section:first-child {
  padding-top: 0;
}
.form section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  margin: 0 0 12px;
  color: var(--primary-dark);
}

.num {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sub {
  font-size: 12px;
  font-weight: normal;
  color: var(--text-muted);
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}

.grid.nutrition {
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
}

.span2 {
  grid-column: span 2;
}

.req {
  color: var(--error);
  font-style: normal;
}

.inline {
  display: flex;
  gap: 8px;
}
.inline input {
  flex: 1;
  min-width: 0;
}
.inline select {
  width: 84px;
  flex-shrink: 0;
}

.hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.hint.warn {
  color: var(--warning);
}

.fill-btn {
  margin-left: auto;
  padding: 3px 10px;
  font-size: 12px;
  background: var(--primary-light);
  color: var(--primary-dark);
  border-radius: 12px;
}
.fill-btn:hover {
  background: #c8e6c9;
}
</style>
