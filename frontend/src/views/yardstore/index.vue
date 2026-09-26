<template>
  <section class="page" data-module="yardstore">
    <header class="page-head">
      <div>
        <h2>堆存记录管理</h2>
        <p class="page-desc">维护堆存单，围绕堆存单号、关联箱号、箱区编号、贝位号做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记堆存单</button>
        <button class="btn" type="button" @click="exportRows">导出堆存记录清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table ref="tableRef" class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'located-row': isLocated(row) }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyHint }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆存记录记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/yardstore'
const columns = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
const actions = ["确认进场", "确认提离", "撤销堆存"]
const statuses = ["待进场", "堆存中", "待提离", "已提离"]
const stats = [{"label": "堆存中箱量", "value": 0}, {"label": "今日进场箱量", "value": 0}, {"label": "今日提离箱量", "value": 0}]

// 过滤条件在地址栏与本地各留一份：切到别的入口再回来、刷新页面都不丢
const STORAGE_KEY = 'yardstore.filters'
const PARAM_MAP: Record<string, string> = { 堆存单号: 'keyword', 关联箱号: 'container', 箱区编号: 'block' }

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const tableRef = ref<HTMLElement | null>(null)

const activeConditions = computed(() =>
  filterFields
    .map((field) => ({ field, value: (filters.value[field] ?? '').trim() }))
    .filter((item) => item.value.length > 0),
)

const emptyHint = computed(() => {
  if (!activeConditions.value.length) {
    return '暂无堆存记录数据，可先登记堆存单'
  }
  const conds = activeConditions.value.map((item) => `${item.field}「${item.value}」`).join('、')
  const hasSlip = activeConditions.value.some((item) => item.field === '堆存单号')
  const reason = hasSlip ? '请核对堆存单号是否填写正确，或调整过滤条件后重试' : '请调整过滤条件后重试'
  return `未找到符合条件的堆存单：${conds}。${reason}`
})

// 过滤结果里直接定位到那一条：单号或箱号精确命中，或条件把结果收敛到唯一一条
const locatedId = computed(() => {
  if (!rows.value.length || !activeConditions.value.length) {
    return null
  }
  const slip = (filters.value['堆存单号'] ?? '').trim()
  if (slip) {
    const hit = rows.value.find((row) => String(row['堆存单号'] ?? '') === slip)
    if (hit) {
      return hit.id
    }
  }
  const box = (filters.value['关联箱号'] ?? '').trim()
  if (box) {
    const hit = rows.value.find((row) => String(row['关联箱号'] ?? '') === box)
    if (hit) {
      return hit.id
    }
  }
  return rows.value.length === 1 ? rows.value[0].id : null
})

function isLocated(row: Row): boolean {
  return locatedId.value !== null && locatedId.value === row.id
}

function readStoredFilters(): Record<string, string> {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Record<string, unknown>
    const stored: Record<string, string> = {}
    for (const field of filterFields) {
      const value = raw[field]
      if (typeof value === 'string' && value.trim()) {
        stored[field] = value.trim()
      }
    }
    return stored
  } catch {
    return {}
  }
}

function persistFilters() {
  const current: Record<string, string> = {}
  for (const { field, value } of activeConditions.value) {
    current[field] = value
  }
  if (Object.keys(current).length) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(current))
  } else {
    localStorage.removeItem(STORAGE_KEY)
  }
  void router.replace({ query: current })
}

function applyFilters() {
  persistFilters()
  void reload()
}

function resetFilters() {
  filters.value = {}
  persistFilters()
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '堆存单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('堆存记录动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录操作失败'
  }
}

async function locateRow() {
  await nextTick()
  tableRef.value?.querySelector('.located-row')?.scrollIntoView({ block: 'nearest' })
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const { field, value } of activeConditions.value) {
    params.set(PARAM_MAP[field], value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('堆存单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await locateRow()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录列表读取失败'
  }
}

onMounted(() => {
  const fromQuery: Record<string, string> = {}
  for (const field of filterFields) {
    const value = route.query[field]
    if (typeof value === 'string' && value.trim()) {
      fromQuery[field] = value.trim()
    }
  }
  filters.value = Object.keys(fromQuery).length ? fromQuery : readStoredFilters()
  if (Object.keys(filters.value).length) {
    persistFilters()
  }
  void reload()
})
</script>
