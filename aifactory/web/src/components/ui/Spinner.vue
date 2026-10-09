<script setup lang="ts">
// The shared busy indicator: shown inside the clicked button while its action runs.
// Its look (and the `spin` class of a refreshing icon) lives in style.css, the same everywhere.
withDefaults(defineProps<{ size?: number }>(), { size: 14 })
</script>

<template>
  <span
    class="spinner"
    data-test="spinner"
    aria-hidden="true"
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
</template>
