<script setup>
import { computed } from 'vue'

const props = defineProps({
  form: { type: Object, required: true },
  validation: { type: Object, default: null },
})

const BLANK = '＿＿＿'
const show = (v) => (v !== null && v !== undefined && v !== '' ? v : BLANK)

const ingredientsText = computed(() => {
  const text = (props.form.ingredients_text || '')
    .split(/[、,，;；\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
    .join('、')
  return text || BLANK
})

const allergenText = computed(() => {
  if (props.form.allergen_statement) return props.form.allergen_statement
  const detected = props.validation?.detected_allergens || []
  if (detected.length) return `（待补充）本品含有${detected.join('、')}及其制品。`
  return '无'
})

const nutritionRows = computed(() => props.validation?.nutrition_table || [])

const shelfLifeText = computed(() => {
  const { shelf_life_value: v, shelf_life_unit: u } = props.form
  if (v === null || v === '' || v === undefined) return BLANK
  return `${v}${u}`
})

const netContentText = computed(() => {
  const { net_content_value: v, net_content_unit: u } = props.form
  if (v === null || v === '' || v === undefined) return BLANK
  return `${v}${u}`
})
</script>

<template>
  <div class="preview-wrap">
    <div class="label-card">
      <header class="label-head">
        <div v-if="form.brand" class="brand-name">{{ form.brand }}</div>
        <div class="product-name">{{ show(form.product_name) }}</div>
        <div class="net-content">净含量：{{ netContentText }}</div>
      </header>

      <section class="block">
        <p><strong>配料表：</strong>{{ ingredientsText }}</p>
        <p class="allergen"><strong>致敏物质提示：</strong>{{ allergenText }}</p>
      </section>

      <section class="block nutrition">
        <div class="nutrition-title">
          <strong>营养成分表</strong>
          <span>Nutrition Information</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>项目</th>
              <th>每 100 克（g）</th>
              <th>NRV%</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in nutritionRows" :key="row.key">
              <td>{{ row.name }}</td>
              <td>{{ row.value === null ? BLANK : `${row.value} ${row.unit}` }}</td>
              <td>{{ row.nrv === null ? BLANK : row.nrv + '%' }}</td>
            </tr>
            <tr v-if="!nutritionRows.length">
              <td colspan="3" class="empty-cell">填写营养成分后自动生成</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="block meta">
        <p><strong>生产日期：</strong>{{ show(form.production_date) }}</p>
        <p>
          <strong>保质期：</strong>{{ shelfLifeText }}
          <span v-if="validation?.expiry_date" class="expiry">
            （此日期前最佳：{{ validation.expiry_date }}）
          </span>
        </p>
        <p><strong>贮存条件：</strong>{{ show(form.storage_condition) }}</p>
        <p><strong>生产者：</strong>{{ show(form.manufacturer) }}</p>
        <p><strong>地　址：</strong>{{ show(form.address) }}</p>
        <p><strong>食品生产许可证编号：</strong>{{ show(form.license_no) }}</p>
        <p><strong>产品标准号：</strong>{{ show(form.standard_no) }}</p>
      </section>

      <footer class="barcode" aria-hidden="true">
        <div class="bars"></div>
        <div class="barcode-num">6 901234 567890</div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.preview-wrap {
  padding: 20px;
  display: flex;
  justify-content: center;
  max-height: calc(100vh - 160px);
  overflow-y: auto;
}

.label-card {
  width: 100%;
  max-width: 420px;
  background: #fff;
  border: 2px solid #333;
  border-radius: 4px;
  font-size: 13px;
  color: #212121;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}

.label-head {
  text-align: center;
  padding: 18px 16px 14px;
  border-bottom: 2px solid #333;
  background: linear-gradient(180deg, #faf8f3 0%, #fff 100%);
}

.brand-name {
  font-size: 12px;
  letter-spacing: 4px;
  color: #8d6e63;
  margin-bottom: 4px;
}

.product-name {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 2px;
}

.net-content {
  margin-top: 6px;
  font-size: 12px;
  color: #555;
}

.block {
  padding: 10px 16px;
  border-bottom: 1px solid #999;
}

.block p {
  margin: 4px 0;
}

.allergen {
  color: #b71c1c;
}

.nutrition-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}
.nutrition-title strong {
  font-size: 15px;
}
.nutrition-title span {
  font-size: 10px;
  color: #777;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  border: 1px solid #333;
  padding: 4px 8px;
  text-align: left;
}

th {
  background: #f0ede6;
  font-weight: 700;
}

td:last-child,
th:last-child {
  text-align: center;
  width: 64px;
}

.empty-cell {
  text-align: center;
  color: #999;
}

.meta p {
  font-size: 12px;
}

.expiry {
  color: #555;
}

.barcode {
  padding: 12px 16px 14px;
  text-align: center;
}

.bars {
  height: 40px;
  margin: 0 auto 4px;
  width: 200px;
  background: repeating-linear-gradient(
    90deg,
    #212121 0 2px, transparent 2px 5px,
    #212121 5px 6px, transparent 6px 10px,
    #212121 10px 13px, transparent 13px 16px,
    #212121 16px 17px, transparent 17px 21px
  );
}

.barcode-num {
  font-size: 11px;
  letter-spacing: 3px;
  color: #333;
}
</style>
