const GOAL_VALUES = [
  "服装融合",
  "帽子 / 头饰",
  "品牌Logo",
  "品牌配色",
  "产品元素",
  "场景融合",
  "联名故事",
  "周边应用",
];

const TRIGGER_NAMES = new Set([
  "ai_supplement",
  "adopt_suggestion",
  "regenerate_suggestion",
  "clear_goal",
  "start_workflow",
  "advance_workflow",
  "open_agent_detail",
  "export_package",
  "retry_agent",
  "open_api_settings",
  "test_api_connection_with_credential",
  "test_api_connection",
  "save_api_settings_with_credential",
  "save_api_settings",
  "delete_api_credentials",
  "close_api_settings",
]);

const API_PRESETS = {
  custom: {
    provider: "openai_compatible",
    base_url: "",
    fast_model: "gpt-5.6-luna",
    main_model: "gpt-5.6-terra",
    image_model: "gpt-image-2",
  },
  teamorouter: {
    provider: "openai_compatible",
    base_url: "https://api.teamorouter.com/v1",
    fast_model: "gpt-5.6-luna",
    main_model: "gpt-5.6-terra",
    image_model: "gpt-image-2",
  },
};

// Ephemeral only: never serialized, never sent back from Python, and cleared
// on every settings action. This survives harmless renderer refreshes while a
// user is typing into the password field.
const pendingCredentials = new Map();

const FALLBACK_AGENTS = [
  {
    name: "IP Preparation Agent",
    cn: "IP素材预处理",
    desc: "检查IP图片质量并生成可进入后续流程的标准资产。",
    steps: ["检测主体完整度与背景复杂度", "确认当前主体可被稳定识别", "生成标准IP参考资产"],
    inputs: ["用户上传的IP参考图"],
    logic: ["检测清晰度、背景、遮挡与主体完整度", "复杂背景执行主体提取与清洗", "保留原始角色轮廓与关键视觉信息"],
    output: "Clean IP Asset",
  },
  {
    name: "IP Intelligence Agent",
    cn: "IP身份特征分析",
    desc: "建立 IP DNA 与 IP Identity Grammar，区分身份锚点、可形变特征和姿势相关特征。",
    steps: ["提取身份锚点与关系几何", "整理比例、面部与线条语法", "建立允许合法变化的 Identity Grammar"],
    inputs: ["Clean IP Asset"],
    logic: ["解释角色为何仍是同一角色", "区分可形变、姿势相关与禁止漂移特征", "Identity Preservation 不等于 Pose Preservation"],
    output: "IP DNA + IP Identity Grammar",
  },
  {
    name: "Brand Intelligence Agent",
    cn: "品牌识别分析",
    desc: "理解品牌基础视觉、色彩与品牌气质。",
    steps: ["识别品牌图像中的主要视觉资产", "提取配色与标志识别", "建立品牌基础画像"],
    inputs: ["用户上传的品牌参考图"],
    logic: ["识别标志性视觉元素", "提取颜色、空间、产品与品牌气质", "整理基础品牌资产"],
    output: "Brand Profile",
  },
  {
    name: "Brand Collaboration Agent",
    cn: "历史联名检索策略",
    desc: "判断是否存在历史联名数据，并决定参考路径。",
    steps: ["检查历史联名可用性", "选择历史优先或AI补充路径", "整理联名参考策略"],
    inputs: ["Brand Profile", "品牌名称/视觉信息"],
    logic: ["有历史数据时提取案例规律", "缺少数据时采用相似品类参考", "参考规律但不复制既有形象"],
    output: "Collaboration Reference Strategy",
  },
  {
    name: "Brand Feature Agent",
    cn: "品牌元素池",
    desc: "把品牌拆成多种可融合元素，而不是只使用Logo。",
    steps: ["拆解品牌符号与产品元素", "构建服装/帽子/场景元素池", "标注元素识别强度"],
    inputs: ["Brand Profile", "Collaboration Reference Strategy"],
    logic: ["整理Logo与颜色", "整理制服、帽子和产品", "整理门店与品牌场景"],
    output: "Brand Feature Pool",
  },
  {
    name: "Creative Brief Agent",
    cn: "创意需求理解",
    desc: "把用户多选项、自由输入和AI补充整理成结构化创意Brief。",
    steps: ["理解多选目标主次关系", "结合自由输入补全意图", "生成可执行 Creative Brief"],
    inputs: ["用户目标", "AI补充建议", "IP Identity Grammar", "Brand Feature Pool"],
    logic: ["自由输入优先于多选与AI补充", "判断主载体和辅助层", "明确目标收敛，模糊目标探索"],
    output: "Creative Brief",
  },
  {
    name: "Fusion Decision Agent",
    cn: "融合策略决策",
    desc: "根据 Creative Brief 决定联名关系，让品牌进入角色行为、身份与产品互动。",
    steps: ["匹配用户目标与品牌 Integration Affordance", "确定 Fusion Relationship 与融合深度", "生成最终 Fusion Strategy"],
    inputs: ["Creative Brief", "IP Identity Grammar", "Brand Feature Pool"],
    logic: ["明确 IP 与 Brand 的角色关系", "优先考虑产品互动、行为与角色融合", "避免 Sticker-like 机械贴标"],
    output: "Fusion Strategy + Fusion Relationship",
  },
  {
    name: "IP Adaptation Agent",
    cn: "IP姿势与身份适配",
    desc: "把联名关系转成可执行的动作、姿势与附着计划，同时遵守 IP Identity Grammar。",
    steps: ["确定目标动作、姿势与视角", "建立 Pose Blueprint 与 Deformation Map", "输出品牌附着和生成指令"],
    inputs: ["IP Identity Grammar", "Creative Brief", "Fusion Strategy", "Fusion Relationship", "Brand Feature Pool", "User Intent"],
    logic: ["允许姿势、视角、肢体与表情合法变化", "保持身份锚点、关系几何、比例和线条语法", "禁止将原图姿势当作冻结模板"],
    output: "IP Adaptation Plan",
  },
  {
    name: "Fusion Generation Agent",
    cn: "联名候选生成",
    desc: "按 Fusion Relationship 与 IP Adaptation Plan 生成候选，把原图作为身份参考而非冻结姿势模板。",
    steps: ["装载 IP Identity Grammar", "应用 Pose Blueprint 与品牌融合 Prompt", "生成候选并提交 Pose-Aware Guardian"],
    inputs: ["Fusion Strategy", "IP Adaptation Plan", "IP Identity Grammar", "Brand Feature Pool"],
    logic: ["可改变姿势、视角、肢体与身体朝向", "必须保持身份锚点、面部、耳朵、比例与线条语法", "候选必须经过 Pose-Aware Guardian"],
    output: "Candidate Design",
  },
  {
    name: "IP Guardian Agent",
    cn: "姿势感知IP身份守护",
    desc: "检查候选完成目标动作后是否仍遵守同一套 IP Identity Grammar，而不是比较姿势是否相同。",
    steps: ["理解原始、目标与候选姿势", "区分合法形变与 Identity Drift", "计算身份分并执行 Pose / Intent / Brand Gates"],
    inputs: ["原始IP与候选图", "IP Identity Grammar", "IP Adaptation Plan", "Creative Brief", "Fusion Relationship", "User Intent"],
    logic: ["姿势与视角变化本身不扣身份分", "惩罚面部、耳朵、比例、线条与物种漂移", "Python 决定 Reject / Revise / Pass"],
    output: "Pose-Aware Guardian Report + Revision Instruction",
  },
  {
    name: "Ranking Agent",
    cn: "方案评分排序",
    desc: "只有通过Guardian的候选才能进入评分与排序。",
    steps: ["计算IP与目标匹配度", "计算品牌识别与融合自然度", "输出综合评分与理由"],
    inputs: ["Guardian Pass候选", "Creative Brief", "Brand Feature Pool"],
    logic: ["用户目标与IP身份各25%", "品牌识别与融合自然度各15%", "商业价值、历史参考和创新性共20%"],
    output: "Ranking Result",
  },
  {
    name: "Design Package Agent",
    cn: "设计内容包封装",
    desc: "把最终通过的方案整理成设计师可继续使用的内容包。",
    steps: ["整理最终视觉与设计说明", "生成规范文件结构", "封装联名设计内容包"],
    inputs: ["最终通过方案", "评分结果", "Creative Brief", "品牌与IP资产"],
    logic: ["输出位图效果图", "输出可编辑格式说明", "输出规范、Prompt与结构化JSON"],
    output: "Collaboration Design Package",
  },
];

const SCORE_LABELS = {
  user_goal_match: "用户目标匹配",
  ip_identity_consistency: "IP身份一致性",
  brand_recognition: "品牌识别度",
  fusion_naturalness: "融合自然度",
  commercial_value: "商业应用价值",
  historical_collaboration_reference: "历史联名参考",
  innovation: "创新性",
};

const runtimeByRoot = new WeakMap();

function objectValue(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function arrayValue(value) {
  return Array.isArray(value) ? value : [];
}

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function normalizedStatus(value) {
  return String(value ?? "ready").trim().toLowerCase();
}

function booleanValue(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return booleanValue(firstDefined(value.ready, value.ok, value.enabled, value.status), fallback);
  }
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
    if (["true", "yes", "1", "ready", "connected", "live", "enabled"].includes(normalized)) return true;
    if (["false", "no", "0", "not_configured", "error", "disabled", "unavailable"].includes(normalized)) return false;
  }
  return fallback;
}

function createElement(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}

function imageSource(value, previews = {}) {
  if (!value) return "";
  if (typeof value === "string") {
    return previews[value] || value;
  }
  const item = objectValue(value);
  const direct = firstDefined(
    item.preview_url,
    item.data_url,
    item.image_url,
    item.url,
    item.uri,
    item.src,
  );
  if (direct) return String(direct);
  const id = firstDefined(item.asset_id, item.id);
  return id ? String(previews[id] || "") : "";
}

function agentName(value) {
  if (typeof value === "string") return value;
  const item = objectValue(value);
  return String(firstDefined(item.agent_name, item.name, ""));
}

function getRuntime(root) {
  let runtime = runtimeByRoot.get(root);
  if (!runtime) {
    runtime = {
      eventCounter: 0,
      autoAdvanceTokens: new Set(),
      lastDownloadToken: null,
      lastNotificationToken: null,
      pendingExport: false,
      toastMessage: "",
      toastExpiresAt: 0,
      activeAgent: null,
      apiSettingsOpen: false,
      apiSettingsDraft: null,
      apiConnectionTesting: false,
      deleteCredentialConfirmation: false,
      images: { ip_image: null, brand_image: null },
      selectedGoals: [],
      goalText: "",
    };
    runtimeByRoot.set(root, runtime);
  }
  return runtime;
}

function buildPageState(data) {
  const workflow = objectValue(
    firstDefined(data.workflow_snapshot, data.workflow, data.snapshot),
  );
  const rawPage = data.page_state;
  const page = { ...workflow, ...objectValue(rawPage) };
  if (typeof rawPage === "string") page.status = rawPage;
  if (!page.status && data.status) page.status = data.status;
  return page;
}

function snapshotRevision(pageState) {
  return firstDefined(
    pageState.revision,
    pageState.snapshot_revision,
    pageState.updated_at,
    pageState.checkpoint_version,
    arrayValue(pageState.events).length,
    0,
  );
}

function snapshotEventId(pageState) {
  const events = arrayValue(pageState.events);
  const event = objectValue(events.at(-1));
  return firstDefined(event.event_id, event.id, event.timestamp, null);
}

function triggerId(componentKey, triggerName, runtime) {
  runtime.eventCounter += 1;
  const randomPart = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : Math.random().toString(36).slice(2);
  return `${componentKey || "component"}:${triggerName}:${Date.now().toString(36)}:${runtime.eventCounter}:${randomPart}`;
}

function suggestionItems(value) {
  if (value === undefined || value === null || value === "") return [];
  if (typeof value === "string") {
    return value.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => suggestionItems(item)).slice(0, 24);
  }
  const item = objectValue(value);
  const nested = firstDefined(item.items, item.suggestions, item.recommendations);
  if (nested) return suggestionItems(nested);
  return Object.entries(item).flatMap(([key, entry]) => {
    if (entry === undefined || entry === null || entry === "") return [];
    if (Array.isArray(entry)) return [`${key}：${entry.join("、")}`];
    if (typeof entry === "object") return [`${key}：${JSON.stringify(entry)}`];
    return [`${key}：${entry}`];
  }).slice(0, 24);
}

function archivePayload(data, pageState, resultData) {
  const designOutput = objectValue(objectValue(pageState.outputs)["Design Package Agent"]);
  return objectValue(firstDefined(
    data.download,
    data.export_archive,
    pageState.download,
    resultData.download,
    resultData.archive,
    designOutput.download,
    designOutput.archive,
  ));
}

export default function(component) {
  const {
    data: rawData,
    key: componentKey,
    parentElement,
    setStateValue,
    setTriggerValue,
  } = component;

  const data = objectValue(rawData);
  const stateData = objectValue(data.state);
  const pageState = buildPageState(data);
  const runtime = getRuntime(parentElement);
  const listeners = [];
  const timers = new Set();
  const readers = new Set();

  const query = (selector) => parentElement.querySelector(selector);
  const later = (callback, delay) => {
    const timer = globalThis.setTimeout(() => {
      timers.delete(timer);
      callback();
    }, delay);
    timers.add(timer);
    return timer;
  };
  const listen = (target, eventName, handler, options) => {
    if (!target) return;
    target.addEventListener(eventName, handler, options);
    listeners.push(() => target.removeEventListener(eventName, handler, options));
  };

  const providerStatus = objectValue(data.provider_status);
  const healthStatus = objectValue(data.health);
  const apiSettings = objectValue(data.api_settings);
  const apiReadiness = objectValue(data.api_readiness);
  const apiConnectionResult = objectValue(firstDefined(
    data.api_connection_result,
    apiSettings.connection_result,
    apiReadiness.connection_result,
  ));
  const apiSettingsResult = objectValue(data.api_settings_result);
  const credentialConfigured = booleanValue(firstDefined(
    apiReadiness.credential_configured,
    apiSettings.credential_configured,
    healthStatus.credential_configured,
    providerStatus.credential_configured,
    false,
  ));
  const competitionMode = Boolean(firstDefined(
    pageState.competition_mode,
    providerStatus.competition_mode,
    false,
  ));
  const appTitle = query(".page-header h1");
  if (appTitle && data.app_name) appTitle.textContent = String(data.app_name);
  const providerMode = String(firstDefined(
    apiReadiness.mode,
    pageState.provider_mode,
    providerStatus.provider_mode,
    healthStatus.provider_mode,
    data.demo_mode ? "demo" : "unknown",
  )).toLowerCase();
  const searchMode = String(firstDefined(
    pageState.search_mode,
    providerStatus.search_mode,
    healthStatus.search_mode,
    "unknown",
  )).toLowerCase();
  const imageVerified = Boolean(firstDefined(
    pageState.image_provider_verified,
    providerStatus.image_provider_verified,
    healthStatus.image_provider_verified,
    false,
  ));
  const multiReferenceStatus = String(firstDefined(
    pageState.multi_reference_image_edit,
    providerStatus.multi_reference_image_edit_status,
    healthStatus.multi_reference_image_edit,
    "UNVERIFIED",
  )).toUpperCase();
  const runModeBadge = query("#runModeBadge");
  const isDemo = Boolean(data.demo_mode) || providerMode === "demo";
  const isLive = providerMode === "live";
  if (runModeBadge) {
    runModeBadge.classList.toggle("demo", isDemo);
    runModeBadge.classList.toggle("unverified", !isDemo && !isLive);
    runModeBadge.textContent = isDemo
      ? "DEMO"
      : isLive
        ? (pageState.run_id ? "LIVE RUN" : "LIVE READY")
        : "UNVERIFIED";
  }
  const runIdStatus = query("#runIdStatus");
  if (runIdStatus) runIdStatus.textContent = pageState.run_id
    ? `Run: ${pageState.run_id}`
    : "No active run";
  const runStartedStatus = query("#runStartedStatus");
  if (runStartedStatus) runStartedStatus.textContent = pageState.started_at
    ? `Started: ${pageState.started_at}`
    : "Not started";
  const providerModeStatus = query("#providerModeStatus");
  if (providerModeStatus) {
    const luna = isDemo
      ? "Luna Demo"
      : healthStatus.luna_ready ? "Luna Ready" : "Luna unchecked";
    const terra = isDemo
      ? "Terra Demo"
      : healthStatus.terra_ready ? "Terra Ready" : "Terra unchecked";
    providerModeStatus.textContent = `${luna} · ${terra}`;
  }
  const searchModeStatus = query("#searchModeStatus");
  if (searchModeStatus) searchModeStatus.textContent = searchMode === "demo"
    ? "Search: DEMO / MOCK"
    : `Search: ${searchMode.toUpperCase()}`;
  const imageModeStatus = query("#imageModeStatus");
  if (imageModeStatus) imageModeStatus.textContent = isDemo
    ? `Image: DEMO · Multi-ref ${multiReferenceStatus}`
    : imageVerified
      ? `Image: READY · Multi-ref ${multiReferenceStatus}`
      : `Image: UNVERIFIED · Multi-ref ${multiReferenceStatus}`;

  const connectionState = String(firstDefined(
    apiReadiness.connection_status,
    apiReadiness.status,
    apiSettings.connection_status,
    apiConnectionResult.status,
    "",
  )).trim().toLowerCase();
  const settingsOperationSucceeded = apiSettingsResult.ok === true;
  const connectionHasError = ["error", "failed", "invalid", "unavailable"].includes(connectionState)
    || apiReadiness.configuration_error === true
    || apiSettingsResult.ok === false
    || (!settingsOperationSucceeded && apiConnectionResult.ok === false);
  const readinessConnected = ["connected", "ready", "live"].includes(connectionState);
  const apiConnected = (credentialConfigured || readinessConnected) && !connectionHasError;
  const apiStatus = query("#apiConnectionStatus");
  if (apiStatus) {
    apiStatus.classList.toggle("connected", apiConnected);
    apiStatus.classList.toggle("error", connectionHasError);
    apiStatus.classList.toggle("not-configured", !apiConnected && !connectionHasError);
    apiStatus.textContent = connectionHasError
      ? "● API 配置错误"
      : apiConnected
        ? "● API 已连接"
        : "● API 未配置";
  }

  const explicitDemoMode = [
    apiReadiness.demo_mode,
    apiReadiness.using_demo,
    apiReadiness.demo_selected,
    String(apiReadiness.mode || "").toLowerCase() === "demo",
    data.demo_mode,
    isDemo,
  ].some((value) => booleanValue(value));
  const serviceStatus = (element, readyValue) => {
    if (!element) return;
    const ready = booleanValue(readyValue);
    const label = explicitDemoMode
      ? "DEMO"
      : connectionHasError
        ? "ERROR"
        : credentialConfigured && ready
          ? "READY"
          : "NOT CONFIGURED";
    element.textContent = label;
    element.classList.toggle("ready", label === "READY");
    element.classList.toggle("error", label === "ERROR");
    element.classList.toggle("demo", label === "DEMO");
  };
  serviceStatus(query("#fastServiceStatus"), firstDefined(
    apiReadiness.fast_ready,
    apiReadiness.fast,
    objectValue(apiReadiness.services).fast,
    healthStatus.fast_ready,
    healthStatus.luna_ready,
    apiConnected,
  ));
  serviceStatus(query("#mainServiceStatus"), firstDefined(
    apiReadiness.main_ready,
    apiReadiness.main,
    objectValue(apiReadiness.services).main,
    healthStatus.main_ready,
    healthStatus.terra_ready,
    apiConnected,
  ));
  serviceStatus(query("#imageServiceStatus"), firstDefined(
    apiReadiness.image_ready,
    apiReadiness.image,
    objectValue(apiReadiness.services).image,
    healthStatus.image_ready,
    healthStatus.image_provider_configured,
    apiConnected,
  ));
  const searchServiceStatus = query("#searchServiceStatus");
  if (searchServiceStatus) {
    const readinessSearch = String(firstDefined(
      objectValue(apiReadiness.services).search,
      searchMode,
      "DEMO / MOCK",
    )).trim().toLowerCase();
    const searchLive = readinessSearch === "live" || readinessSearch === "ready";
    searchServiceStatus.textContent = searchLive ? "LIVE" : "DEMO / MOCK";
    searchServiceStatus.classList.toggle("ready", searchLive);
    searchServiceStatus.classList.toggle("demo", !searchLive);
  }

  const toast = query("#toast");
  const showToast = (message) => {
    if (!toast) return;
    runtime.toastMessage = String(message);
    runtime.toastExpiresAt = Date.now() + 1900;
    toast.textContent = runtime.toastMessage;
    toast.classList.add("show");
    later(() => {
      if (Date.now() >= runtime.toastExpiresAt) toast.classList.remove("show");
    }, 1910);
  };

  if (toast && runtime.toastExpiresAt > Date.now()) {
    toast.textContent = runtime.toastMessage;
    toast.classList.add("show");
    later(() => toast.classList.remove("show"), runtime.toastExpiresAt - Date.now() + 10);
  } else if (toast) {
    toast.classList.remove("show");
  }

  const backendNotification = objectValue(data.notification);
  const notificationMessage = backendNotification.message;
  const notificationToken = String(firstDefined(
    backendNotification.event_id,
    backendNotification.id,
    notificationMessage,
    "",
  ));
  if (notificationMessage && notificationToken !== runtime.lastNotificationToken) {
    runtime.lastNotificationToken = notificationToken;
    showToast(notificationMessage);
  }

  const emitTrigger = (name, payload = {}, options = {}) => {
    if (!TRIGGER_NAMES.has(name)) return;
    const event = {
      event_id: triggerId(componentKey, name, runtime),
      action: name,
      run_id: firstDefined(pageState.run_id, null),
      revision: snapshotRevision(pageState),
      snapshot_event_id: snapshotEventId(pageState),
      emitted_at: new Date().toISOString(),
      ...payload,
    };
    if (options.stateKey) setStateValue(options.stateKey, event);
    else setTriggerValue(name, event);
  };

  const timeoutValue = (value, fallback) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    return Math.min(3600, Math.max(1, Math.round(numeric)));
  };
  const settingsPreset = String(firstDefined(apiSettings.preset, "custom")).toLowerCase();
  const publicApiSettings = {
    provider: String(firstDefined(apiSettings.provider, "openai_compatible")),
    preset: API_PRESETS[settingsPreset] ? settingsPreset : "custom",
    base_url: String(firstDefined(apiSettings.base_url, "")),
    model_fast: String(firstDefined(
      apiSettings.model_fast,
      apiSettings.fast_model,
      API_PRESETS.custom.fast_model,
    )),
    model_main: String(firstDefined(
      apiSettings.model_main,
      apiSettings.main_model,
      API_PRESETS.custom.main_model,
    )),
    image_model: String(firstDefined(apiSettings.image_model, API_PRESETS.custom.image_model)),
    fast_timeout: timeoutValue(apiSettings.fast_timeout, 60),
    main_timeout: timeoutValue(apiSettings.main_timeout, 120),
    image_timeout: timeoutValue(apiSettings.image_timeout, 180),
  };

  const requestedApiSettingsOpen = firstDefined(
    apiSettings.modal_open,
    apiSettings.open,
    data.api_settings_open,
  );
  if (requestedApiSettingsOpen === true) runtime.apiSettingsOpen = true;
  if (apiSettings.force_close === true) runtime.apiSettingsOpen = false;
  if (!runtime.apiSettingsDraft) {
    runtime.apiSettingsDraft = { ...publicApiSettings };
  }

  const apiSettingsBackdrop = query("#apiSettingsBackdrop");
  const apiSettingsModal = query(".api-settings-modal");
  const apiSettingsForm = query("#apiSettingsForm");
  const apiProvider = query("#apiProvider");
  const apiPreset = query("#apiPreset");
  const apiBaseUrl = query("#apiBaseUrl");
  const apiKeyInput = query("#apiKeyInput");
  const apiFastModel = query("#apiFastModel");
  const apiMainModel = query("#apiMainModel");
  const apiImageModel = query("#apiImageModel");
  const apiFastTimeout = query("#apiFastTimeout");
  const apiMainTimeout = query("#apiMainTimeout");
  const apiImageTimeout = query("#apiImageTimeout");
  const apiCredentialNote = query("#apiCredentialNote");
  const apiResultPanel = query("#apiConnectionResult");
  const testApiConnectionBtn = query("#testApiConnectionBtn");
  const advancedImageTestBtn = query("#advancedImageTestBtn");
  const deleteCredentialConfirm = query("#deleteCredentialConfirm");

  // A renderer refresh after the trigger means Python has finished the
  // blocking provider check and returned a result (success or failure).
  if (runtime.apiConnectionTesting) runtime.apiConnectionTesting = false;

  const clearCredentialDom = () => {
    const currentCredentialInput = query("#apiKeyInput");
    if (currentCredentialInput) currentCredentialInput.value = "";
  };
  const clearCredentialInput = () => {
    clearCredentialDom();
    pendingCredentials.delete(String(componentKey || "component"));
  };
  // The DOM field stays transient while the modal is open. It is cleared on
  // open/close and synchronously before every settings trigger is emitted.

  const setFormValue = (element, value) => {
    if (element && document.activeElement !== element) element.value = String(value ?? "");
  };
  const hydrateApiSettingsForm = () => {
    const draft = runtime.apiSettingsDraft || publicApiSettings;
    setFormValue(apiProvider, draft.provider);
    setFormValue(apiPreset, draft.preset);
    setFormValue(apiBaseUrl, draft.base_url);
    setFormValue(apiFastModel, draft.model_fast);
    setFormValue(apiMainModel, draft.model_main);
    setFormValue(apiImageModel, draft.image_model);
    setFormValue(apiFastTimeout, draft.fast_timeout);
    setFormValue(apiMainTimeout, draft.main_timeout);
    setFormValue(apiImageTimeout, draft.image_timeout);
  };
  hydrateApiSettingsForm();

  if (apiKeyInput) {
    apiKeyInput.placeholder = credentialConfigured
      ? "已保存安全凭据（重新输入可替换）"
      : "输入 API Key";
    listen(apiKeyInput, "input", () => {
      pendingCredentials.set(
        String(componentKey || "component"),
        String(apiKeyInput.value || ""),
      );
    });
  }
  if (apiCredentialNote) {
    apiCredentialNote.classList.remove("testing");
    apiCredentialNote.removeAttribute("role");
    apiCredentialNote.removeAttribute("aria-live");
    const sessionOnly = apiSettings.session_only === true
      || (credentialConfigured && apiSettings.credential_persistent === false);
    apiCredentialNote.classList.toggle("configured", credentialConfigured && !sessionOnly);
    apiCredentialNote.classList.toggle("warning", sessionOnly);
    const ephemeralTestPassed = !credentialConfigured && apiConnectionResult.ok === true;
    apiCredentialNote.textContent = ephemeralTestPassed
      ? "连接测试已通过。点击“保存设置”将保存刚才通过测试的 API Key。"
      : sessionOnly
      ? "系统安全凭据存储不可用，本次 API Key 仅在当前会话中使用。"
      : credentialConfigured
        ? "已保存安全凭据。如需替换，请输入新的 API Key。"
        : "尚未保存安全凭据。";
  }

  const safeBrowserMessage = (value) => {
    let message = String(value ?? "").trim();
    if (!message) return "连接未完成，请检查 Provider 和模型设置。";
    if (/traceback|stack trace/i.test(message)) {
      return "连接未完成，请检查 Provider 和模型设置。";
    }
    message = message
      .replace(/\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b/gi, "[credential redacted]")
      .replace(/(?:authorization|api[_ -]?key|token|password|secret)\s*[:=]\s*[^\s,;]+/gi, "credential=[redacted]")
      .replace(/(^|\s)\/(?:Users|home|private|tmp|var)\/[^\s]+/g, "$1[local path]");
    return message.slice(0, 320);
  };

  const renderApiConnectionResult = () => {
    if (!apiResultPanel) return;
    apiResultPanel.classList.remove("show", "success", "error", "testing");
    const settingsMessage = String(firstDefined(apiSettingsResult.message, ""));
    const connectionMessage = String(firstDefined(apiConnectionResult.message, ""));
    const showSettingsResult = Object.keys(apiSettingsResult).length > 0
      && settingsMessage !== connectionMessage;
    const displayedResult = showSettingsResult ? apiSettingsResult : apiConnectionResult;
    const resultStatus = String(firstDefined(displayedResult.status, "")).toLowerCase();
    const hasResult = Object.keys(displayedResult).length > 0;
    if (!hasResult) {
      apiResultPanel.textContent = "";
      return;
    }
    apiResultPanel.classList.add("show");
    if (["testing", "pending", "running"].includes(resultStatus)) {
      apiResultPanel.classList.add("testing");
      apiResultPanel.textContent = "API Connection\n正在分阶段检查 Provider、Fast 与 Main 模型…";
      return;
    }
    const resultOk = displayedResult.ok === true
      || ["ok", "success", "connected", "ready"].includes(resultStatus);
    if (resultOk) {
      apiResultPanel.classList.add("success");
      const checks = arrayValue(displayedResult.checks);
      if (checks.length) {
        const checkLabels = { provider: "Provider", fast: "Fast Model", main: "Main Model", image: "Image Model" };
        const lines = checks.map((rawCheck) => {
          const check = objectValue(rawCheck);
          const status = String(check.status || "unverified").toLowerCase();
          const mark = status === "pass" ? "✓" : status === "fail" ? "✗" : "•";
          const label = checkLabels[check.name] || "Service";
          const model = check.model ? `  ${safeBrowserMessage(check.model)}` : "";
          return `${mark} ${label}${model}`;
        });
        apiResultPanel.textContent = ["API Connection", ...lines].join("\n");
      } else {
        apiResultPanel.textContent = `API Settings\n✓ ${safeBrowserMessage(displayedResult.message)}`;
      }
      return;
    }
    apiResultPanel.classList.add("error");
    apiResultPanel.textContent = `API Connection\n✗ ${safeBrowserMessage(firstDefined(
      displayedResult.browser_message,
      displayedResult.error,
      displayedResult.message,
    ))}`;
  };
  renderApiConnectionResult();

  const setApiTestLoading = (loading, advancedImageTest = false) => {
    runtime.apiConnectionTesting = Boolean(loading);
    [testApiConnectionBtn, advancedImageTestBtn].forEach((button) => {
      if (!button) return;
      button.disabled = Boolean(loading);
      button.setAttribute("aria-busy", String(Boolean(loading)));
    });
    if (testApiConnectionBtn) {
      testApiConnectionBtn.classList.toggle("is-loading", Boolean(loading));
      testApiConnectionBtn.textContent = loading ? "连接测试中…" : "测试连接";
    }
    if (loading && apiCredentialNote) {
      apiCredentialNote.classList.remove("configured", "warning");
      apiCredentialNote.classList.add("testing");
      apiCredentialNote.setAttribute("role", "status");
      apiCredentialNote.setAttribute("aria-live", "polite");
      apiCredentialNote.textContent = advancedImageTest
        ? "正在执行高级图像测试，请保持页面打开…"
        : "正在测试 API 连接，请保持页面打开…";
    }
    if (loading && apiResultPanel) {
      apiResultPanel.className = "api-connection-result show testing";
      apiResultPanel.textContent = advancedImageTest
        ? "API Connection\n正在执行高级图像测试，请保持页面打开…"
        : "API Connection\n正在检查 Provider、Fast 和 Main，请保持页面打开（通常需要 10–90 秒）…";
    }
  };
  setApiTestLoading(false);

  const setApiSettingsVisibility = (open) => {
    runtime.apiSettingsOpen = Boolean(open);
    apiSettingsBackdrop?.classList.toggle("show", runtime.apiSettingsOpen);
    apiSettingsBackdrop?.setAttribute("aria-hidden", String(!runtime.apiSettingsOpen));
    if (runtime.apiSettingsOpen) {
      later(() => apiProvider?.focus(), 0);
    }
  };
  setApiSettingsVisibility(runtime.apiSettingsOpen);

  const readApiSettingsForm = () => ({
    provider: String(apiProvider?.value || "openai_compatible"),
    preset: String(apiPreset?.value || "custom"),
    base_url: String(apiBaseUrl?.value || "").trim(),
    model_fast: String(apiFastModel?.value || "").trim(),
    model_main: String(apiMainModel?.value || "").trim(),
    image_model: String(apiImageModel?.value || "").trim(),
    fast_timeout: timeoutValue(apiFastTimeout?.value, 60),
    main_timeout: timeoutValue(apiMainTimeout?.value, 120),
    image_timeout: timeoutValue(apiImageTimeout?.value, 180),
  });
  const apiSettingsPayload = (advancedImageTest = false, sourceElement = null) => {
    const settings = readApiSettingsForm();
    runtime.apiSettingsDraft = { ...settings };
    const sourceForm = sourceElement?.closest?.("form");
    const currentCredentialInput = sourceForm?.querySelector?.("#apiKeyInput")
      || query("#apiKeyInput");
    const apiKey = String(
      currentCredentialInput?.value
      || pendingCredentials.get(String(componentKey || "component"))
      || "",
    ).trim();
    const payload = {
      ...settings,
      timeouts: {
        fast: settings.fast_timeout,
        main: settings.main_timeout,
        image: settings.image_timeout,
      },
      advanced_image_test: advancedImageTest,
      ...(apiKey ? { credential_input: apiKey } : {}),
    };
    return payload;
  };
  const clearCredentialAfterAction = () => {
    // Components v2 can briefly keep an old renderer listener alive while its
    // replacement mounts. All listeners for one DOM action must read the same
    // one-shot value. Clear only after the current event dispatch completes,
    // so a duplicate listener cannot overwrite the trigger with an empty key.
    globalThis.setTimeout(clearCredentialInput, 250);
  };

  const openApiSettings = () => {
    runtime.apiSettingsDraft = { ...publicApiSettings };
    runtime.deleteCredentialConfirmation = false;
    hydrateApiSettingsForm();
    clearCredentialInput();
    setApiSettingsVisibility(true);
    emitTrigger("open_api_settings", { credential_configured: credentialConfigured });
  };
  const closeApiSettings = (reason = "cancel", extra = {}) => {
    clearCredentialInput();
    runtime.apiSettingsDraft = null;
    runtime.deleteCredentialConfirmation = false;
    if (deleteCredentialConfirm) deleteCredentialConfirm.hidden = true;
    setApiSettingsVisibility(false);
    emitTrigger("close_api_settings", { reason, ...extra });
  };

  listen(query("#apiSettingsBtn"), "click", openApiSettings);
  listen(query("#closeApiSettingsBtn"), "click", () => closeApiSettings("close"));
  listen(query("#cancelApiSettingsBtn"), "click", () => closeApiSettings("cancel"));
  listen(apiSettingsBackdrop, "click", (event) => {
    if (event.target === apiSettingsBackdrop) closeApiSettings("backdrop");
  });

  const updateApiSettingsDraft = () => {
    runtime.apiSettingsDraft = readApiSettingsForm();
  };
  [apiProvider, apiBaseUrl, apiFastModel, apiMainModel, apiImageModel,
    apiFastTimeout, apiMainTimeout, apiImageTimeout].forEach((field) => {
    listen(field, "input", updateApiSettingsDraft);
    listen(field, "change", updateApiSettingsDraft);
  });
  listen(apiPreset, "change", () => {
    const presetName = String(apiPreset?.value || "custom");
    const preset = API_PRESETS[presetName] || API_PRESETS.custom;
    if (presetName === "teamorouter") {
      setFormValue(apiProvider, preset.provider);
      setFormValue(apiBaseUrl, preset.base_url);
      setFormValue(apiFastModel, preset.fast_model);
      setFormValue(apiMainModel, preset.main_model);
      setFormValue(apiImageModel, preset.image_model);
    }
    updateApiSettingsDraft();
  });

  const testApiConnection = (advancedImageTest, sourceElement) => {
    if (!apiSettingsForm?.reportValidity()) return;
    const payload = apiSettingsPayload(advancedImageTest, sourceElement);
    // Replace the saved-credential note and any previous connection result
    // before handing control to Streamlit. The next renderer restores the
    // credential note and paints only the newly returned result.
    setApiTestLoading(true, advancedImageTest);
    emitTrigger(
      payload.credential_input
        ? "test_api_connection_with_credential"
        : "test_api_connection",
      payload,
    );
  };
  listen(testApiConnectionBtn, "click", (event) => {
    testApiConnection(false, event.currentTarget);
    clearCredentialAfterAction();
  });
  listen(advancedImageTestBtn, "click", (event) => {
    testApiConnection(true, event.currentTarget);
    clearCredentialAfterAction();
  });
  listen(apiSettingsForm, "submit", (event) => {
    event.preventDefault();
    if (!apiSettingsForm.reportValidity()) return;
    const payload = apiSettingsPayload(false, event.currentTarget);
    emitTrigger(
      payload.credential_input
        ? "save_api_settings_with_credential"
        : "save_api_settings",
      payload,
    );
    clearCredentialAfterAction();
    showToast("正在保存 API 设置并更新主页状态…");
  });

  const showDeleteCredentialConfirmation = () => {
    runtime.deleteCredentialConfirmation = true;
    if (deleteCredentialConfirm) deleteCredentialConfirm.hidden = false;
    later(() => query("#confirmDeleteApiCredentialsBtn")?.focus(), 0);
  };
  const hideDeleteCredentialConfirmation = () => {
    runtime.deleteCredentialConfirmation = false;
    if (deleteCredentialConfirm) deleteCredentialConfirm.hidden = true;
  };
  const deleteCredentialButton = query("#deleteApiCredentialsBtn");
  if (deleteCredentialButton) deleteCredentialButton.disabled = !credentialConfigured;
  if (deleteCredentialConfirm) {
    deleteCredentialConfirm.hidden = !runtime.deleteCredentialConfirmation;
  }
  listen(deleteCredentialButton, "click", showDeleteCredentialConfirmation);
  listen(query("#cancelDeleteApiCredentialsBtn"), "click", hideDeleteCredentialConfirmation);
  listen(query("#confirmDeleteApiCredentialsBtn"), "click", () => {
    clearCredentialInput();
    hideDeleteCredentialConfirmation();
    emitTrigger("delete_api_credentials", { confirmed: true });
    showToast("正在删除 API 凭据");
  });
  listen(document, "keydown", (event) => {
    if (event.key === "Escape" && runtime.apiSettingsOpen) closeApiSettings("escape");
  });

  const persistPageView = (activeAgent) => {
    setStateValue("page_state", {
      status: firstDefined(pageState.status, "ready"),
      run_id: firstDefined(pageState.run_id, null),
      revision: snapshotRevision(pageState),
      active_agent: activeAgent,
    });
  };

  const userIntent = objectValue(pageState.user_intent);
  const stateValue = (name) => firstDefined(data[name], stateData[name], userIntent[name]);
  const selectedHydration = stateValue("selected_goals");
  if (Array.isArray(selectedHydration)) {
    const selectedFromPython = selectedHydration
      .map((goal) => goal === "帽子/头饰" ? "帽子 / 头饰" : String(goal))
      .filter((goal) => GOAL_VALUES.includes(goal));
    runtime.selectedGoals = [...new Set(selectedFromPython)];
  }
  const goalHydration = stateValue("goal_text");
  if (goalHydration !== undefined && goalHydration !== null) {
    runtime.goalText = String(goalHydration);
  }
  runtime.images.ip_image = firstDefined(
    stateValue("ip_image"),
    objectValue(pageState.input_assets).ip_image,
    runtime.images.ip_image,
  );
  runtime.images.brand_image = firstDefined(
    stateValue("brand_image"),
    objectValue(pageState.input_assets).brand_image,
    runtime.images.brand_image,
  );

  const previews = objectValue(firstDefined(data.asset_previews, data.previews));
  const hydrateImage = (role) => {
    const prefix = role === "ip_image" ? "ip" : "brand";
    const image = query(`#${prefix}Img`);
    const tip = query(`#${prefix}Tip`);
    const source = imageSource(runtime.images[role], previews);
    if (image) {
      if (source) {
        if (image.src !== source) image.src = source;
        image.style.display = "block";
      } else {
        image.removeAttribute("src");
        image.style.display = "none";
      }
    }
    if (tip) tip.style.display = source ? "none" : "block";
  };
  hydrateImage("ip_image");
  hydrateImage("brand_image");

  const goalOptions = [...parentElement.querySelectorAll(".goal-option")];
  const paintGoals = () => {
    const selected = new Set(runtime.selectedGoals);
    goalOptions.forEach((option) => {
      const isSelected = selected.has(option.dataset.value);
      option.classList.toggle("selected", isSelected);
      option.setAttribute("aria-checked", String(isSelected));
    });
  };
  paintGoals();

  const goalText = query("#goalText");
  const activeElement = parentElement.activeElement || document.activeElement;
  if (goalText && activeElement !== goalText && goalText.value !== runtime.goalText) {
    goalText.value = runtime.goalText;
  }

  const renderSuggestion = (value) => {
    const panel = query("#aiSuggestion");
    const list = query("#aiSuggestionList");
    const items = suggestionItems(value);
    if (!panel || !list) return;
    list.replaceChildren(...items.map((item) => createElement("li", "", item)));
    panel.classList.toggle("show", items.length > 0);
  };
  renderSuggestion(stateValue("ai_suggestion"));
  const adoptSuggestionButton = query("#adoptSuggestionBtn");
  const suggestionAdopted = booleanValue(firstDefined(
    data.ai_suggestion_adopted,
    stateData.ai_suggestion_adopted,
    false,
  ));
  if (adoptSuggestionButton) {
    adoptSuggestionButton.disabled = suggestionAdopted;
    adoptSuggestionButton.textContent = suggestionAdopted ? "✓ 已采用" : "采用建议";
  }

  const syncIntentState = () => {
    const currentText = goalText ? goalText.value : runtime.goalText;
    runtime.goalText = currentText;
    setStateValue("selected_goals", [...runtime.selectedGoals]);
    setStateValue("goal_text", currentText);
    return { selected_goals: [...runtime.selectedGoals], goal_text: currentText };
  };

  const loadAssetState = (role, value, message) => {
    runtime.images[role] = value;
    hydrateImage(role);
    // Submit both sides as one atomic value. Safari may otherwise deliver two
    // independent Component state updates across different rerenders and let
    // the newest image replace the already persisted sibling.
    setStateValue("image_pair", {
      ip_image: runtime.images.ip_image,
      brand_image: runtime.images.brand_image,
    });
    showToast(message);
  };

  const openAssetPicker = (role) => {
    const input = query(role === "ip_image" ? "#ipFileInput" : "#brandFileInput");
    input?.click();
  };

  const readUpload = (role, input) => {
    const file = input.files?.[0];
    if (!file) return;
    const allowed = new Set(["image/png", "image/jpeg", "image/webp"]);
    const extensionAllowed = /\.(png|jpe?g|webp)$/i.test(file.name);
    const maxBytes = Number(data.max_upload_bytes || 50 * 1024 * 1024);
    if ((!allowed.has(file.type) && !(file.type === "" && extensionAllowed)) || file.size <= 0) {
      input.value = "";
      showToast("请选择 PNG、JPEG 或 WebP 图片");
      return;
    }
    if (file.size > maxBytes) {
      input.value = "";
      showToast(`图片不能超过 ${Math.ceil(maxBytes / 1024 / 1024)} MB`);
      return;
    }
    const reader = new FileReader();
    readers.add(reader);
    reader.onload = () => {
      readers.delete(reader);
      input.value = "";
      const payload = {
        source: "upload",
        filename: file.name,
        mime_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        data_url: String(reader.result || ""),
      };
      loadAssetState(
        role,
        payload,
        role === "ip_image" ? "IP图片已选择并等待安全校验" : "品牌图片已选择并等待安全校验",
      );
    };
    reader.onerror = () => {
      readers.delete(reader);
      input.value = "";
      showToast("图片读取失败，请重新选择");
    };
    reader.onabort = () => {
      readers.delete(reader);
      input.value = "";
    };
    reader.readAsDataURL(file);
  };

  [["ip_image", "#ipPreview", "#ipFileInput"], ["brand_image", "#brandPreview", "#brandFileInput"]]
    .forEach(([role, previewSelector, inputSelector]) => {
      const preview = query(previewSelector);
      const input = query(inputSelector);
      listen(preview, "click", () => openAssetPicker(role));
      listen(preview, "keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openAssetPicker(role);
        }
      });
      listen(input, "change", () => readUpload(role, input));
    });

  goalOptions.forEach((option) => {
    const toggle = () => {
      const value = option.dataset.value;
      if (runtime.selectedGoals.includes(value)) {
        runtime.selectedGoals = runtime.selectedGoals.filter((goal) => goal !== value);
      } else {
        runtime.selectedGoals = GOAL_VALUES.filter(
          (goal) => runtime.selectedGoals.includes(goal) || goal === value,
        );
      }
      paintGoals();
      setStateValue("selected_goals", [...runtime.selectedGoals]);
      showToast(runtime.selectedGoals.length
        ? `已选择 ${runtime.selectedGoals.length} 个联名目标`
        : "已取消全部目标，将由AI探索");
    };
    listen(option, "click", toggle);
    listen(option, "keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
  });

  listen(goalText, "input", () => { runtime.goalText = goalText.value; });
  listen(goalText, "blur", () => setStateValue("goal_text", goalText.value));

  const isRunning = ["running", "processing"].includes(normalizedStatus(pageState.status));
  const workflowStartEnabled = booleanValue(firstDefined(
    apiReadiness.workflow_start_enabled,
    explicitDemoMode || credentialConfigured,
  ));
  const startButton = query("#startBtn");
  const configureApiButton = query("#configureApiBtn");
  const useDemoButton = query("#useDemoBtn");
  const providerGateHint = query("#providerGateHint");
  if (startButton) {
    startButton.disabled = !workflowStartEnabled;
    startButton.setAttribute("aria-disabled", String(!workflowStartEnabled));
    if (!workflowStartEnabled) startButton.setAttribute("aria-describedby", "providerGateHint");
    else startButton.removeAttribute("aria-describedby");
  }
  [query("#aiSupplementBtn"), query("#regenerateSuggestionBtn")].forEach((button) => {
    if (!button) return;
    button.disabled = !workflowStartEnabled;
    button.setAttribute("aria-disabled", String(!workflowStartEnabled));
  });
  if (configureApiButton) configureApiButton.hidden = workflowStartEnabled;
  if (useDemoButton) useDemoButton.hidden = workflowStartEnabled;
  if (providerGateHint) {
    providerGateHint.hidden = workflowStartEnabled;
    providerGateHint.textContent = connectionHasError
      ? "API 配置有误，请修正设置或使用 Demo。"
      : "请先配置 API，或使用 Demo 演示。";
  }
  listen(configureApiButton, "click", openApiSettings);
  listen(useDemoButton, "click", () => {
    showToast("正在切换到明确的 DEMO MODE");
    closeApiSettings("use_demo", { use_demo: true });
  });
  listen(query("#aiSupplementBtn"), "click", () => {
    const intent = syncIntentState();
    showToast("正在生成结构化创意补充");
    emitTrigger("ai_supplement", intent);
  });
  listen(adoptSuggestionButton, "click", () => {
    if (suggestionAdopted) return;
    showToast("正在采用 AI 补充建议");
    emitTrigger("adopt_suggestion", { suggestion: stateValue("ai_suggestion") });
  });
  listen(query("#regenerateSuggestionBtn"), "click", () => {
    const intent = syncIntentState();
    showToast("正在重新生成 AI 建议");
    emitTrigger("regenerate_suggestion", intent);
  });
  listen(query("#clearGoalBtn"), "click", () => {
    runtime.selectedGoals = [];
    runtime.goalText = "";
    if (goalText) goalText.value = "";
    paintGoals();
    renderSuggestion(null);
    setStateValue("selected_goals", []);
    setStateValue("goal_text", "");
    setStateValue("ai_suggestion", null);
    showToast("用户目标已清空");
    emitTrigger("clear_goal");
  });
  listen(startButton, "click", () => {
    if (!workflowStartEnabled) {
      showToast("请先配置 API，或使用 Demo");
      return;
    }
    if (isRunning && !competitionMode) {
      showToast("Workflow 正在运行，请稍候");
      return;
    }
    const hasIp = Boolean(imageSource(runtime.images.ip_image, previews));
    const hasBrand = Boolean(imageSource(runtime.images.brand_image, previews));
    if (!hasIp || !hasBrand) {
      showToast("请先加载 IP 与品牌参考图");
      return;
    }
    const intent = syncIntentState();
    showToast(intent.selected_goals.length || intent.goal_text
      ? "AI Workflow 已启动"
      : "未设置明确目标，将进入 AI 探索模式");
    emitTrigger("start_workflow", {
      ...intent,
      has_ip_image: hasIp,
      has_brand_image: hasBrand,
      ip_asset_id: objectValue(runtime.images.ip_image).asset_id || null,
      brand_asset_id: objectValue(runtime.images.brand_image).asset_id || null,
    });
  });

  const records = arrayValue(firstDefined(pageState.execution_records, data.execution_records));
  const recordFor = (name) => objectValue(records.find((record) => agentName(record) === name));
  const suppliedCatalog = arrayValue(firstDefined(data.agent_catalog, pageState.agent_catalog, data.agents));
  const catalog = FALLBACK_AGENTS.map((fallback) => {
    const supplied = objectValue(suppliedCatalog.find((entry) => agentName(entry) === fallback.name));
    return { ...fallback, ...supplied, name: fallback.name };
  });
  const agentFor = (name) => catalog.find((agent) => agent.name === name)
    || { name, cn: "", desc: "", steps: [], inputs: [], logic: [], output: "" };

  const workflowStage = query("#workflowStage");
  const renderReady = () => {
    workflowStage?.classList.remove("completed-mode");
    const card = createElement("div", "ready-card");
    card.append(
      createElement("h3", "", "AI Workflow Ready"),
      createElement("p", "", "等待输入完成并启动Agent调度"),
    );
    workflowStage?.replaceChildren(card);
  };

  const makeAgentCard = (agent, index, record, state) => {
    const card = createElement("div", `agent-card${state === "error" ? " error-card" : ""}`);
    const top = createElement("div", "agent-top");
    const heading = createElement("div");
    heading.append(
      createElement("h3", "", `${String(index + 1).padStart(2, "0")} · ${agent.name}`),
      createElement("div", "agent-cn", agent.cn),
    );
    const pillText = state === "done" ? "已完成" : state === "error" ? "执行失败" : "处理中";
    const pill = createElement("div", `status-pill${state === "done" ? " done" : state === "error" ? " error" : ""}`, pillText);
    top.append(heading, pill);
    const description = createElement("div", "agent-desc", firstDefined(record.responsibility, agent.desc));
    const progressBox = createElement("div", "progress-box");
    const progress = firstDefined(
      pageState.progress_text,
      record.error,
      record.output_summary,
      record.decision_summary,
      arrayValue(agent.steps)[Number(pageState.step_index || 0)],
      arrayValue(agent.steps)[0],
      "等待后端执行",
    );
    const progressText = createElement("div", "progress-text");
    progressText.append(createElement("span", "", progress));
    if (state === "processing") progressText.append(createElement("span", "progress-dots"));
    progressBox.append(createElement("div", "progress-label", "当前处理摘要"), progressText);
    card.append(top, description, progressBox);
    return card;
  };

  const pruneAdvanceTokens = () => {
    if (runtime.autoAdvanceTokens.size <= 100) return;
    runtime.autoAdvanceTokens = new Set([...runtime.autoAdvanceTokens].slice(-50));
  };
  const advanceToken = (reason, name) => [
      pageState.run_id || "no-run",
      snapshotRevision(pageState),
      snapshotEventId(pageState) || "no-event",
      name || "no-agent",
      reason,
      arrayValue(pageState.completed_agents).length,
    ].join(":");
  const autoAdvance = (reason, name) => {
    const token = advanceToken(reason, name);
    if (runtime.autoAdvanceTokens.has(token)) return;
    runtime.autoAdvanceTokens.add(token);
    pruneAdvanceTokens();
    emitTrigger("advance_workflow", {
      reason,
      agent_name: name || null,
      dedupe_token: token,
    }, { stateKey: "advance_request" });
  };

  const renderCompleted = (completedNames) => {
    if (!workflowStage) return;
    workflowStage.classList.add("completed-mode");
    const completedSet = new Set(completedNames);
    const ordered = catalog.filter((agent) => completedSet.has(agent.name));
    const grid = createElement("div", "completed-grid");
    grid.dataset.agentCount = String(ordered.length);
    grid.setAttribute("aria-label", `${ordered.length} Agent completed workflow`);
    ordered.forEach((agent) => {
      const index = catalog.findIndex((entry) => entry.name === agent.name);
      const card = createElement("button", "completed-card");
      card.type = "button";
      card.append(
        createElement("h4", "", `${String(index + 1).padStart(2, "0")} · ${agent.name}`),
        createElement("div", "cn", agent.cn),
        createElement("div", "done-text", "✅ 已完成 · 点击查看明细"),
      );
      listen(card, "click", () => openAgentDetail(agent.name));
      grid.append(card);
    });
    workflowStage.replaceChildren(grid);
  };

  const renderError = () => {
    if (!workflowStage) return;
    workflowStage.classList.remove("completed-mode");
    const failedName = agentName(firstDefined(pageState.failed_agent, pageState.current_agent))
      || "Workflow";
    const agent = agentFor(failedName);
    const index = Math.max(0, catalog.findIndex((entry) => entry.name === failedName));
    const record = recordFor(failedName);
    const card = makeAgentCard(agent, index, { ...record, error: firstDefined(pageState.error, record.error, "执行失败") }, "error");
    const actions = createElement("div", "action-row error-actions");
    const retry = createElement("button", "", "重试当前 Agent");
    retry.type = "button";
    listen(retry, "click", () => {
      showToast(`正在重试 ${failedName}`);
      emitTrigger("retry_agent", { agent_name: failedName });
    });
    actions.append(retry);
    card.append(actions);
    workflowStage.replaceChildren(card);
  };

  const outputs = objectValue(pageState.outputs);
  const workflowStatus = normalizedStatus(firstDefined(pageState.status, "ready"));
  const completedNames = arrayValue(pageState.completed_agents).map(agentName).filter(Boolean);
  records.forEach((record) => {
    if (normalizedStatus(record.status) === "completed") completedNames.push(agentName(record));
  });
  const uniqueCompleted = [...new Set(completedNames)];
  const workflowComplete = ["completed", "complete", "done"].includes(workflowStatus)
    || pageState.workflow_complete === true;

  const currentName = agentName(pageState.current_agent);
  const lastCompletedName = agentName(pageState.last_completed_agent);
  const completedAnimationToken = lastCompletedName
    ? advanceToken("completed_animation", lastCompletedName)
    : "";
  const shouldAnimateCompletion = Boolean(
    lastCompletedName && !runtime.autoAdvanceTokens.has(completedAnimationToken),
  );
  if (["failed", "error"].includes(workflowStatus) || pageState.error) {
    renderError();
  } else if (shouldAnimateCompletion) {
    workflowStage?.classList.remove("completed-mode");
    const completedAgent = agentFor(lastCompletedName);
    const completedIndex = Math.max(0, catalog.findIndex((entry) => entry.name === lastCompletedName));
    const completedRecord = recordFor(lastCompletedName);
    const card = makeAgentCard(completedAgent, completedIndex, completedRecord, "done");
    workflowStage?.replaceChildren(card);
    later(() => card.classList.add("slide-out"), 330);
    if (workflowComplete) {
      later(() => {
        runtime.autoAdvanceTokens.add(completedAnimationToken);
        pruneAdvanceTokens();
        renderCompleted(uniqueCompleted.length ? uniqueCompleted : catalog.map((agent) => agent.name));
      }, 1080);
    } else {
      later(() => {
        runtime.autoAdvanceTokens.add(completedAnimationToken);
        pruneAdvanceTokens();
        if (currentName) {
          const nextAgent = agentFor(currentName);
          const nextIndex = Math.max(0, catalog.findIndex((entry) => entry.name === currentName));
          workflowStage?.replaceChildren(makeAgentCard(nextAgent, nextIndex, recordFor(currentName), "processing"));
          later(() => autoAdvance("processing", currentName), 180);
        } else {
          later(() => autoAdvance("select_next_agent", null), 180);
        }
      }, 1080);
    }
  } else if (workflowComplete) {
    renderCompleted(uniqueCompleted.length ? uniqueCompleted : catalog.map((agent) => agent.name));
  } else if (currentName) {
    workflowStage?.classList.remove("completed-mode");
    const agent = agentFor(currentName);
    const index = Math.max(0, catalog.findIndex((entry) => entry.name === currentName));
    const record = recordFor(currentName);
    const recordStatus = normalizedStatus(firstDefined(record.status, pageState.agent_status, "processing"));
    const done = recordStatus === "completed"
      || agentName(pageState.last_completed_agent) === currentName
      || pageState.phase === "agent_completed";
    const card = makeAgentCard(agent, index, record, done ? "done" : "processing");
    workflowStage?.replaceChildren(card);
    if (done) {
      later(() => card.classList.add("slide-out"), 330);
      later(() => autoAdvance("completed_animation", currentName), 1080);
    } else {
      const needsAdvance = firstDefined(
        pageState.needs_advance,
        pageState.awaiting_frontend_advance,
        true,
      );
      if (needsAdvance && data.auto_advance !== false) {
        later(() => autoAdvance("processing", currentName), 180);
      }
    }
  } else if (isRunning && data.auto_advance !== false) {
    renderReady();
    later(() => autoAdvance("select_next_agent", null), 180);
  } else {
    renderReady();
  }

  const detailLookup = (name) => {
    const details = firstDefined(data.agent_details, pageState.agent_details);
    if (Array.isArray(details)) return objectValue(details.find((entry) => agentName(entry) === name));
    return objectValue(objectValue(details)[name]);
  };

  const modalBackdrop = query("#modalBackdrop");
  const modal = query(".modal");
  const modalBody = query("#modalBody");
  const hasDetailValue = (value) => {
    if (value === undefined || value === null) return false;
    if (typeof value === "string") return value.trim().length > 0;
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "object") return Object.keys(value).length > 0;
    return true;
  };
  const firstDetailValue = (...values) => values.find(hasDetailValue);
  const compactDetailObject = (entries) => Object.fromEntries(
    entries.filter(([, value]) => hasDetailValue(value)),
  );
  const appendDetailBlock = (title, value) => {
    if (!modalBody || !hasDetailValue(value)) return;
    const block = createElement("div", "detail-block");
    block.append(createElement("h4", "", title));
    if (Array.isArray(value)) {
      const list = createElement("ul");
      value.forEach((entry) => list.append(createElement("li", "", typeof entry === "object" ? JSON.stringify(entry) : entry)));
      block.append(list);
    } else if (typeof value === "object") {
      block.append(createElement("pre", "detail-json", JSON.stringify(value, null, 2)));
    } else {
      block.append(createElement("p", "", value));
    }
    modalBody.append(block);
  };

  const renderAgentDetail = (name) => {
    const agent = agentFor(name);
    const index = Math.max(0, catalog.findIndex((entry) => entry.name === name));
    const record = recordFor(name);
    const detail = detailLookup(name);
    const output = firstDetailValue(
      detail.structured_output,
      record.output,
      outputs[name],
      detail.output,
      agent.output,
    );
    const outputObject = objectValue(output);
    const title = query("#modalTitle");
    const subtitle = query("#modalSubtitle");
    if (title) title.textContent = `${String(index + 1).padStart(2, "0")} · ${name}`;
    if (subtitle) subtitle.textContent = firstDefined(detail.cn, agent.cn, "");
    modalBody?.replaceChildren();

    if (name === "IP Intelligence Agent") {
      appendDetailBlock("Role", firstDetailValue(
        detail.role,
        detail.responsibility,
        record.responsibility,
        agent.desc,
      ));
      appendDetailBlock("Inputs", firstDetailValue(detail.inputs, record.input_summary, agent.inputs));
      appendDetailBlock("IP Identity Grammar", firstDetailValue(
        detail.ip_identity_grammar,
        detail.identity_grammar,
        outputObject.ip_identity_grammar,
        outputObject.identity_grammar,
        outputObject.identity_lock,
        typeof output === "string" ? output : undefined,
      ));
      appendDetailBlock("IP DNA", firstDetailValue(detail.ip_dna, outputObject.ip_dna));
      appendDetailBlock("Handoff", firstDetailValue(detail.handoff, record.handoff));
      appendDetailBlock("Warnings", firstDetailValue(detail.warnings, record.warnings));
    } else if (name === "IP Adaptation Agent") {
      const brief = objectValue(outputs["Creative Brief Agent"]);
      const identityPreservation = objectValue(firstDetailValue(
        detail.identity_preservation,
        outputObject.identity_preservation,
      ));
      const deformationMap = objectValue(firstDetailValue(
        detail.deformation_map,
        outputObject.deformation_map,
      ));
      const allowedTransformations = compactDetailObject([
        ["transform", deformationMap.transform],
        ["pose_dependent", deformationMap.pose_dependent],
      ]);
      appendDetailBlock("Role", firstDetailValue(
        detail.role,
        outputObject.role,
        brief.desired_character_role,
        detail.responsibility,
        record.responsibility,
        agent.desc,
      ));
      appendDetailBlock("Inputs", firstDetailValue(detail.inputs, record.input_summary, agent.inputs));
      appendDetailBlock("Target Pose", firstDetailValue(detail.target_pose, outputObject.target_pose));
      appendDetailBlock("Pose Blueprint", firstDetailValue(detail.pose_blueprint, outputObject.pose_blueprint));
      appendDetailBlock("Identity Anchors", firstDetailValue(
        detail.identity_anchors,
        outputObject.identity_anchors,
        identityPreservation.anchors_to_preserve,
      ));
      appendDetailBlock("Allowed Transformations", firstDetailValue(
        detail.allowed_transformations,
        outputObject.allowed_transformations,
        allowedTransformations,
      ));
      appendDetailBlock("Brand Attachments", firstDetailValue(
        detail.brand_attachments,
        detail.brand_attachment,
        outputObject.brand_attachments,
        outputObject.brand_attachment,
      ));
      appendDetailBlock("Occlusion Rules", firstDetailValue(detail.occlusion_rules, outputObject.occlusion_rules));
      appendDetailBlock("Generation Instructions", firstDetailValue(
        detail.generation_instructions,
        outputObject.generation_instructions,
        detail.decision_summary,
        typeof output === "string" ? output : undefined,
      ));
      appendDetailBlock("Handoff", firstDetailValue(detail.handoff, record.handoff));
      appendDetailBlock("Warnings", firstDetailValue(detail.warnings, record.warnings));
    } else if (name === "IP Guardian Agent") {
      const adaptation = objectValue(outputs["IP Adaptation Agent"]);
      const intelligence = objectValue(outputs["IP Intelligence Agent"]);
      const ipDna = objectValue(intelligence.ip_dna);
      const assessment = objectValue(firstDetailValue(
        detail.assessment,
        outputObject.assessment,
        outputObject.vision_assessment,
      ));
      const checks = objectValue(outputObject.checks);
      const deformationMap = objectValue(adaptation.deformation_map);
      const allowedTransformations = compactDetailObject([
        ["transform", deformationMap.transform],
        ["pose_dependent", deformationMap.pose_dependent],
      ]);
      const revision = compactDetailObject([
        ["identity_corrections", outputObject.identity_corrections],
        ["pose_corrections", outputObject.pose_corrections],
        ["brand_corrections", outputObject.brand_corrections],
        ["style_corrections", outputObject.style_corrections],
        ["revision_instruction", outputObject.revision_instruction],
      ]);
      appendDetailBlock("Role", firstDetailValue(
        detail.role,
        detail.responsibility,
        record.responsibility,
        agent.desc,
      ));
      appendDetailBlock("Inputs", firstDetailValue(detail.inputs, record.input_summary, agent.inputs));
      appendDetailBlock("Original Pose", firstDetailValue(
        detail.original_pose,
        outputObject.original_pose,
        assessment.original_pose,
        ipDna.pose,
      ));
      appendDetailBlock("Target Pose", firstDetailValue(
        detail.target_pose,
        outputObject.target_pose,
        assessment.target_pose,
        adaptation.target_pose,
      ));
      appendDetailBlock("Candidate Pose", firstDetailValue(
        detail.candidate_pose,
        outputObject.candidate_pose,
        assessment.candidate_pose,
      ));
      appendDetailBlock("Allowed Transformation", firstDetailValue(
        detail.allowed_transformation,
        detail.allowed_transformations,
        outputObject.allowed_transformation,
        outputObject.allowed_transformations,
        allowedTransformations,
      ));
      appendDetailBlock("Identity Drift", firstDetailValue(
        detail.identity_drift,
        outputObject.identity_drift,
        assessment.identity_drift,
        outputObject.forbidden_drift,
        outputObject.major_differences,
      ));
      appendDetailBlock("Pose Compliance", firstDetailValue(
        detail.pose_compliance,
        outputObject.target_pose_compliance,
        assessment.target_pose_compliance,
        checks.target_pose_compliance,
      ));
      appendDetailBlock("Brand Integration Compliance", firstDetailValue(
        detail.brand_integration_compliance,
        outputObject.brand_integration_compliance,
        assessment.brand_integration_compliance,
        checks.brand_integration_compliance,
      ));
      appendDetailBlock("Identity Score", firstDetailValue(
        detail.identity_score,
        outputObject.identity_score,
        outputObject.score,
      ));
      appendDetailBlock("Verdict", firstDetailValue(detail.verdict, outputObject.verdict));
      appendDetailBlock("Revision", firstDetailValue(detail.revision, revision));
      appendDetailBlock("Evidence / Reasons", firstDetailValue(
        detail.score_reasons,
        detail.reasons,
        outputObject.score_reasons,
        outputObject.findings,
        detail.decision_summary,
        typeof output === "string" ? output : undefined,
      ));
      appendDetailBlock("Handoff", firstDetailValue(detail.handoff, record.handoff));
      appendDetailBlock("Warnings", firstDetailValue(detail.warnings, record.warnings));
    } else {
      appendDetailBlock("职责", firstDetailValue(detail.responsibility, record.responsibility, agent.desc));
      appendDetailBlock("输入", firstDetailValue(detail.inputs, record.input_summary, agent.inputs));
      appendDetailBlock("处理摘要 / 规则", firstDetailValue(detail.logic, detail.decision_summary, record.decision_summary, agent.logic));
      appendDetailBlock("输出", output);
      appendDetailBlock("评分 / 判断理由", firstDetailValue(detail.score_reasons, detail.reasons, objectValue(record.output).score_reasons));
      appendDetailBlock("Workflow handoff", firstDetailValue(detail.handoff, record.handoff));
      appendDetailBlock("警告", firstDetailValue(detail.warnings, record.warnings));
    }
    if (name === "IP Guardian Agent") {
      const rejectedSource = imageSource(firstDefined(
        demoAssets.guardian_rejected,
        demoAssets.rejected,
        data.guardian_rejected_image,
      ), previews);
      if (rejectedSource && modalBody) {
        const block = createElement("div", "detail-block");
        block.append(createElement("h4", "", "Guardian 示例：旧候选为什么被拒绝"));
        const demo = createElement("div", "guardian-demo");
        const image = createElement("img");
        image.src = rejectedSource;
        image.alt = "被拒绝的旧候选";
        const copy = createElement("div");
        copy.append(
          createElement("div", "reject", "首次候选：Reject · IP一致性不足"),
          createElement("p", "", "候选图被泛化成普通卡通狗，头部、耳朵、面部与线条语言偏离原始IP。"),
          createElement("div", "pass", "修正策略：恢复原IP的面部、耳朵与线条 Identity Grammar；目标姿势、视角、肢体动作和品牌互动仍可合法变化。"),
        );
        demo.append(image, copy);
        block.append(demo);
        modalBody.append(block);
      }
    }
  };

  function openAgentDetail(name) {
    runtime.activeAgent = name;
    renderAgentDetail(name);
    modalBackdrop?.classList.add("show");
    showToast(`正在查看 ${name} 处理明细`);
    persistPageView(name);
    emitTrigger("open_agent_detail", { agent_name: name });
    later(() => query("#closeModalBtn")?.focus(), 0);
  }

  const closeModal = () => {
    runtime.activeAgent = null;
    modalBackdrop?.classList.remove("show");
    showToast("Agent 明细已关闭");
    persistPageView(null);
  };
  listen(query("#closeModalBtn"), "click", closeModal);
  listen(modalBackdrop, "click", (event) => {
    if (event.target === modalBackdrop) closeModal();
  });
  listen(document, "keydown", (event) => {
    if (event.key === "Escape" && modalBackdrop?.classList.contains("show")) closeModal();
  });

  const requestedActiveAgent = agentName(firstDefined(pageState.active_agent, stateData.page_state?.active_agent));
  if (requestedActiveAgent && requestedActiveAgent !== runtime.activeAgent) {
    runtime.activeAgent = requestedActiveAgent;
  }
  if (runtime.activeAgent) {
    renderAgentDetail(runtime.activeAgent);
    modalBackdrop?.classList.add("show");
  } else {
    modalBackdrop?.classList.remove("show");
  }

  const resultData = objectValue(firstDefined(data.result, pageState.result, data.final_result));
  const guardianOutput = objectValue(firstDefined(
    data.guardian,
    resultData.guardian,
    resultData.guardian_result,
    outputs["IP Guardian Agent"],
  ));
  const rankingOutput = objectValue(firstDefined(
    data.ranking,
    resultData.ranking,
    resultData.ranking_result,
    outputs["Ranking Agent"],
  ));
  const guardianVerdict = String(firstDefined(
    guardianOutput.verdict,
    guardianOutput.status,
    resultData.guardian_verdict,
    resultData.guardian_status,
    "",
  )).toUpperCase();
  const hasRanking = Object.keys(rankingOutput).length > 0
    && firstDefined(rankingOutput.total_score, rankingOutput.score, resultData.total_score) !== undefined;
  const resultAllowed = workflowComplete && guardianVerdict === "PASS" && hasRanking;
  const resultSection = query("#resultSection");
  resultSection?.classList.toggle("show", resultAllowed);

  if (resultAllowed) {
    const finalImage = query(".final-result-image");
    const finalSource = imageSource(firstDefined(
      resultData.image,
      resultData.image_uri,
      resultData.result_image_uri,
      resultData.final_image,
      objectValue(outputs["Fusion Generation Agent"]).image_uri,
      data.final_result_image,
    ), previews);
    if (finalImage && finalSource) finalImage.src = finalSource;
    const resultTitle = query("#resultTitle");
    const resultDescription = query("#resultDescription");
    if (resultTitle) resultTitle.textContent = String(firstDefined(
      resultData.theme_name,
      resultData.title,
      "线条小狗 × 麦当劳 · 快乐值班员",
    ));
    if (resultDescription) resultDescription.textContent = String(firstDefined(
      resultData.fusion_logic,
      resultData.description,
      resultData.summary,
      "IP身份约束已通过，品牌元素按创意Brief完成融合。",
    ));
    const tags = arrayValue(firstDefined(resultData.design_tags, resultData.tags));
    const resultTags = query("#resultTags");
    resultTags?.replaceChildren(...[
      ...(tags.length ? tags : ["服装融合", "品牌识别", "IP Identity Grammar"]),
      "Pose-Aware Guardian Pass",
    ].filter((value, index, all) => all.indexOf(value) === index)
      .map((value) => createElement("span", "tag", value)));

    const total = Number(firstDefined(rankingOutput.total_score, rankingOutput.score, resultData.total_score, 0));
    const totalNode = query("#scoreTotal");
    if (totalNode) totalNode.textContent = `综合评分 ${Number.isFinite(total) ? Math.round(total) : 0} / 100`;
    const breakdown = objectValue(firstDefined(rankingOutput.score_breakdown, rankingOutput.scores, resultData.scores));
    const scoreList = query("#scoreList");
    scoreList?.replaceChildren(...Object.entries(breakdown).map(([name, score]) => {
      const row = createElement("div", "score-row");
      row.append(
        createElement("span", "", SCORE_LABELS[name] || name),
        createElement("span", "", score),
      );
      return row;
    }));
    const reasons = objectValue(firstDefined(rankingOutput.score_reasons, rankingOutput.reasons));
    const scoreReasons = query("#scoreReasons");
    scoreReasons?.replaceChildren(...Object.entries(reasons).map(([name, reason]) =>
      createElement("div", "", `${SCORE_LABELS[name] || name}：${reason}`)));
  }

  const safeFilename = (value) => {
    const filename = String(value || "following-blowing-design-package.zip").split(/[\\/]/).pop();
    return filename.toLowerCase().endsWith(".zip") ? filename : `${filename}.zip`;
  };
  const downloadArchive = (archive) => {
    if (!Object.keys(archive).length) return false;
    const filename = safeFilename(firstDefined(archive.filename, archive.package_name));
    const mimeType = String(firstDefined(archive.mime_type, "application/zip"));
    let href = String(firstDefined(archive.data_uri, archive.url, ""));
    let objectUrl = "";
    const encoded = firstDefined(archive.data_base64, archive.base64, archive.content_base64);
    try {
      if (encoded) {
        const binary = atob(String(encoded).replace(/^data:[^,]+,/, ""));
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        objectUrl = URL.createObjectURL(new Blob([bytes], { type: mimeType }));
        href = objectUrl;
      }
      if (!/^(blob:|data:application\/(zip|octet-stream);base64,|https?:\/\/)/i.test(href)) return false;
      const link = createElement("a");
      link.href = href;
      link.download = filename;
      link.hidden = true;
      parentElement.append(link);
      link.click();
      link.remove();
      if (objectUrl) later(() => URL.revokeObjectURL(objectUrl), 1000);
      return true;
    } catch (_error) {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      return false;
    }
  };

  const archive = archivePayload(data, pageState, resultData);
  const archiveToken = String(firstDefined(
    archive.event_id,
    archive.sha256,
    archive.id,
    `${snapshotRevision(pageState)}:${archive.filename || archive.package_name || "archive"}:${String(archive.data_base64 || "").length}`,
  ));
  if ((runtime.pendingExport || archive.auto_download === true)
      && Object.keys(archive).length
      && archiveToken !== runtime.lastDownloadToken) {
    later(() => {
      if (downloadArchive(archive)) {
        runtime.lastDownloadToken = archiveToken;
        runtime.pendingExport = false;
        showToast("联名设计内容包已生成，正在下载");
      }
    }, 0);
  }

  listen(query("#exportBtn"), "click", () => {
    runtime.pendingExport = true;
    // When Python has already prepared the archive, download synchronously in
    // the user's click gesture. Emitting a trigger first can cause Components
    // v2 to remount the root before a temporary anchor is clicked.
    if (Object.keys(archive).length && downloadArchive(archive)) {
      runtime.lastDownloadToken = archiveToken;
      runtime.pendingExport = false;
      showToast("正在下载联名设计内容包");
      return;
    }
    showToast("正在封装效果图、设计说明与结构化文件");
    emitTrigger("export_package", { archive_ready: false });
  });

  return () => {
    listeners.splice(0).forEach((remove) => remove());
    timers.forEach((timer) => globalThis.clearTimeout(timer));
    timers.clear();
    readers.forEach((reader) => {
      if (reader.readyState === FileReader.LOADING) reader.abort();
    });
    readers.clear();
    modal?.blur();
  };
}
