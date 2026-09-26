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

    <form class="filter-bar" @submit.prevent="applySearch">
      <label class="filter-item">
        <span>堆存单号</span>
        <input
          v-model.trim="orderNoInput"
          placeholder="按堆存单号检索，如 YARD-0001"
          @keydown.enter.prevent="applySearch"
        />
      </label>
      <label class="filter-item">
        <span>关联箱号</span>
        <input
          v-model.trim="containerNoInput"
          placeholder="按关联箱号检索，与堆存单号叠加"
          @keydown.enter.prevent="applySearch"
        />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span class="filter-hint">两个条件同时填写时按交集过滤</span>
    </form>

    <p v-if="notice" class="filter-notice">{{ notice }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="String(row.id)"
          :ref="(el) => setRowRef(el as Element | null, row.id)"
          :class="{ 'located-row': Number(row.id) === locatedId }"
        >
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
          <td :colspan="columns.length + 1" class="empty-state">
            {{ notice ? '没有符合筛选条件的堆存单' : '暂无堆存记录数据，可先登记堆存单' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆存记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/yardstore'
const FILTER_STORAGE_KEY = 'yardstore:filters'
const SCROLL_STORAGE_KEY = 'yardstore:scrollY'
// 列表页一次取全量（后端上限 200），保证筛选与定位覆盖当前列表全集
const LIST_SIZE = 200
const columns = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
const actions = ["确认进场", "确认提离", "撤销堆存"]
const statuses = ["待进场", "堆存中", "待提离", "已提离"]
const stats = [{"label": "堆存中箱量", "value": 0}, {"label": "今日进场箱量", "value": 0}, {"label": "今日提离箱量", "value": 0}]

interface PersistedFilters {
  orderNo: string
  containerNo: string
  locateId: number | null
}

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const notice = ref('')
const orderNoInput = ref('')
const containerNoInput = ref('')
const appliedFilters = ref<PersistedFilters>({ orderNo: '', containerNo: '', locateId: null })
const locatedId = ref<number | null>(null)
const rowRefs = new Map<number, HTMLElement>()

function setRowRef(el: Element | null, id: Row['id']) {
  const rowId = Number(id)
  if (el instanceof HTMLElement) {
    rowRefs.set(rowId, el)
  } else {
    rowRefs.delete(rowId)
  }
}

function readStoredFilters(): Partial<PersistedFilters> {
  try {
    const raw = window.sessionStorage.getItem(FILTER_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as Partial<PersistedFilters>) : {}
  } catch {
    return {}
  }
}

function persistFilters(filters: PersistedFilters) {
  try {
    window.sessionStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters))
  } catch {
    // 隐私模式等场景写不进存储时，仅依赖 URL 保留条件
  }
}

/** 初始条件：URL 查询参数优先（刷新、分享链接），其次用本地缓存（侧边栏切入口回来）。 */
function initialFilters(): PersistedFilters {
  const stored = readStoredFilters()
  const fromQuery: PersistedFilters = {
    orderNo: typeof route.query.orderNo === 'string' ? route.query.orderNo : (stored.orderNo ?? ''),
    containerNo:
      typeof route.query.containerNo === 'string' ? route.query.containerNo : (stored.containerNo ?? ''),
    locateId:
      route.query.locate !== undefined && route.query.locate !== ''
        ? Number(route.query.locate)
        : stored.locateId ?? null,
  }
  if (!Number.isFinite(fromQuery.locateId)) {
    fromQuery.locateId = null
  }
  return fromQuery
}

function syncUrl(filters: PersistedFilters) {
  const query: Record<string, string> = {}
  if (filters.orderNo) query.orderNo = filters.orderNo
  if (filters.containerNo) query.containerNo = filters.containerNo
  if (filters.locateId !== null) query.locate = String(filters.locateId)
  void router.replace({ query })
}

function hasActiveFilters(): boolean {
  return Boolean(appliedFilters.value.orderNo || appliedFilters.value.containerNo)
}

function buildQuery(filters: PersistedFilters): string {
  const params = new URLSearchParams({ page: '1', size: String(LIST_SIZE) })
  if (filters.orderNo) params.set('order_no', filters.orderNo)
  if (filters.containerNo) params.set('container_no', filters.containerNo)
  return params.toString()
}

async function reload(options: { scrollIntoView?: boolean } = {}) {
  errorMessage.value = ''
  notice.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery(appliedFilters.value)}`)
    if (!response.ok) {
      let detail = '堆存单列表读取失败'
      try {
        const payload = (await response.json()) as { detail?: string }
        if (payload.detail) detail = payload.detail
      } catch {
        // 后端未返回结构化错误时沿用兜底文案
      }
      throw new Error(detail)
    }
    const payload = (await response.json()) as {
      items?: Row[]
      total?: number
      notice?: string | null
    }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    notice.value = payload.notice ?? ''

    let targetId = appliedFilters.value.locateId
    if (targetId === null && hasActiveFilters() && rows.value.length === 1) {
      // 筛选只命中一条时，直接定位到那一条
      targetId = Number(rows.value[0].id)
      appliedFilters.value.locateId = targetId
      persistFilters(appliedFilters.value)
      syncUrl(appliedFilters.value)
    }
    locatedId.value = targetId
    if (locatedId.value !== null && !rows.value.some((row) => Number(row.id) === locatedId.value)) {
      // 定位目标不在当前过滤结果里时，不误导用户
      locatedId.value = null
    }

    await nextTick()
    if (options.scrollIntoView && locatedId.value !== null) {
      rowRefs.get(locatedId.value)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else if (!options.scrollIntoView) {
      restoreScroll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录列表读取失败'
  }
}

function restoreScroll() {
  const saved = window.sessionStorage.getItem(SCROLL_STORAGE_KEY)
  if (saved !== null) {
    const y = Number(saved)
    if (Number.isFinite(y)) window.scrollTo(0, y)
  }
  window.sessionStorage.removeItem(SCROLL_STORAGE_KEY)
}

function saveScroll() {
  try {
    window.sessionStorage.setItem(SCROLL_STORAGE_KEY, String(window.scrollY))
  } catch {
    // 存储不可用时忽略，不影响动作执行
  }
}

function applySearch() {
  appliedFilters.value = {
    orderNo: orderNoInput.value,
    containerNo: containerNoInput.value,
    // 过滤后唯一结果直接定位到那一条
    locateId: null,
  }
  persistFilters(appliedFilters.value)
  syncUrl(appliedFilters.value)
  void reload({ scrollIntoView: true })
}

function resetFilters() {
  orderNoInput.value = ''
  containerNoInput.value = ''
  appliedFilters.value = { orderNo: '', containerNo: '', locateId: null }
  locatedId.value = null
  persistFilters(appliedFilters.value)
  syncUrl(appliedFilters.value)
  void reload({ scrollIntoView: false })
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '堆存单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  // 进场/提离后刷新列表：保留当前条件与次序，并回到原来的滚动位置
  saveScroll()
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
    window.sessionStorage.removeItem(SCROLL_STORAGE_KEY)
    errorMessage.value = error instanceof Error ? error.message : '堆存记录操作失败'
  }
}

onMounted(() => {
  appliedFilters.value = initialFilters()
  orderNoInput.value = appliedFilters.value.orderNo
  containerNoInput.value = appliedFilters.value.containerNo
  locatedId.value = appliedFilters.value.locateId
  // 条件来自本地缓存（侧边栏切入口回来）时，把地址栏也补齐，保证刷新语义一致
  if (window.location.search === '') {
    syncUrl(appliedFilters.value)
  }
  void reload({ scrollIntoView: locatedId.value !== null })
})

onUnmounted(() => {
  rowRefs.clear()
})
</script>
