<script setup>
import { computed } from 'vue'

const props = defineProps({
  packages: { type: Array, default: () => [] },
  effectiveId: { type: Number, default: null },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['new-draft', 'edit', 'recheck', 'archive', 'delete'])

const STATUS = {
  draft: { text: '草稿', cls: 'draft' },
  published: { text: '已发布', cls: 'published' },
  archived: { text: '已归档', cls: 'archived' },
}

const sorted = computed(() =>
  [...props.packages].sort((a, b) => b.version - a.version),
)

function isEffective(pkg) {
  return pkg.id === props.effectiveId
}
</script>

<template>
  <div class="pkg-list">
    <div class="toolbar">
      <h2>规则包版本</h2>
      <button class="btn primary" @click="emit('new-draft')">＋ 新建草稿</button>
    </div>

    <div v-if="loading" class="muted">加载中…</div>
    <table v-else class="tbl">
      <thead>
        <tr>
          <th>版本</th>
          <th>名称</th>
          <th>状态</th>
          <th>生效日期</th>
          <th>发布时间</th>
          <th class="ops">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="pkg in sorted" :key="pkg.id">
          <td class="ver">v{{ pkg.version }}</td>
          <td>
            {{ pkg.name }}
            <span v-if="isEffective(pkg)" class="eff-tag">当前生效</span>
          </td>
          <td><span :class="['status-tag', STATUS[pkg.status].cls]">{{ STATUS[pkg.status].text }}</span></td>
          <td>{{ pkg.effective_date || '—' }}</td>
          <td>{{ pkg.published_at ? new Date(pkg.published_at + 'Z').toLocaleString('zh-CN') : '—' }}</td>
          <td class="ops">
            <button v-if="pkg.status === 'draft'" class="link" @click="emit('edit', pkg)">编辑/发布</button>
            <button v-if="pkg.status === 'published'" class="link" @click="emit('recheck', pkg)">重检历史标签</button>
            <button v-if="pkg.status === 'published' && !isEffective(pkg)" class="link warn" @click="emit('archive', pkg)">
              归档
            </button>
            <button v-if="pkg.status === 'draft'" class="link danger" @click="emit('delete', pkg)">删除</button>
            <span v-if="pkg.status === 'archived'" class="muted">—</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="hint">
      已发布版本为不可变快照：正在执行的校验始终按其版本快照运行，发布新版本不会中断或改变进行中的校验。
    </p>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
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
  vertical-align: middle;
}
.tbl th {
  color: var(--text-muted);
  font-weight: 600;
  background: #fafbfa;
}
.ver {
  font-weight: 700;
  color: var(--primary-dark);
}
.ops {
  white-space: nowrap;
  text-align: right;
}
.status-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
}
.status-tag.draft {
  background: #fff8e1;
  color: #b26a00;
}
.status-tag.published {
  background: var(--pass-bg);
  color: var(--pass);
}
.status-tag.archived {
  background: #eceff1;
  color: #607d8b;
}
.eff-tag {
  margin-left: 8px;
  padding: 1px 8px;
  border-radius: 8px;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
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
.link.warn {
  color: var(--warning);
}
.link.danger {
  color: var(--error);
}
.muted {
  color: var(--text-muted);
  font-size: 13px;
}
.hint {
  margin: 12px 2px 0;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
