<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useUserStore } from '../stores/user';
import { useSidebar } from '../composables/useSidebar';
import MainLayout from '../layouts/MainLayout.vue';

type GuideTab = 'modes' | 'llamaindex' | 'mcp' | 'ragflow';
type ModeId = 'agent' | 'knowledge' | 'writing';

interface FlowNode {
  name: string;
  owner: string;
  action: string;
  input: string;
  output: string;
  result: string;
  branch?: string;
}

interface FlowScenario {
  id: string;
  title: string;
  summary: string;
  task: string;
  route: string;
  nodes: FlowNode[];
}

interface McpCard {
  name: string;
  status: '已接入' | '非 MCP' | '可扩展';
  description: string;
  tools: string[];
}

const router = useRouter();
const userStore = useUserStore();
const { isExpanded, toggleSidebar } = useSidebar();

if (!userStore.userId) router.push('/');

const modeFlows: Record<ModeId, FlowScenario> = {
  agent: {
    id: 'agent',
    title: '智能体模式：系统先判断任务类型，再选择一条工作流',
    summary: '适合用户不想预先判断该用聊天、知识库还是写作时。只有智能体模式会让模型做意图分类。',
    task: '你好，请介绍一下你能做什么。',
    route: 'START → summarize → intent_router(chat) → chat_agent → finalize → END',
    nodes: [
      {
        name: 'summarize', owner: 'LangMem / LangGraph',
        action: '读取当前线程的历史消息。对话过长时压缩旧消息，保留摘要和最近原文。',
        input: '本轮问题 + PostgreSQL 中的会话历史', output: 'summarized_messages',
        result: '得到可供本轮模型使用的精简上下文。',
      },
      {
        name: 'intent_router', owner: 'LangGraph + DeepSeek',
        action: '判断用户是在普通聊天、查询知识还是要求写作。当前示例被判断为 chat。',
        input: '“你好，请介绍一下你能做什么”', output: 'intent = chat',
        result: '选择 chat_agent；不会调用知识库，也不会进入写作子图。',
        branch: '可能分支：chat → chat_agent；knowledge → knowledge_agent；writing → writing_workflow。',
      },
      {
        name: 'chat_agent', owner: 'LangGraph + DeepSeek',
        action: '结合摘要后的会话上下文，直接生成自然语言回答。',
        input: '系统角色 + summarized_messages', output: 'AIMessage(answer)',
        result: '生成能力介绍或普通对话答案。',
      },
      {
        name: 'finalize', owner: 'LangGraph',
        action: '把节点结果整理成主服务认识的 answer、sources 和 intent。',
        input: 'answer + messages', output: 'answer + sources=[] + intent=chat',
        result: '本轮图执行完成，结果返回 main_service。',
      },
      {
        name: 'SSE 返回前端', owner: 'main_service → Vue',
        action: '主服务将内容转换为流式事件，前端逐字展示并保存会话。',
        input: 'LangGraph 最终状态', output: '聊天气泡',
        result: '用户看到最终回答。',
      },
    ],
  },
  knowledge: {
    id: 'knowledge',
    title: '知识库模式：跳过意图猜测，强制查询已上传文档',
    summary: '适合明确要从企业文档、简历、制度或资料库中找答案的任务。答案附带真实召回来源。',
    task: '刘帅康的教育背景是什么？',
    route: 'START → summarize → intent_router(强制 knowledge) → knowledge_agent → query_rag → knowledge_guard → finalize → END',
    nodes: [
      {
        name: 'summarize', owner: 'LangMem / LangGraph',
        action: '恢复当前会话上下文，让“他”“上一份文件”等指代仍然可理解。',
        input: '本轮问题 + 会话历史', output: 'summarized_messages',
        result: '准备好带上下文的检索问题。',
      },
      {
        name: 'intent_router', owner: 'LangGraph',
        action: '看到 mode=knowledge 后直接设置 intent=knowledge，不调用模型重新分类。',
        input: 'mode = knowledge', output: 'intent = knowledge',
        result: '确定进入 knowledge_agent。',
      },
      {
        name: 'knowledge_agent', owner: 'LangGraph',
        action: '提取最近一条用户问题，准备调用 MCP 工具 query_rag。',
        input: '用户问题', output: '{ query: 用户问题 }',
        result: 'LangGraph 本身不读取文档，只准备工具参数。',
      },
      {
        name: 'query_rag', owner: 'MCP · :8010/mcp',
        action: '通过 streamable-http 接收工具调用，再用 HTTP 转发到 rag_api_service。',
        input: 'query 字符串', output: 'MCP 工具结果',
        result: '这是本项目当前唯一对外暴露的 MCP 工具。',
      },
      {
        name: '检索与生成', owner: 'rag_api_service → RAGFlow → DeepSeek',
        action: 'RAGFlow 检索相关 Chunk；适配层把 Chunk 交给文本模型生成仅依据资料的答案。',
        input: 'query + Dataset', output: 'answer + sources',
        result: '当前示例可召回简历中的教育经历，并返回原文来源。',
      },
      {
        name: 'knowledge_guard', owner: 'LangGraph',
        action: '检查答案是否为空、查询失败或明确“不知道”。质量不足时才进入 Tavily 联网兜底。',
        input: 'answer', output: 'finalize 或 fallback_search',
        result: '当前答案有效，直接进入 finalize。',
        branch: '失败分支：fallback_search → Tavily（需要 TAVILY_API_KEY）→ finalize。',
      },
      {
        name: 'finalize', owner: 'LangGraph → main_service',
        action: '保留 answer 和 sources，并通过 SSE 返回前端。',
        input: '答案 + 来源片段', output: '可展开来源的聊天消息',
        result: '用户既看到结论，也能展开核对文档原文。',
      },
    ],
  },
  writing: {
    id: 'writing',
    title: '写作模式：从需求分析到人工确认的完整写作子图',
    summary: '适合报告、文章、邮件和方案。系统会先理解需求，再研究、列大纲、写草稿、审稿，并把最终决定交给用户。',
    task: '写一篇 800 字、面向非技术面试官的 RAG 项目介绍。',
    route: 'understand → research → outline → draft → review ⇄ revise → human_review → format_output',
    nodes: [
      {
        name: 'summarize + intent_router', owner: 'LangGraph 主图',
        action: '恢复会话上下文；看到 mode=writing 后强制进入 writing_workflow。',
        input: 'query + mode=writing', output: 'intent=writing',
        result: '主图调用写作子图。',
      },
      {
        name: 'understand', owner: '写作子图',
        action: '提取主题、字数、风格、读者和特殊要求，并判断需求是否清晰。',
        input: '原始写作需求', output: 'requirements + need_clarification',
        result: '当前示例信息完整，不需要追问。',
        branch: '若不清晰：ask_clarification 暂停 → 用户补充 → 返回 understand。',
      },
      {
        name: 'research', owner: '写作子图 + Tavily（可选）',
        action: '搜索与主题相关的公开资料；未配置 Tavily 时使用模型已有知识继续。',
        input: 'query + requirements', output: 'research_notes',
        result: '形成写作参考素材。注意：Tavily 是 LangChain 工具，不是 MCP。',
      },
      {
        name: 'outline', owner: '写作子图 + DeepSeek',
        action: '根据需求和资料规划章节、逻辑顺序及各部分字数。',
        input: 'requirements + research_notes', output: 'outline',
        result: '得到结构化文章大纲。',
      },
      {
        name: 'draft', owner: '写作子图 + DeepSeek',
        action: '严格依照大纲生成 Markdown 草稿。',
        input: 'requirements + outline + research_notes', output: 'draft',
        result: '产生第一版完整文章。',
      },
      {
        name: 'review', owner: '审稿节点 + DeepSeek',
        action: '检查需求符合度、结构、事实、语言和完整性。',
        input: 'draft + requirements', output: 'review_result + review_passed',
        result: '决定草稿通过还是进入自动修订。',
      },
      {
        name: 'revise（条件循环）', owner: '修订节点 + DeepSeek',
        action: '如果审稿不通过，根据审稿意见修改草稿，然后再次进入 review。',
        input: 'draft + review_result', output: 'revised draft',
        result: '形成 review ⇄ revise 质量循环，直到机器审稿通过。',
      },
      {
        name: 'human_review', owner: 'LangGraph interrupt + 用户',
        action: '暂停图执行，把草稿交给用户。用户可以确认、直接修改或要求重写。',
        input: '机器审稿通过的草稿', output: 'approve / edit / rewrite',
        result: '最终内容始终由用户决定。',
      },
      {
        name: 'format_output', owner: '写作子图',
        action: '整理最终 Markdown、消息和来源字段，结束写作子图。',
        input: '用户确认后的内容', output: 'answer',
        result: '回到主图 finalize，再流式返回前端。',
      },
    ],
  },
};

const llamaIndexFlow: FlowScenario = {
  id: 'llamaindex',
  title: 'LlamaIndex 数据接入：把“一个文件”变成“能被问题命中的检索单元”',
  summary: '这条链路只在 RAG_BACKEND=legacy 且 ENABLE_LEGACY_RAG=true 时启用；当前默认 RAGFlow 不会加载它。',
  task: '示例：管理员上传《员工手册.pdf》，之后用户询问“年假有几天？”',
  route: '文件 → Document → Node[] → Chroma + BM25 → 候选合并 → 重排 → 回答',
  nodes: [
    {
      name: '① 接收文件', owner: 'main_service → rag_api_service',
      action: '前端把文件作为 multipart 上传。服务保存文件，并生成稳定 doc_id。',
      input: '员工手册.pdf（二进制）', output: '文件路径 + doc_id + 文件名等元数据',
      result: '此时只是收到文件，还不能检索。',
    },
    {
      name: '② 读取并统一格式', owner: 'LlamaIndex Reader / PDF Processor',
      action: 'TXT、MD 等由 Reader 读取；PDF 先提取正文和图片并转换为统一文本/Markdown。',
      input: '不同格式的原始文件', output: 'Document',
      result: 'Document 表示“一份完整资料”，包含全文和文件级元数据。',
    },
    {
      name: '③ 切成 Node', owner: 'SentenceSplitter',
      action: '按照 chunk_size 切分长文，相邻块用 chunk_overlap 保留少量重复上下文。',
      input: '1 个 Document', output: '多个 Node',
      result: 'Node 才是实际检索单位；每个 Node 都保留原文件 doc_id。',
    },
    {
      name: '④ 建立两种索引', owner: 'Embedding + ChromaDB + BM25',
      action: '同一批 Node 同时进入语义向量索引和关键词索引。',
      input: 'Node[]', output: 'Chroma 向量库 + BM25 词项索引',
      result: '“休假天数”和“年假几天”可被语义命中；制度编号等精确词可被 BM25 命中。',
    },
    {
      name: '⑤ 两路召回', owner: 'Hybrid Retriever',
      action: '用户提问时，向量检索和 BM25 同时找候选 Node，再合并去重。',
      input: '“年假有几天？”', output: '较宽的候选 Node 集合',
      result: '先保证相关内容尽量不漏掉。',
    },
    {
      name: '⑥ 重排', owner: 'SentenceTransformerRerank',
      action: '让重排模型逐一比较问题与候选片段，把真正回答问题的内容排到前面。',
      input: '问题 + 候选 Node', output: 'Top-K 高相关 Node',
      result: '过滤只提到“休假”但没有年假天数的弱相关段落。',
    },
    {
      name: '⑦ 生成并返回来源', owner: 'Response Synthesizer',
      action: '文本模型只依据 Top-K Node 组织回答，同时返回文件名和原文片段。',
      input: '问题 + Top-K Node', output: 'answer + sources',
      result: '用户看到年假结论，并能核对《员工手册.pdf》的对应原文。',
    },
  ],
};

const mcpFlow: FlowScenario = {
  id: 'mcp',
  title: 'MCP 在本项目中的作用：让 LangGraph 用统一工具协议调用知识库',
  summary: 'MCP 不是知识库，也不负责解析文件。它是 Agent 与外部能力之间的工具协议层。',
  task: '示例：knowledge_agent 调用 query_rag({ query: “教育背景是什么？” })',
  route: 'knowledge_agent → MCP Client → :8010/mcp → query_rag → :8011 REST → RAGFlow',
  nodes: [
    {
      name: 'Agent 决定用工具', owner: 'knowledge_agent',
      action: '知识模式已确定需要查文档，于是构造 query_rag 的参数。',
      input: '用户问题', output: '{ query: string }',
      result: 'Agent 不需要知道 RAGFlow 的地址、Dataset 或 API 格式。',
    },
    {
      name: '发现 MCP 工具', owner: 'MultiServerMCPClient',
      action: '连接 MCP_SERVICE_URL，初始化会话并读取服务端公开的工具列表。',
      input: 'http://127.0.0.1:8010/mcp', output: '[query_rag]',
      result: '当前只能发现 query_rag 一个工具。',
    },
    {
      name: '调用 query_rag', owner: 'FastMCP · tuling-rag',
      action: '通过 streamable-http 执行工具，并校验 query 参数。',
      input: '{ query }', output: '结构化 MCP result',
      result: 'MCP 服务只做协议适配和代理，不保存文档。',
    },
    {
      name: '转发统一 RAG API', owner: 'mcp_service → rag_api_service',
      action: '工具内部 POST /api/docs/query。RAG 后端由 rag_api_service 自己决定。',
      input: 'HTTP JSON', output: 'answer + sources + retrieval',
      result: '切换 RAGFlow/Legacy 时，LangGraph 和 MCP 调用方式都不变。',
    },
    {
      name: '返回 Agent', owner: 'MCP Client → LangGraph',
      action: '解析 structuredContent，写入 AIMessage，并把 sources 放入消息元数据。',
      input: 'MCP result', output: 'GraphState',
      result: '后续由 knowledge_guard 做质量判断。',
    },
  ],
};

const ragflowFlow: FlowScenario = {
  id: 'ragflow',
  title: 'RAGFlow 文档解析：从页面识别到可检索 Chunk',
  summary: '当前默认链路。页面会实时显示 RAGFlow 的 status、progress、progress_msg 和 chunk_count。',
  task: '示例：上传一份同时包含正文、图片、公式和表格的 PDF。',
  route: '上传 → OCR/版面 → 公式/图片/表格 → Chunk → Embedding → Elasticsearch → 可检索',
  nodes: [
    {
      name: '上传与创建任务', owner: 'rag_api_service → RAGFlow Dataset',
      action: '上传文件并启动异步解析，立即返回 document_id。',
      input: 'PDF / Office / TXT 等', output: 'document_id + RUNNING',
      result: '前端开始每 2 秒查询解析进度。',
    },
    {
      name: 'OCR 与版面分析', owner: 'DeepDoc',
      action: '渲染页面，识别扫描文字、标题、段落、阅读顺序和各区域坐标。',
      input: '页面图像', output: '带位置的文本与布局区域',
      result: '多栏 PDF 不再简单按提取顺序拼成错乱文本。',
    },
    {
      name: '公式区域', owner: 'DeepDoc 公式检测',
      action: '区分公式与普通段落，尽量保留数学符号、上下标和表达结构。',
      input: '疑似公式区域', output: '公式表达 + 页面位置',
      result: '公式可以随上下文进入后续 Chunk；扫描质量仍会影响准确率。',
    },
    {
      name: '图片理解', owner: 'GLM Vision',
      action: '提取有信息量的图片区域，由视觉模型生成可检索的中文语义描述。',
      input: '图片裁剪 + 周边文本', output: '图片描述',
      result: '用户即使没有使用图片中的原词，也能通过语义检索找到它。',
    },
    {
      name: '表格结构', owner: 'DeepDoc Table Analysis',
      action: '识别表格边界、行列与单元格关系，再组织成结构化文本。',
      input: '表格区域', output: '有行列关系的文本',
      result: '避免把整张表格压成无法理解的一串字符。',
    },
    {
      name: '结构化分块', owner: 'RAGFlow Parser',
      action: '沿标题、段落和内容区域边界组合 Chunk，并保留文件名与页面位置。',
      input: '正文 + 公式 + 图片描述 + 表格文本', output: 'Chunk[] + metadata',
      result: '页面显示实时 chunk_count；解析完成后可以逐块查看。',
    },
    {
      name: '向量化与索引', owner: 'Qwen3 Embedding / TEI / Elasticsearch',
      action: '将 Chunk 分批转换为 1024 维向量，并写入检索索引。',
      input: 'Chunk[]', output: 'DONE + 可检索索引',
      result: '只有状态到 DONE，这份文档才真正可以参与知识库问答。',
    },
  ],
};

const mcpCards: McpCard[] = [
  {
    name: 'tuling-rag · :8010/mcp', status: '已接入',
    description: '本项目当前唯一运行中的 MCP 服务，使用 streamable-http。',
    tools: ['query_rag(query)：查询 RAGFlow/Legacy，返回 answer、sources、retrieval'],
  },
  {
    name: '文档管理 REST · :8011', status: '非 MCP',
    description: '上传、列表、进度、Chunk 查看、删除和重置直接走 REST，未暴露给 Agent。',
    tools: ['POST /upload', 'GET /documents', 'GET /chunks/{id}', 'DELETE /documents/{id}'],
  },
  {
    name: 'Tavily 与 LangMem', status: '非 MCP',
    description: 'Tavily 是当前知识兜底和写作研究使用的 LangChain 工具；LangMem 管理/搜索工具已定义，但尚未挂载到当前主图节点。',
    tools: ['web_search（当前可选，需 TAVILY_API_KEY）', 'manage_memory（已定义，主图未启用）', 'search_memory（已定义，主图未启用）'],
  },
  {
    name: '可继续接入的 MCP 类型', status: '可扩展',
    description: 'MultiServerMCPClient 已支持增加多个服务，但当前仓库尚未配置以下连接。接入前需要单独部署并配置权限。',
    tools: ['Filesystem：受控文件读写', 'GitHub：Issue / PR / 仓库操作', 'PostgreSQL：受限数据库查询', 'Browser/Search：网页访问', '飞书/邮件：企业协作能力'],
  },
];

const tabs: Array<{ id: GuideTab; label: string; index: string }> = [
  { id: 'modes', label: '三种模式', index: '01' },
  { id: 'llamaindex', label: 'LlamaIndex 数据接入', index: '02' },
  { id: 'mcp', label: 'MCP 服务', index: '03' },
  { id: 'ragflow', label: 'RAGFlow 文档解析', index: '04' },
];

const activeTab = ref<GuideTab>('modes');
const activeMode = ref<ModeId>('agent');
const activeNodeIndex = ref(0);
const playing = ref(true);
let timer: ReturnType<typeof setInterval> | null = null;
let startDelay: ReturnType<typeof setTimeout> | null = null;

const currentFlow = computed<FlowScenario>(() => {
  if (activeTab.value === 'modes') return modeFlows[activeMode.value];
  if (activeTab.value === 'llamaindex') return llamaIndexFlow;
  if (activeTab.value === 'mcp') return mcpFlow;
  return ragflowFlow;
});

const activeNode = computed(() => currentFlow.value.nodes[activeNodeIndex.value]);
const completedNodes = computed(() => currentFlow.value.nodes.slice(0, activeNodeIndex.value + 1));
const progress = computed(() => ((activeNodeIndex.value + 1) / currentFlow.value.nodes.length) * 100);

function stopTimer() {
  if (timer) clearInterval(timer);
  if (startDelay) clearTimeout(startDelay);
  timer = null;
  startDelay = null;
}

function startPlayback() {
  stopTimer();
  playing.value = true;
  timer = setInterval(() => {
    if (activeNodeIndex.value < currentFlow.value.nodes.length - 1) {
      activeNodeIndex.value += 1;
    } else {
      playing.value = false;
      stopTimer();
    }
  }, 2600);
}

function resetFlow(autoPlay = true) {
  stopTimer();
  activeNodeIndex.value = 0;
  playing.value = autoPlay;
  if (autoPlay) startDelay = setTimeout(startPlayback, 450);
}

function selectTab(tab: GuideTab) {
  activeTab.value = tab;
}

function selectMode(mode: ModeId) {
  activeMode.value = mode;
}

function selectNode(index: number) {
  stopTimer();
  playing.value = false;
  activeNodeIndex.value = index;
}

function togglePlayback() {
  if (playing.value) {
    playing.value = false;
    stopTimer();
  } else if (activeNodeIndex.value >= currentFlow.value.nodes.length - 1) {
    resetFlow(true);
  } else {
    startPlayback();
  }
}

function nextNode() {
  stopTimer();
  playing.value = false;
  if (activeNodeIndex.value < currentFlow.value.nodes.length - 1) activeNodeIndex.value += 1;
}

watch([activeTab, activeMode], () => resetFlow(true));
onMounted(() => resetFlow(true));
onBeforeUnmount(stopTimer);
</script>

<template>
  <MainLayout :show-sidebar="true">
    <div class="guide-page">
      <header class="guide-header">
        <button v-if="!isExpanded" class="icon-button" type="button" aria-label="展开侧边栏" @click="toggleSidebar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 12h18M3 6h18M3 18h18" />
          </svg>
        </button>
        <div class="guide-header__title">
          <strong>帅康 AI · 系统是怎样工作的</strong>
          <span>用一个真实任务，跟着节点一步一步执行</span>
        </div>
        <button class="back-button" type="button" @click="router.push('/chat')">返回对话</button>
      </header>

      <main class="guide-content">
        <section class="guide-intro">
          <span class="guide-intro__tag">任务驱动说明</span>
          <h1>不用先理解术语，先看数据在系统里怎么走</h1>
          <p>流程默认自动播放。蓝色节点表示正在执行，带对勾的节点表示已经完成；点击任意节点可以暂停并查看它的真实输入与输出。</p>
        </section>

        <nav class="guide-tabs" aria-label="说明主题">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            :class="{ active: activeTab === tab.id }"
            @click="selectTab(tab.id)"
          >
            <span>{{ tab.index }}</span>{{ tab.label }}
          </button>
        </nav>

        <section v-if="activeTab === 'modes'" class="mode-picker" aria-label="选择工作模式">
          <button type="button" :class="{ active: activeMode === 'agent' }" @click="selectMode('agent')">
            <strong>智能体模式</strong><span>系统自动判断走聊天、知识还是写作</span>
          </button>
          <button type="button" :class="{ active: activeMode === 'knowledge' }" @click="selectMode('knowledge')">
            <strong>知识库模式</strong><span>不猜意图，直接查已上传文档</span>
          </button>
          <button type="button" :class="{ active: activeMode === 'writing' }" @click="selectMode('writing')">
            <strong>写作模式</strong><span>进入多节点写作、审稿与人工确认</span>
          </button>
        </section>

        <section class="task-card">
          <div>
            <span class="task-card__label">本次演示任务</span>
            <h2>{{ currentFlow.task }}</h2>
            <p>{{ currentFlow.summary }}</p>
          </div>
          <div class="task-card__route">
            <span>实际路径</span>
            <code>{{ currentFlow.route }}</code>
          </div>
        </section>

        <section class="flow-board">
          <div class="node-rail">
            <button
              v-for="(node, index) in currentFlow.nodes"
              :key="`${currentFlow.id}-${node.name}`"
              type="button"
              :class="{
                active: activeNodeIndex === index,
                complete: index < activeNodeIndex,
                pending: index > activeNodeIndex,
              }"
              @click="selectNode(index)"
            >
              <span class="node-rail__number">{{ index < activeNodeIndex ? '✓' : index + 1 }}</span>
              <span class="node-rail__text"><strong>{{ node.name }}</strong><small>{{ node.owner }}</small></span>
              <span v-if="index < currentFlow.nodes.length - 1" class="node-rail__line"></span>
            </button>
          </div>

          <div class="node-stage">
            <div class="node-stage__topline">
              <span>正在执行 · {{ activeNodeIndex + 1 }}/{{ currentFlow.nodes.length }}</span>
              <span :class="['play-status', playing && 'running']">{{ playing ? '自动播放中' : '已暂停' }}</span>
            </div>
            <h2>{{ activeNode.name }}</h2>
            <span class="owner-chip">负责服务：{{ activeNode.owner }}</span>
            <p class="node-stage__action">{{ activeNode.action }}</p>

            <div class="io-grid">
              <article><span>这个节点收到</span><p>{{ activeNode.input }}</p></article>
              <article><span>这个节点产出</span><p>{{ activeNode.output }}</p></article>
            </div>

            <article class="result-card">
              <span>执行后发生什么</span>
              <p>{{ activeNode.result }}</p>
              <small v-if="activeNode.branch">{{ activeNode.branch }}</small>
            </article>

            <div class="flow-progress"><span :style="{ width: `${progress}%` }"></span></div>
            <div class="flow-controls">
              <button type="button" @click="resetFlow(true)">从头演示</button>
              <button type="button" class="primary" @click="togglePlayback">{{ playing ? '暂停' : '继续播放' }}</button>
              <button type="button" :disabled="activeNodeIndex >= currentFlow.nodes.length - 1" @click="nextNode">下一节点</button>
            </div>
          </div>

          <aside class="execution-log">
            <div class="execution-log__header"><strong>任务执行记录</strong><span>实时</span></div>
            <ol>
              <li v-for="(node, index) in completedNodes" :key="`log-${node.name}`" :class="{ current: index === activeNodeIndex }">
                <span>{{ index === activeNodeIndex ? '执行中' : '完成' }}</span>
                <div><strong>{{ node.name }}</strong><p>{{ node.result }}</p></div>
              </li>
            </ol>
          </aside>
        </section>

        <section v-if="activeTab === 'llamaindex'" class="concept-section">
          <div class="section-heading"><span>先记住三个对象</span><h2>LlamaIndex 不是数据库，它负责把数据组织成可检索对象</h2></div>
          <div class="concept-grid">
            <article><strong>Document</strong><p>一份完整资料，例如整本《员工手册》。用于保存全文和文件级元数据。</p></article>
            <article><strong>Node / Chunk</strong><p>从 Document 切出的一个可召回片段。用户查询时，真正参与匹配的是 Node。</p></article>
            <article><strong>Index / Retriever</strong><p>Index 保存“如何找到 Node”；Retriever 根据问题从索引中取回相关 Node。</p></article>
          </div>
          <div class="boundary-note"><strong>当前边界：</strong>这套 LlamaIndex 链路只是 Legacy 备用实现；默认 RAGFlow 模式负责解析、分块、索引和检索，两套实现不会同时加载。</div>
        </section>

        <section v-if="activeTab === 'mcp'" class="mcp-section">
          <div class="section-heading"><span>能力清单</span><h2>哪些是 MCP，哪些不是，当前能调用什么</h2></div>
          <div class="mcp-grid">
            <article v-for="card in mcpCards" :key="card.name">
              <div class="mcp-card__title"><strong>{{ card.name }}</strong><span :class="card.status">{{ card.status }}</span></div>
              <p>{{ card.description }}</p>
              <ul><li v-for="tool in card.tools" :key="tool">{{ tool }}</li></ul>
            </article>
          </div>
          <div class="boundary-note"><strong>扩展方法：</strong>在 MultiServerMCPClient 中增加服务地址 → 获取该服务 tools → 在对应 Agent 节点中明确允许调用。接入不等于自动授权，文件、数据库和 GitHub 等服务应配置最小权限。</div>
        </section>
      </main>
    </div>
  </MainLayout>
</template>

<style scoped>
.guide-page { height: 100%; overflow-y: auto; background: radial-gradient(circle at 12% 8%, var(--color-accent-subtle), transparent 25%), var(--color-bg); }
.guide-header { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: var(--space-3); min-height: var(--header-height); padding: var(--space-3) var(--space-6); border-bottom: 1px solid var(--color-border); background: color-mix(in srgb, var(--color-bg-elevated) 94%, transparent); backdrop-filter: blur(16px); }
.guide-header__title { display: flex; flex: 1; flex-direction: column; gap: 2px; }
.guide-header__title strong { color: var(--color-text); font-size: var(--text-base); }
.guide-header__title span { color: var(--color-text-tertiary); font-size: var(--text-xs); }
.icon-button, .back-button, .flow-controls button { border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-bg-elevated); color: var(--color-text-secondary); transition: all var(--transition-fast); }
.icon-button { width: 36px; height: 36px; }
.back-button { padding: var(--space-2) var(--space-3); }
.guide-content { width: min(1380px, calc(100% - 48px)); margin: 0 auto; padding: var(--space-10) 0 var(--space-16); }
.guide-intro { max-width: 980px; }
.guide-intro__tag, .section-heading > span { color: var(--color-accent); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.guide-intro h1 { margin-top: var(--space-3); color: var(--color-primary); font-family: var(--font-serif); font-size: clamp(2rem, 4vw, 3.25rem); line-height: 1.15; letter-spacing: -0.035em; }
.guide-intro p { max-width: 900px; margin-top: var(--space-4); color: var(--color-text-secondary); font-size: var(--text-base); line-height: 1.8; }
.guide-tabs { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: var(--space-8) 0 var(--space-5); }
.guide-tabs button { display: flex; align-items: center; gap: 8px; padding: 10px 16px; border: 1px solid var(--color-border); border-radius: var(--radius-full); background: var(--color-bg-elevated); color: var(--color-text-secondary); font-weight: var(--font-medium); }
.guide-tabs button span { color: var(--color-text-tertiary); font-size: 11px; }
.guide-tabs button.active { border-color: var(--color-accent); background: var(--color-accent); color: white; box-shadow: 0 8px 20px rgba(74, 108, 247, .2); }
.guide-tabs button.active span { color: rgba(255,255,255,.7); }
.mode-picker { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); margin-bottom: var(--space-5); }
.mode-picker button { display: flex; flex-direction: column; gap: 5px; padding: var(--space-4); text-align: left; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-bg-elevated); color: var(--color-text); }
.mode-picker button span { color: var(--color-text-tertiary); font-size: var(--text-xs); line-height: 1.5; }
.mode-picker button.active { border-color: var(--color-accent); box-shadow: inset 0 0 0 1px var(--color-accent); background: var(--color-accent-subtle); }
.mode-picker button.active strong { color: var(--color-accent); }
.task-card { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(300px, .75fr); gap: var(--space-6); padding: var(--space-6); border: 1px solid var(--color-border); border-radius: var(--radius-xl); background: var(--color-bg-elevated); }
.task-card__label, .task-card__route > span { color: var(--color-accent); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.task-card h2 { margin-top: var(--space-2); color: var(--color-primary); font-size: clamp(1.2rem, 2vw, 1.65rem); }
.task-card p { margin-top: var(--space-2); color: var(--color-text-secondary); line-height: 1.7; }
.task-card__route { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--color-bg-secondary); }
.task-card__route code { color: var(--color-text-secondary); font-family: var(--font-mono); font-size: var(--text-xs); line-height: 1.7; white-space: normal; }
.flow-board { display: grid; grid-template-columns: minmax(230px, .72fr) minmax(430px, 1.35fr) minmax(260px, .8fr); gap: var(--space-4); margin-top: var(--space-5); align-items: stretch; }
.node-rail, .node-stage, .execution-log { border: 1px solid var(--color-border); border-radius: var(--radius-xl); background: var(--color-bg-elevated); }
.node-rail { padding: var(--space-4); }
.node-rail button { position: relative; display: flex; width: 100%; min-height: 66px; gap: var(--space-3); padding: var(--space-2); text-align: left; color: var(--color-text-secondary); }
.node-rail__number { position: relative; z-index: 2; display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; flex: 0 0 30px; border: 1px solid var(--color-border); border-radius: 50%; background: var(--color-bg); font-size: 12px; font-weight: var(--font-semibold); }
.node-rail__text { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.node-rail__text strong { overflow-wrap: anywhere; color: inherit; font-size: var(--text-sm); }
.node-rail__text small { color: var(--color-text-tertiary); font-size: 11px; line-height: 1.4; }
.node-rail__line { position: absolute; top: 38px; bottom: -4px; left: 23px; width: 2px; background: var(--color-border); }
.node-rail button.complete .node-rail__number { border-color: var(--color-success); background: var(--color-success); color: white; }
.node-rail button.complete .node-rail__line { background: var(--color-success); }
.node-rail button.active { color: var(--color-accent); }
.node-rail button.active .node-rail__number { border-color: var(--color-accent); background: var(--color-accent); color: white; box-shadow: 0 0 0 5px var(--color-accent-subtle); }
.node-rail button.pending { opacity: .58; }
.node-stage { display: flex; min-height: 570px; flex-direction: column; padding: var(--space-6); background: color-mix(in srgb, var(--color-accent-subtle) 34%, var(--color-bg-elevated)); }
.node-stage__topline, .execution-log__header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); color: var(--color-text-tertiary); font-size: var(--text-xs); }
.play-status { padding: 4px 9px; border-radius: var(--radius-full); background: var(--color-bg-tertiary); }
.play-status.running { background: var(--color-accent-subtle); color: var(--color-accent); }
.node-stage h2 { margin-top: var(--space-6); color: var(--color-primary); font-size: clamp(1.55rem, 2.6vw, 2.2rem); line-height: 1.25; }
.owner-chip { align-self: flex-start; margin-top: var(--space-3); padding: 5px 10px; border-radius: var(--radius-full); background: var(--color-accent); color: white; font-size: var(--text-xs); }
.node-stage__action { margin-top: var(--space-5); color: var(--color-text-secondary); font-size: var(--text-base); line-height: 1.85; }
.io-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); margin-top: var(--space-5); }
.io-grid article, .result-card { padding: var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-bg-elevated); }
.io-grid span, .result-card > span { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.io-grid p, .result-card p { margin-top: var(--space-2); color: var(--color-text); font-size: var(--text-sm); line-height: 1.65; }
.result-card { margin-top: var(--space-3); border-color: color-mix(in srgb, var(--color-accent) 25%, var(--color-border)); }
.result-card small { display: block; margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px dashed var(--color-border); color: var(--color-warning); line-height: 1.6; }
.flow-progress { height: 5px; margin-top: auto; overflow: hidden; border-radius: var(--radius-full); background: var(--color-bg-tertiary); }
.flow-progress span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--color-accent), var(--color-accent-light)); transition: width .35s ease; }
.flow-controls { display: flex; justify-content: space-between; gap: var(--space-2); margin-top: var(--space-4); }
.flow-controls button { padding: 8px 13px; font-size: var(--text-xs); }
.flow-controls button.primary { border-color: var(--color-accent); background: var(--color-accent); color: white; }
.flow-controls button:disabled { cursor: not-allowed; opacity: .45; }
.execution-log { min-height: 570px; padding: var(--space-5); }
.execution-log__header strong { color: var(--color-text); font-size: var(--text-sm); }
.execution-log__header span { padding: 3px 8px; border-radius: var(--radius-full); background: rgba(34,197,94,.1); color: var(--color-success); }
.execution-log ol { display: flex; flex-direction: column; gap: var(--space-4); margin-top: var(--space-5); }
.execution-log li { display: grid; grid-template-columns: 46px 1fr; gap: var(--space-2); }
.execution-log li > span { padding-top: 2px; color: var(--color-success); font-size: 10px; font-weight: var(--font-semibold); }
.execution-log li.current > span { color: var(--color-accent); }
.execution-log li strong { color: var(--color-text); font-size: var(--text-xs); }
.execution-log li p { margin-top: 4px; color: var(--color-text-tertiary); font-size: 11px; line-height: 1.55; }
.concept-section, .mcp-section { margin-top: var(--space-8); }
.section-heading h2 { max-width: 900px; margin-top: var(--space-2); color: var(--color-primary); font-size: clamp(1.45rem, 2.6vw, 2rem); }
.concept-grid, .mcp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); margin-top: var(--space-5); }
.concept-grid article, .mcp-grid article { padding: var(--space-5); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-bg-elevated); }
.concept-grid strong, .mcp-grid strong { color: var(--color-primary); }
.concept-grid p, .mcp-grid p { margin-top: var(--space-2); color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.7; }
.mcp-grid { grid-template-columns: repeat(2, 1fr); }
.mcp-card__title { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.mcp-card__title span { flex: 0 0 auto; padding: 4px 8px; border-radius: var(--radius-full); font-size: 10px; }
.mcp-card__title span.已接入 { background: rgba(34,197,94,.1); color: var(--color-success); }
.mcp-card__title span.非.MCP { background: var(--color-bg-tertiary); color: var(--color-text-tertiary); }
.mcp-card__title span.可扩展 { background: var(--color-accent-subtle); color: var(--color-accent); }
.mcp-grid ul { margin-top: var(--space-3); padding-left: 18px; color: var(--color-text-secondary); font-size: var(--text-xs); line-height: 1.75; }
.boundary-note { margin-top: var(--space-4); padding: var(--space-4) var(--space-5); border-left: 3px solid var(--color-warning); border-radius: 0 var(--radius-md) var(--radius-md) 0; background: color-mix(in srgb, var(--color-warning) 8%, var(--color-bg-elevated)); color: var(--color-text-secondary); font-size: var(--text-sm); line-height: 1.75; }
.boundary-note strong { color: var(--color-warning); }
button:hover:not(:disabled) { border-color: var(--color-accent); }

@media (max-width: 1120px) {
  .flow-board { grid-template-columns: 240px minmax(0, 1fr); }
  .execution-log { grid-column: 1 / -1; min-height: auto; }
  .execution-log ol { display: grid; grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 780px) {
  .guide-content { width: min(100% - 28px, 1380px); padding-top: var(--space-6); }
  .guide-header { padding-inline: var(--space-4); }
  .guide-header__title span { display: none; }
  .mode-picker, .task-card, .flow-board, .io-grid, .concept-grid, .mcp-grid { grid-template-columns: 1fr; }
  .node-stage { min-height: 560px; }
  .execution-log { grid-column: auto; }
  .execution-log ol { display: flex; }
  .flow-controls { flex-wrap: wrap; }
}
</style>
