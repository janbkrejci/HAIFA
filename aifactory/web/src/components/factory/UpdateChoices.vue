<script setup lang="ts">
import { toRaw } from 'vue'
import type { FactoryUpdatePlan, FactoryOptions } from '@/lib/api'
import DiffContent from '@/components/review/DiffContent.vue'
const props = defineProps<{ plan: FactoryUpdatePlan; options: FactoryOptions }>()
const emit = defineEmits<{ change: [options: FactoryOptions] }>()
const groups = [ { title: 'Aktualizuje se z knihovny', statuses: ['take','taken','merged','restore'] }, { title: 'Ponechá se změna v repu', statuses: ['keep'] }, { title: 'Změněno v obou', statuses: ['conflict','unknown'] } ]
function choose(key: 'take' | 'merge' | 'migrate', selector: string) {
  const value = structuredClone(toRaw(props.options))
  value[key] = value[key]?.includes(selector) ? value[key]!.filter(s => s !== selector) : [...(value[key] ?? []), selector]
  if (key === 'merge') value.take = value.take?.filter(s => s !== selector && !s.startsWith(selector + ':'))
  if (key === 'take') value.merge = value.merge?.filter(s => s !== selector.split(':')[0])
  emit('change', value)
}
</script>
<template>
  <div v-for="s in options.take" :key="s"><button type="button" @click="choose('take',s)">Zrušit převzetí {{ s }}</button></div>
  <div v-for="s in options.merge" :key="s"><button type="button" @click="choose('merge',s)">Zrušit sloučení {{ s }}</button></div>
  <section v-for="group in groups" :key="group.title">
    <h3>{{ group.title }}</h3>
    <template v-for="item in plan.update?.items" :key="`${item.type}/${item.name}`">
      <div v-for="file in item.files.filter(f => group.statuses.includes(f.status))" :key="file.file">
        <p>{{ item.type }}/{{ item.name }}:{{ file.file }} — {{ file.status }}</p>
        <template v-if="['conflict','unknown'].includes(file.status)">
          <label><input type="checkbox" :checked="options.take?.includes(`${item.type}/${item.name}:${file.file}`)" @change="choose('take', `${item.type}/${item.name}:${file.file}`)">Převzít</label>
          <label v-if="item.merge_available"><input type="checkbox" :checked="options.merge?.includes(`${item.type}/${item.name}`)" @change="choose('merge', `${item.type}/${item.name}`)">Sloučit</label>
          <p>Změna v repu</p><DiffContent :patch="file.ours_diff" />
          <p>Změna v knihovně</p><DiffContent :patch="file.theirs_diff" />
        </template>
        <DiffContent v-if="file.diff" :patch="file.diff" />
      </div>
    </template>
  </section>
  <section><h3>Migrace</h3>
    <div v-for="m in plan.update?.migrations" :key="m.id">
      <label><input type="checkbox" :checked="options.migrate?.includes(m.id)" @change="choose('migrate', m.id)">{{ m.title }} ({{ m.id }})</label>
      <DiffContent :patch="m.diff" />
    </div>
  </section>
</template>
