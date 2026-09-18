<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api'

const emit = defineEmits(['toast', 'labels-changed'])

const STATUS_TEXT = { pass: '通过', warning: '警告', fail: '未通过', error: '错误' }
const CHANGE_TEXT = { added: '新增检查项', removed: '不再触发', changed: '结果变化' }

const packages = ref([])
const categories = ref([])
const definitions = ref([])
const selectedId = ref(null)
const detail = ref(null)
const loading = ref(false)
const saving = ref(false)

// 草稿编辑状态：code -> { enabled, params }
const editRules = reactive({})
// JSON 参数的文本编辑缓冲：`${code}.${key}` -> string
const jsonTexts = reactive({})

const publishDate = ref(new Date().toISOString().slice(0, 10))
const showPublishBar = ref(false)

const jobs = ref([])
const activeJob = ref(null)
const onlyChanged = ref(true)
const expanded = reactive(new Set())
let pollTimer = null

const isDraft = computed(() => detail.value?.status === 'draft')

const defByCode = computed(() => Object.fromEntries(definitions.value.map((d) => [d.code, d])))

const groupedRules = computed(() => {
  if (!detail.value) return []
  const configs = Object.fromEntries((detail.value.rules || []).map((r) => [r.code, r]))
  return categories.value
    .map((cat) => ({
      ...cat,
      rules: definitions.value
        .filter((d) => d.category === cat.key)
        .map((d) => ({ def: d, config: configs[d.code] || { enabled: true, params: {} } })),
    }))
    .filter((g) => g.rules.length)
})

const visibleItems = computed(() => {
  if (!activeJob.value) return []
  const items = activeJob.value.items || []
  return onlyChanged.value ? items.filter((it) => it.diff.length || it.old_status !== it.new_status) : items
})

function toast(message) {
  emit('toast', message)
}

async function refreshPackages(keepSelection = true) {
  packages.value = await api.listPackages()
  if (!keepSelection || !packages.value.some((p) => p.id === selectedId.value)) {
    const active = packages.value.find((p) => p.is_active)
    selectedId.value = (active || packages.value[0])?.id ?? null
  }
}

async function refreshJobs() {
  jobs.value = await api.listRecheckJobs()
}

async function selectPackage(id) {
  selectedId.value = id
  showPublishBar.value = false
  loading.value = true
  try {
    detail.value = await api.getPackage(id)
    syncEditState()
  } catch (e) {
    toast('加载规则包失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function syncEditState() {
  Object.keys(editRules).forEach((k) => delete editRules[k])
  Object.keys(jsonTexts).forEach((k) => delete jsonTexts[k])
  if (!detail.value) return
  const configs = Object.fromEntries((detail.value.rules || []).map((r) => [r.code, r]))
  for (const def of definitions.value) {
    const cfg = configs[def.code] || { enabled: true, params: {} }
    const params = {}
    for (const p of def.params) {
      const value = cfg.params?.[p.key] ?? p.default
      params[p.key] = value
      if (p.type === 'json') {
        jsonTexts[`${def.code}.${p.key}`] = JSON.stringify(value, null, 2)
      }
    }
    editRules[def.code] = { enabled: cfg.enabled !== false, params }
  }
}

async function createDraft(baseId = null) {
  try {
    const created = await api.createPackage(baseId ? { base_id: baseId } : {})
    await refreshPackages(false)
    toast(`已创建草稿 ${created.version}，可编辑后发布`)
    await selectPackage(created.id)
  } catch (e) {
    toast('创建草稿失败：' + e.message)
  }
}

async function saveDraft({ silent = false } = {}) {
  saving.value = true
  try {
    const rules = []
    for (const def of definitions.value) {
      const state = editRules[def.code]
      const params = {}
      for (const p of def.params) {
        if (p.type === 'json') {
          const text = jsonTexts[`${def.code}.${p.key}`]
          try {
            params[p.key] = JSON.parse(text || 'null') ?? p.default
          } catch {
            toast(`规则「${def.name}」的参数「${p.label}」不是合法 JSON`)
            return false
          }
        } else {
          params[p.key] = state.params[p.key]
        }
      }
      rules.push({ code: def.code, enabled: state.enabled, params })
    }
    detail.value = await api.updatePackage(selectedId.value, {
      name: detail.value.name,
      version: detail.value.version,
      remark: detail.value.remark,
      rules,
    })
    await refreshPackages()
    syncEditState()
    if (!silent) toast('草稿已保存')
    return true
  } catch (e) {
    toast('保存失败：' + e.message)
    return false
  } finally {
    saving.value = false
  }
}

async function publish() {
  if (!publishDate.value) {
    toast('请选择生效日期')
    return
  }
  try {
    if (!(await saveDraft({ silent: true }))) return
    detail.value = await api.publishPackage(selectedId.value, publishDate.value)
    showPublishBar.value = false
    await refreshPackages()
    toast(`已发布 ${detail.value.version}，${publishDate.value} 起生效`)
  } catch (e) {
    toast('发布失败：' + e.message)
  }
}

async function removeDraft() {
  if (!confirm(`确定删除草稿 ${detail.value.version} 吗？`)) return
  try {
    await api.deletePackage(selectedId.value)
    selectedId.value = null
    detail.value = null
    await refreshPackages(false)
    if (selectedId.value) await selectPackage(selectedId.value)
    toast('草稿已删除')
  } catch (e) {
    toast('删除失败：' + e.message)
  }
}

async function startRecheck() {
  try {
    const { job_id } = await api.recheck(selectedId.value)
    toast('批量重检已开始')
    pollJob(job_id)
  } catch (e) {
    toast('启动重检失败：' + e.message)
  }
}

async function pollJob(jobId) {
  clearInterval(pollTimer)
  const tick = async () => {
    try {
      const jobData = await api.getRecheckJob(jobId)
      activeJob.value = jobData
      refreshJobs()
      if (jobData.status !== 'running') {
        clearInterval(pollTimer)
        pollTimer = null
        emit('labels-changed')
        toast(`重检完成：共 ${jobData.total} 个标签，${jobData.changed} 个结论有变化`)
      }
    } catch {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }
  await tick()
  if (activeJob.value?.status === 'running') {
    pollTimer = setInterval(tick, 700)
  }
}

async function openJob(jobId) {
  try {
    activeJob.value = await api.getRecheckJob(jobId)
    if (activeJob.value.status === 'running') pollJob(jobId)
  } catch (e) {
    toast('加载任务失败：' + e.message)
  }
}

function toggleExpand(itemId) {
  if (expanded.has(itemId)) expanded.delete(itemId)
  else expanded.add(itemId)
}

function paramSummary(def, config) {
  const parts = []
  for (const p of def.params) {
    const value = config.params?.[p.key] ?? p.default
    if (p.type === 'boolean') parts.push(`${p.label}：${value ? '是' : '否'}`)
    else if (p.type === 'json') parts.push(`${p.label}：自定义`)
    else parts.push(`${p.label}：${value}`)
  }
  return parts.join('；')
}

onMounted(async () => {
  try {
    const defs = await api.ruleDefinitions()
    definitions.value = defs.definitions
    categories.value = defs.categories
    await refreshPackages(false)
    await refreshJobs()
    if (selectedId.value) await selectPackage(selectedId.value)
  } catch (e) {
    toast('无法加载规则中心：' + e.message)
  }
})

onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<template>
  <main class="rule-center">
    <aside class="panel pkg-list">
      <div class="pkg-list-head">
        <h2>规则包版本</h2>
        <button class="btn-mini primary" @click="createDraft()">＋ 新建草稿</button>
      </div>

      <div
        v-for="pkg in packages"
        :key="pkg.id"
        :class="['pkg-card', { selected: pkg.id === selectedId }]"
        @click="selectPackage(pkg.id)"
      >
        <div class="pkg-card-top">
          <strong>{{ pkg.version }}</strong>
          <span :class="['status-badge', pkg.status]">
            {{ pkg.status === 'draft' ? '草稿' : '已发布' }}
          </span>
          <span v-if="pkg.is_active" class="status-badge active">当前生效</span>
        </div>
        <div class="pkg-card-name">{{ pkg.name }}</div>
        <div class="pkg-card-meta">
          <template v-if="pkg.status === 'published'">{{ pkg.effective_date }} 起生效</template>
          <template v-else>未发布</template>
        </div>
      </div>

      <div v-if="jobs.length" class="job-history">
        <h3>最近重检</h3>
        <div
          v-for="j in jobs.slice(0, 5)"
          :key="j.id"
          class="job-row"
          @click="openJob(j.id)"
        >
          <span>#{{ j.id }} · {{ j.package_version }}</span>
          <span :class="['job-status', j.status]">
            {{ j.status === 'running' ? `进行中 ${j.completed}/${j.total}` : j.status === 'done' ? `完成 · ${j.changed} 项变化` : '失败' }}
          </span>
        </div>
      </div>
    </aside>

    <section class="panel pkg-detail">
      <div v-if="!detail" class="empty-detail">请选择左侧规则包，或新建草稿</div>

      <template v-else>
        <header class="detail-head">
          <div class="detail-title">
            <template v-if="isDraft">
              <input v-model="detail.version" class="version-input" placeholder="版本号，如 v1.1" />
              <input v-model="detail.name" class="name-input" placeholder="规则包名称" />
            </template>
            <template v-else>
              <h2>{{ detail.name }} <span class="ver">{{ detail.version }}</span></h2>
              <p class="meta">
                {{ detail.effective_date }} 起生效
                <span v-if="detail.published_at"> · 发布于 {{ detail.published_at.slice(0, 16).replace('T', ' ') }}</span>
                <span v-if="detail.is_active" class="status-badge active">当前生效</span>
              </p>
            </template>
          </div>
          <div class="detail-actions">
            <template v-if="isDraft">
              <button class="btn ghost" :disabled="saving" @click="saveDraft">
                {{ saving ? '保存中…' : '保存草稿' }}
              </button>
              <button class="btn primary" @click="showPublishBar = !showPublishBar">发布</button>
              <button class="btn danger" @click="removeDraft">删除</button>
            </template>
            <template v-else>
              <button class="btn ghost" @click="createDraft(detail.id)">基于此版本新建草稿</button>
              <button class="btn primary" @click="startRecheck">批量重检历史标签</button>
            </template>
          </div>
        </header>

        <div v-if="isDraft && showPublishBar" class="publish-bar">
          <span>生效日期：</span>
          <input v-model="publishDate" type="date" />
          <button class="btn primary" @click="publish">确认发布</button>
          <span class="hint">发布后规则快照即冻结，执行中的校验不受影响；生效日期可设为未来。</span>
        </div>

        <div v-if="isDraft" class="remark-row">
          <input v-model="detail.remark" placeholder="版本说明（可选），如：调整能量折算容差至 ±20%" />
        </div>
        <p v-else-if="detail.remark" class="remark-text">版本说明：{{ detail.remark }}</p>

        <div v-for="group in groupedRules" :key="group.key" class="rule-group">
          <h3>{{ group.label }}</h3>
          <div v-for="{ def, config } in group.rules" :key="def.code" class="rule-row">
            <template v-if="isDraft">
              <label class="switch">
                <input v-model="editRules[def.code].enabled" type="checkbox" />
                <span class="slider"></span>
              </label>
              <div class="rule-body">
                <div class="rule-name">
                  {{ def.name }}
                  <code>{{ def.code }}</code>
                </div>
                <p class="rule-desc">{{ def.description }}</p>
                <div v-if="editRules[def.code].enabled && def.params.length" class="params">
                  <div v-for="p in def.params" :key="p.key" class="param">
                    <label v-if="p.type === 'boolean'" class="param-bool">
                      <input v-model="editRules[def.code].params[p.key]" type="checkbox" />
                      {{ p.label }}
                    </label>
                    <template v-else-if="p.type === 'number'">
                      <span class="param-label">{{ p.label }}</span>
                      <input
                        v-model.number="editRules[def.code].params[p.key]"
                        type="number"
                        :min="p.min"
                        :max="p.max"
                        :step="p.step || 1"
                      />
                    </template>
                    <template v-else-if="p.type === 'text'">
                      <span class="param-label">{{ p.label }}</span>
                      <input v-model="editRules[def.code].params[p.key]" type="text" />
                    </template>
                    <template v-else>
                      <span class="param-label">{{ p.label }}（JSON）</span>
                      <textarea
                        v-model="jsonTexts[`${def.code}.${p.key}`]"
                        rows="4"
                        class="json-editor"
                        spellcheck="false"
                      ></textarea>
                    </template>
                    <p v-if="p.help" class="param-help">{{ p.help }}</p>
                  </div>
                </div>
              </div>
            </template>

            <template v-else>
              <span :class="['rule-state', config.enabled !== false ? 'on' : 'off']">
                {{ config.enabled !== false ? '启用' : '停用' }}
              </span>
              <div class="rule-body">
                <div class="rule-name">{{ def.name }} <code>{{ def.code }}</code></div>
                <p class="rule-desc">{{ def.description }}</p>
                <p v-if="config.enabled !== false && def.params.length" class="rule-params">
                  {{ paramSummary(def, config) }}
                </p>
              </div>
            </template>
          </div>
        </div>

        <section v-if="activeJob" class="recheck-result">
          <div class="recheck-head">
            <h3>
              重检结果 · 任务 #{{ activeJob.id }}
              <span class="ver">{{ activeJob.package_version }}</span>
            </h3>
            <label class="filter">
              <input v-model="onlyChanged" type="checkbox" /> 仅看有差异
            </label>
          </div>

          <div class="progress">
            <div
              class="progress-bar"
              :style="{ width: (activeJob.total ? (activeJob.completed / activeJob.total) * 100 : 0) + '%' }"
            ></div>
          </div>
          <p class="progress-text">
            {{ activeJob.status === 'running' ? '重检中…' : activeJob.status === 'done' ? '已完成' : '失败' }}
            {{ activeJob.completed }}/{{ activeJob.total }}，{{ activeJob.changed }} 个标签结论有变化
          </p>

          <div v-for="item in visibleItems" :key="item.id" class="diff-item">
            <div class="diff-head" @click="toggleExpand(item.id)">
              <span class="diff-name">{{ item.label_name }}</span>
              <span class="diff-versions">
                {{ item.old_package_version || '（无历史记录）' }} → {{ activeJob.package_version }}
              </span>
              <span v-if="item.old_status" :class="['mini-badge', item.old_status]">
                {{ STATUS_TEXT[item.old_status] }}
              </span>
              <span class="arrow">→</span>
              <span :class="['mini-badge', item.new_status]">{{ STATUS_TEXT[item.new_status] }}</span>
              <span class="diff-count">{{ item.diff.length ? `${item.diff.length} 项差异` : '结论一致' }}</span>
              <span class="expand-icon">{{ expanded.has(item.id) ? '▲' : '▼' }}</span>
            </div>
            <ul v-if="expanded.has(item.id) && item.diff.length" class="diff-list">
              <li v-for="(d, i) in item.diff" :key="i">
                <span :class="['change-tag', d.change]">{{ CHANGE_TEXT[d.change] }}</span>
                <div class="change-body">
                  <div class="change-rule">{{ d.rule }} <code>{{ d.code }}</code></div>
                  <div class="change-msg">
                    <span v-if="d.old_message" :class="['msg', d.old_status]">旧：{{ d.old_message }}</span>
                    <span v-if="d.new_message" :class="['msg', d.new_status]">新：{{ d.new_message }}</span>
                  </div>
                </div>
              </li>
            </ul>
          </div>
          <p v-if="activeJob.status === 'done' && !visibleItems.length" class="all-same">
            所有标签在新规则下结论一致，无差异。
          </p>
        </section>
      </template>
    </section>
  </main>
</template>

<style scoped>
.rule-center {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
@media (max-width: 960px) {
  .rule-center {
    grid-template-columns: 1fr;
  }
}

.panel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 2px 10px rgba(38, 50, 56, 0.05);
}

/* ---- 左侧：规则包列表 ---- */
.pkg-list {
  padding: 16px;
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 60px);
  overflow-y: auto;
}

.pkg-list-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.pkg-list-head h2 {
  margin: 0;
  font-size: 15px;
  color: var(--primary-dark);
}

.btn-mini {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 8px;
}
.btn-mini.primary {
  background: var(--primary);
  color: #fff;
}

.pkg-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.pkg-card:hover {
  border-color: var(--primary);
}
.pkg-card.selected {
  border-color: var(--primary);
  background: var(--primary-light);
}

.pkg-card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pkg-card-name {
  font-size: 12px;
  color: var(--text);
  margin-top: 2px;
}
.pkg-card-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.status-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  background: #eceff1;
  color: var(--text-muted);
}
.status-badge.draft {
  background: var(--warning-bg);
  color: var(--warning);
}
.status-badge.published {
  background: #e3f2fd;
  color: #1565c0;
}
.status-badge.active {
  background: var(--pass-bg);
  color: var(--pass);
}

.job-history {
  margin-top: 16px;
  border-top: 1px dashed var(--border);
  padding-top: 10px;
}
.job-history h3 {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 8px;
}
.job-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 5px 6px;
  border-radius: 6px;
  cursor: pointer;
}
.job-row:hover {
  background: #f4f7f4;
}
.job-status.running {
  color: #1565c0;
}
.job-status.done {
  color: var(--pass);
}
.job-status.failed {
  color: var(--error);
}

/* ---- 右侧：详情 ---- */
.pkg-detail {
  padding: 20px;
  min-height: 300px;
}
.empty-detail {
  text-align: center;
  color: var(--text-muted);
  padding: 60px 0;
}

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--border);
  padding-bottom: 14px;
}
.detail-title h2 {
  margin: 0;
  font-size: 17px;
  color: var(--primary-dark);
}
.ver {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 600;
}
.meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}
.version-input {
  width: 110px;
  font-weight: 700;
}
.name-input {
  width: 320px;
  margin-left: 8px;
}
.detail-actions {
  display: flex;
  gap: 8px;
}

.btn {
  padding: 8px 16px;
  font-size: 13px;
  border-radius: 8px;
}
.btn.primary {
  background: var(--primary);
  color: #fff;
}
.btn.ghost {
  background: #fff;
  border: 1px solid var(--border);
}
.btn.danger {
  background: #fff;
  border: 1px solid #ef9a9a;
  color: var(--error);
}

.publish-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--primary-light);
  border-radius: 10px;
  padding: 10px 14px;
  margin-top: 12px;
  font-size: 13px;
  flex-wrap: wrap;
}
.publish-bar input[type='date'] {
  width: 160px;
}
.publish-bar .hint {
  font-size: 12px;
  color: var(--text-muted);
}

.remark-row {
  margin-top: 12px;
}
.remark-text {
  font-size: 12px;
  color: var(--text-muted);
  margin: 10px 0 0;
}

/* ---- 规则列表 ---- */
.rule-group h3 {
  font-size: 13px;
  margin: 18px 0 8px;
  color: var(--text);
}

.rule-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 8px;
  background: #fbfdfb;
}

.rule-body {
  flex: 1;
  min-width: 0;
}
.rule-name {
  font-size: 13px;
  font-weight: 600;
}
.rule-name code {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 400;
  margin-left: 6px;
}
.rule-desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-muted);
}
.rule-params {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--primary-dark);
}

.rule-state {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}
.rule-state.on {
  background: var(--pass-bg);
  color: var(--pass);
}
.rule-state.off {
  background: #eceff1;
  color: var(--text-muted);
}

/* 开关 */
.switch {
  position: relative;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider {
  position: absolute;
  inset: 0;
  background: #cfd8dc;
  border-radius: 20px;
  transition: 0.2s;
  cursor: pointer;
}
.slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  left: 2px;
  top: 2px;
  background: #fff;
  border-radius: 50%;
  transition: 0.2s;
}
.switch input:checked + .slider {
  background: var(--primary);
}
.switch input:checked + .slider::before {
  transform: translateX(16px);
}

/* 参数 */
.params {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #f4f7f4;
  border-radius: 8px;
  padding: 10px 12px;
}
.param {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.param-label {
  color: var(--text-muted);
  min-width: 130px;
}
.param input[type='number'] {
  width: 120px;
}
.param input[type='text'] {
  flex: 1;
  min-width: 200px;
}
.param-bool {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.param-bool input {
  width: auto;
}
.param-help {
  width: 100%;
  margin: 0;
  font-size: 11px;
  color: var(--text-muted);
}
.json-editor {
  width: 100%;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

/* ---- 重检结果 ---- */
.recheck-result {
  margin-top: 20px;
  border-top: 2px solid var(--border);
  padding-top: 14px;
}
.recheck-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.recheck-head h3 {
  margin: 0;
  font-size: 14px;
}
.filter {
  font-size: 12px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
}
.filter input {
  width: auto;
}

.progress {
  height: 6px;
  background: #eceff1;
  border-radius: 3px;
  margin-top: 10px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--primary);
  transition: width 0.3s ease;
}
.progress-text {
  font-size: 12px;
  color: var(--text-muted);
  margin: 6px 0 12px;
}

.diff-item {
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 8px;
  overflow: hidden;
}
.diff-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  flex-wrap: wrap;
}
.diff-head:hover {
  background: #f7faf7;
}
.diff-name {
  font-weight: 600;
}
.diff-versions {
  font-size: 11px;
  color: var(--text-muted);
}
.arrow {
  color: var(--text-muted);
}
.diff-count {
  font-size: 11px;
  color: var(--warning);
  margin-left: auto;
}
.expand-icon {
  font-size: 10px;
  color: var(--text-muted);
}

.mini-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  color: #fff;
}
.mini-badge.pass {
  background: var(--pass);
}
.mini-badge.warning {
  background: var(--warning);
}
.mini-badge.fail {
  background: var(--error);
}

.diff-list {
  list-style: none;
  margin: 0;
  padding: 8px 12px 12px;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.diff-list li {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  font-size: 12px;
}
.change-tag {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 10px;
  margin-top: 1px;
}
.change-tag.added {
  background: #e3f2fd;
  color: #1565c0;
}
.change-tag.removed {
  background: #eceff1;
  color: var(--text-muted);
}
.change-tag.changed {
  background: var(--warning-bg);
  color: var(--warning);
}
.change-rule {
  font-weight: 600;
}
.change-rule code {
  font-weight: 400;
  color: var(--text-muted);
  font-size: 11px;
  margin-left: 4px;
}
.change-msg {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 2px;
}
.msg.error {
  color: var(--error);
}
.msg.warning {
  color: var(--warning);
}
.msg.pass {
  color: var(--pass);
}

.all-same {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px 0;
}
</style>
