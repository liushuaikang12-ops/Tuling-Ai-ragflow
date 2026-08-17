<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useUserStore } from '../stores/user';
import { useSidebar } from '../composables/useSidebar';
import MainLayout from '../layouts/MainLayout.vue';

type DetailTone = 'normal' | 'accent' | 'warning';

interface GuideDetail {
  title: string;
  text: string;
  tone?: DetailTone;
}

interface GuideStep {
  label: string;
  title: string;
  description: string;
  input: string;
  output: string;
  modules: string[];
  details: GuideDetail[];
}

interface GuideSection {
  id: string;
  index: string;
  eyebrow: string;
  title: string;
  subtitle: string;
  status: string;
  steps: GuideStep[];
}

const router = useRouter();
const userStore = useUserStore();
const { isExpanded, toggleSidebar } = useSidebar();

if (!userStore.userId) {
  router.push('/');
}

const sections: GuideSection[] = [
  {
    id: 'llamaindex',
    index: '01',
    eyebrow: '数据接入 · 可选 Legacy 链路',
    title: 'LlamaIndex 把不同文件变成可检索的数据节点',
    subtitle: '读取、标准化、分块、建立双索引，再通过混合检索与重排返回带来源的答案。',
    status: '仅在 RAG_BACKEND=legacy 时启用',
    steps: [
      {
        label: '文件接入',
        title: '文档从统一上传接口进入摄取管道',
        description: '前端 multipart 上传经过 main_service 转发到 rag_api_service，原始文件保留稳定文档 ID 和基础元数据。',
        input: 'PDF / DOCX / TXT / MD / CSV',
        output: 'Document + metadata',
        modules: ['REST Upload', 'SimpleDirectoryReader', '稳定 doc_id'],
        details: [
          { title: '统一入口', text: '调用方不需要理解解析器，只负责上传文件和可选分块参数。' },
          { title: '格式分流', text: 'PDF 进入专用多模态处理器，普通文本由 LlamaIndex Reader 读取。' },
          { title: '可追溯', text: '文件名、类型、上传时间和 doc_id 会随节点进入后续索引。', tone: 'accent' },
        ],
      },
      {
        label: '内容标准化',
        title: '把不同文件统一为 LlamaIndex Document',
        description: '普通文本直接标准化；PDF 先转换为 Markdown，并把提取图片保存到独立目录。',
        input: '原始文件与二进制内容',
        output: '统一 Markdown / 文本语义',
        modules: ['MultimodalPDFProcessor', 'PDF → Markdown', 'Metadata'],
        details: [
          { title: '普通文档', text: 'SimpleDirectoryReader 读取正文并补充稳定元数据。' },
          { title: 'PDF 文档', text: 'MultimodalPDFProcessor 转换 Markdown，同时提取页面图片。' },
          { title: '职责边界', text: '这是旧版可选实现；当前默认解析由 RAGFlow 完成。', tone: 'warning' },
        ],
      },
      {
        label: '语义分块',
        title: '长文档被切成可独立召回的语义节点',
        description: 'SentenceSplitter 根据 chunk_size 和 chunk_overlap 切分，同时保留文档级元数据与上下文连续性。',
        input: 'Document',
        output: 'Node[]',
        modules: ['SentenceSplitter', 'chunk_size', 'chunk_overlap'],
        details: [
          { title: '控制粒度', text: '块太大影响召回精度，块太小会损失上下文。' },
          { title: '上下文重叠', text: '相邻节点保留少量重复文本，减少句意被截断。' },
          { title: '结构保留', text: '每个节点都能追溯到原始文件和文档 ID。', tone: 'accent' },
        ],
      },
      {
        label: '双路索引',
        title: '向量语义与 BM25 关键词同时建索引',
        description: 'Chroma 保存向量表示，BM25 保存词项统计。两条检索通道互补，兼顾语义相似与精确关键词。',
        input: 'Node[]',
        output: 'Chroma + BM25',
        modules: ['Embedding', 'ChromaDB', 'BM25Retriever'],
        details: [
          { title: '向量通道', text: '适合表达不同但语义相近的问题。' },
          { title: '关键词通道', text: '适合专有名词、编号、公式符号和精确短语。' },
          { title: '本地持久化', text: '索引分别保存在 chroma_db 与 storage_bm25。', tone: 'accent' },
        ],
      },
      {
        label: '检索重排',
        title: '候选节点合并后重排，再交给生成模型',
        description: '向量与 BM25 候选合并，SentenceTransformerRerank 重新排序，最终生成 answer 和 sources。',
        input: '用户问题',
        output: 'answer + sources',
        modules: ['Hybrid Retriever', 'Reranker', 'Response Synthesizer'],
        details: [
          { title: '扩大召回', text: '先从两条通道获得更完整的候选集合。' },
          { title: '提高精度', text: '重排模型根据问题与片段的真实相关度重新打分。' },
          { title: '来源可见', text: '最终答案附带原文片段，便于核验与展开查看。', tone: 'accent' },
        ],
      },
    ],
  },
  {
    id: 'langgraph',
    index: '02',
    eyebrow: '智能编排 · 三种交互模式',
    title: 'LangGraph 决定这一轮应该检索、写作还是对话',
    subtitle: '同一个线程保存上下文，前端显式模式优先，智能体模式再由意图路由器自动选择工作流。',
    status: '当前运行中 · DeepSeek 文本模型',
    steps: [
      {
        label: '接收状态',
        title: '消息、用户与会话被映射到独立线程',
        description: 'main_service 将用户名和 conversation_id 映射为确定性 UUID，确保不同用户、不同会话相互隔离。',
        input: 'query + mode + conversation_id',
        output: 'GraphState',
        modules: ['JWT User', 'UUID5 Thread', 'PostgreSQL Checkpoint'],
        details: [
          { title: '用户隔离', text: '相同会话稳定映射到同一个 LangGraph Thread。' },
          { title: '重启恢复', text: '检查点保存在 PostgreSQL，服务重启后仍可继续会话。' },
          { title: '模式显式传递', text: 'agent、knowledge、writing 通过请求字段进入图状态。', tone: 'accent' },
        ],
      },
      {
        label: '短期记忆',
        title: '长对话先摘要，再进入意图路由',
        description: 'SummarizationNode 保留历史摘要和最近消息，避免上下文无限增长，同时维持连续对话。',
        input: '完整消息历史',
        output: '摘要 + 最近消息',
        modules: ['LangMem', 'SummarizationNode', 'RunningSummary'],
        details: [
          { title: '保留重点', text: '旧消息压缩为摘要，近期消息保持原文。' },
          { title: '控制上下文', text: '减少模型输入长度和长对话成本。' },
          { title: '知识模式兼容', text: '未配置文本模型时可透传消息，不阻塞纯知识检索。', tone: 'accent' },
        ],
      },
      {
        label: '三种模式',
        title: '前端选择决定主图的第一条分支',
        description: '知识库与写作模式直接进入对应工作流；智能体模式分析当前意图后再选择聊天、知识或写作节点。',
        input: 'mode',
        output: 'intent',
        modules: ['agent', 'knowledge', 'writing'],
        details: [
          { title: '智能体模式', text: 'summarize → intent_router → chat / knowledge / writing，适合通用任务。' },
          { title: '知识库模式', text: 'knowledge_agent → MCP query_rag → quality guard → finalize。', tone: 'accent' },
          { title: '写作模式', text: 'writing_workflow → 需求理解 → 大纲 → 草稿 → 审核 → 人工确认。', tone: 'warning' },
        ],
      },
      {
        label: '知识检索',
        title: '知识智能体通过 MCP 访问唯一的 RAG 查询工具',
        description: 'LangGraph 不包含解析和索引代码，只调用 mcp_service.query_rag，再由纯代理访问 rag_api_service。',
        input: '用户问题',
        output: '检索答案与来源',
        modules: ['knowledge_agent', 'MCP', 'knowledge_guard'],
        details: [
          { title: '服务解耦', text: 'LangGraph 只理解工具协议，不依赖 RAGFlow 或 Legacy 实现细节。' },
          { title: '质量守卫', text: '空答案或失败答案会进入 fallback_search。' },
          { title: '来源绑定', text: 'sources 写入 AIMessage 元数据，历史消息仍能展示来源。', tone: 'accent' },
        ],
      },
      {
        label: '写作子图',
        title: '文章在多节点循环中生成和审校',
        description: '需求不清晰会中断并提问；审核不通过自动修订；草稿完成后等待用户确认、编辑或重写。',
        input: '写作需求',
        output: 'Markdown 成稿',
        modules: ['understand', 'outline', 'draft', 'review', 'human_review'],
        details: [
          { title: '澄清循环', text: 'understand ↔ ask_clarification，直到主题与方向明确。' },
          { title: '质量循环', text: 'review ↔ revise，直到审核结论通过。' },
          { title: '人工控制', text: '用户可确认、直接修改或要求重新生成草稿。', tone: 'accent' },
        ],
      },
    ],
  },
  {
    id: 'ragflow',
    index: '03',
    eyebrow: '文档理解 · 当前默认链路',
    title: 'RAGFlow 把复杂版面拆成可检索的文本、公式、图片和表格',
    subtitle: '上传后异步完成版面分析、多模态识别、语义分块与向量索引，项目只通过适配层管理任务和查询。',
    status: '当前默认 · RAG_BACKEND=ragflow',
    steps: [
      {
        label: '上传入库',
        title: '文件进入独立的 RAGFlow Dataset',
        description: 'rag_api_service 把文件转发到 Tuling-AI Dataset，立即返回文档 ID，解析任务在 RAGFlow 中异步执行。',
        input: 'multipart files',
        output: 'document_id + task',
        modules: ['RAGFlow REST API', 'Dataset', '异步解析'],
        details: [
          { title: '统一知识库', text: '上传、列表、删除、分块和检索都围绕同一个 Dataset。' },
          { title: '异步处理', text: '大文件上传后不会阻塞前端，页面可以持续查询解析进度。' },
          { title: '完全解耦', text: 'RAGFlow 模式不会导入 LlamaIndex、Chroma 或旧 PDF 解析器。', tone: 'accent' },
        ],
      },
      {
        label: '页面与版面',
        title: 'DeepDoc 先理解页面结构，再决定内容类型',
        description: 'PDF 页面被渲染并进行布局分析，标题、段落、图片、表格和公式区域被定位，阅读顺序得到恢复。',
        input: 'PDF 页面 / Office 内容',
        output: '带坐标的布局区域',
        modules: ['DeepDoc', 'Layout Analysis', 'Reading Order'],
        details: [
          { title: 'OCR 文本', text: '扫描件先经过文字检测与识别，输出可搜索文本。' },
          { title: '版面区域', text: '区域类型与坐标帮助恢复多栏、标题和段落顺序。' },
          { title: '结构优先', text: '先识别“这是什么”，再决定如何抽取，减少简单纯文本解析造成的错序。', tone: 'accent' },
        ],
      },
      {
        label: '多模态识别',
        title: '公式、图片和表格走各自的识别模块',
        description: '复杂区域不会被当成普通段落硬拆：公式保留表达，图片生成语义描述，表格尽量恢复行列结构。',
        input: '布局区域 + 页面图像',
        output: '结构化多模态内容',
        modules: ['Formula Region', 'GLM Vision', 'Table Structure'],
        details: [
          { title: '公式识别', text: '检测公式区域并保留公式表达；扫描质量会影响符号与上下标准确率。', tone: 'warning' },
          { title: '图片识别', text: '提取图片区域，由已配置的 GLM 视觉模型生成可检索语义描述。', tone: 'accent' },
          { title: '表格识别', text: '定位表格边界和单元格关系，将行列内容组织为可进入分块的结构化文本。', tone: 'accent' },
        ],
      },
      {
        label: '语义分块',
        title: '解析结果按结构与语义组织成 Chunk',
        description: '标题、正文和多模态描述被组合为检索单元，Chunk 保留文档名、页码、位置等来源信息。',
        input: '结构化解析结果',
        output: 'chunks + metadata',
        modules: ['Chunk Method', 'Metadata', 'Page Position'],
        details: [
          { title: '不是盲切字符', text: '尽量沿标题、段落和内容区域边界形成检索单元。' },
          { title: '多模态入块', text: '图片说明、表格文本和公式表达能够随相邻上下文进入索引。' },
          { title: '来源定位', text: '召回结果保留文档与页面信息，前端可以展示相关来源。', tone: 'accent' },
        ],
      },
      {
        label: '向量索引',
        title: '本地 TEI 把 Chunk 转换为语义向量',
        description: 'Qwen3-Embedding-0.6B 在本地 TEI 服务中生成 1024 维向量，RAGFlow 负责写入检索索引。',
        input: 'chunk text',
        output: '1024-d embedding',
        modules: ['TEI CPU', 'Qwen3-Embedding-0.6B', 'Elasticsearch'],
        details: [
          { title: '本地嵌入', text: 'Embedding 不依赖外部 API，文档向量化在本地完成。' },
          { title: '混合召回', text: '查询阶段组合语义向量和文本相关性，而不是只靠单一路径。' },
          { title: '后端透明', text: '上层始终消费统一 answer / sources，不关心索引实现。', tone: 'accent' },
        ],
      },
      {
        label: '检索回答',
        title: '召回片段沿微服务链路返回给用户',
        description: 'query_rag 从 RAGFlow 获取候选 Chunk，适配为 answer 和 sources，再由 LangGraph 质量守卫决定直接输出或降级。',
        input: 'query',
        output: 'answer + sources',
        modules: ['Retrieval', 'rag_api_service', 'MCP', 'knowledge_guard'],
        details: [
          { title: '链路清晰', text: 'LangGraph → MCP → rag_api_service → RAGFlow。' },
          { title: '原文兜底', text: '即使未启用额外答案生成，也可以直接返回高相关原文片段。' },
          { title: '可验证回答', text: '每次知识回答携带来源，用户可以展开核对。', tone: 'accent' },
        ],
      },
    ],
  },
];

const activeSectionId = ref('ragflow');
const activeStepIndex = ref(0);

const activeSection = computed(
  () => sections.find(section => section.id === activeSectionId.value) || sections[0],
);
const activeStep = computed(() => activeSection.value.steps[activeStepIndex.value]);
const progress = computed(
  () => ((activeStepIndex.value + 1) / activeSection.value.steps.length) * 100,
);

function selectSection(id: string) {
  activeSectionId.value = id;
  activeStepIndex.value = 0;
}

function selectStep(index: number) {
  activeStepIndex.value = index;
}

function previousStep() {
  if (activeStepIndex.value > 0) activeStepIndex.value -= 1;
}

function nextStep() {
  if (activeStepIndex.value < activeSection.value.steps.length - 1) {
    activeStepIndex.value += 1;
  } else {
    const sectionIndex = sections.findIndex(section => section.id === activeSectionId.value);
    selectSection(sections[(sectionIndex + 1) % sections.length].id);
  }
}
</script>

<template>
  <MainLayout :show-sidebar="true">
    <div class="guide-page">
      <header class="guide-page__header">
        <button
          v-if="!isExpanded"
          class="guide-page__menu-btn"
          type="button"
          aria-label="展开侧边栏"
          @click="toggleSidebar"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12h18M3 6h18M3 18h18" />
          </svg>
        </button>
        <div>
          <span class="guide-page__brand">帅康 AI · 使用说明</span>
          <p>点击模块与步骤，查看系统内部的数据流转</p>
        </div>
        <button class="guide-page__back" type="button" @click="router.push('/chat')">返回对话</button>
      </header>

      <main class="guide-page__content">
        <section class="guide-hero">
          <div class="guide-hero__eyebrow">
            <span>{{ activeSection.index }}</span>
            <span>·</span>
            <span>{{ activeSection.eyebrow }}</span>
            <strong>{{ activeSection.status }}</strong>
          </div>
          <h1>{{ activeSection.title }}</h1>
          <p>{{ activeSection.subtitle }}</p>
        </section>

        <nav class="guide-tabs" aria-label="使用说明模块">
          <button
            v-for="section in sections"
            :key="section.id"
            type="button"
            :class="{ 'guide-tabs__item--active': activeSectionId === section.id }"
            @click="selectSection(section.id)"
          >
            <span>{{ section.index }}</span>
            {{ section.id === 'llamaindex' ? 'LlamaIndex 接入' : section.id === 'langgraph' ? 'LangGraph 工作流' : 'RAGFlow 文档解析' }}
          </button>
        </nav>

        <section class="guide-explainer">
          <div class="guide-explainer__main">
            <div class="guide-steps" aria-label="流程步骤">
              <template v-for="(step, index) in activeSection.steps" :key="step.label">
                <button
                  type="button"
                  :class="{ 'guide-steps__item--active': activeStepIndex === index }"
                  @click="selectStep(index)"
                >
                  <span>{{ index + 1 }}</span>
                  {{ step.label }}
                </button>
                <span v-if="index < activeSection.steps.length - 1" class="guide-steps__arrow">→</span>
              </template>
            </div>

            <div class="guide-stage">
              <div class="guide-stage__meta">
                <span>输入：{{ activeStep.input }}</span>
                <span>输出：{{ activeStep.output }}</span>
              </div>
              <h2>{{ activeStep.title }}</h2>
              <p>{{ activeStep.description }}</p>
              <div class="guide-stage__modules">
                <span v-for="module in activeStep.modules" :key="module">{{ module }}</span>
              </div>
            </div>

            <div class="guide-progress" aria-hidden="true">
              <span :style="{ width: `${progress}%` }"></span>
            </div>
            <div class="guide-actions">
              <button type="button" :disabled="activeStepIndex === 0" @click="previousStep">上一步</button>
              <span>{{ activeStepIndex + 1 }} / {{ activeSection.steps.length }}</span>
              <button type="button" class="guide-actions__next" @click="nextStep">
                {{ activeStepIndex === activeSection.steps.length - 1 ? '下个模块' : '下一步' }}
              </button>
            </div>
          </div>

          <aside class="guide-details">
            <h3>这个阶段解释了三件事</h3>
            <article
              v-for="(detail, index) in activeStep.details"
              :key="detail.title"
              :class="[
                'guide-details__item',
                detail.tone === 'accent' && 'guide-details__item--accent',
                detail.tone === 'warning' && 'guide-details__item--warning',
              ]"
            >
              <span>{{ String(index + 1).padStart(2, '0') }}</span>
              <div>
                <h4>{{ detail.title }}</h4>
                <p>{{ detail.text }}</p>
              </div>
            </article>
          </aside>
        </section>
      </main>
    </div>
  </MainLayout>
</template>

<style scoped>
.guide-page {
  height: 100%;
  overflow-y: auto;
  background:
    radial-gradient(circle at 12% 12%, var(--color-accent-subtle), transparent 28%),
    var(--color-bg);
}

.guide-page__header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--header-height);
  padding: var(--space-3) var(--space-6);
  border-bottom: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-elevated) 94%, transparent);
  backdrop-filter: blur(16px);
}

.guide-page__header > div {
  flex: 1;
}

.guide-page__header p {
  margin-top: 2px;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.guide-page__brand {
  color: var(--color-text);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.guide-page__menu-btn,
.guide-page__back,
.guide-actions button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}

.guide-page__menu-btn {
  width: 36px;
  height: 36px;
}

.guide-page__back {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}

.guide-page__menu-btn:hover,
.guide-page__back:hover,
.guide-actions button:hover:not(:disabled) {
  border-color: var(--color-border-hover);
  color: var(--color-accent);
}

.guide-page__content {
  width: min(1240px, calc(100% - 48px));
  margin: 0 auto;
  padding: var(--space-10) 0 var(--space-16);
}

.guide-hero {
  max-width: 1020px;
}

.guide-hero__eyebrow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  color: var(--color-accent);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  letter-spacing: 0.04em;
}

.guide-hero__eyebrow strong {
  padding: 5px 12px;
  border-radius: var(--radius-full);
  background: var(--color-accent);
  color: white;
  font-size: var(--text-xs);
  letter-spacing: 0;
}

.guide-hero h1 {
  margin-top: var(--space-4);
  color: var(--color-primary);
  font-family: var(--font-serif);
  font-size: clamp(2rem, 4.2vw, 3.4rem);
  line-height: 1.12;
  letter-spacing: -0.035em;
}

.guide-hero > p {
  max-width: 900px;
  margin-top: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-lg);
  line-height: 1.7;
}

.guide-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: var(--space-8) 0 var(--space-6);
}

.guide-tabs button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all var(--transition-fast);
}

.guide-tabs button:hover {
  border-color: var(--color-border-hover);
  color: var(--color-text);
}

.guide-tabs button span {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.guide-tabs .guide-tabs__item--active {
  border-color: var(--color-accent);
  background: var(--color-accent);
  color: white;
  box-shadow: 0 8px 20px rgba(74, 108, 247, 0.22);
}

.guide-tabs .guide-tabs__item--active span {
  color: rgba(255, 255, 255, 0.72);
}

.guide-explainer {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.9fr);
  gap: var(--space-6);
  align-items: stretch;
}

.guide-explainer__main {
  display: flex;
  flex-direction: column;
  min-height: 540px;
  padding: var(--space-6);
  border: 1px solid color-mix(in srgb, var(--color-accent) 14%, var(--color-border));
  border-radius: var(--radius-xl);
  background: color-mix(in srgb, var(--color-accent-subtle) 48%, var(--color-bg-elevated));
}

.guide-steps {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding-bottom: var(--space-5);
  border-bottom: 1px solid var(--color-border);
}

.guide-steps button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: all var(--transition-fast);
}

.guide-steps button span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 1px solid currentColor;
  border-radius: 50%;
  font-size: 11px;
}

.guide-steps button:hover {
  border-color: var(--color-accent-light);
  color: var(--color-accent);
}

.guide-steps .guide-steps__item--active {
  border-color: var(--color-accent);
  background: var(--color-accent);
  color: white;
}

.guide-steps__arrow {
  color: var(--color-text-tertiary);
}

.guide-stage {
  flex: 1;
  padding: var(--space-8) var(--space-2);
}

.guide-stage__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.guide-stage__meta span,
.guide-stage__modules span {
  padding: 5px 10px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.guide-stage h2 {
  max-width: 720px;
  margin-top: var(--space-6);
  color: var(--color-primary);
  font-size: clamp(1.5rem, 3vw, 2.35rem);
  line-height: 1.25;
}

.guide-stage > p {
  max-width: 760px;
  margin-top: var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-base);
  line-height: 1.85;
}

.guide-stage__modules {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-6);
}

.guide-stage__modules span {
  background: var(--color-accent-subtle);
  color: var(--color-accent-dark);
  font-weight: var(--font-medium);
}

.guide-progress {
  height: 4px;
  overflow: hidden;
  border-radius: var(--radius-full);
  background: var(--color-bg-tertiary);
}

.guide-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--color-accent), var(--color-accent-light));
  transition: width var(--transition-slow);
}

.guide-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-top: var(--space-4);
}

.guide-actions button {
  min-width: 96px;
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
}

.guide-actions button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.guide-actions > span {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.guide-actions .guide-actions__next {
  border-color: var(--color-accent);
  background: var(--color-accent);
  color: white;
}

.guide-details {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--space-4);
}

.guide-details > h3 {
  color: var(--color-text-secondary);
  font-size: var(--text-lg);
}

.guide-details__item {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
  transition: transform var(--transition-fast), border-color var(--transition-fast);
}

.guide-details__item:hover {
  transform: translateY(-2px);
  border-color: var(--color-border-hover);
}

.guide-details__item > span {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.guide-details__item h4 {
  color: var(--color-text);
  font-size: var(--text-base);
}

.guide-details__item p {
  margin-top: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.65;
}

.guide-details__item--accent {
  border-color: color-mix(in srgb, var(--color-accent) 22%, var(--color-border));
  background: var(--color-accent-subtle);
}

.guide-details__item--warning {
  border-color: color-mix(in srgb, var(--color-warning) 28%, var(--color-border));
  background: color-mix(in srgb, var(--color-warning) 8%, var(--color-bg-elevated));
}

@media (max-width: 1050px) {
  .guide-explainer {
    grid-template-columns: 1fr;
  }

  .guide-explainer__main {
    min-height: 500px;
  }

  .guide-details {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .guide-details > h3 {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .guide-page__content {
    width: min(100% - 28px, 1240px);
    padding-top: var(--space-6);
  }

  .guide-page__header {
    padding: var(--space-3) var(--space-4);
  }

  .guide-page__header p,
  .guide-page__back {
    display: none;
  }

  .guide-hero > p {
    font-size: var(--text-base);
  }

  .guide-tabs {
    display: grid;
    grid-template-columns: 1fr;
  }

  .guide-tabs button {
    justify-content: flex-start;
    border-radius: var(--radius-md);
  }

  .guide-explainer__main {
    min-height: 0;
    padding: var(--space-4);
  }

  .guide-steps__arrow {
    display: none;
  }

  .guide-stage {
    padding: var(--space-6) 0;
  }

  .guide-details {
    grid-template-columns: 1fr;
  }
}
</style>
