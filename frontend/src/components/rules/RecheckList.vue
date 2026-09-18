<script setup>
defineProps({
  batches: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})
defineEmits(['open', 'refresh'])

const STATUS_TEXT = { pending: '排队中', running: '重检中', completed: '已完成', failed: '失败' }
</script>

<template>
  <div>
    <div class="toolbar">
      <h2>批量重检任务</h2>
      <button class="btn ghost" @click="$emit('refresh')">刷新</button>
    </div>
    <p class="hint">
      新规则发布后，可对历史标签批量重检。任务启动时即固定规则快照，逐条对比新旧结论；
      每个标签都会新增一条 trigger=recheck 的校验留痕，原留痕完整保留用于审计。
    </p>
    <table class="tbl">
      <thead>
        <tr>
          <th>#</th>
          <th>重检版本</th>
          <th>基准版本</th>
          <th>状态 / 进度</th>
          <th>结果变化</th>
          <th>创建时间</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="b in batches" :key="b.id">
          <td>{{ b.id }}</td>
          <td><b>v{{ b.package_version }}</b></td>
          <td>{{ b.baseline_version ? `v${b.baseline_version}（各自最近留痕）` : '各自最近留痕' }}</td>
          <td>
            <span :class="['st', b.status]">{{ STATUS_TEXT[b.status] }}</span>
            <span class="prog">{{ b.processed }} / {{ b.total }}</span>
            <div v-if="b.status === 'failed'" class="err">{{ b.error_message }}</div>
          </td>
          <td>
            <span v-if="b.status === 'completed'" :class="{ changed: b.changed_count > 0 }">
              {{ b.changed_count }} / {{ b.total }} 条有差异
            </span>
            <span v-else>—</span>
          </td>
          <td>{{ b.created_at ? new Date(b.created_at + 'Z').toLocaleString('zh-CN') : '' }}</td>
          <td class="ops"><button class="link" @click="$emit('open', b)">查看差异</button></td>
        </tr>
        <tr v-if="!loading && !batches.length">
          <td colspan="7" class="empty">还没有重检任务。在「规则包版本」页对已发布版本点击「重检历史标签」。</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
h2 {
  margin: 0;
  font-size: 16px;
}
.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.tbl th,
.tbl td {
  text-align: left;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.tbl th {
  color: var(--text-muted);
  font-weight: 600;
  background: #fafbfa;
}
.st {
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
}
.st.running {
  background: #e3f2fd;
  color: #1565c0;
}
.st.completed {
  background: var(--pass-bg);
  color: var(--pass);
}
.st.pending {
  background: #fff8e1;
  color: #b26a00;
}
.st.failed {
  background: var(--error-bg);
  color: var(--error);
}
.prog {
  margin-left: 8px;
  color: var(--text-muted);
  font-size: 12px;
}
.err {
  color: var(--error);
  font-size: 12px;
}
.changed {
  color: var(--warning);
  font-weight: 600;
}
.ops {
  text-align: right;
}
.link {
  background: none;
  padding: 2px 8px;
  color: var(--primary-dark);
  font-size: 12px;
}
.link:hover {
  text-decoration: underline;
}
.empty {
  text-align: center;
  color: var(--text-muted);
  padding: 28px 0;
}
.hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
