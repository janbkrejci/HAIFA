<script setup lang="ts">
// Shared markdown view: rendered preview (default) or raw source, switched by tabs.
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/lib/markdown'

const props = defineProps<{ source: string; empty?: string }>()

const mode = ref<'preview' | 'source'>('preview')
const html = computed(() => renderMarkdown(props.source))
const blank = computed(() => !props.source.trim())
</script>

<template>
  <div class="mdview">
    <p v-if="blank" class="faint" data-test="md-empty">{{ empty ?? '—' }}</p>
    <template v-else>
      <div class="md-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          data-test="md-tab-preview"
          :class="{ active: mode === 'preview' }"
          :aria-selected="mode === 'preview'"
          @click="mode = 'preview'"
        >
          Náhled
        </button>
        <button
          type="button"
          role="tab"
          data-test="md-tab-source"
          :class="{ active: mode === 'source' }"
          :aria-selected="mode === 'source'"
          @click="mode = 'source'"
        >
          Zdroj
        </button>
      </div>
      <div v-if="mode === 'preview'" class="md" data-test="md-preview" v-html="html" />
      <pre v-else class="md-source" data-test="md-source">{{ source }}</pre>
    </template>
  </div>
</template>
