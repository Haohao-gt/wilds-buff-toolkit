<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import logoUrl from './assets/logo.png'

const skills = ref([])
const q = ref('')
const filter = ref('ALL')
const active = ref(0)
const chosen = ref([null, null, null])
const stampIdx = ref(-1)
const dragSkill = ref(null)
const dragOver = ref('')
const listEl = ref(null)
const queueEdit = ref(0)

const game = ref({
  connected: false, pid: 0, hero: '', level: 0,
  cards: [], logs: [], mapReady: false, mapProgress: 0, armed: 0,
})

/* ---------- 预设方案 ---------- */
function blankQueue() { return Array(9).fill(null) }
function loadPresets() {
  try {
    const d = JSON.parse(localStorage.getItem('buff_presets_v2') || 'null')
    if (Array.isArray(d) && d.length) return d
  } catch (e) { /* ignore */ }
  return [{ name: '方案 1', queue: blankQueue(), idx: 0 }]
}
const presets = ref(loadPresets())
const presetIdx = ref(0)
const auto = ref(localStorage.getItem('buff_auto') === '1')

const queue = computed({
  get: () => presets.value[presetIdx.value].queue,
  set: (v) => { presets.value[presetIdx.value].queue = v },
})
const qIndex = computed({
  get: () => presets.value[presetIdx.value].idx || 0,
  set: (v) => { presets.value[presetIdx.value].idx = v },
})

watch(presets, (v) => {
  try { localStorage.setItem('buff_presets_v2', JSON.stringify(v)) } catch (e) { /* ignore */ }
}, { deep: true })
watch(auto, (v) => {
  try { localStorage.setItem('buff_auto', v ? '1' : '0') } catch (e) { /* ignore */ }
})

function addPreset() {
  const n = presets.value.length + 1
  presets.value.push({ name: '方案 ' + n, queue: blankQueue(), idx: 0 })
  presetIdx.value = presets.value.length - 1
}
function delPreset() {
  if (presets.value.length <= 1) return
  presets.value.splice(presetIdx.value, 1)
  presetIdx.value = Math.min(presetIdx.value, presets.value.length - 1)
}
function renamePreset() {
  const p = presets.value[presetIdx.value]
  const name = window.prompt('方案名称', p.name)
  if (name && name.trim()) p.name = name.trim().slice(0, 8)
}
function clearQueue() {
  presets.value[presetIdx.value].queue = blankQueue()
  presets.value[presetIdx.value].idx = 0
}

/* ---------- 基础 ---------- */
const toast = ref({ show: false, msg: '', kind: '' })
let toastTimer = null
let timer = null
let lastSig = ''
let firstState = true
let lastCount = -1
let prevArmed = 0
let autoDoneFor = -1

const tabs = [
  { key: 'ALL', label: '全部' },
  { key: '随机BUFF', label: '增益' },
  { key: '主动技能', label: '主动' },
  { key: '特殊/局外', label: '特殊' },
]
const roman = ['Ⅰ', 'Ⅱ', 'Ⅲ']

const filtered = computed(() => {
  const s = q.value.trim().toLowerCase()
  return skills.value
    .filter((x) => {
      if (filter.value !== 'ALL' && x.cat !== filter.value) return false
      if (!s) return true
      return x.name.toLowerCase().includes(s) || String(x.id).includes(s)
    })
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-Hans-CN'))
})

const catKey = (cat) => (cat === '主动技能' ? 'active' : cat === '特殊/局外' ? 'special' : 'buff')
const target = (i) => chosen.value[i] || (game.value.cards ? game.value.cards[i] : null)
const initial = (s) => (s ? s.name.replace(/^[-\s]+/, '').charAt(0) : '?')

function post(cmd) {
  try { window.chrome.webview.postMessage(cmd) } catch (e) { /* ignore */ }
}
function startDrag(e) {
  if (e.button === 0) post('drag')
}

function showToast(msg, kind = '') {
  toast.value = { show: true, msg, kind }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value.show = false }, 1900)
}

async function api(path, opts) {
  const r = await fetch(path, opts)
  return r.json()
}

async function loadSkills() {
  const d = await api('/api/skills')
  skills.value = d.skills
}

async function connect(silent = false) {
  const d = await api('/api/connect', { method: 'POST' })
  if (!silent) showToast(d.msg, d.ok ? 'ok' : 'err')
  await refresh()
  return d.ok
}

/* ---------- 拖放 / 选择 ---------- */
function onDragStart(e, s) {
  dragSkill.value = s
  try {
    e.dataTransfer.setData('text/plain', String(s.id))
    e.dataTransfer.effectAllowed = 'copy'
  } catch (err) { /* ignore */ }
}

function onDropCard(i) {
  if (!dragSkill.value) return
  chosen.value[i] = dragSkill.value
  active.value = i
  stampIdx.value = i
  setTimeout(() => { stampIdx.value = -1 }, 240)
  showToast(`卡 ${i + 1} → ${dragSkill.value.name}`, 'ok')
  dragSkill.value = null
  dragOver.value = ''
}

function onDropQueue(i) {
  if (!dragSkill.value) return
  queue.value[i] = dragSkill.value
  showToast(`方案「${presets.value[presetIdx.value].name}」第 ${i + 1} 位 → ${dragSkill.value.name}`, 'ok')
  dragSkill.value = null
  dragOver.value = ''
}

function clearQueueSlot(i) {
  queue.value[i] = null
}

function queueActiveEvent(i) {
  queueEdit.value = i
}

function assignToQueueEdit(s) {
  queue.value[queueEdit.value] = s
  showToast(`方案「${presets.value[presetIdx.value].name}」第 ${queueEdit.value + 1} 位 → ${s.name}`, 'ok')
}

/* ---------- 装填 ---------- */
async function applyIds(ids) {
  const d = await api('/api/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slots: ids, hold: Number(localStorage.getItem('buff_hold') || 120) }),
  })
  showToast(d.msg, d.ok ? 'ok' : 'err')
  return d.ok
}

async function apply() {
  const slots = chosen.value.map((s) => (s ? s.id : null))
  if (!slots.some(Boolean)) { showToast('先给至少一个卡位选择技能', 'err'); return }
  await applyIds(slots)
  await refresh()
}

async function manualRead() {
  chosen.value = [null, null, null]
  if (!game.value.connected) {
    const ok = await connect(false)
    if (ok) showToast('已连接，已读取当前手牌', 'ok')
    return
  }
  await refresh()
  showToast('已重新读取当前手牌', 'ok')
}

async function onAutoChange(e) {
  auto.value = e.target.checked
  if (!auto.value) return
  if (qIndex.value >= 9) { showToast('当前方案已全部完成', 'err'); return }
  const sk = queue.value[qIndex.value]
  if (!sk) { showToast('当前方案这一位还没设置技能', 'err'); return }
  if (!game.value.connected || !game.value.cards || game.value.cards.length !== 3) {
    showToast('等待出卡后自动装填', 'ok'); return
  }
  const ok = await applyIds([sk.id, sk.id, sk.id])
  if (ok) {
    qIndex.value += 1
    showToast(`自动装填 ${qIndex.value}/9：${sk.name}`, 'ok')
  }
}

/* ---------- 状态轮询 ---------- */
async function refresh() {
  const st = await api('/api/state')
  game.value = st

  if (prevArmed > 0 && st.armed === 0 && chosen.value.some(Boolean)) {
    chosen.value = [null, null, null]
    showToast('装填窗口已结束，未点卡', 'err')
  }
  prevArmed = st.armed || 0

  const lvl = st.level || 0
  if (lvl !== lastCount) {
    if (lastCount !== -1) {
      chosen.value = [null, null, null]
      showToast('新一手牌', 'ok')
    }
    lastCount = lvl
  }

  if (auto.value && lvl > 0 && st.cards && st.cards.length === 3
      && qIndex.value < 9 && queue.value[qIndex.value] && autoDoneFor !== lvl) {
    const sk = queue.value[qIndex.value]
    const ok = await applyIds([sk.id, sk.id, sk.id])
    if (ok) {
      autoDoneFor = lvl
      qIndex.value += 1
      showToast(`自动装填 ${qIndex.value}/9：${sk.name}`, 'ok')
    }
  }

  const sig = (st.cards || []).map((x) => x.cfg).join(',') + '@' + st.level
  if (sig !== lastSig && st.cards && st.cards.length === 3) {
    lastSig = sig
    firstState = false
  }
}

function onKey(e) {
  if (e.key === 'F1') { e.preventDefault(); apply() }
  if (e.key === '1' || e.key === '2' || e.key === '3') active.value = Number(e.key) - 1
  if (e.key === 'Escape') chosen.value[active.value] = null
}

watch([q, filter], () => {
  if (listEl.value) listEl.value.scrollTop = 0
})

onMounted(async () => {
  await loadSkills()
  if (localStorage.getItem('buff_autoconnect') !== '0') await connect(true)
  else await refresh()
  if (listEl.value) listEl.value.scrollTop = 0
  timer = setInterval(refresh, 800)
  setInterval(() => { if (!game.value.pid) connect(true) }, 3000)
  window.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  clearInterval(timer)
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="app flex h-full w-full flex-col overflow-hidden">
    <div class="tb flex h-[36px] shrink-0 items-center gap-2 px-2" @mousedown="startDrag">
      <img :src="logoUrl" class="h-[22px] w-[22px] rounded-[7px]" alt="" draggable="false" />
      <div class="flex items-baseline gap-1.5">
        <span class="tb-title">BUFF 编排台</span>
        <span class="tb-sub">WILDS TOOLKIT</span>
      </div>
      <div class="ml-auto flex items-center gap-0.5">
        <button class="wbtn" @mousedown.stop @click="post('pin')">⌖</button>
        <button class="wbtn" @mousedown.stop @click="post('min')">—</button>
        <button class="wbtn close" @mousedown.stop @click="post('close')">✕</button>
      </div>
    </div>

    <div class="flex min-h-0 flex-1">
      <aside class="lib panel m-2 mr-0 flex w-[228px] shrink-0 flex-col overflow-hidden">
        <div class="flex items-center justify-between px-3 pb-1 pt-2.5">
          <span class="flex items-center gap-1.5 text-[13px] font-extrabold text-cream [text-shadow:0_1px_2px_rgba(0,0,0,.45)]">
            <i class="h-3 w-1 rounded-full bg-gold"></i>技能库
          </span>
          <span class="rounded-full bg-white/15 px-2 py-0.5 font-mono text-[10px] text-cream/85">{{ filtered.length }}</span>
        </div>

        <div class="px-2.5 pt-1">
          <div class="relative">
            <svg class="absolute left-2 top-1/2 h-[13px] w-[13px] -translate-y-1/2" viewBox="0 0 24 24"
                 fill="none" stroke="#BFE0FA" stroke-width="2.4" stroke-linecap="round">
              <circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" />
            </svg>
            <input v-model="q" placeholder="搜索技能或编号"
                   class="h-[30px] w-full rounded-lg border border-white/25 bg-[#0B2E52]/70 pl-8 pr-2 text-[12px] text-cream outline-none placeholder:text-white/45 focus:border-gold" />
          </div>
        </div>

        <div class="flex gap-1 px-2.5 py-1.5">
          <button v-for="t in tabs" :key="t.key" @click="filter = t.key"
                  class="h-[24px] rounded-full px-2.5 text-[11px] font-bold transition-colors"
                  :class="filter === t.key ? 'bg-gold text-brown shadow-[0_2px_0_#8A4B0F]' : 'text-cream/75 hover:bg-white/10 hover:text-cream'">
            {{ t.label }}
          </button>
        </div>

        <div ref="listEl" class="min-h-0 flex-1 overflow-y-auto px-1.5 pb-1">
          <button v-for="s in filtered" :key="s.id" draggable="true" @dragstart="onDragStart($event, s)"
                  @dblclick="assignToQueueEdit(s)"
                  class="flex h-[34px] w-full cursor-grab items-center gap-2 rounded-lg px-1.5 text-left transition-colors hover:bg-white/10 active:cursor-grabbing">
            <span class="grid h-[26px] w-[26px] shrink-0 place-items-center overflow-hidden rounded-full border-2 border-white/45 text-[11px] font-bold text-white [text-shadow:0_1px_2px_rgba(0,0,0,.35)]"
                  :class="catKey(s.cat) === 'active' ? 'bg-gradient-to-br from-[#63E0D6] to-[#1F9C92]'
                          : catKey(s.cat) === 'special' ? 'bg-gradient-to-br from-[#C9B0FF] to-[#7B57D8]'
                          : 'bg-gradient-to-br from-[#FFD66B] to-[#E0951B]'">
              <img v-if="s.icon" :src="s.icon" class="h-full w-full object-cover" alt="" />
              <template v-else>{{ s.name.charAt(0) }}</template>
            </span>
            <span class="min-w-0 flex-1 truncate text-[12.5px] font-semibold text-cream">{{ s.name }}</span>
            <span v-if="s.lv" class="shrink-0 rounded-md border border-gold/60 bg-gold/20 px-1 py-0.5 font-mono text-[9.5px] font-bold text-gold">L{{ s.lv }}</span>
          </button>
        </div>

        <div class="flex h-[24px] shrink-0 items-center justify-between border-t border-white/15 px-3 text-[10px] text-[#A9C9E2]">
          <span>拖到卡位 / 队列</span><span>F1 装填</span>
        </div>
      </aside>

      <main class="flex min-h-0 min-w-0 flex-1 flex-col gap-2 overflow-hidden p-2">

        <div class="flex min-h-0 flex-1 min-w-0 flex-col gap-2">
              <div class="flex shrink-0 items-center gap-2 rounded-xl border border-white/25 bg-deep/70 px-3 py-1.5">
                <span class="text-[13.5px] font-extrabold text-cream [text-shadow:0_1px_2px_rgba(0,0,0,.45)]">本局配给</span>
                <span class="h-px flex-1 bg-white/20"></span>
                <span class="font-mono text-[10.5px] text-[#CFE6FA]">LV {{ game.connected ? game.level : '—' }}</span>
                <span class="flex items-center gap-1 text-[11px] font-bold" :class="game.connected ? 'text-[#8CF5B4]' : 'text-[#9FC3E0]'">
                  <i class="h-1.5 w-1.5 rounded-full" :class="game.connected ? 'bg-[#8CF5B4]' : 'bg-white/40'"></i>
                  {{ game.connected ? '对局中' : (game.pid ? '等待对局' : '未连接') }}
                </span>
              </div>

              <div class="grid shrink-0 grid-cols-3 gap-2">
                <div v-for="i in 3" :key="i" @click="active = i - 1"
                     @dragover.prevent="dragOver = 'card-' + (i - 1)" @dragleave="dragOver = ''" @drop.prevent="onDropCard(i - 1)"
                     class="card" :class="{ on: active === i - 1, over: dragOver === 'card-' + (i - 1), filled: !!chosen[i - 1] }">
                  <span class="absolute left-2 top-1 text-[9px] font-bold text-[#9FC3E0]">{{ roman[i - 1] }}</span>
                  <span class="orb mt-2"
                        :class="chosen[i - 1]
                          ? (catKey(chosen[i - 1].cat) === 'active'
                              ? 'bg-gradient-to-br from-[#63E0D6] to-[#1F9C92]'
                              : catKey(chosen[i - 1].cat) === 'special'
                                ? 'bg-gradient-to-br from-[#C9B0FF] to-[#7B57D8]'
                                : 'bg-gradient-to-br from-[#FFD66B] to-[#E0951B]')
                          : 'bg-[#0B2E52]/80 text-white/40'">
                    <img v-if="target(i - 1) && target(i - 1).icon" :src="target(i - 1).icon" class="h-full w-full object-cover" alt="" />
                    <span v-else-if="target(i - 1)"
                          class="grid h-full w-full place-items-center"
                          :class="catKey(target(i - 1).cat) === 'active' ? 'bg-gradient-to-br from-[#63E0D6] to-[#1F9C92]'
                                  : catKey(target(i - 1).cat) === 'special' ? 'bg-gradient-to-br from-[#C9B0FF] to-[#7B57D8]'
                                  : 'bg-gradient-to-br from-[#FFD66B] to-[#E0951B]'">
                      {{ initial(target(i - 1)) }}
                    </span>
                    <template v-else>{{ initial(target(i - 1)) }}</template>
                  </span>
                  <span class="mt-1.5 block w-full truncate px-1 text-center text-[12.5px] font-extrabold text-cream [text-shadow:0_1px_2px_rgba(0,0,0,.4)]">
                    {{ target(i - 1) ? target(i - 1).name : '空位' }}
                  </span>
                  <span class="mb-1 text-[9px] font-bold" :class="chosen[i - 1] ? 'text-gold' : 'text-[#9FC3E0]'">
                    {{ chosen[i - 1] ? '已替换' : (target(i - 1) ? '当前' : '待指定') }}
                  </span>
                </div>
              </div>

              <div class="panel shrink-0 px-2.5 py-2">
                <div class="flex flex-wrap items-center gap-1">
                  <span class="sec-title">预设方案</span>
                  <button v-for="(p, i) in presets" :key="i" @click="presetIdx = i"
                          class="pchip" :class="{ on: presetIdx === i }">{{ p.name }}</button>
                  <button class="pbtn" @click="addPreset">＋</button>
                  <button class="pbtn" @click="renamePreset">改名</button>
                  <button class="pbtn" @click="delPreset">删除</button>
                  <button class="pbtn ml-auto" @click="clearQueue">清空</button>
                </div>
                <div class="mt-2 flex items-center gap-1">
                  <button v-for="n in 9" :key="n" @click="queueActiveEvent(n - 1)"
                          @dragover.prevent="dragOver = 'queue-' + (n - 1)" @dragleave="dragOver = ''" @drop.prevent="onDropQueue(n - 1)"
                          @contextmenu.prevent="clearQueueSlot(n - 1)"
                          draggable="true" @dragstart.stop="dragQueueFrom = n - 1" @dragend="dragQueueFrom = -1"
                          class="slot" :class="{ on: queueEdit === n - 1, over: dragOver === 'queue-' + (n - 1), done: n - 1 < qIndex }"
                          :title="queue[n-1] ? queue[n-1].name : '空位 ' + n">
                    <img v-if="queue[n-1] && queue[n-1].icon" :src="queue[n-1].icon" class="h-full w-full object-cover" alt="" />
                    <span v-else-if="queue[n-1]" class="grid h-full w-full place-items-center text-[15px] font-extrabold text-white [text-shadow:0_1px_2px_rgba(0,0,0,.35)]"
                          :class="catKey(queue[n-1].cat) === 'active' ? 'bg-gradient-to-br from-[#63E0D6] to-[#1F9C92]'
                                  : catKey(queue[n-1].cat) === 'special' ? 'bg-gradient-to-br from-[#C9B0FF] to-[#7B57D8]'
                                  : 'bg-gradient-to-br from-[#FFD66B] to-[#E0951B]'">
                      {{ queue[n-1].name.charAt(0) }}
                    </span>
                    <span v-else class="text-[11px] font-bold text-[#B9D6EC]">{{ n }}</span>
                  </button>
                  <span class="ml-1 font-mono text-[10px] text-[#9FC3E0]">{{ qIndex }}/9</span>
                </div>
              </div>

              <div class="flex shrink-0 items-center gap-2 pr-1">
                <button class="btn-gold" @click="apply">
                  装填到手牌
                  <kbd>F1</kbd>
                </button>
                <button class="btn" @click="manualRead">读取</button>
                <button class="btn" @click="chosen = [null, null, null]">清空</button>
                <label class="ml-auto flex cursor-pointer items-center gap-1.5 text-[10.5px] font-bold text-[#D8ECFA]">
                  <input v-model="auto" type="checkbox" class="hidden" @change="onAutoChange" />
                  <i class="relative h-[16px] w-[28px] rounded-full border border-white/35 bg-[#0B2E52]/80 transition-colors"
                     :class="auto ? 'border-gold bg-gold/30' : ''">
                    <span class="absolute left-[2px] top-[1.5px] h-[11px] w-[11px] rounded-full bg-white/65 transition-transform"
                          :class="auto ? 'translate-x-[12px] bg-gold' : ''"></span>
                  </i>
                  逐级自动
                </label>
              </div>

              <div class="log panel min-h-0 flex-1 overflow-y-auto px-2.5 py-1.5 font-mono text-[10.5px] leading-relaxed text-[#BFE6FF]">
                <div v-if="!game.logs || game.logs.length === 0" class="text-white/35">连接游戏并进入对局后，这里显示运行记录。</div>
                <div v-for="(l, idx) in game.logs" :key="idx"
                     :class="/失败|错误|找不到|未就绪|跳过/.test(l) ? 'text-[#FFC97A]' : (/完成|成功|已写入|已应用|已连接|已装填/.test(l) ? 'text-[#9CF0B8]' : '')">
                  {{ l }}
                </div>
              </div>
        </div>

        <div class="status flex shrink-0 items-center gap-3 rounded-xl border border-white/25 px-3 py-1 font-mono text-[10px] text-[#CFE6FA]">
          <span>PID <b class="text-cream">{{ game.pid || '—' }}</b></span>
          <span>角色 <b class="text-cream">{{ game.hero || '—' }}</b></span>
          <span>手牌 <b class="text-cream">{{ game.cards ? game.cards.length : 0 }}</b></span>
          <span v-if="game.armed" class="armed rounded-md bg-gold px-1.5 py-0.5 font-bold text-brown">已装填 · {{ game.armed }}s</span>
          <span class="ml-auto text-[#9FC3E0]">{{ game.mapReady ? '配置就绪' : '配置索引 ' + (game.mapProgress || 0) + '%' }}</span>
        </div>
      </main>
    </div>

    <transition name="toast">
      <div v-if="toast.show" class="toast" :class="toast.kind">{{ toast.msg }}</div>
    </transition>
  </div>
</template>

<style>
.app { background: radial-gradient(1200px 700px at 18% -12%, #2E7CC4 0%, #154C86 46%, #0B2E52 100%); }
.tb { background: linear-gradient(180deg, #2E7CC4, #154C86); border-bottom: 1px solid rgba(255,255,255,.18); }
.tb-title { font-size: 13.5px; font-weight: 800; color: #FFF6DC; letter-spacing: .4px; text-shadow: 0 1px 2px rgba(0,0,0,.45); }
.tb-sub { font-size: 8.5px; letter-spacing: 2px; color: #9FC3E0; }
.wbtn { width: 30px; height: 24px; border-radius: 6px; color: #CFE6FA; font-size: 12px; display: grid; place-items: center; transition: background .14s, color .14s; }
.wbtn:hover { background: rgba(255,255,255,.16); color: #fff; }
.wbtn.close:hover { background: #D84A3F; }
.panel { background: linear-gradient(180deg, rgba(26,92,150,.92), rgba(11,46,82,.94)); border: 2px solid rgba(255,255,255,.20); border-radius: 14px; box-shadow: inset 0 1px 0 rgba(255,255,255,.26), 0 6px 16px rgba(0,0,0,.26); }
.sec-title { font-size: 10.5px; font-weight: 800; color: #FFC93C; letter-spacing: .5px; }
.card { position: relative; display: flex; flex-direction: column; align-items: center; padding: 5px 4px 4px; border-radius: 14px; border: 2px solid rgba(255,255,255,.20); background: linear-gradient(180deg, rgba(23,83,140,.85), rgba(11,46,82,.85)); cursor: pointer; transition: transform .16s, box-shadow .16s, border-color .16s; }
.card:hover { transform: translateY(-2px); border-color: rgba(255,255,255,.45); }
.card.on { border-color: #FFC93C; box-shadow: 0 0 0 3px rgba(255,201,60,.18), 0 8px 18px rgba(0,0,0,.25); }
.card.over { border-color: #FFC93C; box-shadow: 0 0 0 3px rgba(255,201,60,.38); }
.card.filled .orb { border-color: rgba(255,201,60,.75); }
.orb { width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; overflow: hidden; border: 2px solid rgba(255,255,255,.55); box-shadow: inset 0 2px 4px rgba(255,255,255,.25), 0 2px 6px rgba(0,0,0,.25); font-size: 18px; font-weight: 800; color: #fff; }
.pchip { height: 22px; max-width: 64px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 8px; border-radius: 7px; border: 1px solid rgba(255,255,255,.25); font-size: 10.5px; color: #CFE6FA; transition: all .14s; }
.pchip:hover { background: rgba(255,255,255,.12); }
.pchip.on { background: linear-gradient(180deg,#FFD96B,#F0A21E); border-color: #8A4B0F; color: #4A2A0C; font-weight: 800; }
.pbtn { height: 22px; padding: 0 7px; border-radius: 7px; border: 1px solid rgba(255,255,255,.22); font-size: 10px; color: #CFE6FA; transition: background .14s; }
.pbtn:hover { background: rgba(255,255,255,.12); }
.slot { width: 36px; height: 36px; border-radius: 9px; border: 2px solid rgba(255,255,255,.25); display: grid; place-items: center; overflow: hidden; background: rgba(11,46,82,.55); transition: transform .14s, border-color .14s, box-shadow .14s; }
.slot:hover { transform: translateY(-1px) scale(1.04); }
.slot.on { border-color: #FFC93C; }
.slot.over { border-color: #FFC93C; box-shadow: 0 0 0 3px rgba(255,201,60,.35); }
.slot.done { opacity: .42; }
.btn { height: 34px; padding: 0 14px; border-radius: 10px; border: 1.5px solid rgba(255,255,255,.35); background: rgba(255,255,255,.10); color: #FFF6DC; font-size: 12.5px; font-weight: 700; transition: background .15s, transform .1s; }
.btn:hover { background: rgba(255,255,255,.18); }
.btn:active { transform: translateY(1px); }
.btn-gold { height: 36px; padding: 0 18px; border-radius: 11px; border: 2px solid #8A4B0F; background: linear-gradient(180deg,#FFD96B,#F0A21E); color: #4A2A0C; font-size: 13px; font-weight: 800; box-shadow: 0 4px 0 #8A4B0F, 0 8px 14px rgba(0,0,0,.22); transition: transform .08s, box-shadow .08s; }
.btn-gold:hover { filter: brightness(1.05); }
.btn-gold:active { transform: translateY(3px); box-shadow: 0 1px 0 #8A4B0F; }
.btn-gold kbd { margin-left: 6px; border-radius: 4px; background: rgba(0,0,0,.14); padding: 1px 4px; font-size: 9px; }
.status { background: linear-gradient(180deg, rgba(15,58,100,.85), rgba(9,40,72,.85)); }
.log { scrollbar-width: thin; }
.log::-webkit-scrollbar { width: 6px; }
.log::-webkit-scrollbar-thumb { background: rgba(255,255,255,.22); border-radius: 3px; }
.toast-enter-active, .toast-leave-active { transition: opacity .16s ease, transform .16s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, 10px); }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(255,201,60,.5); } 50% { box-shadow: 0 0 0 7px rgba(255,201,60,0); } }
.armed { animation: pulse 1.6s infinite; }
.toast { position: fixed; left: 50%; bottom: 14px; transform: translateX(-50%); z-index: 20; border-radius: 10px; border: 2px solid; padding: 6px 14px; font-size: 12px; font-weight: 800; box-shadow: 0 8px 20px rgba(0,0,0,.35); }
.toast.ok { border-color: #8A4B0F; background: #FFC93C; color: #4A2A0C; }
.toast.err { border-color: #7A1F1A; background: #E5533D; color: #fff; }
</style>
