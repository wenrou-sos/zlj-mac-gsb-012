<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import PackageList from './rules/PackageList.vue'
import PackageEditor from './rules/PackageEditor.vue'
import RecheckList from './rules/RecheckList.vue'
import RecheckDetail from './rules/RecheckDetail.vue'

const emit = defineEmits(['toast'])

const tab = ref('packages') // packages | rechecks
const packages = ref([])
const batches = ref([])
const catalog = ref(null)
const labels = ref([])
const effective = ref(null)
const loading = ref(false)

const editing = ref(null)
const showDraftModal = ref(false)
const showRecheckModal = ref(false)
const recheckTarget = ref(null)
const viewingBatchId = ref(null)

const draftForm = ref({ based_on: '', name: '', effective_date: '' })
const recheckForm = ref({ baseline: '', label_scope: 'all' })

const published = computed(() => packages.value.filter((p) => p.status === 'published'))
const viewingBatch = computed(() => batches.value.find((b) => b.id === viewingBatchId.value) || null)

async function refresh() {
  loading.value = true
  try {
    const [pkgs, cats, ls] = await Promise.all([
      api.packages(),
      api.ruleCatalog(),
      api.list(),
    ])
    packages.value = pkgs
    catalog.value = cats
    labels.value = ls
    try {
      effective.value = await api.effectivePackage()
    } catch {
      effective.value = null
    }
    batches.value = await api.rechecks()
    const live = batches.value.filter((b) => b.status === 'pending' || b.status === 'running')
    if (live.length) setTimeout(refresh, 1500)
  } catch (e) {
    emit('toast', '加载规则中心失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function openDraftModal() {
  draftForm.value = {
    based_on: effective.value?.id || published.value[0]?.id || '',
    name: '',
    effective_date: new Date().toISOString().slice(0, 10),
  }
  showDraftModal.value = true
}

async function submitDraft() {
  try {
    const pkg = await api.createDraft({
      based_on_package_id: draftForm.value.based_on ? Number(draftForm.value.based_on) : null,
      name: draftForm.value.name || null,
      effective_date: draftForm.value.effective_date,
    })
    showDraftModal.value = false
    await refresh()
    editing.value = packages.value.find((p) => p.id === pkg.id)
  } catch (e) {
    emit('toast', '创建草稿失败：' + e.message)
  }
}

async function saveEditor() {
  await refresh()
  editing.value = packages.value.find((p) => p.id === editing.value.id)
}

async function publishedEditor() {
  editing.value = null
  await refresh()
  tab.value = 'packages'
}

async function removePackage(pkg) {
  if (!confirm(`确定删除草稿 v${pkg.version}？`)) return
  try {
    await api.deletePackage(pkg.id)
    await refresh()
    emit('toast', '草稿已删除')
  } catch (e) {
    emit('toast', '删除失败：' + e.message)
  }
}

async function archivePackage(pkg) {
  if (!confirm(`归档 v${pkg.version} 后将不能再用于新校验（历史留痕不受影响），确认？`)) return
  try {
    await api.archivePackage(pkg.id)
    await refresh()
  } catch (e) {
    emit('toast', '归档失败：' + e.message)
  }
}

function openRecheckModal(pkg) {
  recheckTarget.value = pkg
  recheckForm.value = { baseline: '', label_scope: 'all' }
  showRecheckModal.value = true
}

async function submitRecheck() {
  try {
    const labelIds =
      recheckForm.value.label_scope === 'all'
        ? null
        : labels.value.map((l) => l.id) // 目前仅提供“全部”，预留选择范围
    const batch = await api.createRecheck({
      package_id: recheckTarget.value.id,
      baseline_package_id: recheckForm.value.baseline
        ? Number(recheckForm.value.baseline)
        : null,
      label_ids: labelIds,
    })
    showRecheckModal.value = false
    tab.value = 'rechecks'
    viewingBatchId.value = batch.id
    setTimeout(refresh, 600)
  } catch (e) {
    emit('toast', '创建重检任务失败：' + e.message)
  }
}

async function openBatch(batch) {
  viewingBatchId.value = batch.id
  try {
    const detail = await api.recheck(batch.id)
    const idx = batches.value.findIndex((b) => b.id === detail.id)
    if (idx >= 0) batches.value[idx] = detail
    else batches.value.unshift(detail)
  } catch (e) {
    emit('toast', e.message)
  }
}

onMounted(refresh)
</script>

<template>
  <div class="rule-center">
    <div v-if="editing && catalog" class="editor-wrap">
      <PackageEditor
        :package="editing"
        :catalog="catalog"
        :labels="labels"
        @saved="saveEditor"
        @published="publishedEditor"
        @cancel="editing = null"
        @toast="(m) => emit('toast', m)"
      />
    </div>

    <template v-else>
      <div class="tabs">
        <button :class="['tab', { active: tab === 'packages' }]" @click="tab = 'packages'">
          规则包版本
        </button>
        <button :class="['tab', { active: tab === 'rechecks' }]" @click="tab = 'rechecks'">
          批量重检与差异
        </button>
        <span v-if="effective" class="eff-line">
          当前生效：v{{ effective.version }} · {{ effective.effective_date }} 起生效
        </span>
      </div>

      <PackageList
        v-if="tab === 'packages'"
        :packages="packages"
        :effective-id="effective?.id"
        :loading="loading"
        @new-draft="openDraftModal"
        @edit="(p) => (editing = p)"
        @recheck="openRecheckModal"
        @archive="archivePackage"
        @delete="removePackage"
      />

      <template v-if="tab === 'rechecks'">
        <RecheckDetail
          v-if="viewingBatch"
          :batch="viewingBatch"
          @back="viewingBatchId = null"
        />
        <RecheckList
          v-else
          :batches="batches"
          :loading="loading"
          @open="openBatch"
          @refresh="refresh"
        />
      </template>
    </template>

    <!-- 新建草稿弹窗 -->
    <div v-if="showDraftModal" class="modal-mask" @click.self="showDraftModal = false">
      <div class="modal">
        <h3>新建规则草稿</h3>
        <label>
          基于已发布版本
          <select v-model="draftForm.based_on">
            <option value="">空白草稿（使用内置默认目录配置）</option>
            <option v-for="p in published" :key="p.id" :value="p.id">
              v{{ p.version }} {{ p.name }}（{{ p.effective_date }} 生效）
            </option>
          </select>
        </label>
        <label>
          生效日期
          <input v-model="draftForm.effective_date" type="date" />
        </label>
        <label>
          版本说明（可选）
          <input v-model="draftForm.name" placeholder="如：2026 钠阈值收紧" />
        </label>
        <p class="tip">草稿保存为同系列下一版本（v{{ Math.max(0, ...packages.map((p) => p.version)) + 1 }}），
          发布前不影响任何线上校验；同一系列同时只允许一个草稿。</p>
        <div class="modal-ops">
          <button class="btn ghost" @click="showDraftModal = false">取消</button>
          <button class="btn primary" @click="submitDraft">创建并编辑</button>
        </div>
      </div>
    </div>

    <!-- 发起重检弹窗 -->
    <div v-if="showRecheckModal" class="modal-mask" @click.self="showRecheckModal = false">
      <div class="modal">
        <h3>用 v{{ recheckTarget?.version }} 重检历史标签</h3>
        <label>
          基准版本（用于差异对比）
          <select v-model="recheckForm.baseline">
            <option value="">自动：取每条标签最近一次校验所用版本（推荐）</option>
            <option
              v-for="p in packages.filter((x) => x.status === 'published' || x.status === 'archived')"
              :key="p.id"
              :value="p.id"
            >
              v{{ p.version }} {{ p.name }}
            </option>
          </select>
        </label>
        <label>
          重检范围
          <select v-model="recheckForm.label_scope">
            <option value="all">全部历史标签（{{ labels.length }} 条）</option>
          </select>
        </label>
        <p class="tip">重检在后台执行，每个标签都会生成 trigger=recheck 的新留痕，原始留痕保留；差异按规则 code 逐条对比。</p>
        <div class="modal-ops">
          <button class="btn ghost" @click="showRecheckModal = false">取消</button>
          <button class="btn primary" @click="submitRecheck">开始重检</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rule-center {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 20px 48px;
}
.editor-wrap {
  margin-top: 14px;
}
.tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 18px;
}
.tab {
  padding: 12px 18px;
  background: none;
  border-radius: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-muted);
  border-bottom: 2px solid transparent;
}
.tab.active {
  color: var(--primary-dark);
  border-bottom-color: var(--primary);
}
.eff-line {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-muted);
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(38, 50, 56, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: 460px;
  background: #fff;
  border-radius: 14px;
  padding: 22px 24px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.2);
}
.modal h3 {
  margin: 0 0 16px;
  font-size: 16px;
}
.modal label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 12px;
}
.tip {
  font-size: 12px;
  color: var(--text-muted);
  margin: 4px 0 16px;
}
.modal-ops {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
