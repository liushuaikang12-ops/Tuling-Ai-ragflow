<script setup lang="ts">
import { ref, computed } from 'vue';

type ChatMode = 'agent' | 'knowledge' | 'writing';

interface Props {
  isLoading?: boolean;
  isWaitingInteraction?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  isLoading: false,
  isWaitingInteraction: false,
});

const message = ref('');
const isFocused = ref(false);
const selectedMode = ref<ChatMode>('agent');
const modeOptions: Array<{ value: ChatMode; label: string; description: string }> = [
  { value: 'agent', label: '智能体模式', description: '自动分析并选择处理流程' },
  { value: 'knowledge', label: '知识库模式', description: '检索已上传的文档' },
  { value: 'writing', label: '写作模式', description: '进入写作与审阅流程' },
];
const emit = defineEmits<{
  send: [message: string, mode: ChatMode];
  pause: [];
}>();

const hasContent = computed(() => message.value.trim().length > 0);
const isDisabled = computed(() => props.isLoading || props.isWaitingInteraction);
const currentMode = computed(() => modeOptions.find(item => item.value === selectedMode.value)!);

const sendMessage = () => {
  if (!message.value.trim() || isDisabled.value) return;
  emit('send', message.value, selectedMode.value);
  message.value = '';
};

const pauseGeneration = () => {
  emit('pause');
};
</script>

<template>
  <div class="chat-input" :class="{ 'chat-input--focused': isFocused }">
    <div class="chat-input__modes" role="tablist" aria-label="对话模式">
      <button
        v-for="mode in modeOptions"
        :key="mode.value"
        type="button"
        role="tab"
        class="chat-input__mode"
        :class="{ 'chat-input__mode--active': selectedMode === mode.value }"
        :aria-selected="selectedMode === mode.value"
        :disabled="isDisabled"
        :title="mode.description"
        @click="selectedMode = mode.value"
      >
        <span class="chat-input__mode-label">{{ mode.label }}</span>
        <span class="chat-input__mode-description">{{ mode.description }}</span>
      </button>
    </div>

    <div class="chat-input__wrapper">
      <!-- 输入框 -->
      <div class="chat-input__field-wrapper">
        <input
          v-model="message"
          @keyup.enter="sendMessage"
          @focus="isFocused = true"
          @blur="isFocused = false"
          :placeholder="isWaitingInteraction ? '请先完成上方的交互操作...' : (isLoading ? 'AI 正在回复中...' : `${currentMode.label}：${currentMode.description}`)"
          type="text"
          class="chat-input__field"
          :disabled="isDisabled"
        />
        <div class="chat-input__indicator" v-if="message.length > 0 && !isDisabled">
          <span class="chat-input__char-count">{{ message.length }}</span>
        </div>
      </div>

      <!-- 发送/暂停按钮 -->
      <button
        v-if="!isLoading"
        @click="sendMessage"
        :disabled="!hasContent || isWaitingInteraction"
        class="chat-input__send"
        :class="{ 'chat-input__send--active': hasContent && !isWaitingInteraction }"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
        </svg>
      </button>

      <!-- 暂停按钮 -->
      <button
        v-else
        @click="pauseGeneration"
        class="chat-input__pause"
        title="停止生成"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      </button>
    </div>

    <!-- 提示文字 -->
    <div class="chat-input__hints">
      <template v-if="isWaitingInteraction">
        <span class="chat-input__hint chat-input__hint--warning">
          请先完成上方的交互操作
        </span>
      </template>
      <template v-else-if="!isLoading">
        <span class="chat-input__hint chat-input__hint--mode">
          当前：{{ currentMode.label }}
        </span>
        <span class="chat-input__hint">
          按 <kbd>Enter</kbd> 发送
        </span>
        <span class="chat-input__hint">
          <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行
        </span>
      </template>
      <template v-else>
        <span class="chat-input__hint chat-input__hint--loading">
          AI 正在生成回复，点击停止按钮可中断
        </span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  padding: var(--space-4);
  background-color: var(--color-bg-elevated);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border);
  transition: all var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.chat-input--focused {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-subtle), var(--shadow-md);
}

.chat-input__modes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.chat-input__mode {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  text-align: left;
  transition: all var(--transition-fast);
}

.chat-input__mode:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  background-color: var(--color-bg-tertiary);
}

.chat-input__mode--active {
  border-color: var(--color-accent);
  background-color: var(--color-accent-subtle);
  color: var(--color-accent);
}

.chat-input__mode:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.chat-input__mode-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.chat-input__mode-description {
  overflow: hidden;
  width: 100%;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-input__wrapper {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

/* 知识库开关按钮 */
.chat-input__knowledge {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all var(--transition-fast);
  flex-shrink: 0;
  background-color: var(--color-bg-secondary);
  color: var(--color-text-tertiary);
  border: 1px solid var(--color-border);
}

.chat-input__knowledge:hover:not(:disabled) {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border-color: var(--color-border-hover);
}

.chat-input__knowledge--active {
  background-color: var(--color-accent-subtle);
  color: var(--color-accent);
  border-color: var(--color-accent);
}

.chat-input__knowledge--active:hover:not(:disabled) {
  background-color: var(--color-accent);
  color: white;
}

.chat-input__knowledge--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 输入框 */
.chat-input__field-wrapper {
  flex: 1;
  position: relative;
  min-width: 0;
}

.chat-input__field {
  width: 100%;
  padding: var(--space-3);
  background: transparent;
  border: none;
  font-size: var(--text-base);
  color: var(--color-text);
  outline: none;
  box-sizing: border-box;
}

.chat-input__field:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.chat-input__field::placeholder {
  color: var(--color-text-tertiary);
}

.chat-input__indicator {
  position: absolute;
  right: 0;
  bottom: -4px;
}

.chat-input__char-count {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* 发送按钮 */
.chat-input__send {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-tertiary);
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.chat-input__send--active {
  background: linear-gradient(135deg, var(--color-accent), var(--color-accent-dark));
  color: white;
  box-shadow: 0 4px 12px rgba(74, 108, 247, 0.3);
}

.chat-input__send--active:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(74, 108, 247, 0.4);
}

.chat-input__send:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

/* 暂停按钮 */
.chat-input__pause {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all var(--transition-fast);
  flex-shrink: 0;
  animation: pulse-border 2s ease-in-out infinite;
}

.chat-input__pause:hover {
  background-color: var(--color-error);
  color: white;
  border-color: var(--color-error);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
}

@keyframes pulse-border {
  0%, 100% {
    border-color: var(--color-border);
  }
  50% {
    border-color: var(--color-error);
  }
}

/* 提示文字 */
.chat-input__hints {
  display: flex;
  justify-content: center;
  gap: var(--space-4);
  margin-top: var(--space-2);
}

.chat-input__hint {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.chat-input__hint--loading {
  color: var(--color-warning);
  animation: fade-pulse 1.5s ease-in-out infinite;
}

.chat-input__hint--warning {
  color: var(--color-warning);
  font-weight: var(--font-medium);
}

.chat-input__hint--mode {
  color: var(--color-accent);
  font-weight: var(--font-medium);
}

@media (max-width: 720px) {
  .chat-input__mode-description {
    display: none;
  }

  .chat-input__mode {
    align-items: center;
    text-align: center;
  }
}

@keyframes fade-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.chat-input__hint kbd {
  display: inline-block;
  padding: 2px 6px;
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 11px;
  border: 1px solid var(--color-border);
}
</style>
