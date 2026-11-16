<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJson, postJson } from '../api'

const handovers = ref([])
const selectedHandoverId = ref('')
const compensable = ref([])
const selectedKeys = ref([])
const reason = ref('')

const active = ref(null)
const history = ref([])
const expanded = ref(null)
const msg = ref('')
const ok = ref(false)
const busy = ref(false)

const completedHandovers = computed(() =>
  handovers.value.filter((h) => h.status === '已完成'),
)

async function refresh() {
  const [logs, comps] = await Promise.all([
    getJson('/api/handovers'),
    getJson('/api/compensations'),
  ])
  handovers.value = logs
  history.value = comps
  active.value = comps.find((c) => c.status === '进行中') || null
  if (active.value) {
    active.value = await getJson(`/api/compensations/${active.value.id}`)
  }
}

async function loadCompensable() {
  selectedKeys.value = []
  compensable.value = []
  expanded.value = null
  if (!selectedHandoverId.value) return
  msg.value = ''
  try {
    compensable.value = await getJson(
      `/api/handovers/${selectedHandoverId.value}/compensable`,
    )
  } catch (e) {
    msg.value = String(e.message || e)
  }
}

function toggleKey(key) {
  const i = selectedKeys.value.indexOf(key)
  if (i >= 0) selectedKeys.value.splice(i, 1)
  else selectedKeys.value.push(key)
}

async function create() {
  msg.value = ''
  ok.value = false
  busy.value = true
  try {
    const created = await postJson('/api/compensations', {
      handover_id: Number(selectedHandoverId.value),
      biz_keys: selectedKeys.value,
      reason: reason.value,
    })
    ok.value = true
    msg.value = `已开补偿单 #${created.id}，待回拨 ${created.key_count} 个业务键`
    reason.value = ''
    selectedKeys.value = []
    selectedHandoverId.value = ''
    compensable.value = []
    await refresh()
  } catch (e) {
    msg.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function completeActive() {
  if (!active.value) return
  if (!window.confirm(`确认整单回拨 ${active.value.key_count} 个业务键到原交班方？`)) return
  msg.value = ''
  ok.value = false
  busy.value = true
  try {
    const done = await postJson(`/api/compensations/${active.value.id}/complete`)
    ok.value = done.status === '已完成'
    msg.value = `补偿单 #${done.id} 已完成，${done.key_count} 个业务键已回到原交班方`
    await refresh()
  } catch (e) {
    msg.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function toggleExpand(id) {
  if (expanded.value?.id === id) {
    expanded.value = null
    return
  }
  try {
    expanded.value = await getJson(`/api/compensations/${id}`)
  } catch (e) {
    msg.value = String(e.message || e)
  }
}

onMounted(async () => {
  try {
    await refresh()
  } catch (e) {
    msg.value = String(e.message || e)
  }
})
</script>

<template>
  <div>
    <h1>补偿回拨</h1>
    <p class="lead">
      交班完成后发现错交，只能通过补偿单把指定业务键从接班方回拨到原交班方；
      回拨整单原子，补偿进行中与正向交班全局互斥。
    </p>

    <div class="panel">
      <div class="row">
        <label>原交班单
          <select v-model="selectedHandoverId" @change="loadCompensable">
            <option value="">选择已完成的交班单</option>
            <option v-for="h in completedHandovers" :key="h.id" :value="h.id">
              {{ h.doc_no }} · {{ h.from_shift_name }} → {{ h.to_shift_name }}
            </option>
          </select>
        </label>
        <label>回拨原因
          <input v-model="reason" type="text" placeholder="例如：错交晚班" />
        </label>
        <button
          class="btn"
          :disabled="busy || !!active || !selectedKeys.length"
          @click="create"
        >发起补偿回拨</button>
      </div>

      <p v-if="active" class="msg">补偿单 #{{ active.id }} 进行中，处理完成前不能发起新的交班或补偿。</p>
      <p class="msg" :class="{ ok }">{{ msg }}</p>

      <div v-if="selectedHandoverId" style="margin-top: 12px">
        <h2>可回拨业务键</h2>
        <table v-if="compensable.length">
          <thead><tr><th>选择</th><th>业务键</th><th>标题</th><th>当前归属</th></tr></thead>
          <tbody>
            <tr v-for="b in compensable" :key="b.batch_id">
              <td>
                <input
                  type="checkbox"
                  :checked="selectedKeys.includes(b.biz_key)"
                  :disabled="!!active"
                  @change="toggleKey(b.biz_key)"
                />
              </td>
              <td>{{ b.biz_key }}</td>
              <td>{{ b.title }}</td>
              <td>#{{ b.owner_shift_id }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="msg">该交班单已没有可回拨的业务键。</p>
      </div>
    </div>

    <div class="panel" v-if="active">
      <h2>当前补偿单 #{{ active.id }} · {{ active.status }}</h2>
      <p class="lead" style="margin-bottom: 12px">
        {{ active.related_doc_no }} · {{ active.from_shift_name }} → {{ active.to_shift_name }}
        · 回拨 {{ active.key_count }} 个业务键
      </p>
      <table>
        <thead><tr><th>业务键</th><th>标题</th><th>回拨前归属</th></tr></thead>
        <tbody>
          <tr v-for="i in active.items || []" :key="i.batch_id">
            <td>{{ i.biz_key }}</td>
            <td>{{ i.title }}</td>
            <td>#{{ i.owner_shift_id_before }}</td>
          </tr>
        </tbody>
      </table>
      <div class="row" style="margin-top: 14px">
        <button class="btn" :disabled="busy" @click="completeActive">完成补偿回拨</button>
      </div>
    </div>

    <div class="panel">
      <h2>补偿单历史</h2>
      <table>
        <thead>
          <tr><th>单号</th><th>原交班单</th><th>回拨方</th><th>接收方</th><th>键数</th><th>状态</th><th>完成时间</th><th>清单</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in history" :key="c.id">
            <td>#{{ c.id }}</td>
            <td>{{ c.related_doc_no }}</td>
            <td>{{ c.from_shift_name }}</td>
            <td>{{ c.to_shift_name }}</td>
            <td>{{ c.key_count }}</td>
            <td>
              <span class="tag" :class="{ on: c.status === '已完成' }">{{ c.status }}</span>
            </td>
            <td>{{ c.finished_at || '—' }}</td>
            <td>
              <button class="btn ghost" @click="toggleExpand(c.id)">
                {{ expanded && expanded.id === c.id ? '收起' : '查看' }}
              </button>
            </td>
          </tr>
          <tr v-if="!history.length">
            <td colspan="8">暂无补偿单</td>
          </tr>
        </tbody>
      </table>
      <div v-if="expanded" style="margin-top: 14px">
        <h2>补偿单 #{{ expanded.id }} 清单</h2>
        <table>
          <thead><tr><th>业务键</th><th>标题</th><th>回拨前归属</th><th>当前归属</th><th>批次状态</th></tr></thead>
          <tbody>
            <tr v-for="i in expanded.items" :key="i.batch_id">
              <td>{{ i.biz_key }}</td>
              <td>{{ i.title }}</td>
              <td>#{{ i.owner_shift_id_before }}</td>
              <td>#{{ i.owner_shift_id_now }}</td>
              <td>{{ i.batch_status }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="expanded.reason" class="msg">{{ expanded.reason }}</p>
      </div>
    </div>
  </div>
</template>
