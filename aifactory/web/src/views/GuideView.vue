<script setup lang="ts">
// #/guide[/<chapter>[/<section>]]: the user and administrator guide. Chapters on the left with
// the sections of the open one and a search over all of them; the chapter rendered on the right.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { BookOpen, Search } from 'lucide-vue-next'
import { errorText } from '@/lib/format'
import { fetchGuide, search, sections, type GuideChapter } from '@/lib/guide'
import { renderMarkdown } from '@/lib/markdown'
import { guideHref, useRouteParams } from '@/lib/router'
import Spinner from '@/components/ui/Spinner.vue'

const params = useRouteParams()
const chapters = ref<GuideChapter[] | null>(null)
const error = ref('')
const query = ref('')
const article = ref<HTMLElement | null>(null)

const current = computed<GuideChapter | null>(() => {
  const list = chapters.value ?? []
  return list.find((c) => c.id === params.value[0]) ?? list[0] ?? null
})
const currentSections = computed(() => (current.value ? sections(current.value.markdown).filter((s) => s.id) : []))
const html = computed(() => (current.value ? renderMarkdown(current.value.markdown) : ''))
const hits = computed(() => search(chapters.value ?? [], query.value))
const index = computed(() => (chapters.value ?? []).findIndex((c) => c.id === current.value?.id))
const previous = computed(() => (chapters.value ?? [])[index.value - 1] ?? null)
const next = computed(() => (index.value < 0 ? null : (chapters.value ?? [])[index.value + 1] ?? null))

/** Give the rendered `## ` headings their section ids and scroll to the one in the URL. */
async function place(): Promise<void> {
  await nextTick()
  const root = article.value
  if (!root) return
  const heads = Array.from(root.querySelectorAll('h2'))
  heads.forEach((h, i) => { h.id = currentSections.value[i]?.id ?? '' })
  const target = params.value[1]
  const el = target ? heads.find((h) => h.id === target) : null
  if (el) el.scrollIntoView({ block: 'start' })
  else window.scrollTo({ top: 0 })
}

watch([html, () => params.value[1]], () => { void place() })

onMounted(async () => {
  try {
    chapters.value = await fetchGuide()
    void place()
  } catch (err) {
    error.value = errorText(err)
  }
})
</script>

<template>
  <section class="guide" data-test="guide">
    <div v-if="error" class="guide-error" data-test="guide-error">Příručku se nepodařilo načíst: {{ error }}</div>
    <div v-else-if="chapters === null" class="guide-loading"><Spinner /> Načítám příručku…</div>
    <div v-else class="guide-layout">
      <nav class="guide-nav" aria-label="Kapitoly příručky">
        <h1><BookOpen :size="20" aria-hidden="true" /> Příručka</h1>
        <label class="guide-search">
          <Search :size="15" aria-hidden="true" />
          <input v-model="query" type="search" placeholder="Hledat v příručce" aria-label="Hledat v příručce" data-test="guide-search" />
        </label>
        <ol v-if="!query.trim()" class="guide-chapters">
          <li v-for="c in chapters" :key="c.id">
            <a :href="guideHref(c.id)" :class="{ active: c.id === current?.id }" :data-test="`guide-chapter-${c.id}`">{{ c.title }}</a>
            <ul v-if="c.id === current?.id && currentSections.length" class="guide-sections">
              <li v-for="s in currentSections" :key="s.id">
                <a :href="guideHref(c.id, s.id)" :class="{ active: s.id === params[1] }">{{ s.title }}</a>
              </li>
            </ul>
          </li>
        </ol>
        <div v-else class="guide-hits" data-test="guide-hits">
          <p v-if="!hits.length" class="faint">Nic nenalezeno.</p>
          <a
            v-for="h in hits"
            :key="`${h.chapter.id}/${h.section.id}`"
            class="guide-hit"
            :href="guideHref(h.chapter.id, h.section.id || null)"
            data-test="guide-hit"
            @click="query = ''"
          >
            <strong>{{ h.chapter.title }}<template v-if="h.section.title"> › {{ h.section.title }}</template></strong>
            <span>{{ h.snippet }}</span>
          </a>
        </div>
      </nav>
      <article class="guide-article">
        <div ref="article" class="md" data-test="guide-article" v-html="html" />
        <footer class="guide-pager">
          <a v-if="previous" :href="guideHref(previous.id)" data-test="guide-previous">← {{ previous.title }}</a>
          <span v-else />
          <a v-if="next" :href="guideHref(next.id)" data-test="guide-next">{{ next.title }} →</a>
        </footer>
      </article>
    </div>
  </section>
</template>

<style scoped>
.guide {
  padding: 28px;
  max-width: 1280px;
  margin: 0 auto;
}

.guide-loading,
.guide-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--dim);
}

.guide-error {
  color: var(--red);
}

.guide-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.guide-nav {
  position: sticky;
  top: 84px;
  max-height: calc(100vh - 104px);
  overflow-y: auto;
}

.guide-nav h1 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  font-size: 22px;
}

.guide-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  margin-bottom: 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--dim);
}

.guide-search input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  outline: none;
}

.guide-chapters,
.guide-sections {
  list-style: none;
  margin: 0;
  padding: 0;
}

.guide-chapters > li {
  margin: 2px 0;
}

.guide-chapters a {
  display: block;
  padding: 5px 10px;
  border-radius: 6px;
  color: var(--text);
  text-decoration: none;
}

.guide-chapters a:hover {
  background: var(--panel-2);
}

.guide-chapters a.active {
  background: var(--panel-2);
  color: var(--purple);
  font-weight: 700;
}

.guide-sections {
  margin: 2px 0 8px 12px;
  border-left: 1px solid var(--border-soft);
}

.guide-sections a {
  padding: 3px 10px;
  font-size: 14px;
  color: var(--dim);
  font-weight: 400;
}

.guide-sections a.active {
  color: var(--cyan);
  font-weight: 400;
}

.guide-hits {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.guide-hit {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  color: var(--text);
  text-decoration: none;
  font-size: 14px;
}

.guide-hit:hover {
  background: var(--panel-2);
}

.guide-hit span {
  color: var(--dim);
}

.guide-article {
  padding: 24px 32px;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.guide-article :deep(h1) {
  font-size: 26px;
  margin-bottom: 14px;
}

.guide-article :deep(h2) {
  font-size: 20px;
  margin-top: 28px;
  padding-top: 8px;
  border-top: 1px solid var(--border-soft);
  scroll-margin-top: 84px;
}

.guide-article :deep(pre.md-code) {
  padding: 10px 14px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--panel-2);
  overflow-x: auto;
}

.guide-pager {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 28px;
  padding-top: 14px;
  border-top: 1px solid var(--border-soft);
}

.guide-pager a {
  color: var(--blue);
  text-decoration: none;
}

@media (max-width: 900px) {
  .guide-layout {
    grid-template-columns: 1fr;
  }

  .guide-nav {
    position: static;
    max-height: none;
  }
}
</style>
