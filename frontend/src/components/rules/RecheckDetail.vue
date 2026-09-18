<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  batch: { type: Object, required: true },
})
defineEmits(['back'])

const STATUS_TEXT = { pass: '通过', warning: '警告', fail: '未通过' }
const CHANGE_TEXT = { added: '新增检查项', removed: '检查项停用/消失', status: '级别变化', message: '说明变化' }

const filter = ref('changed') // changed / all
const expanded = ref(null)

const items = computed(() => {
  const list = props.batch.items || []
  return filter.value === 'changed' ? list.filter((i) => i.changed) : list
})

function flowText(flow) {
  if (flow === null || flow === undefined) return ''
  if (flow > 0) return '（变差）'
  if (flow < 0) return '（改善）'
  return ''
}
</script>

<template>
  <div>
    <div class="toolbar">
      <button class="btn ghost" @click="$emit('back')">← 返回任务列表</button>
      <h2>重检任务 #{{ batch.id }} · v{{ batch.package_version }} 新旧差异</h2>
    </div>

    <div class="summary">
      <span>共 <b>{{ batch.total }}</b> 条标签</span>
      <span>已处理 <b>{{ batch.processed }}</b></span>
      <span class="changed">结果有差异 <b>{{ batch.changed_count }}</b></span>
      <span :class="['st', batch.status]">{{ { pending: '排队中', running: '重检中', completed: '已完成', failed: '失败' }[batch.status] }}</span>
    </div>

    <div class="filters">
      <label><input type="radio" value="changed" v-model="filter" /> 仅看有差异（{{ batch.changed_count }}）</label>
      <label><input type="radio" value="all" v-model="filter" /> 全部标签（{{ batch.total }}）</label>
    </div>

    <div class="items">
      <div v-for="item in items" :key="item.id" class="card" :class="{ changed: item.changed }">
        <div class="card-head" @click="expanded = expanded === item.id ? null : item.id">
          <span class="name">{{ item.label_name }}</span>
          <span class="status-flow">
            <span :class="['pill', item.old_status]">{{ item.old_status ? STATUS_TEXT[item.old_status] : '无历史' }}</span>
            <span class="arrow">→</span>
            <span :class="['pill', item.new_status]">{{ STATUS_TEXT[item.new_status] }}</span>
            <em v-if="item.changed">{{ flowText(item.diff?.status_flow) }}</em>
          </span>
          <span class="toggle">{{ expanded === item.id ? '收起 ▲' : `展开 ${item.diff?.change_count || 0} 处差异 ▼` }}</span>
        </div>

        <div v-if="expanded === item.id" class="diff-body">
          <p v-if="!item.diff?.changes?.length" class="muted">逐项检查结果完全一致。</p>
          <table v-else class="diff-tbl">
            <thead>
              <tr>
                <th>规则</th>
                <th>变化</th>
                <th>旧版本结果</th>
                <th>新版本结果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="ch in item.diff.changes" :key="ch.code" :class="ch.type">
                <td>
                  <div class="rname">{{ ch.name }}</div>
                  <code>{{ ch.code }}</code>
                </td>
                <td class="ctype">{{ CHANGE_TEXT[ch.type] }}</td>
                <td>
                  <span v-if="ch.old_status" :class="['pill', ch.old_status]">{{ STATUS_TEXT[ch.old_status] }}</span>
                  <span v-else class="muted">—</span>
                  <div class="msg">{{ ch.old_message }}</div>
                </td>
                <td>
                  <span v-if="ch.new_status" :class="['pill', ch.new_status]">{{ STATUS_TEXT[ch.new_status] }}</span>
                  <span v-else class="muted">规则停用，不再检查</span>
                  <div class="msg">{{ ch.new_message }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p v-if="!items.length" class="muted empty">没有符合筛选条件的标签。</p>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 14px;
}
.toolbar h2 {
  margin: 0;
  font-size: 16px;
}
.summary {
  display: flex;
  gap: 20px;
  align-items: center;
  padding: 10px 14px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 13px;
  margin-bottom: 12px;
}
.summary .changed b {
  color: var(--warning);
}
.st {
  margin-left: auto;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
}
.st.running { background: #e3f2fd; color: #1565c0; }
.st.completed { background: var(--pass-bg); color: var(--pass); }
.st.pending { background: #fff8e1; color: #b26a00; }
.st.failed { background: var(--error-bg); color: var(--error); }
.filters {
  display: flex;
  gap: 18px;
  font-size: 13px;
  margin-bottom: 10px;
}
.filters input {
  width: auto;
  margin-right: 4px;
}
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 10px;
  overflow: hidden;
}
.card.changed {
  border-left: 3px solid var(--warning);
}
.card-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  cursor: pointer;
}
.name {
  font-weight: 600;
  min-width: 180px;
}
.status-flow {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-flow em {
  font-style: normal;
  font-size: 12px;
  color: var(--text-muted);
}
.arrow {
  color: var(--text-muted);
}
.toggle {
  margin-left: auto;
  font-size: 12px;
  color: var(--primary-dark);
}
.pill {
  display: inline-block;
  padding: 1px 9px;
  border-radius: 9px;
  font-size: 11px;
}
.pill.pass { background: var(--pass-bg); color: var(--pass); }
.pill.warning { background: var(--warning-bg); color: var(--warning); }
.pill.fail { background: var(--error-bg); color: var(--error); }
.diff-body {
  padding: 0 14px 14px;
}
.diff-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.diff-tbl th,
.diff-tbl td {
  text-align: left;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  vertical-align: top;
}
.diff-tbl th {
  color: var(--text-muted);
  font-weight: 600;
}
.rname {
  font-weight: 600;
}
code {
  font-size: 11px;
  color: #90a4ae;
}
.ctype {
  white-space: nowrap;
  color: var(--warning);
}
tr.added .ctype { color: var(--primary); }
tr.removed .ctype { color: var(--text-muted); }
.msg {
  margin-top: 4px;
  color: var(--text-muted);
}
.muted {
  color: var(--text-muted);
}
.empty {
  text-align: center;
  padding: 24px 0;
}
</style>
