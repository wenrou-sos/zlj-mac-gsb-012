<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { api } from '../../api'

const props = defineProps({
  package: { type: Object, required: true },
  catalog: { type: Object, required: true },
  labels: { type: Array, default: () => [] },
})
const emit = defineEmits(['published', 'saved', 'cancel', 'toast'])

const SEVERITY_OPTIONS = [
  { value: 'error', label: '错误' },
  { value: 'warning', label: '警告' },
]

const meta = reactive({
  name: '',
  description: '',
  effectiveDate: '',
})

const unitsText = ref('')
const shelfUnitsText = ref('')
const nrv = reactive({})
const factors = reactive({})
const allergenText = ref('')
const rulesState = reactive({}) // code -> { enabled, severity, params: {key: raw} }

const trialLabelId = ref('')
const trialResult = ref(null)
const trialLoading = ref(false)
const saving = ref(false)
const publishing = ref(false)
const dirty = ref(false)

const groups = computed(() =>
  props.catalog.categories.map((cat) => ({
    ...cat,
    rules: props.catalog.rules.filter((r) => r.category === cat.key),
  })),
)

watch(
  () => props.package,
  (pkg) => {
    if (!pkg) return
    meta.name = pkg.name
    meta.description = pkg.description || ''
    meta.effectiveDate = pkg.effective_date || ''
    const gp = pkg.config?.params || {}
    unitsText.value = (gp.net_content_units || []).join('、')
    shelfUnitsText.value = (gp.shelf_life_units || []).join('、')
    Object.assign(nrv, gp.nrv || {})
    Object.assign(factors, gp.energy_factors || {})
    allergenText.value = Object.entries(gp.allergen_keywords || {})
      .map(([cat, kws]) => `${cat}: ${(kws || []).join(',')}`)
      .join('\n')

    Object.keys(rulesState).forEach((k) => delete rulesState[k])
    const defaults = props.catalog.default_config.rules
    for (const def of props.catalog.rules) {
      const cur = pkg.config?.rules?.[def.code] || defaults[def.code]
      const params = {}
      for (const spec of def.params || []) {
        params[spec.key] = cur.params?.[spec.key] ?? def.defaults?.[spec.key] ?? ''
      }
      rulesState[def.code] = {
        enabled: cur.enabled ?? true,
        severity: cur.severity || def.default_severity,
        params,
      }
    }
    dirty.value = false
    trialResult.value = null
  },
  { immediate: true },
)

function markDirty() {
  dirty.value = true
}

function parseList(text) {
  return text.split(/[、,，\s]+/).map((s) => s.trim()).filter(Boolean)
}

function parseAllergens(text) {
  const map = {}
  for (const line of text.split('\n')) {
    const t = line.trim()
    if (!t) continue
    const idx = t.indexOf(':')
    const idx2 = t.indexOf('：')
    const cut = idx === -1 ? idx2 : idx2 === -1 ? idx : Math.min(idx, idx2)
    if (cut === -1) return { error: `行缺少“:”分隔：${t}` }
    const cat = t.slice(0, cut).trim()
    const kws = t.slice(cut + 1).split(/[,，、]/).map((s) => s.trim()).filter(Boolean)
    if (!cat || !kws.length) return { error: `行格式有误：${t}` }
    map[cat] = kws
  }
  return { value: map }
}

function buildConfig() {
  const allergenParsed = parseAllergens(allergenText.value)
  if (allergenParsed.error) return { error: '过敏原词表：' + allergenParsed.error }
  const rules = {}
  for (const def of props.catalog.rules) {
    const st = rulesState[def.code]
    const params = {}
    for (const spec of def.params || []) {
      let v = st.params[spec.key]
      if (spec.type === 'number') {
        const n = Number(v)
        if (Number.isNaN(n)) return { error: `规则「${def.name}」的参数 ${spec.label} 必须是数字` }
        if (spec.min !== null && spec.min !== undefined && n < spec.min)
          return { error: `规则「${def.name}」的参数 ${spec.label} 不能小于 ${spec.min}` }
        v = n
      }
      params[spec.key] = v
    }
    rules[def.code] = { enabled: st.enabled, severity: st.severity, params }
  }
  return {
    value: {
      params: {
        net_content_units: parseList(unitsText.value),
        shelf_life_units: parseList(shelfUnitsText.value),
        nrv: { ...nrv },
        energy_factors: { ...factors },
        allergen_keywords: allergenParsed.value,
      },
      rules,
    },
  }
}

async function save() {
  const built = buildConfig()
  if (built.error) return emit('toast', built.error)
  saving.value = true
  try {
    await api.updatePackage(props.package.id, {
      name: meta.name,
      description: meta.description,
      effective_date: meta.effectiveDate,
      config: built.value,
    })
    dirty.value = false
    emit('saved')
    emit('toast', '草稿已保存')
  } catch (e) {
    emit('toast', '保存失败：' + e.message)
  } finally {
    saving.value = false
  }
}

async function publish() {
  const built = buildConfig()
  if (built.error) return emit('toast', built.error)
  if (!meta.effectiveDate) return emit('toast', '请选择生效日期')
  if (!confirm(`确认发布 v${props.package.version}？\n发布后配置将固化为不可变快照，生效日期 ${meta.effectiveDate}。`))
    return
  publishing.value = true
  try {
    await api.updatePackage(props.package.id, {
      name: meta.name,
      description: meta.description,
      effective_date: meta.effectiveDate,
      config: built.value,
    })
    await api.publishPackage(props.package.id, meta.effectiveDate)
    emit('published')
    emit('toast', `v${props.package.version} 已发布`)
  } catch (e) {
    emit('toast', '发布失败：' + e.message)
  } finally {
    publishing.value = false
  }
}

async function runTrial() {
  if (!trialLabelId.value) return
  const label = props.labels.find((l) => l.id === Number(trialLabelId.value))
  if (!label) return
  const built = buildConfig()
  if (built.error) return emit('toast', built.error)
  trialLoading.value = true
  try {
    // 先把当前编辑内容存到草稿，再以草稿版本试跑（不落库、不留痕）
    await api.updatePackage(props.package.id, { config: built.value })
    trialResult.value = await api.validate(label, props.package.id)
    dirty.value = false
  } catch (e) {
    emit('toast', '试用失败：' + e.message)
  } finally {
    trialLoading.value = false
  }
}

const nrvFields = computed(() => props.catalog.global_params_schema.find((s) => s.group === 'nrv')?.fields || [])
const factorFields = computed(() => props.catalog.global_params_schema.find((s) => s.group === 'energy_factors')?.fields || [])
</script>

<template>
  <div class="editor">
    <div class="head">
      <div>
        <h2>编辑草稿 v{{ package.version }}</h2>
        <span v-if="dirty" class="dirty">● 有未保存修改</span>
      </div>
      <div class="head-ops">
        <button class="btn ghost" @click="emit('cancel')">返回列表</button>
        <button class="btn ghost" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存草稿' }}</button>
        <button class="btn primary" :disabled="publishing" @click="publish">
          {{ publishing ? '发布中…' : '发布此版本' }}
        </button>
      </div>
    </div>

    <section class="block">
      <h3>版本信息</h3>
      <div class="grid">
        <label class="span2">
          规则包名称
          <input v-model="meta.name" @input="markDirty" />
        </label>
        <label>
          生效日期
          <input v-model="meta.effectiveDate" type="date" @change="markDirty" />
        </label>
        <label>
          状态
          <input value="草稿（可编辑）" disabled />
        </label>
        <label class="span2">
          说明
          <input v-model="meta.description" @input="markDirty" placeholder="本版本相对上一版的变更说明" />
        </label>
      </div>
    </section>

    <section class="block">
      <h3>全局参数</h3>
      <div class="grid">
        <label>
          净含量允许单位（顿号/逗号分隔）
          <input v-model="unitsText" @input="markDirty" />
        </label>
        <label>
          保质期允许单位
          <input v-model="shelfUnitsText" @input="markDirty" />
        </label>
      </div>

      <div class="sub">
        <p class="sub-title">营养素参考值 NRV</p>
        <div class="numgrid">
          <label v-for="f in nrvFields" :key="f.key">
            {{ f.label }}
            <input v-model.number="nrv[f.key]" type="number" min="0" step="any" @input="markDirty" />
          </label>
        </div>
      </div>

      <div class="sub">
        <p class="sub-title">能量折算系数 (kJ/g)</p>
        <div class="numgrid">
          <label v-for="f in factorFields" :key="f.key">
            {{ f.label }}
            <input v-model.number="factors[f.key]" type="number" min="0" step="any" @input="markDirty" />
          </label>
        </div>
      </div>

      <div class="sub">
        <p class="sub-title">
          致敏物质关键词表
          <span class="tip">每行一类，格式「类别: 关键词1,关键词2」</span>
        </p>
        <textarea v-model="allergenText" rows="6" @input="markDirty"></textarea>
      </div>
    </section>

    <section class="block" v-for="group in groups" :key="group.key">
      <h3>{{ group.icon }} {{ group.label }}</h3>
      <table class="rule-tbl">
        <thead>
          <tr>
            <th class="c-enable">启用</th>
            <th>规则</th>
            <th class="c-sev">不通过级别</th>
            <th class="c-params">参数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="def in group.rules" :key="def.code" :class="{ off: !rulesState[def.code]?.enabled }">
            <td class="c-enable">
              <input type="checkbox" v-model="rulesState[def.code].enabled" @change="markDirty" />
            </td>
            <td>
              <div class="rule-name">{{ def.name }}</div>
              <div class="rule-desc">{{ def.description }}</div>
              <code class="rule-code">{{ def.code }}</code>
            </td>
            <td class="c-sev">
              <select v-model="rulesState[def.code].severity" @change="markDirty" :disabled="!rulesState[def.code]?.enabled">
                <option v-for="opt in SEVERITY_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
              </select>
            </td>
            <td class="c-params">
              <div v-for="spec in def.params || []" :key="spec.key" class="param">
                <label>
                  {{ spec.label }}
                  <input
                    v-model="rulesState[def.code].params[spec.key]"
                    :type="spec.type === 'number' ? 'number' : 'text'"
                    :step="spec.step || 'any'"
                    :min="spec.min"
                    @input="markDirty"
                    :disabled="!rulesState[def.code]?.enabled"
                  />
                </label>
              </div>
              <span v-if="!(def.params || []).length" class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="block trial">
      <h3>草稿试用（不落库、不留痕）</h3>
      <p class="hint">选择一条已保存标签，用当前编辑中的配置实时试跑，验证参数调整效果后再发布。</p>
      <div class="trial-bar">
        <select v-model="trialLabelId">
          <option value="" disabled>选择标签…</option>
          <option v-for="l in labels" :key="l.id" :value="l.id">
            {{ l.product_name || '(未命名)' }}（最近：v{{ l.latest_package_version ?? '?' }}
            {{ l.latest_status || '' }}）
          </option>
        </select>
        <button class="btn ghost" :disabled="trialLoading || !trialLabelId" @click="runTrial">
          {{ trialLoading ? '试跑中…' : '用当前配置试跑' }}
        </button>
      </div>
      <div v-if="trialResult" class="trial-result">
        <div :class="['verdict', trialResult.status]">
          试跑结论：{{ { pass: '通过', warning: '有警告', fail: '未通过' }[trialResult.status] }}
          （✕ {{ trialResult.summary.errors }}　⚠ {{ trialResult.summary.warnings }}　✓ {{ trialResult.summary.passed }}）
        </div>
        <ul class="trial-items">
          <li v-for="r in trialResult.results.filter((x) => x.status !== 'pass')" :key="r.code" :class="r.status">
            <b>{{ r.status === 'error' ? '✕' : '⚠' }}</b> {{ r.message }}
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}
.head h2 {
  margin: 0;
  font-size: 17px;
  display: inline;
}
.head-ops {
  display: flex;
  gap: 8px;
}
.dirty {
  margin-left: 10px;
  color: var(--warning);
  font-size: 12px;
}
.block {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}
.block h3 {
  margin: 0 0 12px;
  font-size: 14px;
  color: var(--primary-dark);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.span2 {
  grid-column: span 2;
}
.sub {
  margin-top: 14px;
}
.sub-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
}
.tip {
  font-weight: normal;
  color: var(--text-muted);
  font-size: 12px;
  margin-left: 8px;
}
.numgrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px 12px;
}
.rule-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.rule-tbl th,
.rule-tbl td {
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
.rule-tbl th {
  color: var(--text-muted);
  font-weight: 600;
  font-size: 12px;
}
.c-enable {
  width: 44px;
  text-align: center;
}
.c-enable input {
  width: auto;
}
.c-sev {
  width: 100px;
}
.c-params {
  width: 240px;
}
tr.off {
  opacity: 0.55;
}
.rule-name {
  font-weight: 600;
}
.rule-desc {
  color: var(--text-muted);
  font-size: 12px;
}
.rule-code {
  font-size: 11px;
  color: #90a4ae;
  background: #f4f6f4;
  padding: 0 5px;
  border-radius: 4px;
}
.param {
  margin-bottom: 6px;
}
.param label {
  font-size: 11px;
  color: var(--text-muted);
}
.muted {
  color: var(--text-muted);
}
.hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-muted);
}
.trial-bar {
  display: flex;
  gap: 10px;
}
.trial-bar select {
  max-width: 360px;
}
.trial-result {
  margin-top: 12px;
}
.verdict {
  padding: 8px 12px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
}
.verdict.pass {
  background: var(--pass-bg);
  color: var(--pass);
}
.verdict.warning {
  background: var(--warning-bg);
  color: var(--warning);
}
.verdict.fail {
  background: var(--error-bg);
  color: var(--error);
}
.trial-items {
  margin: 8px 0 0;
  padding-left: 4px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.trial-items li.error {
  color: var(--error);
}
.trial-items li.warning {
  color: var(--warning);
}
</style>
