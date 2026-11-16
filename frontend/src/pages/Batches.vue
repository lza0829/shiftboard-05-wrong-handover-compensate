<script setup>
import { onMounted, ref } from 'vue'
import { getJson } from '../api'

const rows = ref([])
const err = ref('')

onMounted(async () => {
  try {
    rows.value = await getJson('/api/batches')
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>

<template>
  <div>
    <h1>在途批次</h1>
    <p class="lead">批次归属当前值班班次；归属只能通过正向交班或补偿回拨变更，系统不提供手工改归属入口。</p>
    <p v-if="err" class="msg">{{ err }}</p>
    <div class="panel">
      <table>
        <thead>
          <tr><th>业务键</th><th>标题</th><th>归属班次</th><th>状态</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="b in rows" :key="b.id">
            <td>{{ b.biz_key }}</td>
            <td>{{ b.title }}</td>
            <td>{{ b.owner_shift_name || '—' }}</td>
            <td>
              <span class="tag" :class="{ on: b.status === '在途' }">{{ b.status }}</span>
              <span v-if="b.compensation_pending" class="tag" style="margin-left: 6px">补偿回拨中</span>
            </td>
            <td>{{ b.note || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
