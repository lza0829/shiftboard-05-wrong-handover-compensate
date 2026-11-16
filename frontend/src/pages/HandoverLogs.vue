<script setup>
import { onMounted, ref } from 'vue'
import { getJson } from '../api'

const rows = ref([])
const err = ref('')

onMounted(async () => {
  try {
    rows.value = await getJson('/api/records')
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>

<template>
  <div>
    <h1>交班记录</h1>
    <p class="lead">正向交班与补偿回拨分开留档：单据类型、对端单号、清单数量、最终状态。</p>
    <p v-if="err" class="msg">{{ err }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>类型</th><th>单号</th><th>关联单</th><th>回拨方/交班方</th>
            <th>接收方/接班方</th><th>数量</th><th>状态</th><th>开始</th><th>结束</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.kind + r.id">
            <td>
              <span class="tag" :class="{ on: r.kind === 'compensation' }">{{ r.doc_type }}</span>
            </td>
            <td>{{ r.doc_no }}</td>
            <td>{{ r.related_doc_no || '—' }}</td>
            <td>{{ r.from_shift_name }}</td>
            <td>{{ r.to_shift_name }}</td>
            <td>{{ r.count }} <span class="muted">{{ r.count_label }}</span></td>
            <td>{{ r.status }}</td>
            <td>{{ r.started_at }}</td>
            <td>{{ r.finished_at || '—' }}</td>
          </tr>
          <tr v-if="!rows.length">
            <td colspan="9">暂无单据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
