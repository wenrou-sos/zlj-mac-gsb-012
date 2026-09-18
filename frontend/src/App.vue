<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from './api'
import LabelForm from './components/LabelForm.vue'
import ValidationPanel from './components/ValidationPanel.vue'
import LabelPreview from './components/LabelPreview.vue'
import RuleCenter from './components/RuleCenter.vue'

const NUMERIC_FIELDS = [
  'net_content_value', 'energy_kj', 'protein_g', 'fat_g',
  'carbohydrate_g', 'sodium_mg', 'shelf_life_value',
]

const emptyForm = () => ({
  product_name: '',
  brand: '',
  net_content_value: null,
  net_content_unit: 'g',
  standard_no: '',
  ingredients_text: '',
  allergen_statement: '',
  energy_kj: null,
  protein_g: null,
  fat_g: null,
  carbohydrate_g: null,
  sodium_mg: null,
  shelf_life_value: null,
  shelf_life_unit: '天',
  storage_condition: '',
  production_date: '',
  manufacturer: '',
  address: '',
  license_no: '',
})

const form = reactive(emptyForm())
const labels = ref([])
const currentId = ref(null)
const validation = ref(null)
const validating = ref(false)
const saving = ref(false)
const activeTab = ref('validate')
const view = ref('labels')
const toast = ref('')

let toastTimer = null
function showToast(message) {
  toast.value = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toast.value = ''), 2600)
}

function splitIngredients(text) {
  return (text || '')
    .split(/[、,，;；\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function buildPayload() {
  const { ingredients_text, ...rest } = form
  const payload = { ...rest, ingredients: splitIngredients(ingredients_text) }
  for (const key of NUMERIC_FIELDS) {
    const v = payload[key]
    if (v === '' || v === undefined || v === null || Number.isNaN(v)) {
      payload[key] = null
    }
  }
  if (payload.shelf_life_value !== null) {
    payload.shelf_life_value = Math.round(Number(payload.shelf_life_value))
  }
  return payload
}

let debounceTimer = null
watch(form, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runValidate, 400)
})

async function runValidate() {
  validating.value = true
  try {
    validation.value = await api.validate(buildPayload())
  } catch (e) {
    showToast('校验失败：' + e.message)
  } finally {
    validating.value = false
  }
}

async function refreshList() {
  labels.value = await api.list()
}

function loadLabel(item) {
  const { ingredients, ...rest } = item
  Object.assign(form, emptyForm(), rest, {
    ingredients_text: (ingredients || []).join('、'),
  })
  currentId.value = item.id
}

function onSelectLabel(event) {
  const id = Number(event.target.value)
  const item = labels.value.find((l) => l.id === id)
  if (item) loadLabel(item)
}

function newLabel() {
  Object.assign(form, emptyForm())
  currentId.value = null
  validation.value = null
}

async function save() {
  saving.value = true
  try {
    const payload = buildPayload()
    const saved = currentId.value
      ? await api.update(currentId.value, payload)
      : await api.create(payload)
    currentId.value = saved.id
    await refreshList()
    showToast('已保存')
  } catch (e) {
    showToast('保存失败：' + e.message)
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!currentId.value) return
  if (!confirm('确定删除当前标签吗？')) return
  try {
    await api.remove(currentId.value)
    newLabel()
    await refreshList()
    showToast('已删除')
  } catch (e) {
    showToast('删除失败：' + e.message)
  }
}

function fillAllergenStatement() {
  const detected = validation.value?.detected_allergens || []
  if (!detected.length) return
  form.allergen_statement = `本品含有${detected.join('、')}及其制品。`
}

onMounted(async () => {
  try {
    await refreshList()
    if (labels.value.length) loadLabel(labels.value[0])
    await runValidate()
  } catch (e) {
    showToast('无法连接后端服务：' + e.message)
  }
})
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand">
        <span class="logo">🥫</span>
        <div>
          <h1>食品包装标签校验平台</h1>
          <p>字段 · 单位 · 营养成分 · 过敏原 自动合规检查</p>
        </div>
      </div>
      <div class="actions">
        <div class="view-switch">
          <button :class="['switch-btn', { active: view === 'labels' }]" @click="view = 'labels'">
            标签校验
          </button>
          <button :class="['switch-btn', { active: view === 'rules' }]" @click="view = 'rules'">
            规则中心
          </button>
        </div>
        <template v-if="view === 'labels'">
          <select class="saved-select" :value="currentId ?? ''" @change="onSelectLabel">
            <option value="" disabled>选择已保存的标签…</option>
            <option v-for="item in labels" :key="item.id" :value="item.id">
              {{ item.product_name || '(未命名)' }}{{ item.brand ? ' · ' + item.brand : ''
              }}{{ item.rule_package_version ? ' · ' + item.rule_package_version : ''
              }}{{ item.last_validation_status === 'fail' ? ' ✕' : item.last_validation_status === 'warning' ? ' ⚠' : '' }}
            </option>
          </select>
          <button class="btn ghost" @click="newLabel">＋ 新建</button>
          <button class="btn primary" :disabled="saving" @click="save">
            {{ saving ? '保存中…' : currentId ? '保存修改' : '保存标签' }}
          </button>
          <button v-if="currentId" class="btn danger" @click="remove">删除</button>
        </template>
      </div>
    </header>

    <RuleCenter v-if="view === 'rules'" @toast="showToast" @labels-changed="refreshList" />

    <main v-else class="content">
      <section class="panel form-panel">
        <LabelForm
          :form="form"
          :detected-allergens="validation?.detected_allergens || []"
          @fill-allergen="fillAllergenStatement"
        />
      </section>

      <section class="panel result-panel">
        <div class="tabs">
          <button
            :class="['tab', { active: activeTab === 'validate' }]"
            @click="activeTab = 'validate'"
          >
            校验结果
            <span v-if="validation" :class="['badge', validation.status]">
              {{ validation.summary.errors + validation.summary.warnings || '✓' }}
            </span>
          </button>
          <button
            :class="['tab', { active: activeTab === 'preview' }]"
            @click="activeTab = 'preview'"
          >
            标签预览
          </button>
        </div>
        <ValidationPanel
          v-show="activeTab === 'validate'"
          :validation="validation"
          :validating="validating"
        />
        <LabelPreview
          v-show="activeTab === 'preview'"
          :form="form"
          :validation="validation"
        />
      </section>
    </main>

    <transition name="fade">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.layout {
  max-width: 1440px;
  margin: 0 auto;
  padding: 0 20px 40px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 18px 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  font-size: 34px;
}

.brand h1 {
  margin: 0;
  font-size: 20px;
  color: var(--primary-dark);
}

.brand p {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.saved-select {
  width: 220px;
}

.view-switch {
  display: flex;
  background: #e8ece8;
  border-radius: 10px;
  padding: 3px;
  gap: 2px;
}

.switch-btn {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border-radius: 8px;
}
.switch-btn.active {
  background: #fff;
  color: var(--primary-dark);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

.btn.primary {
  background: var(--primary);
  color: #fff;
}
.btn.primary:hover:not(:disabled) {
  background: var(--primary-dark);
}
.btn.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.btn.ghost {
  background: #fff;
  border: 1px solid var(--border);
}
.btn.ghost:hover {
  border-color: var(--primary);
  color: var(--primary);
}
.btn.danger {
  background: #fff;
  border: 1px solid #ef9a9a;
  color: var(--error);
}
.btn.danger:hover {
  background: var(--error-bg);
}

.content {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

@media (max-width: 960px) {
  .content {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 2px 10px rgba(38, 50, 56, 0.05);
}

.form-panel {
  padding: 20px;
}

.result-panel {
  position: sticky;
  top: 16px;
  overflow: hidden;
}

.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  background: #fafbfa;
}

.tab {
  flex: 1;
  padding: 12px;
  background: none;
  border-radius: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-muted);
  border-bottom: 2px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.tab.active {
  color: var(--primary-dark);
  border-bottom-color: var(--primary);
  background: #fff;
}

.badge {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.badge.fail { background: var(--error); }
.badge.warning { background: var(--warning); }
.badge.pass { background: var(--pass); }

.toast {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  background: #37474f;
  color: #fff;
  padding: 10px 22px;
  border-radius: 24px;
  font-size: 13px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  z-index: 99;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
