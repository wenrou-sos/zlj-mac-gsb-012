<script setup>
import { computed } from 'vue'

const props = defineProps({
  validation: { type: Object, default: null },
  validating: { type: Boolean, default: false },
})

const CATEGORIES = [
  { key: 'field', label: '字段完整性', icon: '📋' },
  { key: 'unit', label: '单位规范', icon: '⚖️' },
  { key: 'nutrition', label: '营养成分', icon: '🥗' },
  { key: 'allergen', label: '过敏原提示', icon: '⚠️' },
]

const STATUS_TEXT = { pass: '校验通过', warning: '存在警告', fail: '校验未通过' }
const ICONS = { pass: '✓', warning: '⚠', error: '✕' }

const grouped = computed(() => {
  if (!props.validation) return []
  return CATEGORIES.map((cat) => ({
    ...cat,
    items: props.validation.results.filter((r) => r.category === cat.key),
  })).filter((g) => g.items.length)
})
</script>

<template>
  <div class="panel-body">
    <div v-if="!validation" class="empty">
      <p>填写左侧表单后将自动开始校验…</p>
    </div>

    <template v-else>
      <div v-if="validation.rule_package" class="rule-line">
        <span class="rule-dot"></span>
        本次校验使用：{{ validation.rule_package.package_name }}
        <b>v{{ validation.rule_package.package_version }}</b>
        <span v-if="validation.rule_package.package_status === 'draft'" class="draft-flag">草稿试用 · 不留痕</span>
        <span v-else-if="validation.record_id" class="record-flag">已记录 #{{ validation.record_id }}</span>
      </div>
      <div :class="['summary', validation.status]">
        <div class="verdict">
          <span class="verdict-icon">
            {{ validation.status === 'pass' ? '✓' : validation.status === 'fail' ? '✕' : '⚠' }}
          </span>
          <strong>{{ STATUS_TEXT[validation.status] }}</strong>
          <span v-if="validating" class="spin">校验中…</span>
        </div>
        <div class="counts">
          <span class="count error">✕ {{ validation.summary.errors }} 错误</span>
          <span class="count warning">⚠ {{ validation.summary.warnings }} 警告</span>
          <span class="count pass">✓ {{ validation.summary.passed }} 通过</span>
        </div>
      </div>

      <div v-for="group in grouped" :key="group.key" class="group">
        <h3>{{ group.icon }} {{ group.label }}</h3>
        <ul>
          <li v-for="item in group.items" :key="item.code + item.message" :class="item.status">
            <span class="icon">{{ ICONS[item.status] }}</span>
            <span>{{ item.message }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.panel-body {
  padding: 16px 20px 20px;
  max-height: calc(100vh - 160px);
  overflow-y: auto;
}

.empty {
  padding: 40px 0;
  text-align: center;
  color: var(--text-muted);
}

.rule-line {
  font-size: 12px;
  color: var(--text-muted);
  background: #f4f6f4;
  border-radius: 8px;
  padding: 7px 12px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.rule-line b {
  color: var(--primary-dark);
}
.rule-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary);
}
.draft-flag {
  background: #fff8e1;
  color: #b26a00;
  padding: 0 8px;
  border-radius: 8px;
  font-size: 11px;
}
.record-flag {
  color: var(--primary);
  font-size: 11px;
}

.summary {
  border-radius: 10px;
  padding: 12px 16px;
  margin-bottom: 16px;
}
.summary.pass { background: var(--pass-bg); }
.summary.warning { background: var(--warning-bg); }
.summary.fail { background: var(--error-bg); }

.verdict {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  margin-bottom: 6px;
}
.summary.pass .verdict { color: var(--pass); }
.summary.warning .verdict { color: var(--warning); }
.summary.fail .verdict { color: var(--error); }

.verdict-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 14px;
}
.summary.pass .verdict-icon { background: var(--pass); }
.summary.warning .verdict-icon { background: var(--warning); }
.summary.fail .verdict-icon { background: var(--error); }

.spin {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}

.counts {
  display: flex;
  gap: 14px;
  font-size: 12px;
}
.count.error { color: var(--error); }
.count.warning { color: var(--warning); }
.count.pass { color: var(--pass); }

.group h3 {
  font-size: 13px;
  margin: 16px 0 8px;
  color: var(--text);
}

.group ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.group li {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  background: #f7f9f7;
  border-left: 3px solid var(--border);
}
.group li.error {
  background: var(--error-bg);
  border-left-color: var(--error);
}
.group li.warning {
  background: var(--warning-bg);
  border-left-color: var(--warning);
}
.group li.pass {
  border-left-color: var(--pass);
  color: #546e7a;
}

.icon {
  font-weight: 700;
  flex-shrink: 0;
}
li.error .icon { color: var(--error); }
li.warning .icon { color: var(--warning); }
li.pass .icon { color: var(--pass); }
</style>
