export type Locale =
  | "en"
  | "zh"
  | "zh-hant"
  | "ja"
  | "de"
  | "es"
  | "fr"
  | "tr"
  | "uk"
  | "af"
  | "ko"
  | "it"
  | "ga"
  | "pt"
  | "ru"
  | "hu";

export interface Translations {
  // ── Common ──
  common: {
    save: string;
    saving: string;
    cancel: string;
    close: string;
    confirm: string;
    delete: string;
    refresh: string;
    retry: string;
    search: string;
    loading: string;
    create: string;
    creating: string;
    set: string;
    replace: string;
    clear: string;
    live: string;
    off: string;
    enabled: string;
    disabled: string;
    active: string;
    inactive: string;
    unknown: string;
    untitled: string;
    none: string;
    form: string;
    noResults: string;
    of: string;
    page: string;
    msgs: string;
    tools: string;
    match: string;
    other: string;
    configured: string;
    removed: string;
    failedToToggle: string;
    failedToRemove: string;
    failedToReveal: string;
    collapse: string;
    expand: string;
    general: string;
    messaging: string;
    // Optional: non-English locales fall back to the English literal in the
    // component until translated, matching the enriched-profiles keys.
    gateway?: string;
    gatewayHint?: string;
    pluginLoadFailed: string;
    pluginNotRegistered: string;
  };

  // ── App shell ──
  app: {
    brand: string;
    brandShort: string;
    closeNavigation: string;
    closeModelTools: string;
    footer: {
      org: string;
    };
    activeSessionsLabel: string;
    gatewayStatusLabel: string;
    gatewayStrip: {
      failed: string;
      off: string;
      /** ``{pid}`` is replaced with the live gateway process id. */
      pid?: string;
      running: string;
      starting: string;
      stopped: string;
    };
    nav: {
      analytics: string;
      chat: string;
      config: string;
      cron: string;
      documentation: string;
      keys: string;
      logs: string;
      models: string;
      profiles: string;
      plugins: string;
      sessions: string;
      skills: string;
      channels?: string;
      webhooks?: string;
      pairing?: string;
      mcp?: string;
      database?: string;
      memory?: string;
      system?: string;
    };
    modelToolsSheetSubtitle: string;
    modelToolsSheetTitle: string;
    navigation: string;
    openDocumentation: string;
    openNavigation: string;
    pluginNavSection: string;
    /** Optional — fall back to English literals until translated. */
    navSectionRuntime?: string;
    navSectionAgent?: string;
    navSectionGlobal?: string;
    sessionsActiveCount: string;
    statusOverview: string;
    system: string;
    webUi: string;
    /** Optional — fall back to English literals until translated. */
    managingProfile?: string;
    currentProfileOption?: string;
    /** Hub integrated: first switcher option — global default profile. */
    integratedDefaultOption?: string;
    loadingChat?: string;
  };

  /** Optional — embedded /chat tab (dashboard TUI surface). */
  chat?: {
    copyLastResponse: string;
    copied: string;
    sessionTokenUnavailable: string;
    authFailed: string;
    authFailedWithReason: string;
    refusedWithReason: string;
    originMismatch: string;
    embeddedChatDisabled: string;
    localhostOnly: string;
    sessionEnded: string;
  };

  // ── Status page ──
  status: {
    actionFailed: string;
    actionFinished: string;
    actions: string;
    agent: string;
    connected: string;
    connectedPlatforms: string;
    disconnected: string;
    error: string;
    failed: string;
    gateway: string;
    gatewayFailedToStart: string;
    lastUpdate: string;
    noneRunning: string;
    notRunning: string;
    pid: string;
    platformDisconnected: string;
    platformError: string;
    activeSessions: string;
    recentSessions: string;
    restartGateway: string;
    restartingGateway: string;
    running: string;
    runningRemote: string;
    startFailed: string;
    starting: string;
    startedInBackground: string;
    stopped: string;
    updateHermes: string;
    updatingHermes: string;
    waitingForOutput: string;
  };

  // ── Sessions page ──
  sessions: {
    title: string;
    history: string;
    overview: string;
    searchPlaceholder: string;
    noSessions: string;
    noMatch: string;
    startConversation: string;
    noMessages: string;
    untitledSession: string;
    deleteSession: string;
    confirmDeleteTitle: string;
    confirmDeleteMessage: string;
    sessionDeleted: string;
    failedToDelete: string;
    deleteEmpty: string;
    deleteEmptyConfirmTitle: string;
    deleteEmptyConfirmMessage: string;
    emptySessionsDeleted: string;
    failedToDeleteEmpty: string;
    selectSession: string;
    selectAllOnPage: string;
    clearSelection: string;
    selectedCount: string;
    deleteSelected: string;
    deleteSelectedConfirmTitle: string;
    deleteSelectedConfirmMessage: string;
    selectedSessionsDeleted: string;
    failedToDeleteSelected: string;
    resumeInChat: string;
    previousPage: string;
    nextPage: string;
    roles: {
      user: string;
      assistant: string;
      system: string;
      tool: string;
    };
  };

  // ── Analytics page ──
  analytics: {
    period: string;
    totalTokens: string;
    totalSessions: string;
    apiCalls: string;
    dailyTokenUsage: string;
    dailyBreakdown: string;
    perModelBreakdown: string;
    topSkills: string;
    skill: string;
    loads: string;
    edits: string;
    lastUsed: string;
    input: string;
    output: string;
    total: string;
    noUsageData: string;
    startSession: string;
    date: string;
    model: string;
    tokens: string;
    perDayAvg: string;
    acrossModels: string;
    inOut: string;
    /** Optional — token analytics hidden notice (Analytics page). */
    tokenAnalyticsHiddenTitle?: string;
    tokenAnalyticsHiddenBody1?: string;
    tokenAnalyticsHiddenBody1After?: string;
    tokenAnalyticsHiddenBody2?: string;
    tokenAnalyticsHiddenBody3?: string;
    tokenAnalyticsHiddenBody3In?: string;
    tokenAnalyticsConfigLink?: string;
  };

  // ── Models page ──
  models: {
    modelsUsed: string;
    estimatedCost: string;
    tokens: string;
    sessions: string;
    avgPerSession: string;
    apiCalls: string;
    toolCalls: string;
    noModelsData: string;
    startSession: string;
  };

  // ── Logs page ──
  logs: {
    title: string;
    autoRefresh: string;
    file: string;
    level: string;
    component: string;
    lines: string;
    noLogLines: string;
  };

  // ── Cron page ──
  cron: {
    confirmDeleteMessage: string;
    confirmDeleteTitle: string;
    newJob: string;
    nameOptional: string;
    namePlaceholder: string;
    prompt: string;
    promptPlaceholder: string;
    schedule: string;
    schedulePlaceholder: string;
    scheduleMode: string;
    scheduleModes: {
      interval: string;
      daily: string;
      weekly: string;
      monthly: string;
      once: string;
      custom: string;
      intervalEvery: string;
      intervalUnit: string;
      unitMinutes: string;
      unitHours: string;
      unitDays: string;
      timeOfDay: string;
      weekdays: string;
      weekdaysShort: [string, string, string, string, string, string, string];
      dayOfMonth: string;
      onceAt: string;
      customLabel: string;
      customPlaceholder: string;
      customHint: string;
      preview: string;
      previewEmpty: string;
    };
    scheduleDescribe: {
      none: string;
      everyMinutes: string;
      everyHours: string;
      everyDays: string;
      dailyAt: string;
      weeklyAt: string;
      monthlyAt: string;
      onceAt: string;
    };
    deliverTo: string;
    scheduledJobs: string;
    noJobs: string;
    last: string;
    next: string;
    pause: string;
    resume: string;
    triggerNow: string;
    delivery: {
      local: string;
      telegram: string;
      discord: string;
      slack: string;
      email: string;
      wecom?: string;
      clawbot?: string;
      needsHomeChannel?: string;
      noneConfigured?: string;
    };
    /** Optional — fall back to English literals until translated. */
    profile?: string;
    allProfiles?: string;
    jobs?: string;
    blueprints?: string;
    editJob?: string;
    saveChanges?: string;
    savedChanges?: string;
    skills?: string;
    skillsOptional?: string;
    noSkillsInstalled?: string;
    skillsHint?: string;
    closeAriaLabel?: string;
    deliveryFailed?: string;
    runHistory?: string;
    runHistoryTitle?: string;
    runHistoryEmpty?: string;
    runHistorySelect?: string;
    runHistoryLoadFailed?: string;
    executionMode?: string;
    executionModes?: {
      agent: string;
      scriptAgent: string;
      noAgent: string;
      http?: string;
    };
    script?: string;
    scriptPlaceholder?: string;
    scriptHint?: string;
    scriptRequired?: string;
    promptOrSkillsRequired?: string;
    noAgentSkillsHint?: string;
    httpUrl?: string;
    httpUrlPlaceholder?: string;
    httpUrlRequired?: string;
    httpMethod?: string;
    httpTimeout?: string;
    httpHeaders?: string;
    httpHeadersHint?: string;
    httpBody?: string;
    httpBodyHint?: string;
    httpPlaceholderHint?: string;
    modeNoAgent?: string;
    modeScript?: string;
    modeHttp?: string;
    runStatusOk?: string;
    runStatusFailed?: string;
    runCompletedCount?: string;
    blueprintUi?: {
      setUp: string;
      cancel: string;
      scheduleIt: string;
      scheduled: string;
      loadError: string;
      loading: string;
      empty: string;
    };
    blueprintOptions?: Record<string, string>;
  };

  // ── Plugins page ──
  pluginsPage: {
    actionFailed: string;
    authRequired: string;
    authRequiredHint: string;
    contextEngineLabel: string;
    dashboardSlots: string;
    disableRuntime: string;
    enableAfterInstall: string;
    enableRuntime: string;
    forceReinstall: string;
    headline: string;
    hideFromSidebar: string;
    identifierLabel: string;
    identifierPlaceholder: string;
    inactive: string;
    installBtn: string;
    installFailed: string;
    installHeading: string;
    installHint: string;
    installedToast: string;
    memoryProviderLabel: string;
    missingEnvWarn: string;
    noDashboardTab: string;
    openTab: string;
    orphanHeading: string;
    pluginListHeading: string;
    providerDefaults: string;
    providersHeading: string;
    providersHint: string;
    refreshDashboard: string;
    removeConfirm: string;
    removeConfirmDescription: string;
    removeHint: string;
    removedToast: string;
    rescanFailed: string;
    rescanHeading: string;
    rescanHint: string;
    rescanSuccess: string;
    /** Localized sidebar labels for dashboard plugin tabs (key = manifest name). */
    pluginTabLabels?: Record<string, string>;
    runtimeHeading: string;
    runtimeStatus: {
      disabled: string;
      enabled: string;
      inactive: string;
    };
    saveFailed: string;
    saveProviders: string;
    savedProviders: string;
    showInSidebar: string;
    sourceBadge: string;
    updateGit: string;
    versionBadge: string;
  };

  // ── Profiles page ──
  profiles: {
    newProfile: string;
    name: string;
    namePlaceholder: string;
    nameRequired: string;
    nameRule: string;
    invalidName: string;
    cloneFromDefault: string;
    allProfiles: string;
    noProfiles: string;
    defaultBadge: string;
    hasEnv: string;
    model: string;
    skills: string;
    rename: string;
    editSoul: string;
    soulSection: string;
    soulPlaceholder: string;
    saveSoul: string;
    soulSaved: string;
    openInTerminal: string;
    commandCopied: string;
    copyFailed: string;
    confirmDeleteTitle: string;
    confirmDeleteMessage: string;
    created: string;
    deleted: string;
    renamed: string;
    // Optional keys added for the enriched profiles experience. Non-English
    // locales fall back to the English literal in the component until
    // translated, so these are optional to avoid churning every locale file.
    activeProfile?: string;
    activeDashboardNote?: string;
    activeBadge?: string;
    setActive?: string;
    activeSet?: string;
    gatewayRunning?: string;
    gatewayStopped?: string;
    gatewayRunningWarning?: string;
    aliasBadge?: string;
    description?: string;
    descriptionPlaceholder?: string;
    noDescription?: string;
    editDescription?: string;
    descriptionSaved?: string;
    reviewBadge?: string;
    autoGenerate?: string;
    generating?: string;
    describeFailed?: string;
    distribution?: string;
    advancedOptions?: string;
    cloneAll?: string;
    noSkillsOption?: string;
    descriptionOptional?: string;
    modelOptional?: string;
    modelInherit?: string;
    modelLoading?: string;
    modelNone?: string;
    editModel?: string;
    modelSaved?: string;
    modelSelect?: string;
    editMemory?: string;
    memorySaved?: string;
    memoryNextSessionHint?: string;
    memoryEnabledLabel?: string;
    userProfileEnabledLabel?: string;
    memoryCharLimitLabel?: string;
    memoryCharLimitHint?: string;
    userCharLimitLabel?: string;
    userCharLimitHint?: string;
    prefetchLimitLabel?: string;
    prefetchLimitHint?: string;
    actions?: string;
    manageSkills?: string;
    activeSetHint?: string;
  };

  // ── Skills page ──
  skills: {
    title: string;
    searchPlaceholder: string;
    enabledOf: string;
    all: string;
    categories: string;
    filters: string;
    noSkills: string;
    noSkillsMatch: string;
    skillCount: string;
    resultCount: string;
    noDescription: string;
    toolsets: string;
    toolsetLabel: string;
    noToolsetsMatch: string;
    setupNeeded: string;
    disabledForCli: string;
    more: string;
    /** Optional — fall back to English literals until translated. */
    profileSelector?: string;
    currentProfile?: string;
    managingProfile?: string;
    browseHub?: string;
    newSkill?: string;
    configure?: string;
    editSkillMd?: string;
    editAria?: string;
    savedSkill?: string;
    hubSearchPlaceholder?: string;
    search?: string;
    updateAll?: string;
    actionRunning?: string;
    actionDone?: string;
    actionStarting?: string;
    dismiss?: string;
    featuredSkills?: string;
    featuredSubtitle?: string;
    hubEmptyLanding?: string;
    noHubResults?: string;
    hubSearchFailed?: string;
    installingSkill?: string;
    installFailed?: string;
    updatingSkills?: string;
    updateFailed?: string;
    previewFailed?: string;
    scanFailed?: string;
    connectingHubs?: string;
    hubSourcesFallback?: string;
    connectedHubs?: string;
    githubRateLimitedTitle?: string;
    hermesIndexUnavailableTitle?: string;
    rateLimited?: string;
    hubResultCount?: string;
    timedOut?: string;
    openSkill?: string;
    installedBadge?: string;
    details?: string;
    installedButton?: string;
    installButton?: string;
    trustTrusted?: string;
    trustBuiltin?: string;
    trustCommunity?: string;
    detailDialogDescription?: string;
    readSkillMd?: string;
    rescan?: string;
    securityScan?: string;
    filesLabel?: string;
    skillMdEmpty?: string;
    previewLoadFailed?: string;
    scanningMessage?: string;
    scanPrompt?: string;
    verdictLabel?: string;
    scanSummary?: string;
    verdictSafe?: string;
    verdictCaution?: string;
    verdictDangerous?: string;
    policyAllow?: string;
    policyAsk?: string;
    policyBlock?: string;
    noRiskyPatterns?: string;
    /** ToolsetConfigDrawer — optional until translated per locale. */
    toolsetDrawerClose?: string;
    toolsetDrawerEnableAria?: string;
    toolsetDrawerEnabledForAgent?: string;
    toolsetDrawerNoBackends?: string;
    toolsetDrawerNoProviders?: string;
    toolsetDrawerSelected?: string;
    toolsetDrawerSelect?: string;
    toolsetDrawerSaved?: string;
    toolsetDrawerSavedPlaceholder?: string;
    toolsetDrawerGetKey?: string;
    toolsetDrawerSaveKeys?: string;
    toolsetDrawerPostSetupHint?: string;
    toolsetDrawerRunSetup?: string;
    toolsetDrawerInstalling?: string;
    toolsetDrawerStarting?: string;
    toolsetDrawerPostSetupLog?: string;
    toolsetDrawerNousPortal?: string;
    toolsetDrawerLoadFailed?: string;
    toolsetDrawerPostSetupComplete?: string;
    toolsetDrawerPostSetupErrors?: string;
    toolsetDrawerPostSetupLost?: string;
    toolsetDrawerToggled?: string;
    toolsetDrawerToggleFailed?: string;
    toolsetDrawerProviderSet?: string;
    toolsetDrawerSelectProviderFailed?: string;
    toolsetDrawerEnterValue?: string;
    toolsetDrawerSavedKeys?: string;
    toolsetDrawerNothingToSave?: string;
    toolsetDrawerSaveKeysFailed?: string;
    toolsetDrawerPostSetupStartFailed?: string;
    /** Unified catalog search (skills + toolsets + tools + plugins). */
    noCatalogMatch?: string;
    searchKindSkill?: string;
    searchKindToolset?: string;
    searchKindTool?: string;
    searchKindPluginTool?: string;
    catalogSectionSkills?: string;
    catalogSectionToolsets?: string;
    catalogSectionTools?: string;
    catalogSectionPluginTools?: string;
    belongsToToolset?: string;
  };

  // ── Config page ──
  config: {
    configPath: string;
    globalScopeHint?: string;
    filters: string;
    sections: string;
    exportConfig: string;
    importConfig: string;
    resetDefaults: string;
    resetScopeTooltip: string;
    confirmResetScope: string;
    resetScopeToast: string;
    rawYaml: string;
    searchResults: string;
    fields: string;
    noFieldsMatch: string;
    configSaved: string;
    yamlConfigSaved: string;
    failedToSave: string;
    failedToSaveYaml: string;
    failedToLoadRaw: string;
    configImported: string;
    invalidJson: string;
    yamlModeLabel: string;
    confirmResetDescription: string;
    fieldsCount: string;
    arrayItemLabel: string;
    listPlaceholder: string;
    noneOption: string;
    categories: {
      general: string;
      agent: string;
      terminal: string;
      display: string;
      delegation: string;
      memory: string;
      compression: string;
      security: string;
      browser: string;
      voice: string;
      tts: string;
      stt: string;
      logging: string;
      discord: string;
      auxiliary: string;
      bedrock: string;
      curator: string;
      kanban: string;
      model_catalog: string;
      openrouter: string;
      sessions: string;
      tool_loop_guardrails: string;
      tool_output: string;
      updates: string;
    };
  };

  // ── Env / Keys page ──
  env: {
    changesNote: string;
    confirmClearMessage: string;
    confirmClearTitle: string;
    configuredCount: string;
    description: string;
    enterValue: string;
    getKey: string;
    hideAdvanced: string;
    hideValue: string;
    hideValueAria: string;
    jumpToSection: string;
    keysCount: string;
    llmProviders: string;
    notConfigured: string;
    notSet: string;
    providerGroups: {
      anthropic: string;
      dashscopeQwen: string;
      deepseek: string;
      gemini: string;
      glmZai: string;
      huggingFace: string;
      kimiMoonshot: string;
      minimax: string;
      minimaxChina: string;
      nousPortal: string;
      opencodeGo: string;
      opencodeZen: string;
      openrouter: string;
      other: string;
      xiaomiMimo: string;
      moark?: string;
    };
    providersConfigured: string;
    replaceCurrentValue: string;
    revealValueAria: string;
    savedToast: string;
    sectionOAuth: string;
    sectionProviders: string;
    showAdvanced: string;
    showLess: string;
    showMore: string;
    showValue: string;
    testConnection?: string;
    testSuccess?: string;
    testSuccessModels?: string;
    testFailed?: string;
    testUnreachable?: string;
    testNoProbe?: string;
  };

  // ── OAuth ──
  oauth: {
    title: string;
    providerLogins: string;
    description: string;
    connected: string;
    expired: string;
    notConnected: string;
    runInTerminal: string;
    noProviders: string;
    login: string;
    disconnect: string;
    managedExternally: string;
    copied: string;
    cli: string;
    copyCliCommand: string;
    connect: string;
    sessionExpires: string;
    initiatingLogin: string;
    exchangingCode: string;
    connectedClosing: string;
    loginFailed: string;
    sessionExpired: string;
    reOpenAuth: string;
    reOpenVerification: string;
    submitCode: string;
    pasteCode: string;
    waitingAuth: string;
    enterCodePrompt: string;
    pkceStep1: string;
    pkceStep2: string;
    pkceStep3: string;
    flowLabels: {
      pkce: string;
      device_code: string;
      external: string;
    };
    expiresIn: string;
  };

  // ── Language switcher ──
  language: {
    switchTo: string;
  };

  // ── Theme switcher ──
  theme: {
    title: string;
    switchTheme: string;
    /** Font-override section (optional — locales fall back to English). */
    fontTitle?: string;
    fontDefault?: string;
    fontDefaultHint?: string;
    fontSans?: string;
    fontSerif?: string;
    fontMono?: string;
    /** Built-in dashboard theme labels/descriptions keyed by theme `name`. */
    presets?: Record<string, { label: string; description: string }>;
    /** Font catalog labels keyed by font id (e.g. system-sans). */
    fonts?: Record<string, string>;
  };

  // ── Achievements plugin (plugins/hermes-achievements) ──
  achievements: {
    hero: {
      kicker: string;
      title: string;
      subtitle: string;
      scan_subtitle: string;
    };
    actions: {
      rescan: string;
    };
    stats: {
      unlocked: string;
      unlocked_hint: string;
      discovered: string;
      discovered_hint: string;
      secrets: string;
      secrets_hint: string;
      highest_tier: string;
      highest_tier_hint: string;
      latest: string;
      latest_hint_empty: string;
      none_yet: string;
    };
    state: {
      unlocked: string;
      discovered: string;
      secret: string;
    };
    tier: {
      target: string;
      hidden: string;
      complete: string;
      objective: string;
    };
    progress: {
      hidden: string;
    };
    scan: {
      building_headline: string;
      building_detail: string;
      starting_headline: string;
      progress_detail: string;
      idle_detail: string;
    };
    guide: {
      tiers_header: string;
      secret_header: string;
      secret_body: string;
      scan_status_header: string;
      scan_status_body: string;
      what_scanned_header: string;
      what_scanned_body: string;
    };
    card: {
      share_title: string;
      share_label: string;
      share_text: string;
      how_to_reveal: string;
      what_counts: string;
      evidence_label: string;
      evidence_session_fallback: string;
      no_evidence: string;
    };
    latest: {
      header: string;
    };
    empty: {
      no_secrets_header: string;
      no_secrets_body: string;
    };
    filters: {
      all_categories: string;
      visibility_all: string;
      visibility_unlocked: string;
      visibility_discovered: string;
      visibility_secret: string;
    };
    share: {
      dialog_label: string;
      header: string;
      close: string;
      rendering: string;
      card_alt: string;
      error_generic: string;
      x_title: string;
      x_button: string;
      copy_title: string;
      copy_button: string;
      copied: string;
      download_button: string;
      hint: string;
      clipboard_unsupported: string;
      tweet_text: string;
    };
  };

  // ── Kanban ──
  kanban: {
    loading: string;
    loadFailed: string;
    loadFailedHint: string;
    board: string;
    newBoard: string;
    newBoardTitle: string;
    newBoardDescription: string;
    slug: string;
    slugHint: string;
    displayName: string;
    displayNameHint: string;
    description: string;
    descriptionHint: string;
    icon: string;
    iconHint: string;
    switchAfterCreate: string;
    cancel: string;
    creating: string;
    createBoard: string;
    search: string;
    filterCards: string;
    tenant: string;
    allTenants: string;
    assignee: string;
    allProfiles: string;
    showArchived: string;
    lanesByProfile: string;
    nudgeDispatcher: string;
    refresh: string;
    selected: string;
    complete: string;
    archive: string;
    apply: string;
    clear: string;
    createTask: string;
    noTasks: string;
    unassigned: string;
    needsAssignee?: string;
    needsAssigneeHint?: string;
    untitled: string;
    loadingDetail: string;
    addComment: string;
    comment: string;
    status: string;
    workspace: string;
    skills: string;
    createdBy: string;
    result: string;
    comments: string;
    events: string;
    runHistory: string;
    workerLog: string;
    loadingLog: string;
    noWorkerLog: string;
    noDescription: string;
    noComments: string;
    edit: string;
    save: string;
    dependencies: string;
    parents: string;
    children: string;
    none: string;
    addParent: string;
    addChild: string;
    removeDependency: string;
    block: string;
    unblock: string;
    notifyHomeChannels: string;
    diagnostics: string;
    hide: string;
    show: string;
    attention: string;
    tasksNeedAttention: string;
    taskNeedsAttention: string;
    diagnostic: string;
    open: string;
    close: string;
    reassignTo: string;
    copied: string;
    copyCommand: string;
    reclaim: string;
    reassign: string;
    renderingError: string;
    reloadView: string;
    wsAuthFailed: string;
    markDone: string;
    markArchived: string;
    warning: string;
    phantomIds: string;
    active: string;
    ended: string;
    noProfile: string;
    showAllAttempts: string;
    sendingUpdates: string;
    sendNotifications: string;
    archiveBoardConfirm: string;
    archiveBoardTitle: string;
    boardSwitcherHint: string;
    taskCreatedWarning: string;
    moveFailed: string;
    bulkFailed: string;
    completionBlockedHallucination: string;
    suspectedHallucinatedReferences: string;
    pickProfileFirst: string;
    unblockedMessage: string;
    unblockFailed: string;
    reclaimedMessage: string;
    reclaimFailed: string;
    reassignedMessage: string;
    reassignFailed: string;
    selectForBulk: string;
    clickToEdit: string;
    clickToEditAssignee: string;
    emptyAssignee: string;
    columnLabels: {
      triage: string;
      todo: string;
      scheduled: string;
      ready: string;
      running: string;
      blocked: string;
      done: string;
      archived: string;
    };
    columnHelp: {
      triage: string;
      todo: string;
      scheduled: string;
      ready: string;
      running: string;
      blocked: string;
      done: string;
      archived: string;
    };
    confirmDone: string;
    confirmArchive: string;
    confirmBlocked: string;
    confirmScheduled?: string;
    completionSummary: string;
    completionSummaryRequired: string;
    triagePlaceholder: string;
    taskTitlePlaceholder: string;
    specifier: string;
    assigneePlaceholder: string;
    priority: string;
    skillsPlaceholder: string;
    noParent: string;
    workspacePathDir: string;
    workspacePathOptional: string;
    logTruncated: string;
    logAt: string;
    orchestration?: {
      headerExpanded: string;
      headerCollapsed: string;
      label: string;
      modeAuto: string;
      modeManual: string;
      modeLoading: string;
      loadingMode: string;
      modeAutoTitle: string;
      modeManualTitle: string;
      expandTitle: string;
      reload: string;
      loading: string;
      loadFailed: string;
      settingsSaved: string;
      saveFailed: string;
      descriptionSaved: string;
      autoGenerated: string;
      autoGenerateFailed: string;
      orchestratorProfile: string;
      defaultAssignee: string;
      orchestrationMode: string;
      autoDecompose: string;
      autoDecomposeOnHint: string;
      autoDecomposeOffHint: string;
      defaultOption: string;
      resolved: string;
      orchestratorHint: string;
      profileDescriptions: string;
      profileDescriptionsHint: string;
      noProfiles: string;
      profilePlaceholder: string;
      profileDefaultTag: string;
      profileAutoReview: string;
      profileNoDescription: string;
      saving: string;
      generating: string;
      autoButton: string;
      saveProfileTitle: string;
      autoProfileTitle: string;
    };
  };

  // ── MxAI plugin (plugins/mxai/dashboard) ──
  mxai?: {
    hero: {
      kicker: string;
      title: string;
      subtitle: string;
    };
    actions: {
      refresh: string;
      refreshing: string;
      openClient: string;
      launchClient: string;
    };
    loading: string;
    status: {
      ok: string;
      needsAttention: string;
      yes: string;
      no: string;
    };
    stats: {
      bootstrap: string;
      workArmed: string;
      runningTasks: string;
      queued: string;
      agentsActive: string;
    };
    cards: {
      bootstrap: string;
      bootstrapReady: string;
      bootstrapFailed: string;
      bootstrapNotRun: string;
      failedChecks: string;
      lastChecked: string;
      scheduler: string;
      schedulerActive: string;
      queueRunning: string;
      agentClient: string;
      agentClientDesc: string;
    };
  };

  webhooks?: {
    copy: string;
    close: string;
    newSubscription: string;
    deleteTitle: string;
    deleteDescNamed: string;
    deleteDesc: string;
    createdNote: string;
    webhookUrl: string;
    secretOnce: string;
    done: string;
    name: string;
    namePlaceholder: string;
    description: string;
    descriptionPlaceholder: string;
    events: string;
    eventsPlaceholder: string;
    deliverTo: string;
    deliverLog: string;
    deliverEmail: string;
    deliverGithubComment: string;
    deliverOnly: string;
    deliverOnlyHint: string;
    prompt: string;
    promptPlaceholder: string;
    creating: string;
    create: string;
    receiverDisabled: string;
    receiverDisabledDesc: string;
    enabling: string;
    enableWebhooks: string;
    restartPendingDefault: string;
    restarting: string;
    restartGateway: string;
    subscriptions: string;
    subscriptionsHint: string;
    noSubscriptions: string;
    badgeDeliverOnly: string;
    badgeDisabled: string;
    badgeAll: string;
    disable: string;
    enable: string;
    delete: string;
    nameRequired: string;
    created: string;
    gatewayRestarting: string;
    failedLoad: string;
  };

  pairing?: {
    failedToLoad: string;
    missingCode: string;
    approvedUser: string;
    revokedUser: string;
    errorGeneric: string;
    clearConfirm: string;
    clearedRequests: string;
    clearPending: string;
    revokeDialogTitle: string;
    revokeDescriptionNamed: string;
    revokeDescriptionGeneric: string;
    revokeConfirmLabel: string;
    pendingRequestsHeading: string;
    noPendingRequests: string;
    approveButton: string;
    minutesAgo: string;
    approvedUsersHeading: string;
    noApprovedUsers: string;
    revokeAriaLabel: string;
  };

  channels?: {
    // State badge labels
    stateDisabled: string;
    stateNotEnabled: string;
    stateEnabled: string;
    connConnected: string;
    connConnecting: string;
    connDisconnected: string;
    connGatewayStopped: string;
    connError: string;
    connPaused: string;
    // Expiry
    expired: string;
    // Header / restart button
    restartGateway: string;
    restarting: string;
    // Restart banner
    restartBannerMessage: string;
    restartNow: string;
    // Gateway not running banner
    gatewayNotRunningMessage: string;
    // Summary paragraph
    channelsSummary: string;
    // Config modal
    closeAriaLabel: string;
    configureTitle: string;
    setupGuide: string;
    requiredSuffix: string;
    placeholderAlreadySet: string;
    cancel: string;
    saving: string;
    saveAndEnable: string;
    // Toast messages
    nothingToSave: string;
    fieldRequired: string;
    platformSaved: string;
    failedToSave: string;
    gatewayRestarting: string;
    failedToRestart: string;
    // Platform card actions
    enableAriaLabel: string;
    test: string;
    configure: string;
    // Telegram onboarding panel
    setUpWithQr: string;
    starting: string;
    existingCredentials: string;
    telegramPairingExpired: string;
    telegramStillWaiting: string;
    allowedIdsNumericError: string;
    addAtLeastOneId: string;
    gatewayRestartFailed: string;
    telegramSavedRestarting: string;
    telegramSavedRestartFailed: string;
    telegramSavedRestartFailedDetail: string;
    readyBadge: string;
    allowedUsers: string;
    ownerDetected: string;
    addAtLeastOneIdHint: string;
    telegramUserIdPlaceholder: string;
    add: string;
    saveAndRestart: string;
    qrCodeAlt: string;
    waitingBadge: string;
    openTelegram: string;
    /** ClawBot Gateway 绑定面板 */
    clawbot?: {
      hint: string;
      bind: string;
      rebind: string;
      binding: string;
      bindOk: string;
      bindInvalid: string;
      bindTimeout: string;
      qrHint: string;
      qrAlt: string;
      boundLabel: string;
      unbound: string;
      stats: string;
      sessionLabel: string;
      sessionReady: string;
      sessionPending: string;
      sessionHint: string;
      gatewayLabel: string;
      enableSwitchHint: string;
    };
    /** 企微 AI Bot 内联配置面板 */
    wecom?: {
      hint: string;
      botIdPlaceholder: string;
      secretPlaceholder: string;
      websocketUrlLabel: string;
      websocketUrlPlaceholder: string;
      welcomeLabel: string;
      secretHint: string;
      save: string;
    };
    /** Hub 可见平台的中文名称与描述（按 platform.id 索引） */
    platformLabels?: Record<string, { name: string; description: string }>;
    /** 配置弹窗中环境变量字段的中文标签 */
    envFieldLabels?: Record<string, { prompt?: string; description?: string }>;
  };

  mcp?: {
    addServerButton: string;
    closeAriaLabel: string;
    addServerModalTitle: string;
    nameLabel: string;
    namePlaceholder: string;
    transportLabel: string;
    transportHttp: string;
    transportStdio: string;
    urlLabel: string;
    urlPlaceholder: string;
    commandLabel: string;
    commandPlaceholder: string;
    argsLabel: string;
    argsPlaceholder: string;
    envLabel: string;
    envPlaceholder: string;
    addingButton: string;
    addButton: string;
    installModalDescription: string;
    installingButton: string;
    installButton: string;
    serversHeading: string;
    restartNote: string;
    noServersConfigured: string;
    disabledBadge: string;
    disableButton: string;
    enableButton: string;
    testConnectionAriaLabel: string;
    deleteAriaLabel: string;
    connectedNoTools: string;
    toolsResult: string;
    connectionFailed: string;
    envVarSingular: string;
    envVarPlural: string;
    catalogHeading: string;
    catalogDescription: string;
    noCatalogEntries: string;
    installedBadge: string;
    officialBadge: string;
    removeServerTitle: string;
    removeServerDescription: string;
    toastNameRequired: string;
    toastUrlRequired: string;
    toastCommandRequired: string;
    toastAddSuccess: string;
    toastAddFailed: string;
    toastDeleteSuccess: string;
    toastInstallingBackground: string;
    toastInstallSuccess: string;
    toastInstallFailed: string;
  };

  system?: {
    // ActionLogViewer
    logRunning: string;
    logDone: string;
    logExitCode: string;
    logStarting: string;
    logCloseAriaLabel: string;

    // Update confirm dialog
    updateDialogTitle: string;
    updateDialogDescriptionWithCommits: string;
    updateDialogDescriptionGeneric: string;
    updateDialogConfirmLabel: string;

    // Memory reset confirm dialog
    memoryResetTitle: string;
    memoryResetDescription: string;

    // Credential delete confirm dialog
    credRemoveTitle: string;
    credRemoveDescription: string;

    // Checkpoints prune confirm dialog
    checkpointsPruneTitle: string;
    checkpointsPruneDescription: string;

    // Hook delete confirm dialog
    hookRemoveTitle: string;
    hookRemoveDescription: string;

    // Create-hook modal
    hookModalTitle: string;
    hookEventLabel: string;
    hookCommandLabel: string;
    hookCommandPlaceholder: string;
    hookMatcherLabel: string;
    hookMatcherPlaceholder: string;
    hookTimeoutLabel: string;
    hookTimeoutPlaceholder: string;
    hookApproveCheckbox: string;
    hookWarning: string;
    hookCreateButton: string;
    hookCreatingButton: string;
    hookCloseAriaLabel: string;

    // Host section
    hostSectionTitle: string;
    hostLabelOs: string;
    hostLabelArch: string;
    hostLabelHost: string;
    hostLabelPython: string;
    hostLabelHermes: string;
    hostLabelCpu: string;
    hostLabelMemory: string;
    hostLabelDisk: string;
    hostLabelUptime: string;
    hostLabelLoadAvg: string;
    hostCpuCores: string;
    hostUpdateBadgeBehind: string;
    hostUpdateBadgeAvailable: string;
    hostUpdateBadgeLatest: string;
    hostPsutilHint: string;
    hostCheckForUpdates: string;
    hostUpdateNow: string;
    hostUpdateWith: string;

    // Portal section
    portalSectionTitle: string;
    portalLoggedIn: string;
    portalNotLoggedIn: string;
    portalInferenceProvider: string;
    portalManageSubscription: string;
    portalGatewayRouting: string;
    portalLoginHint: string;

    // Curator section
    curatorSectionTitle: string;
    curatorStatusPaused: string;
    curatorStatusActive: string;
    curatorStatusDisabled: string;
    curatorNeverRun: string;
    curatorResume: string;
    curatorPause: string;
    curatorRunNow: string;

    // Gateway section
    gatewaySectionTitle: string;
    gatewayRunning: string;
    gatewayStopped: string;
    gatewayStart: string;
    gatewayRestart: string;
    gatewayStop: string;

    // Memory section
    memorySectionTitle: string;
    memoryExternalProvider: string;
    memoryBuiltinOnly: string;
    memoryChangeInPlugins: string;
    memoryNewCredentials: string;
    memoryBuiltinFiles: string;
    memoryResetMemoryMd: string;
    memoryResetUserMd: string;
    memoryResetAll: string;

    // Credential pool section
    credPoolSectionTitle: string;
    credProviderLabel: string;
    credProviderPlaceholder: string;
    credApiKeyLabel: string;
    credApiKeyPlaceholder: string;
    credLabelLabel: string;
    credLabelPlaceholder: string;
    credAddKey: string;
    credNoPooled: string;
    credRemoveAriaLabel: string;
    credRequiredError: string;
    credAddedSuccess: string;
    credAddFailedError: string;
    credRemovedSuccess: string;
    credRemoveFailedError: string;

    // Operations section
    opsSectionTitle: string;
    opsRunDoctor: string;
    opsSecurityAudit: string;
    opsCreateBackup: string;
    opsUpdateSkills: string;
    opsPromptSize: string;
    opsSupportDump: string;
    opsMigrateConfig: string;

    // Debug share card
    shareDebugTitle: string;
    shareDebugDescription: string;
    shareGenerateLink: string;
    shareUploading: string;
    shareRedactCheckbox: string;
    shareUploadedBadge: string;
    shareRedactedBadge: string;
    shareNotRedactedBadge: string;
    shareAutoDeletes: string;
    shareCopyAll: string;
    shareCopyLinkAriaLabel: string;
    shareUploadFailures: string;
    shareUploadedToast: string;
    shareUploadedRedactedToast: string;
    shareCopyError: string;

    // Import / restore card
    importLabel: string;
    importPlaceholder: string;
    importButton: string;
    importConfirmTitle: string;
    importConfirmDescription: string;
    importConfirmLabel: string;
    importCancelLabel: string;

    // Checkpoints section
    checkpointsSectionTitle: string;
    checkpointsSessions: string;
    checkpointsPrune: string;

    // Shell hooks section
    hooksSectionTitle: string;
    hooksNewHook: string;
    hooksNoneConfigured: string;
    hooksMatcher: string;
    hooksNotExecutable: string;
    hooksAllowed: string;
    hooksNotApproved: string;
    hooksRemoveAriaLabel: string;

    // Gateway toast messages
    gatewayStartedToast: string;
    gatewayFailedToast: string;

    // Curator toast messages
    curatorResumedToast: string;
    curatorPausedToast: string;
    curatorToggleFailedToast: string;

    // Memory toast
    memoryResetToast: string;
    memoryResetFailedToast: string;

    // Update toast messages
    updateAvailableWithCommits: string;
    updateAvailable: string;
    updateLatestVersion: string;
    updateCheckFailed: string;
    updateStarted: string;
    updateFailed: string;
    updateDockerUnsupported: string;

    // Checkpoint prune toasts
    checkpointPruneStarted: string;
    checkpointPruneFailed: string;

    // Hook toasts
    hookCreated: string;
    hookCreateFailed: string;
    hookCommandRequired: string;
    hookRemoved: string;
    hookRemoveFailed: string;
  };

  database?: {
    title: string;
    subtitle: string;
    selectDatabase: string;
    tables: string;
    modeBrowse: string;
    modeSql: string;
    noTables: string;
    sqlQuery: string;
    sqlPlaceholder: string;
    runQuery: string;
    readOnlyHint: string;
    tableData: string;
    pickTable: string;
    queryResult: string;
    enterSql: string;
    paginationSummary: string;
    pageSize: string;
    prevPage: string;
    nextPage: string;
    presetAllRows: string;
    presetCount: string;
    presetRecent: string;
    sqlRequired: string;
    queryFailed: string;
    filePath?: string;
    doubleClickHint?: string;
    rowDetailTitle?: string;
    rowDetailReadOnly?: string;
    saveRow?: string;
    saveRowSuccess?: string;
    saveRowFailed?: string;
    cancel?: string;
    categoryMxai?: string;
    categoryHermes?: string;
    schemaVersion?: string;
    schemaVersionUnknown?: string;
    tabMxai?: string;
    tabHermesGlobal?: string;
    tabHermesProfile?: string;
    readOnlyField?: string;
    tableTagFts?: string;
    tableTagView?: string;
    tableTagSystem?: string;
    tableTagReadonly?: string;
    tableTagFtsTitle?: string;
    tableTagViewTitle?: string;
    tableTagSystemTitle?: string;
    tableTagReadonlyTitle?: string;
    deleteRow?: string;
    deleteSelected?: string;
    deleteConfirmTitle?: string;
    deleteConfirmDescription?: string;
    deleteRowSuccess?: string;
    deleteRowFailed?: string;
    selectAllRows?: string;
    invalidJson?: string;
  };

  memoryPage?: {
    title: string;
    subtitle: string;
    readOnlyHint: string;
    tabFacts: string;
    tabFactsScope?: string;
    tabMarkdown: string;
    provider: string;
    statFacts: string;
    statEntities: string;
    statMemoryMd: string;
    statUserMd: string;
    noStore: string;
    noFacts: string;
    colId: string;
    colContent: string;
    colCategory: string;
    colTrust: string;
    colUpdated: string;
    filterAll: string;
    totalFacts: string;
    memoryMdTitle: string;
    userMdTitle: string;
    routingHint?: string;
    noEntries: string;
    loadFailed: string;
    refresh: string;
    tabRetrieve: string;
    tabSessions: string;
    sessionsSplitOverview: string;
    sessionHistoryTitle: string;
    sessionHistoryHint: string;
    sessionHistorySource: string;
    sessionTranscriptTitle: string;
    sessionTranscriptHint: string;
    sessionHistoryPickMessage: string;
    holographicMemoryTitle: string;
    holographicMemoryHint: string;
    holographicMemorySource: string;
    holographicMemoryEmpty: string;
    holographicMemoryScopeNote: string;
    retrieveSessionContext: string;
    clickUserForRetrieve: string;
    retrieveSectionTitle: string;
    retrieveSectionHint: string;
    sessionsHint: string;
    sessionsEmpty: string;
    sessionsSelect: string;
    sessionsLoadMore: string;
    paginationPrev: string;
    paginationNext: string;
    paginationStatus: string;
    sessionActive: string;
    sessionCompressedBadge: string;
    compressionChainTitle: string;
    compressionChainHint: string;
    compressionChainGen: string;
    compressionChainRoot: string;
    compressionChainTip: string;
    compressionChainCurrent: string;
    compressionChainOpen: string;
    compressionChainShowSummary: string;
    compressionChainHideSummary: string;
    roleUser: string;
    roleAssistant: string;
    roleSystem: string;
    roleTool: string;
    retrieveTitle: string;
    retrieveHint: string;
    retrieveQueryLabel: string;
    retrieveQueryPlaceholder: string;
    retrieveClickUserMessage?: string;
    retrieveNoUserMessages?: string;
    retrieveSelectedSession?: string;
    retrieveEntityLabel: string;
    retrieveEntityPlaceholder: string;
    retrieveEntitiesLabel: string;
    retrieveEntitiesPlaceholder: string;
    retrieveRun: string;
    retrieveRunning: string;
    retrievePresets: string;
    presetLanguage: string;
    presetBusiness: string;
    presetProject: string;
    presetEnv: string;
    sectionSessionStart: string;
    simulateSystemPromptTitle: string;
    simulateSystemPromptHint: string;
    simulateUserMessagesTitle: string;
    simulateUserMessagesHint: string;
    sectionConversationHistory: string;
    sectionSimulatedTurn: string;
    sectionTurnPrefetch: string;
    holographicSystemLabel: string;
    noConversationHistory: string;
    messagesMarkdownLabel: string;
    prefetchInjectionLabel: string;
    sectionFactSearch: string;
    sectionFactProbe: string;
    sectionFactReason: string;
    sectionMarkdownHints: string;
    colScore: string;
    colTarget: string;
    noPrefetch: string;
    noSearchHits: string;
    noProbeHits: string;
    noReasonHits: string;
    noMarkdownHints: string;
    scenarioNoteLabel: string;
    injectContentLabel: string;
    retrieveResultLabel: string;
    matchedFactsLabel: string;
    sectionMarkdownHintsNote: string;
    blockPreview: string;
    configTitle: string;
    configHint: string;
    configEditLink: string;
    configMemoryEnabled: string;
    configUserEnabled: string;
    configMemoryLimit: string;
    configUserLimit: string;
    configPrefetchLimit: string;
    configProvider: string;
    configChars: string;
    configEnabled: string;
    configDisabled: string;
    configAppliedHint: string;
    entityPickerLabel: string;
    entityPickerHint: string;
    entityFactCount: string;
    noEntities: string;
    entityNoiseTag: string;
    entityNoiseHint: string;
    statEntitiesBreakdown: string;
    purgeNoiseEntities: string;
    purgeNoiseRunning: string;
    purgeNoiseDone: string;
    markdownTransientTag: string;
    markdownTransientHint: string;
    purgeTransientMarkdown: string;
    purgeTransientRunning: string;
    statMemoryMdTransient: string;
  };

  files?: {
    refreshAriaLabel: string;
    pathAriaLabel: string;
    pathPlaceholder: string;
    goButton: string;
    uploadButton: string;
    createButton: string;
    uploadAreaAriaLabel: string;
    uploadingLabel: string;
    releaseToUpload: string;
    dropFilesHere: string;
    loadingFallback: string;
    chooseFiles: string;
    columnName: string;
    columnSize: string;
    columnModified: string;
    columnActions: string;
    loadingFiles: string;
    noFiles: string;
    openAriaLabel: string;
    downloadAriaLabel: string;
    deleteAriaLabel: string;
    createFolderTitle: string;
    createFolderTarget: string;
    folderNamePlaceholder: string;
    cancelButton: string;
    deleteTitleWithName: string;
    deleteTitleFallback: string;
    deleteFolderDescription: string;
    deleteFileDescription: string;
    toastPathRequired: string;
    toastDirectoryUnavailable: string;
    toastFolderNameRequired: string;
    toastFolderCreated: string;
    toastCreateFailed: string;
    toastFilesUploaded: string;
    toastUploadFailed: string;
    toastDownloadFailed: string;
    toastDeleted: string;
    toastDeleteFailed: string;
  };

  models2?: {
    // TokenBar segment labels
    cacheRead: string;
    reasoning: string;
    input: string;
    output: string;
    // CapabilityBadges
    capTools: string;
    capVision: string;
    capReasoning: string;
    // Context/output token suffixes
    ctxSuffix: string;
    outSuffix: string;
    // ModelCard badges
    mainBadge: string;
    auxBadgePrefix: string;
    // UseAsMenu
    useAsButton: string;
    menuMainModel: string;
    menuCurrent: string;
    menuAuxiliaryTask: string;
    menuAllAuxTasks: string;
    errorMissingProviderModel: string;
    expensiveModelFallback: string;
    expensiveModelTitle: string;
    switchAnyway: string;
    // AuxiliaryTasksModal
    closeAriaLabel: string;
    auxModalTitle: string;
    resetAllToAuto: string;
    auxModalDescription: string;
    autoUseMainModel: string;
    providerDefault: string;
    changeButton: string;
    setAuxPickerPrefix: string;
    resetAuxTitle: string;
    resetAuxDescription: string;
    resetAllButton: string;
    // ModelSettingsPanel
    modelSettingsTitle: string;
    appliesToNewSessions: string;
    mainModelLabel: string;
    unset: string;
    auxiliaryTasksLabel: string;
    overrideSummary: string;
    allAutoSummary: string;
    configureButton: string;
    setMainModelTitle: string;
    // Token analytics hidden notice
    tokenAnalyticsHidden: string;
    tokenAnalyticsConfigLink: string;
    // Period selector (Models page header)
    periods?: { d7: string; d30: string; d90: string };
    // Auxiliary task slots (_AUX_TASK_SLOTS)
    auxTasks?: Record<string, { label: string; hint: string }>;
  };

  modelPicker?: {
    defaultTitle: string;
    closeAriaLabel: string;
    currentLabel: string;
    currentUnknown: string;
    filterPlaceholder: string;
    persistGlobalHint: string;
    persistGlobalLabel: string;
    cancel: string;
    switch: string;
    expensiveModelTitle: string;
    switchAnyway: string;
    loading: string;
    noMatches: string;
    noProviders: string;
    pickProvider: string;
    noModelsMatchFilter: string;
    noModelsListed: string;
    modelsCount: string;
    currentTag: string;
    sessionRefreshTitle: string;
    sessionRefreshBody: string;
    sessionRefreshConfirm: string;
    sessionRefreshLater: string;
  };

  sessions2?: {
    renameSession: string;
    exportSession: string;
    exportSessionTitle: string;
    sessionTitlePlaceholder: string;
    saveTitle: string;
    cancelRename: string;
    pruneOldSessions: string;
    sessionRenamed: string;
    failedToRenameSession: string;
    failedToExportSession: string;
    enterValidDays: string;
    prunedSessions: string;
    failedToPruneSessions: string;
    pruneDialogTitle: string;
    pruneDialogDescription: string;
    olderThanDays: string;
    prune: string;
    statsTotal: string;
    statsActiveInStore: string;
    statsArchived: string;
    statsMessages: string;
    tabMessages?: string;
    tabLlmRequests?: string;
    llmRequestsEmpty?: string;
    llmRequestsSummary?: string;
    llmRequestRequest?: string;
    llmRequestResponse?: string;
    llmRequestError?: string;
    filterBySource?: string;
    clearSourceFilter?: string;
  };

  profileBuilder?: {
    pageTitle: string;
    cancelButton: string;
    stepIdentity: string;
    stepModel: string;
    stepSkills: string;
    stepMcp: string;
    stepReview: string;
    profileNameLabel: string;
    profileNamePlaceholder: string;
    profileNameError: string;
    descriptionLabel: string;
    descriptionPlaceholder: string;
    modelStepHint: string;
    filterModelsPlaceholder: string;
    loadingModels: string;
    useDefaultModel: string;
    keepAllSkillsLabel: string;
    skillSelectionHint: string;
    filterSkillsPlaceholder: string;
    loadingSkills: string;
    hubSectionLabel: string;
    hubSearchPlaceholder: string;
    hubSearching: string;
    hubSearch: string;
    hubAddButton: string;
    hubRemoveAriaLabel: string;
    mcpStepHint: string;
    mcpServerNamePlaceholder: string;
    mcpUrlPlaceholder: string;
    mcpCommandPlaceholder: string;
    mcpArgsPlaceholder: string;
    mcpAddServerButton: string;
    mcpRemoveButton: string;
    reviewLabelName: string;
    reviewLabelDescription: string;
    reviewLabelModel: string;
    reviewLabelSkills: string;
    reviewLabelHubSkills: string;
    reviewLabelMcpServers: string;
    reviewModelDefault: string;
    reviewSkillsFullBundle: string;
    reviewSkillsKeptCount: string;
    reviewSkillsKeptWithHub: string;
    reviewMcpNone: string;
    backButton: string;
    nextButton: string;
    creatingButton: string;
    createProfileButton: string;
    toastMcpNeedsName: string;
    toastMcpNeedsUrlOrCommand: string;
    toastInvalidProfileName: string;
    toastProfileCreated: string;
    toastProfileCreatedWithInstalls: string;
    toastCreateFailed: string;
  };
}
