<script setup>
import { onMounted, ref } from 'vue'
import { getJson } from '../api'

const rows = ref([])
const err = ref('')
const expanded = ref(null)

onMounted(async () => {
  try {
    rows.value = await getJson('/api/reconcile')
  } catch (e) {
    err.value = String(e.message || e)
  }
})

function toggle(r) {
  expanded.value = expanded.value === r.id ? null : r.id
}
</script>

<template>
  <div>
    <h1>交班对账</h1>
    <p class="lead">
      正向交班：交班方在途应变 0，接班方应接住清单批次数。补偿回拨：指定键整单回到原交班方，
      清单与回拨前后在途集合同源。
    </p>
    <p v-if="err" class="msg">{{ err }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>报告</th><th>类型</th><th>单号</th><th>关联单</th>
            <th>清单/键数</th><th>回拨方/交班方</th><th>接收方/接班方</th><th>一致</th><th>明细</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id">
            <td>#{{ r.id }}</td>
            <td>
              <span class="tag" :class="{ on: r.doc_type === '补偿回拨' }">{{ r.doc_type }}</span>
            </td>
            <td>{{ r.doc_no }}</td>
            <td>{{ r.related_doc_no || '—' }}</td>
            <td>{{ r.before_count }}</td>
            <td>{{ r.after_from_count }}</td>
            <td>{{ r.after_to_count }}</td>
            <td>
              <span class="tag" :class="{ on: r.一致 }">{{ r.一致 ? '一致' : '不一致' }}</span>
            </td>
            <td>
              <button
                v-if="r.detail && r.detail.清单"
                class="btn ghost"
                @click="toggle(r)"
              >
                {{ expanded === r.id ? '收起' : '查看' }}
              </button>
              <span v-else class="muted">—</span>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="9">暂无对账报告</td>
          </tr>
        </tbody>
      </table>
      <div v-if="expanded !== null">
        <template v-for="r in rows" :key="'d' + r.id">
          <div v-if="r.id === expanded && r.detail.清单" style="margin-top: 14px">
            <h2>报告 #{{ r.id }} 补偿清单</h2>
            <table>
              <thead><tr><th>业务键</th><th>批次</th><th>回拨前归属</th><th>回拨后归属</th></tr></thead>
              <tbody>
                <tr v-for="i in r.detail.清单" :key="i.业务键">
                  <td>{{ i.业务键 }}</td>
                  <td>#{{ i.批次ID }}</td>
                  <td>#{{ i.回拨前归属 }}</td>
                  <td>#{{ i.回拨后归属 }}</td>
                </tr>
              </tbody>
            </table>
            <p class="msg">
              回拨前计数：{{ r.detail.回拨前计数.回拨方 }} / {{ r.detail.回拨前计数.接收方 }} ·
              回拨后计数：{{ r.detail.回拨后计数.回拨方 }} / {{ r.detail.回拨后计数.接收方 }}
            </p>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
