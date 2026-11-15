<script setup lang="ts">
import { locale, setLocale, t } from '@/lib/i18n'
import SelectMenu from './ui/SelectMenu.vue'
</script>

<template>
  <SelectMenu
    :model-value="locale"
    :options="[{ value: 'en', label: 'English' }, { value: 'cs', label: 'Čeština' }]"
    :label="t('shell.language')"
    data-test="language-select"
    @update:model-value="setLocale"
  />
</template>
