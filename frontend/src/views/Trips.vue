<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const trips = ref<any[]>([])
const events = ref<any[]>([])
const cancelling = ref<number | null>(null)
async function load() {
  trips.value = await api('/trips')
  try {
    events.value = (await api('/reports/run?line_id=1', { method: 'POST' })).events || []
  } catch { events.value = [] }
}
onMounted(load)
async function cancel(t: any) {
  if (t.status === 'cancelled') return
  cancelling.value = t.id
  try {
    await api(`/trips/${t.id}/cancel`, { method: 'POST' })
    await load()
  } finally { cancelling.value = null }
}
function stripClass(s: string) {
  return s === 'bunching' ? 'bg-bunch' : s === 'large_gap' ? 'bg-large' : ''
}
function label(s: string) {
  return s === 'bunching' ? '串车' : s === 'large_gap' ? '大间隔' : '正常'
}
</script>
<template>
  <h1>班次 · 间隔条带</h1>
  <p class="sub">左侧班次清单，右侧串车/间隔竖直条带；取消的班次不再参与检测</p>
  <div class="bg-split">
    <aside class="bg-trip-col">
      <h2>班次列表</h2>
      <div v-for="r in trips" :key="r.id ?? r.trip_no" class="bg-trip-row"
        :class="{ 'bg-trip-cancelled': r.status === 'cancelled' }">
        <div>
          <div>
            {{ r.trip_no }}
            <span class="badge" :class="r.status === 'cancelled' ? 'badge-bad' : 'badge-ok'">
              {{ r.status === 'cancelled' ? '已取消' : '在跑' }}
            </span>
          </div>
          <div class="bg-trip-meta">线路 {{ r.line_id }} · 车 {{ r.vehicle_no }}</div>
        </div>
        <div class="bg-trip-side">
          <div class="bg-trip-meta">{{ r.planned_depart }}</div>
          <button v-if="r.status !== 'cancelled'" class="btn-cancel"
            :disabled="cancelling === r.id" @click="cancel(r)">取消</button>
        </div>
      </div>
    </aside>
    <div class="bg-strip-col">
      <article
        v-for="(e, i) in events"
        :key="i"
        class="bg-gap-strip"
        :class="stripClass(e.status)"
      >
        <header>{{ e.stop_name }}</header>
        <div class="bg-gap-body">
          <div class="bg-gap-val">{{ e.gap_min }}′</div>
          <div>计划 {{ e.planned_headway_min }}′</div>
          <div>{{ e.earlier_trip }} → {{ e.later_trip }}</div>
          <span class="badge" :class="e.status === 'bunching' ? 'badge-bad' : e.status === 'large_gap' ? 'badge-warn' : 'badge-ok'">
            {{ label(e.status) }}
          </span>
        </div>
      </article>
      <p v-if="!events.length" class="muted">暂无间隔事件</p>
    </div>
  </div>
</template>
