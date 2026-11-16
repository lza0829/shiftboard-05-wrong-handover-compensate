import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './pages/Dashboard.vue'
import Shifts from './pages/Shifts.vue'
import Batches from './pages/Batches.vue'
import HandoverDesk from './pages/HandoverDesk.vue'
import Compensate from './pages/Compensate.vue'
import HandoverLogs from './pages/HandoverLogs.vue'
import Reconcile from './pages/Reconcile.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/shifts', component: Shifts },
    { path: '/batches', component: Batches },
    { path: '/handover', component: HandoverDesk },
    { path: '/compensate', component: Compensate },
    { path: '/logs', component: HandoverLogs },
    { path: '/reconcile', component: Reconcile },
  ],
})
