// State variables
let currentBotStatus = 'stopped';
let savedClientId = '';
let activeGuildId = localStorage.getItem('active_guild_id') || null;
let currentConfig = null;
let socket = null;
let localCustomCommands = {};
let rolePanelButtons = [];
let serverRoles = [];
let customPresetsMap = {};

let cachedGuildNames = {};
try {
  cachedGuildNames = JSON.parse(localStorage.getItem('cached_guild_names') || '{}');
} catch (e) {
  cachedGuildNames = {};
}

// Hosting Mode state (server is the source of truth; do NOT cache here as authoritative — Req 5.5)
let hostingMode = { value: null, pendingTarget: null };

// DOM Elements
const mainApp = document.getElementById('main-app');
const currentTabDesc = document.getElementById('current-tab-desc');

// Tab Descriptors
const TAB_DESCRIPTIONS = {
  'tab-overview': 'Monitor your Discord bot and manage connected servers.',
  'tab-auditor': 'Review server permissions, channels structure, and security checklist.',
  'tab-smart': 'View analytics, charts, and server intelligence insights.',
  'tab-optimizer': 'Apply professional structure and role setups to your server.',
  'tab-commands': 'Map custom commands and responses for quick access.',
  'tab-tickets': 'Configure support desks and ticketing panels for members.',
  'tab-roles': 'Create, edit, and delete server roles directly from the dashboard.',
  'tab-role-panels': 'Deploy interactive self-assignable role selection panels to your server.',
  'tab-templates': 'Save server templates and deploy ready-made configurations.',
  'tab-welcome': 'Configure welcome greetings and automatic role assignments for new users.',
  'tab-automod': 'Activate spam protection, link blocking, and custom word filters.',
  'tab-embed-builder': 'Design and send premium Discord embeds with live preview.',
  'tab-music': 'Stream audio and manage active playlist queues directly.',
  'tab-scheduler': 'Automate timed event announcements and recurring broadcasts.',
  'tab-giveaways': 'Create and manage interactive giveaways with automated winner selection.',
  'tab-leveling': 'Boost chat engagement with XP rewards, ranks, and role incentives.',
  'tab-auto-responder': 'Configure custom keyword triggers and regex replies.',
  'tab-audit-log': 'Review actions and configuration changes performed on the dashboard.',
  'tab-logs': 'View real-time event logs from the bot manager and web server.'
};

// Initialize Application
let isAuthenticated = false;
let authToken = localStorage.getItem('admin_token') || '';

// Global Loading State Reset
function globalLoadingReset() {
  const elementsToHide = [
    'audit-loading',
    'optimizer-status',
    'setup-wizard-loading',
    'progress-overlay'
  ];
  elementsToHide.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  });
  
  // Re-enable action buttons
  const buttons = [
    'btn-execute-optimize',
    'btn-execute-audit',
    'btn-verify-token',
    'btn-prev',
    'btn-next'
  ];
  buttons.forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = false;
  });
  
  // Query all disabled buttons or inputs and re-enable them
  document.querySelectorAll('button:disabled, input[type="submit"]:disabled').forEach(btn => {
    if (btn.id === 'btn-deploy-template-preview') {
      const checkbox = document.getElementById('template-confirm-checkbox');
      if (checkbox && !checkbox.checked) return;
    }
    btn.disabled = false;
  });
}

// Embed Builder Persistence functions
let embedTabs = [{}];
let activeEmbedTabIndex = 0;

function collectCurrentEmbedState() {
  return {
    plainText: document.getElementById('embed-plain-text')?.value || '',
    authorName: document.getElementById('embed-author-name')?.value || '',
    authorIcon: document.getElementById('embed-author-icon')?.value || '',
    title: document.getElementById('embed-title')?.value || '',
    desc: document.getElementById('embed-description-text')?.value || '',
    color: document.getElementById('embed-color-hex')?.value || '#6366F1',
    thumbnail: document.getElementById('embed-thumbnail')?.value || '',
    image: document.getElementById('embed-image')?.value || '',
    footerText: document.getElementById('embed-footer-text')?.value || '',
    footerIcon: document.getElementById('embed-footer-icon')?.value || '',
    includeTimestamp: document.getElementById('embed-timestamp')?.checked || false,
    addReactions: document.getElementById('embed-add-reactions')?.checked || false,
    fields: getEmbedFields()
  };
}

function loadEmbedStateIntoForm(state) {
  if (!state) return;
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val || '';
  };
  setVal('embed-plain-text', state.plainText);
  setVal('embed-author-name', state.authorName);
  setVal('embed-author-icon', state.authorIcon);
  setVal('embed-title', state.title);
  setVal('embed-description-text', state.desc);
  let color = state.color || '#6366F1';
  if (color && !color.startsWith('#')) color = '#' + color;
  setVal('embed-color-hex', color);
  const picker = document.getElementById('embed-color-picker');
  if (picker) picker.value = color;
  setVal('embed-thumbnail', state.thumbnail);
  setVal('embed-image', state.image);
  setVal('embed-footer-text', state.footerText);
  setVal('embed-footer-icon', state.footerIcon);
  const ts = document.getElementById('embed-timestamp');
  if (ts) ts.checked = !!state.includeTimestamp;
  const addReact = document.getElementById('embed-add-reactions');
  if (addReact) addReact.checked = !!state.addReactions;
  const container = document.getElementById('embed-fields-container');
  if (container) {
    container.innerHTML = '';
    if (state.fields && Array.isArray(state.fields)) {
      state.fields.forEach(f => {
        addEmbedFieldWithData(f.name, f.value, f.inline !== false);
      });
    }
  }
}

function saveEmbedBuilderState() {
  embedTabs[activeEmbedTabIndex] = collectCurrentEmbedState();
  localStorage.setItem('embed_builder_tabs', JSON.stringify(embedTabs));
  localStorage.setItem('embed_builder_active_tab', String(activeEmbedTabIndex));
}

function restoreEmbedBuilderState() {
  const tabsStr = localStorage.getItem('embed_builder_tabs');
  if (tabsStr) {
    try {
      embedTabs = JSON.parse(tabsStr);
      if (!Array.isArray(embedTabs) || embedTabs.length === 0) embedTabs = [{}];
    } catch(e) { embedTabs = [{}]; }
  }
  const savedIndex = parseInt(localStorage.getItem('embed_builder_active_tab'), 10);
  if (!isNaN(savedIndex) && savedIndex >= 0 && savedIndex < embedTabs.length) {
    activeEmbedTabIndex = savedIndex;
  } else {
    activeEmbedTabIndex = 0;
  }
  renderEmbedTabs();
  loadEmbedStateIntoForm(embedTabs[activeEmbedTabIndex]);
  updateEmbedPreview();
}

function renderEmbedTabs() {
  const list = document.getElementById('embed-tabs-list');
  if (!list) return;
  list.innerHTML = '';
  embedTabs.forEach((tab, i) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'embed-tab' + (i === activeEmbedTabIndex ? ' active' : '');
    btn.textContent = `Embed ${i + 1}`;
    btn.dataset.index = i;
    btn.addEventListener('click', () => switchEmbedTab(i));
    if (embedTabs.length > 1) {
      const closeBtn = document.createElement('span');
      closeBtn.className = 'embed-tab-close';
      closeBtn.innerHTML = '&times;';
      closeBtn.title = 'Remove embed';
      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeEmbedTab(i);
      });
      btn.appendChild(closeBtn);
    }
    list.appendChild(btn);
  });
}

function switchEmbedTab(index) {
  if (index === activeEmbedTabIndex) return;
  embedTabs[activeEmbedTabIndex] = collectCurrentEmbedState();
  activeEmbedTabIndex = index;
  loadEmbedStateIntoForm(embedTabs[index]);
  renderEmbedTabs();
  updateEmbedPreview();
}

function addEmbedTab() {
  if (embedTabs.length >= 10) {
    showToast('Maximum 10 embeds per message.', 'warning');
    return;
  }
  embedTabs[activeEmbedTabIndex] = collectCurrentEmbedState();
  embedTabs.push({});
  activeEmbedTabIndex = embedTabs.length - 1;
  loadEmbedStateIntoForm(embedTabs[activeEmbedTabIndex]);
  renderEmbedTabs();
  updateEmbedPreview();
}

function removeEmbedTab(index) {
  if (embedTabs.length <= 1) return;
  embedTabs.splice(index, 1);
  if (activeEmbedTabIndex >= embedTabs.length) {
    activeEmbedTabIndex = embedTabs.length - 1;
  }
  loadEmbedStateIntoForm(embedTabs[activeEmbedTabIndex]);
  renderEmbedTabs();
  updateEmbedPreview();
}

function duplicateEmbedTab() {
  if (embedTabs.length >= 10) {
    showToast('Maximum 10 embeds per message.', 'warning');
    return;
  }
  const current = collectCurrentEmbedState();
  embedTabs.splice(activeEmbedTabIndex + 1, 0, JSON.parse(JSON.stringify(current)));
  activeEmbedTabIndex = activeEmbedTabIndex + 1;
  loadEmbedStateIntoForm(embedTabs[activeEmbedTabIndex]);
  renderEmbedTabs();
  updateEmbedPreview();
  showToast('Embed duplicated!', 'success');
}

async function populateSmartSuggestions(guildId) {
  const bar = document.getElementById('smart-suggestions-bar');
  const colorsContainer = document.getElementById('suggested-colors');
  if (!bar || !colorsContainer || !guildId) return;
  
  try {
    const res = await fetch(`/api/guilds/${guildId}/channels`);
    if (!res.ok) return;
    
    bar.style.display = 'block';
    colorsContainer.innerHTML = '';
    
    const serverColors = [
      { color: '#5865F2', name: 'Discord Blurple' },
      { color: '#57F287', name: 'Green' },
      { color: '#FEE75C', name: 'Gold' },
      { color: '#ED4245', name: 'Red' },
    ];
    
    if (currentConfig?.guild_configs?.[guildId]) {
      const gc = currentConfig.guild_configs[guildId];
      if (gc.welcome_settings?.embed_color) {
        serverColors.unshift({ color: gc.welcome_settings.embed_color, name: 'Welcome Color' });
      }
    }
    
    serverColors.forEach(sc => {
      const swatch = document.createElement('span');
      swatch.className = 'color-swatch';
      swatch.style.cssText = `background:${sc.color}; width:20px; height:20px; border-radius:50%; cursor:pointer; display:inline-block; border: 2px solid transparent;`;
      swatch.title = `Apply ${sc.name}`;
      swatch.addEventListener('click', () => {
        const hexInput = document.getElementById('embed-color-hex');
        const picker = document.getElementById('embed-color-picker');
        if (hexInput) hexInput.value = sc.color;
        if (picker) picker.value = sc.color;
        updateEmbedPreview();
      });
      colorsContainer.appendChild(swatch);
    });
    
    document.querySelectorAll('.smart-fill-btn').forEach(btn => {
      btn.onclick = () => {
        const field = btn.getAttribute('data-field');
        if (field === 'author') {
          document.getElementById('embed-author-name').value = currentConfig?.guild_configs?.[guildId]?.welcome_settings?.message_title ? activeGuildName : (activeGuildName || 'Server');
          updateEmbedPreview();
        } else if (field === 'footer') {
          document.getElementById('embed-footer-text').value = `Powered by ${activeGuildName || 'Server'}`;
          updateEmbedPreview();
        } else if (field === 'thumbnail') {
          showToast('Server icon will be used as thumbnail when sent.', 'info');
        }
        showToast('Smart fill applied!', 'success');
      };
    });
  } catch (err) {
    console.error('Error loading smart suggestions:', err);
  }
}

// Intercept fetch calls globally to inject Auth Header, handle token expiration (401), retry 5xx/timeouts (max 2), and enforce a 10s request timeout
const originalFetch = window.fetch;
window.fetch = function (url, options) {
  options = options || {};
  options.headers = options.headers || {};
  
  const tokenUsed = authToken;
  if (authToken) {
    options.headers['Authorization'] = `Bearer ${authToken}`;
  }
  
  let targetUrl = url;
  if (window.BOT_API_URL && window.BOT_API_URL !== '%%BOT_API_URL%%' && typeof url === 'string' && url.startsWith('/')) {
    targetUrl = window.BOT_API_URL.replace(/\/$/, '') + url;
  }
  
  const maxAttempts = 3;
  
  const makeAttempt = (attempt) => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    
    const currentOptions = { ...options, signal: controller.signal };
    
    return originalFetch(targetUrl, currentOptions)
      .then(async (response) => {
        clearTimeout(timeoutId);
        
        if (response.status === 401 && !targetUrl.includes('/api/auth/')) {
          if (tokenUsed && tokenUsed === authToken) {
            // Session expired, clear storage and show login overlay
            logoutLocalState();
            showToast('Session expired. Please log in again.', 'warning');
            checkAuthentication();
            globalLoadingReset();
          }
          return response;
        }
        
        if (response.status >= 500 && attempt < maxAttempts) {
          console.warn(`Fetch to ${url} failed with status ${response.status}. Retrying (attempt ${attempt}/${maxAttempts - 1})...`);
          return makeAttempt(attempt + 1);
        }
        
        if (response.status >= 500) {
          globalLoadingReset();
        }
        
        return response;
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        const isTimeoutOrNetwork = err.name === 'AbortError' || err.message === 'Failed to fetch' || err instanceof TypeError;
        if (isTimeoutOrNetwork && attempt < maxAttempts) {
          console.warn(`Fetch to ${url} encountered error: ${err.message || err}. Retrying (attempt ${attempt}/${maxAttempts - 1})...`);
          return makeAttempt(attempt + 1);
        }
        
        globalLoadingReset();
        throw err;
      });
  };
  
  return makeAttempt(1);
};

document.addEventListener('DOMContentLoaded', async () => {
  // One-shot cleanup of residual credential keys from prior versions (R4.2)
  localStorage.removeItem('bot_token');
  localStorage.removeItem('client_id');

  setupNavigation();
  setupEventListeners();
  initGiveawaysTab();
  
  const authed = await checkAuthentication();
  if (authed) {
    initApp();
  }
});

let isAppInitialized = false;
let statusInterval = null;
function initApp() {
  if (isAppInitialized) return;
  isAppInitialized = true;
  connectWebSocket();
  checkStatus().then(() => {
    // First-launch Hosting Mode chooser — admin-only, only when not yet persisted (Req 1.1, 1.6, 1.7)
    maybeShowHostingModeSelector();
    
    // Check and restore template preview modal state
    const savedTemplate = localStorage.getItem('template_modal_state');
    if (savedTemplate && activeGuildId) {
      openTemplatePreview(savedTemplate);
    }
    
    refreshActiveTabContent();
  });
  fetchConfig();
  fetchStats();
  
  // Restore Embed Builder State
  restoreEmbedBuilderState();
  
  // Refresh loop for status and stats (Tier 3.2, 3.15)
  statusInterval = setInterval(() => {
    if (document.visibilityState === 'hidden') return;
    checkStatus();
    
    if (isAuthenticated) {
      fetchStats();
      
      // Poll music status if the music tab is active
      const activePane = document.querySelector('.tab-pane:not(.hidden)');
      if (activePane && activePane.id === 'tab-music' && activeGuildId) {
        fetchMusicStatus();
      } else if (activePane && activePane.id === 'tab-giveaways' && activeGuildId) {
        loadGiveaways();
      }
    }
  }, 15000);
}

async function fetchStats() {
  if (!isAuthenticated) return;
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const stats = await res.json();
    
    const up = document.getElementById('stat-uptime');
    const msg = document.getElementById('stat-messages');
    const cmd = document.getElementById('stat-commands');
    const jt = document.getElementById('stat-joins-tickets');
    
    if (up) up.textContent = stats.uptime;
    if (msg) msg.textContent = stats.messages_today;
    if (cmd) cmd.textContent = stats.commands_today;
    if (jt) jt.textContent = `${stats.joins_today} / ${stats.tickets_today}`;
  } catch (err) {
    console.error("Error fetching stats:", err);
  }

  try {
    const hRes = await fetch('/api/health/detailed', {
      headers: { 'Authorization': 'Bearer ' + authToken }
    });
    if (hRes.ok) {
      const h = await hRes.json();
      const latEl = document.getElementById('health-latency');
      const memEl = document.getElementById('health-memory');
      const dbEl = document.getElementById('health-db');
      const upEl = document.getElementById('health-uptime');
      if (latEl) {
        latEl.textContent = h.bot_latency_ms + 'ms';
        latEl.style.color = h.bot_latency_ms < 200 ? '#34d399' : h.bot_latency_ms < 500 ? '#fbbf24' : '#f87171';
      }
      if (memEl) memEl.textContent = h.memory_mb + 'MB';
      if (dbEl) dbEl.textContent = h.db_size_mb + 'MB';
      if (upEl) {
        const hrs = Math.floor(h.uptime_seconds / 3600);
        const mins = Math.floor((h.uptime_seconds % 3600) / 60);
        upEl.textContent = hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`;
      }
    }
  } catch (err) {}
}

function logoutLocalState() {
  if (socket) {
    try {
      socket.close();
    } catch (e) {}
    socket = null;
  }
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
  localStorage.removeItem('admin_token');
  localStorage.removeItem('admin_role');
  localStorage.removeItem('admin_guild_id');
  authToken = '';
  isAuthenticated = false;
  isAppInitialized = false;
}

async function checkAuthentication() {
  try {
    const statusRes = await fetch('/api/auth/setup-status');
    const statusData = await statusRes.json();
    
    const setupOverlay = document.getElementById('auth-setup-overlay');
    const loginOverlay = document.getElementById('auth-login-overlay');
    
    if (!statusData.setup) {
      // Show setup password screen
      setupOverlay.classList.remove('hidden');
      loginOverlay.classList.add('hidden');
      mainApp.classList.add('hidden');
      logoutLocalState();
      return false;
    }
    
    if (!authToken) {
      // Show login screen
      loginOverlay.classList.remove('hidden');
      setupOverlay.classList.add('hidden');
      mainApp.classList.add('hidden');
      logoutLocalState();
      
      // Load public status to extract client_id for the login page invite button
      fetch('/api/status').then(res => res.json()).then(data => {
        if (data.client_id) {
          updateInviteLinks(data.client_id);
        }
      }).catch(e => console.error("Error fetching public client ID for invite links:", e));
      
      return false;
    }
    
    // We have a token, verify validity
    const statusCheck = await fetch('/api/status');
    let statusCheckData = null;
    try {
      statusCheckData = await statusCheck.json();
    } catch (e) {
      console.error("Error parsing status JSON:", e);
    }

    if (statusCheck.status === 401 || !statusCheckData || !statusCheckData.role || statusCheckData.role === 'guest') {
      logoutLocalState();
      loginOverlay.classList.remove('hidden');
      setupOverlay.classList.add('hidden');
      mainApp.classList.add('hidden');
      return false;
    }
    
    if (statusCheckData.role) {
      localStorage.setItem('admin_role', statusCheckData.role);
    }
    if (statusCheckData.guild_id) {
      localStorage.setItem('admin_guild_id', statusCheckData.guild_id);
    }
    
    // Valid session! Hide overlays
    setupOverlay.classList.add('hidden');
    loginOverlay.classList.add('hidden');
    isAuthenticated = true;
    return true;
  } catch (err) {
    console.error("Auth check error:", err);
    return false;
  }
}

// ==========================================================================
// Navigation & Tabbing
// ==========================================================================
function refreshActiveTabContent() {
  if (!isAuthenticated) return;
  const activePane = document.querySelector('.tab-pane:not(.hidden)');
  if (!activePane || !activeGuildId) return;
  
  const tab = activePane.id;
  if (tab === 'tab-welcome') {
    syncWelcomePreview();
  } else if (tab === 'tab-roles' || tab === 'tab-role-panels') {
    loadServerRoles();
    if (tab === 'tab-role-panels') {
      populateRolePanelChannels();
    }
  } else if (tab === 'tab-templates') {
    fetchTemplates();
  } else if (tab === 'tab-embed-builder') {
    populateEmbedTargetChannels(activeGuildId);
    fetchCustomPresets(activeGuildId);
    populateSmartSuggestions(activeGuildId);
    updateEmbedPreview();
  } else if (tab === 'tab-giveaways') {
    populateGiveawayChannels(activeGuildId);
    loadGiveaways();
  } else if (tab === 'tab-music') {
    populateMusicVoiceChannels(activeGuildId);
    fetchMusicStatus();
  } else if (tab === 'tab-scheduler') {
    populateSchedulerChannels(activeGuildId);
    fetchScheduledMessages();
  } else if (tab === 'tab-leveling') {
    populateLevelingChannelsAndRoles(activeGuildId);
    fetchLevelingConfig(activeGuildId);
    fetchLeaderboard(activeGuildId);
  } else if (tab === 'tab-auto-responder') {
    fetchAutoResponders();
  } else if (tab === 'tab-audit-log') {
    fetchAuditLogs();
  } else if (tab === 'tab-smart') {
    if (typeof window.loadSmartFeatures === 'function') {
      window.loadSmartFeatures();
    }
  } else if (tab === 'tab-auditor') {
    loadRecommendations();
    loadHealthTimeline();
  }
}

function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const tabPanes = document.querySelectorAll('.tab-pane');

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetTab = item.getAttribute('data-tab');
      localStorage.setItem('active_tab', targetTab);
      
      // Update sidebar active state
      navItems.forEach(nav => nav.classList.remove('active'));
      item.classList.add('active');
      
      // Switch tab panes
      tabPanes.forEach(pane => {
        if (pane.id === targetTab) {
          pane.classList.remove('hidden');
        } else {
          pane.classList.add('hidden');
        }
      });

      // Update tab description in header
      if (TAB_DESCRIPTIONS[targetTab]) {
        currentTabDesc.textContent = TAB_DESCRIPTIONS[targetTab];
      }
      
      refreshActiveTabContent();
    });
  });

  // Restore active tab after setup
  const savedTab = localStorage.getItem('active_tab');
  if (savedTab) {
    const savedItem = document.querySelector(`.nav-item[data-tab="${savedTab}"]`);
    if (savedItem) {
      savedItem.click();
    }
  }
}

// ==========================================================================
// API Operations - Core Bot Status & Config
// ==========================================================================
async function checkStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    
    currentBotStatus = data.status;
    
    // Hosting Mode badge + Local-PC warning panel — render on every poll (Req 4.1, 5.5)
    hostingMode.value = data.hosting_mode || null;
    const _hmRole = data.role || localStorage.getItem('admin_role');
    renderHostingModeBadge(hostingMode.value, _hmRole);
    renderFeatureAvailabilityWarning(hostingMode.value);
    
    // Toggle FFmpeg warning
    const ffmpegWarning = document.getElementById('ffmpeg-warning');
    if (ffmpegWarning) {
      if (data.ffmpeg_installed === false) {
        ffmpegWarning.classList.remove('hidden');
      } else {
        ffmpegWarning.classList.add('hidden');
      }
    }
    
    // Toggle Offline Notice when bot is not running (R3.1)
    // Only show when definitively stopped — NOT during the initial
    // 'connecting' phase which is normal on fresh startup. This prevents
    // the "Dashboard Unavailable" overlay from blocking the hosting-mode
    // selector and the main app during the first few seconds of boot.
    const offlineNotice = document.getElementById('offline-notice-overlay');
    if (data.status === 'stopped') {
      if (offlineNotice) offlineNotice.classList.remove('hidden');
      mainApp.classList.add('hidden');
      return;
    } else {
      if (offlineNotice) offlineNotice.classList.add('hidden');
      mainApp.classList.remove('hidden');
    }
    
    // Load config if not loaded
    if (!currentConfig) {
      await fetchConfig();
    }
    
    updateBotBadge(data);
    updateOverviewCard(data);
    
    // Tenant servers are pinned to their own guild
    const serverSelect = document.getElementById('server-select');
    if (data.role === 'user') {
      if (serverSelect) {
        serverSelect.disabled = true;
        if (data.guild_id) {
          serverSelect.value = data.guild_id;
          if (activeGuildId !== data.guild_id) {
            activeGuildId = data.guild_id;
            handleServerSelection(data.guild_id);
          }
        }
      }
    }
  } catch (err) {
    console.error('Error checking status:', err);
    // Show offline notice on network failure/server down
    const offlineNotice = document.getElementById('offline-notice-overlay');
    if (offlineNotice) offlineNotice.classList.remove('hidden');
    if (mainApp) mainApp.classList.add('hidden');
  }
}

async function fetchConfig(guildId = null) {
  try {
    const url = guildId ? `/api/config?guild_id=${guildId}` : '/api/config';
    const res = await fetch(url);
    if (!res.ok) return;
    currentConfig = await res.json();
    savedClientId = currentConfig.client_id || '';
    
    // Set invite links if client ID is set
    updateInviteLinks(savedClientId);
    
    // Populate form data
    populateWelcomeForm(currentConfig.welcome_settings);
    populateAutomodForm(currentConfig.automod_settings);
    populateMilestoneForm(currentConfig.milestone_settings || {});
    populateTicketsForm(currentConfig.ticket_settings);
    
    // Load custom commands
    localCustomCommands = currentConfig.custom_commands || {};
    renderCustomCommands();
  } catch (err) {
    console.error('Error fetching config:', err);
  }
}

function updateBotBadge(data) {
  const botUsername = document.getElementById('bot-username');
  const botStatus = document.getElementById('bot-status');
  const botAvatar = document.getElementById('bot-avatar');
  
  if (data.status === 'running' && data.bot_user) {
    botUsername.textContent = `${data.bot_user.username}#${data.bot_user.discriminator || '0000'}`;
    botStatus.textContent = 'Online';
    botStatus.className = 'status-online';
    if (data.bot_user.avatar_url) {
      botAvatar.src = data.bot_user.avatar_url;
    }
    
    // Enable/Unlock selector and invite buttons
    document.getElementById('server-select').disabled = false;
    if (savedClientId) {
      document.getElementById('btn-invite-bot').classList.remove('hidden');
      document.getElementById('btn-invite-bot-prompt').classList.remove('hidden');
    }
  } else if (data.status === 'connecting') {
    botUsername.textContent = 'Connecting...';
    botStatus.textContent = 'Connecting';
    botStatus.className = 'status-connecting';
    botAvatar.src = '/static/bot_logo.png';
  } else {
    botUsername.textContent = 'Optimizer Bot';
    botStatus.textContent = 'Offline';
    botStatus.className = 'status-offline';
    botAvatar.src = '/static/bot_logo.png';
    
    // Disable/Lock selector
    document.getElementById('server-select').disabled = true;
    document.getElementById('btn-invite-bot').classList.add('hidden');
    document.getElementById('btn-invite-bot-prompt').classList.add('hidden');
  }
}

function updateOverviewCard(data) {
  const botOverviewAvatar = document.getElementById('bot-overview-avatar');
  const botOverviewStatusText = document.getElementById('bot-overview-status-text');
  const botOverviewStatusWrapper = document.querySelector('.bot-ping-status');
  const botOverviewUsername = document.getElementById('bot-overview-username');
  const botOverviewId = document.getElementById('bot-overview-id');
  const botOverviewGuilds = document.getElementById('bot-overview-guilds');

  if (data.status === 'running' && data.bot_user) {
    if (data.bot_user.avatar_url) botOverviewAvatar.src = data.bot_user.avatar_url;
    botOverviewStatusText.textContent = 'ONLINE';
    botOverviewStatusWrapper.classList.add('online');
    botOverviewUsername.textContent = data.bot_user.username;
    botOverviewId.textContent = data.bot_user.id;
    botOverviewGuilds.textContent = data.bot_user.guilds_count;
  } else {
    botOverviewAvatar.src = '/static/bot_logo.png';
    botOverviewStatusText.textContent = data.status.toUpperCase();
    botOverviewStatusWrapper.classList.remove('online');
    botOverviewUsername.textContent = '-';
    botOverviewId.textContent = '-';
    botOverviewGuilds.textContent = '0';
  }

  // Automatically load guilds if select is empty and we have a session
  const select = document.getElementById('server-select');
  if (select && select.options.length <= 1) {
    refreshGuildsList();
  }
}

function updateInviteLinks(clientId) {
  if (!clientId) return;
  const url = `https://discord.com/api/oauth2/authorize?client_id=${clientId}&permissions=8&scope=bot%20applications.commands`;
  
  const link = document.getElementById('btn-invite-bot');
  if (link) {
    link.href = url;
    link.classList.remove('hidden');
  }
  
  const promptLink = document.getElementById('btn-invite-bot-prompt');
  if (promptLink) {
    promptLink.href = url;
    promptLink.classList.remove('hidden');
  }
  
  const loginInviteBtn = document.getElementById('login-invite-btn');
  if (loginInviteBtn) {
    loginInviteBtn.href = url;
    loginInviteBtn.classList.remove('hidden');
  }

  const loginInviteBtnLarge = document.getElementById('login-invite-btn-large');
  if (loginInviteBtnLarge) {
    loginInviteBtnLarge.href = url;
  }

  const loginInviteContainer = document.getElementById('login-invite-container');
  if (loginInviteContainer) {
    loginInviteContainer.classList.remove('hidden');
  }
}

// ==========================================================================
// Action triggers (Save Config)
// ==========================================================================

// ==========================================================================
// Guilds Fetching & Selecting
// ==========================================================================
async function refreshGuildsList() {
  const select = document.getElementById('server-select');
  if (!select) return;
  let guilds = [];
  let fetchFailed = false;
  try {
    const res = await fetch('/api/guilds');
    if (res.ok) {
      guilds = await res.json();
    } else {
      fetchFailed = true;
    }
  } catch (err) {
    console.error('Error fetching guilds:', err);
    fetchFailed = true;
  }
  
  if (fetchFailed) {
    // Cache/keep selected guild dropdown selection when bot goes offline
    if (activeGuildId) {
      select.value = activeGuildId;
      if (select.selectedIndex === -1) {
        const opt = document.createElement('option');
        opt.value = activeGuildId;
        opt.textContent = `Server ID: ${activeGuildId} (Cached/Offline)`;
        select.appendChild(opt);
        select.value = activeGuildId;
      }
      handleServerSelection(activeGuildId);
    }
    return;
  }
  
  // Clear and build options on successful load
  select.innerHTML = '<option value="">Select a server...</option>';
  
  if (guilds && guilds.length > 0) {
    guilds.forEach(g => {
      cachedGuildNames[g.id] = g.name;
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = `${g.name} (${g.member_count} members)`;
      select.appendChild(opt);
    });
    localStorage.setItem('cached_guild_names', JSON.stringify(cachedGuildNames));
    
    // Check if activeGuildId exists
    if (activeGuildId) {
      const exists = guilds.some(g => String(g.id) === String(activeGuildId));
      if (exists) {
        select.value = activeGuildId;
        handleServerSelection(activeGuildId);
      } else {
        // Fallback only if the saved guild is confirmed missing on successful load
        const fallbackId = guilds[0].id;
        activeGuildId = fallbackId;
        localStorage.setItem('active_guild_id', fallbackId);
        select.value = fallbackId;
        handleServerSelection(fallbackId);
        showToast('Saved server invalid. Auto-selected fallback server.', 'warning');
      }
    } else {
      const fallbackId = guilds[0].id;
      activeGuildId = fallbackId;
      localStorage.setItem('active_guild_id', fallbackId);
      select.value = fallbackId;
      handleServerSelection(fallbackId);
    }
  } else {
    activeGuildId = null;
    localStorage.removeItem('active_guild_id');
  }
  
  showToast('Servers list updated.', 'info');
}

async function handleServerSelection(guildId) {
  stopGiveawaysTicker();
  activeGuildId = guildId;
  
  const helper = document.getElementById('no-server-selected-card');
  const card = document.getElementById('active-server-card');
  const backupCard = document.getElementById('backup-restore-card');
  
  if (!guildId) {
    helper.classList.remove('hidden');
    card.classList.add('hidden');
    if (backupCard) backupCard.classList.add('hidden');
    // Clear audit views
    clearAuditView();
    await fetchConfig(); // Call fetchConfig to restore global defaults
    return;
  }
  
  helper.classList.add('hidden');
  card.classList.remove('hidden');
  if (backupCard) backupCard.classList.remove('hidden');
  
  // Load initial guild information
  try {
    // Run an audit check to populate stats and overview
    const res = await fetch(`/api/guilds/${guildId}/audit`);
    if (!res.ok) return;
    const report = await res.json();
    
    populateServerOverview(report.guild_info);
    populateGuildChannels(guildId);
    await fetchConfig(guildId); // Call fetchConfig to dynamically reload forms
    refreshActiveTabContent(); // Refresh active tab data when server changes
  } catch (err) {
    showToast('Failed to retrieve server specifications.', 'error');
  }
}

function populateServerOverview(info) {
  const icon = document.getElementById('active-guild-icon');
  if (info.icon_url) {
    icon.src = info.icon_url;
    icon.style.display = 'block';
  } else {
    icon.style.display = 'none';
  }
  
  document.getElementById('active-guild-name').textContent = info.name;
  document.getElementById('active-guild-id').textContent = `ID: ${info.id}`;
  document.getElementById('guild-boost-tag').innerHTML = `<i class="fa-solid fa-gem"></i> Boost Level ${info.boost_tier} (${info.boost_count} Boosts)`;
  document.getElementById('guild-stat-members').textContent = info.member_count;
  document.getElementById('guild-stat-online').textContent = `${info.online_count} Online`;
  document.getElementById('guild-stat-channels').textContent = info.text_channels + info.voice_channels;
  document.getElementById('guild-stat-channels-split').textContent = `${info.text_channels} Text / ${info.voice_channels} Voice`;
  document.getElementById('guild-stat-roles').textContent = info.roles;
}

// // Dead code populateWelcomeChannels removed.

// ==========================================================================
// Auditor Scan Execution
// ==========================================================================
function clearAuditView() {
  document.getElementById('audit-results-empty').classList.remove('hidden');
  document.getElementById('audit-results-list').classList.add('hidden');
  document.getElementById('audit-score-value').textContent = '0%';
  document.getElementById('audit-score-circle').style.strokeDashoffset = 314;
  const ratingBadge = document.getElementById('audit-score-rating');
  if (ratingBadge) {
    ratingBadge.className = 'rating-badge rating-none';
    ratingBadge.textContent = 'NOT SCANNED';
  }
}

async function runServerAudit() {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  
  const loading = document.getElementById('audit-loading');
  const empty = document.getElementById('audit-results-empty');
  const list = document.getElementById('audit-results-list');
  const scoreVal = document.getElementById('audit-score-value');
  const scoreCircle = document.getElementById('audit-score-circle');
  
  loading.classList.remove('hidden');
  empty.classList.add('hidden');
  list.classList.add('hidden');
  
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/audit`);
    if (!res.ok) {
      throw new Error('Audit request failed');
    }
    const report = await res.json();
    
    // Update Score Circle (radius=50, circumference=314)
    const score = report.score;
    const offset = 314 - (314 * score) / 100;
    scoreCircle.style.strokeDashoffset = offset;
    scoreVal.textContent = `${score}%`;
    
    // Update rating badge (Tier 3.17)
    const ratingBadge = document.getElementById('audit-score-rating');
    if (ratingBadge) {
      ratingBadge.className = 'score-rating-badge'; // Reset
      if (score >= 90) {
        ratingBadge.textContent = 'SECURE';
        ratingBadge.classList.add('rating-secure');
      } else if (score >= 60) {
        ratingBadge.textContent = 'WARNING';
        ratingBadge.classList.add('rating-warning');
      } else {
        ratingBadge.textContent = 'CRITICAL';
        ratingBadge.classList.add('rating-critical');
      }
    }
    
    // Render Checklist
    list.innerHTML = '';
    report.checklist.forEach(item => {
      const card = document.createElement('div');
      let statusClass = 'check-success';
      let iconClass = 'fa-circle-check';
      if (item.status === 'WARNING') {
        statusClass = 'check-warning';
        iconClass = 'fa-triangle-exclamation';
      } else if (item.status === 'FAIL') {
        statusClass = 'check-danger';
        iconClass = 'fa-circle-xmark';
      }
      
      card.className = `check-card ${statusClass}`;
      card.innerHTML = `
        <i class="fa-solid ${iconClass} check-icon"></i>
        <div class="check-info">
          <h3>${escapeHtml(item.name)}</h3>
          <p>${escapeHtml(item.message)}</p>
        </div>
        <span class="check-badge">${escapeHtml(item.value)}</span>
      `;
      list.appendChild(card);
    });
    
    loading.classList.add('hidden');
    list.classList.remove('hidden');
    showToast('Server audit scan complete.', 'success');
  } catch (err) {
    loading.classList.add('hidden');
    empty.classList.remove('hidden');
    showToast('Audit failed. Ensure bot has permissions.', 'error');
  }
}

// ==========================================================================
// Recommendations & Health Timeline
// ==========================================================================
async function loadRecommendations() {
  if (!activeGuildId) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/intelligence/recommendations`, {
      headers: { 'Authorization': 'Bearer ' + authToken }
    });
    if (!res.ok) return;
    const data = await res.json();
    const loading = document.getElementById('recommendations-loading');
    const list = document.getElementById('recommendations-list');
    const empty = document.getElementById('recommendations-empty');
    if (!list) return;
    loading.classList.add('hidden');
    if (!data.recommendations || data.recommendations.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    list.classList.remove('hidden');
    const categoryColors = {
      security: '#ef4444', moderation: '#f59e0b', engagement: '#818cf8',
      support: '#34d399', cleanup: '#94a3b8'
    };
    const borderColor = 'var(--card-border)';
    const titleColor = 'var(--text-main)';
    const descColor = 'var(--text-sub)';
    list.innerHTML = data.recommendations.map(r => `
      <div style="display: flex; align-items: flex-start; gap: 12px; padding: 12px; border-bottom: 1px solid ${borderColor};">
        <div style="width: 8px; height: 8px; border-radius: 50%; background: ${categoryColors[r.category] || '#94a3b8'}; margin-top: 6px; flex-shrink: 0;"></div>
        <div style="flex: 1;">
          <div style="font-weight: 600; color: ${titleColor}; font-size: 0.9rem;">${r.title}</div>
          <div style="color: ${descColor}; font-size: 0.82rem; margin-top: 2px;">${r.description}</div>
        </div>
        <div style="font-size: 0.75rem; color: ${categoryColors[r.category] || '#94a3b8'}; font-weight: 600; white-space: nowrap;">${r.impact}</div>
      </div>
    `).join('');
  } catch (err) {}
}

let healthTimelineChart = null;
async function loadHealthTimeline() {
  if (!activeGuildId) return;
  const days = document.getElementById('timeline-days')?.value || 30;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/intelligence/health-timeline?days=${days}`, {
      headers: { 'Authorization': 'Bearer ' + authToken }
    });
    if (!res.ok) return;
    const data = await res.json();
    const ctx = document.getElementById('chart-health-timeline');
    if (!ctx || !data.length) return;
    if (healthTimelineChart) healthTimelineChart.destroy();
      const isChartLight = document.body.classList.contains('light-theme');
      const gridColor = isChartLight ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.05)';
      const tickColor = isChartLight ? '#64748b' : '#94a3b8';
      healthTimelineChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: data.map(d => d.date),
          datasets: [
            { label: 'Messages', data: data.map(d => d.total_messages), borderColor: '#818cf8', tension: 0.4, pointRadius: 2 },
            { label: 'Active Users', data: data.map(d => d.unique_active_users), borderColor: '#34d399', tension: 0.4, pointRadius: 2 },
            { label: 'Mod Actions', data: data.map(d => d.mod_actions), borderColor: '#f87171', tension: 0.4, pointRadius: 2 },
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { labels: { color: tickColor } } },
          scales: {
            x: { ticks: { color: tickColor, maxTicksLimit: 10 }, grid: { color: gridColor } },
            y: { ticks: { color: tickColor }, grid: { color: gridColor } }
        }
      }
    });
  } catch (err) {}
}

// ==========================================================================
// Optimizer Presets Setup
// ==========================================================================
let selectedPreset = 'gaming';

function setupPresetSelector() {
  const cards = document.querySelectorAll('.preset-card');
  cards.forEach(card => {
    card.addEventListener('click', () => {
      cards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      selectedPreset = card.getAttribute('data-preset');
    });
  });

  const radioCards = document.querySelectorAll('.radio-card');
  radioCards.forEach(card => {
    card.addEventListener('click', () => {
      radioCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
    });
  });
}

async function runOptimization() {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  
  const handling = document.querySelector('input[name="channel-handling"]:checked').value;
  
  // Prompt confirm if "delete" is selected
  if (handling === 'delete') {
    const doubleCheck = confirm("⚠️ CRITICAL WARNING: You selected 'Deconstruct / Delete All'. This will DELETE ALL CHANNELS and history in your Discord server. This cannot be undone. Are you sure you want to proceed?");
    if (!doubleCheck) return;
  } else {
    const check = confirm(`Are you sure you want to optimize your server with the '${selectedPreset.toUpperCase()}' layout? This will create new categories and channels.`);
    if (!check) return;
  }
  
  const statusDiv = document.getElementById('optimizer-status');
  const statusText = document.getElementById('optimizer-status-text');
  const btn = document.getElementById('btn-execute-optimize');
  
  if (statusDiv) statusDiv.classList.remove('hidden');
  if (btn) btn.disabled = true;
  if (statusText) statusText.textContent = `Applying '${selectedPreset.toUpperCase()}' layout preset...`;
  
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/optimize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: selectedPreset, handling: handling })
    });
    
    if (res.ok) {
      showToast('Server optimized successfully!', 'success');
      statusText.textContent = 'Optimization successful!';
      // Recheck status and audit
      setTimeout(() => {
        handleServerSelection(activeGuildId);
        runServerAudit();
      }, 2000);
    } else {
      const err = await res.json();
      showToast(`Optimization failed: ${err.detail}`, 'error');
      statusText.textContent = 'Optimization failed.';
    }
  } catch (err) {
    showToast('Network error during optimization process.', 'error');
    statusText.textContent = 'Network error.';
  } finally {
    btn.disabled = false;
    setTimeout(() => {
      statusDiv.classList.add('hidden');
    }, 5000);
  }
}

// ==========================================================================
// Welcome Module & Preview
// ==========================================================================
function populateWelcomeForm(settings) {
  if (!settings) return;
  document.getElementById('welcome-enabled').checked = settings.enabled;
  document.getElementById('welcome-title').value = settings.message_title;
  document.getElementById('welcome-description').value = settings.message_description;
  document.getElementById('welcome-color-hex').value = settings.embed_color;
  document.getElementById('welcome-color-picker').value = settings.embed_color;
  document.getElementById('welcome-autoroles').value = settings.auto_assign_roles.join(', ');
  
  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };
  setVal('welcome-author-name', settings.author_name);
  setVal('welcome-author-icon', settings.author_icon);
  setVal('welcome-image', settings.image);
  setVal('welcome-footer-text', settings.footer_text);
  
  syncWelcomePreview();
}

function syncWelcomePreview() {
  const titleVal = document.getElementById('welcome-title').value;
  const descVal = document.getElementById('welcome-description').value;
  const colorVal = document.getElementById('welcome-color-hex').value;
  
  const pTitle = document.getElementById('preview-embed-title');
  const pDesc = document.getElementById('preview-embed-desc');
  const pBorder = document.getElementById('preview-embed-border');
  
  pTitle.textContent = titleVal.replace('{user}', 'GamerName').replace('{server}', 'My Guild');
  pDesc.textContent = descVal.replace('{user}', '@GamerName').replace('{server}', 'My Guild');
  
  try {
    pBorder.style.borderLeftColor = colorVal;
  } catch (e) {}
}

async function saveWelcomeSettings(e) {
  e.preventDefault();
  
  const enabled = document.getElementById('welcome-enabled').checked;
  const channelSelect = document.getElementById('welcome-channel');
  const channel_id = channelSelect.value || null;
  const channel_name = channelSelect.selectedIndex >= 0 ? channelSelect.options[channelSelect.selectedIndex].text : 'welcome';
  const title = document.getElementById('welcome-title').value;
  const description = document.getElementById('welcome-description').value;
  const color = document.getElementById('welcome-color-hex').value;
  const autoRolesRaw = document.getElementById('welcome-autoroles').value;
  
  const auto_assign_roles = autoRolesRaw.split(',')
    .map(r => r.trim())
    .filter(r => r.length > 0);
    
  if (!currentConfig) return;
  
  currentConfig.welcome_settings = {
    enabled,
    channel_id,
    channel_name,
    message_title: title,
    message_description: description,
    embed_color: color,
    auto_assign_roles,
    author_name: document.getElementById('welcome-author-name')?.value || '',
    author_icon: document.getElementById('welcome-author-icon')?.value || '',
    image: document.getElementById('welcome-image')?.value || '',
    footer_text: document.getElementById('welcome-footer-text')?.value || 'Member #{membercount}'
  };
  
  try {
    const url = activeGuildId ? `/api/config?guild_id=${activeGuildId}` : '/api/config';
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentConfig)
    });
    
    if (res.ok) {
      showToast('Welcome configurations updated.', 'success');
    } else {
      showToast('Failed to save welcome settings.', 'error');
    }
  } catch (e) {
    showToast('Network error while saving welcome settings.', 'error');
  }
}

// ==========================================================================
// Milestone Module
// ==========================================================================
function populateMilestoneForm(settings) {
  if (!settings) return;
  document.getElementById('milestone-enabled').checked = settings.enabled || false;
  document.getElementById('milestone-values').value = (settings.milestones || []).join(', ');
  const embed = settings.embed || {};
  document.getElementById('milestone-title').value = embed.title || '🎉 {membercount} MEMBERS!';
  document.getElementById('milestone-desc').value = embed.description || 'We just hit {membercount} members!';
  const color = embed.color || '#FFD700';
  document.getElementById('milestone-color-hex').value = color;
  document.getElementById('milestone-color-picker').value = color;
  
  const chSelect = document.getElementById('milestone-channel');
  if (chSelect && settings.channel_id) {
    chSelect.value = settings.channel_id;
  }
}

async function saveMilestoneSettings(e) {
  e.preventDefault();
  if (!currentConfig) return;
  
  const milestonesRaw = document.getElementById('milestone-values').value;
  const milestones = milestonesRaw.split(',').map(v => parseInt(v.trim(), 10)).filter(v => !isNaN(v) && v > 0);
  
  currentConfig.milestone_settings = {
    enabled: document.getElementById('milestone-enabled').checked,
    channel_id: document.getElementById('milestone-channel').value || null,
    milestones: milestones,
    embed: {
      title: document.getElementById('milestone-title').value,
      description: document.getElementById('milestone-desc').value,
      color: document.getElementById('milestone-color-hex').value
    }
  };
  
  try {
    const url = activeGuildId ? `/api/config?guild_id=${activeGuildId}` : '/api/config';
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentConfig)
    });
    if (res.ok) {
      showToast('Milestone settings saved.', 'success');
    } else {
      showToast('Failed to save milestone settings.', 'error');
    }
  } catch (e) {
    showToast('Network error saving milestone settings.', 'error');
  }
}

// ==========================================================================
// AutoModeration Module Setup
// ==========================================================================
function populateAutomodForm(settings) {
  if (!settings) return;
  document.getElementById('automod-enabled').checked = settings.enabled;
  document.getElementById('automod-profanity').checked = settings.block_profanity;
  document.getElementById('automod-links').checked = settings.block_links;
  document.getElementById('automod-max-mentions').value = settings.max_mentions;
  document.getElementById('automod-words').value = settings.profanity_words.join(', ');
  document.getElementById('automod-whitelisted-domains').value = (settings.whitelisted_domains || []).join('\n');
  document.getElementById('automod-whitelisted-invites').value = (settings.whitelisted_invites || []).join('\n');
}

async function saveAutomodSettings(e) {
  e.preventDefault();
  
  const enabled = document.getElementById('automod-enabled').checked;
  const block_profanity = document.getElementById('automod-profanity').checked;
  const block_links = document.getElementById('automod-links').checked;
  const max_mentions = parseInt(document.getElementById('automod-max-mentions').value, 10);
  const logSelect = document.getElementById('automod-log-channel');
  const log_channel_id = logSelect.value || null;
  const log_channel_name = logSelect.selectedIndex >= 0 ? logSelect.options[logSelect.selectedIndex].text : 'mod-logs';
  const wordsRaw = document.getElementById('automod-words').value;
  const block_invites = block_links;
  const whitelisted_domains = document.getElementById('automod-whitelisted-domains').value
    .split('\n')
    .map(d => d.trim())
    .filter(d => d.length > 0);
  const whitelisted_invites = document.getElementById('automod-whitelisted-invites').value
    .split('\n')
    .map(i => i.strip ? i.strip() : i.trim())
    .filter(i => i.length > 0);
  
  const profanity_words = wordsRaw.split(',')
    .map(w => w.trim())
    .filter(w => w.length > 0);
    
  if (!currentConfig) return;
  
  currentConfig.automod_settings = {
    enabled,
    block_profanity,
    block_links,
    max_mentions,
    log_channel_id,
    log_channel_name,
    profanity_words,
    block_invites,
    whitelisted_domains,
    whitelisted_invites
  };
  
  try {
    const url = activeGuildId ? `/api/config?guild_id=${activeGuildId}` : '/api/config';
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentConfig)
    });
    
    if (res.ok) {
      showToast('AutoMod configurations updated.', 'success');
    } else {
      showToast('Failed to save AutoMod settings.', 'error');
    }
  } catch (e) {
    showToast('Network error saving moderation settings.', 'error');
  }
}

// ==========================================================================
// Tickets & Custom Commands Helpers
// ==========================================================================
function populateTicketsForm(settings) {
  if (!settings) return;
  const enabledEl = document.getElementById('tickets-enabled');
  const categoryEl = document.getElementById('tickets-category');
  const roleEl = document.getElementById('tickets-role');
  if (enabledEl) enabledEl.checked = settings.enabled !== false;
  if (categoryEl) categoryEl.value = settings.category_name || '🎟️ SUPPORT TICKETS';
  if (roleEl) roleEl.value = settings.staff_role_name || 'Moderator';
}

function renderCustomCommands() {
  const tbody = document.getElementById('commands-list-body');
  const empty = document.getElementById('commands-empty');
  if (!tbody || !empty) return;
  
  tbody.innerHTML = '';
  const keys = Object.keys(localCustomCommands);
  if (keys.length === 0) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  
  keys.forEach(trigger => {
    const response = localCustomCommands[trigger];
    const tr = document.createElement('tr');
    
    const tdTrigger = document.createElement('td');
    const code = document.createElement('code');
    code.textContent = trigger;
    tdTrigger.appendChild(code);
    
    const tdResponse = document.createElement('td');
    tdResponse.textContent = response;
    
    const tdActions = document.createElement('td');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-secondary btn-small text-danger btn-delete-cmd';
    btn.setAttribute('data-trigger', trigger);
    btn.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
    tdActions.appendChild(btn);
    
    tr.appendChild(tdTrigger);
    tr.appendChild(tdResponse);
    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  
  // Bind delete event listeners
  document.querySelectorAll('.btn-delete-cmd').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const trigger = e.currentTarget.getAttribute('data-trigger');
      delete localCustomCommands[trigger];
      renderCustomCommands();
      showToast(`Command ${trigger} removed locally. Save to deploy.`, 'info');
    });
  });
}

// ==========================================================================
// Roles & Role Panels Operations
// ==========================================================================
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  const s = String(str);
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

async function loadServerRoles() {
  if (!activeGuildId) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/roles`);
    if (!res.ok) return;
    serverRoles = await res.json();
    
    renderServerRoles();
    populateRolesDropdown();
  } catch (err) {
    console.error('Error fetching server roles:', err);
  }
}

function renderServerRoles() {
  const tbody = document.getElementById('roles-list-body');
  const empty = document.getElementById('roles-empty');
  if (!tbody || !empty) return;
  
  tbody.innerHTML = '';
  if (serverRoles.length === 0) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  
  serverRoles.forEach(role => {
    const tr = document.createElement('tr');
    
    // Role name column with color preview indicator
    const tdName = document.createElement('td');
    const preview = document.createElement('span');
    preview.className = 'role-color-preview mr-2';
    preview.style.backgroundColor = role.color;
    tdName.appendChild(preview);
    
    const nameSpan = document.createElement('span');
    nameSpan.textContent = role.name;
    if (role.hoist) {
      const hoistedTag = document.createElement('small');
      hoistedTag.className = 'text-muted';
      hoistedTag.textContent = ' (hoisted)';
      nameSpan.appendChild(hoistedTag);
    }
    tdName.appendChild(nameSpan);
    
    // Color hex column
    const tdColor = document.createElement('td');
    const code = document.createElement('code');
    code.textContent = role.color;
    tdColor.appendChild(code);
    
    // Members count column
    const tdMembers = document.createElement('td');
    tdMembers.textContent = role.member_count;
    
    // Actions column
    const tdActions = document.createElement('td');
    if (role.managed) {
      const span = document.createElement('span');
      span.className = 'tag tag-pink';
      span.textContent = 'Managed';
      tdActions.appendChild(span);
    } else {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-small text-danger btn-delete-role';
      btn.setAttribute('data-role-id', role.id);
      btn.setAttribute('data-role-name', role.name);
      btn.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
      tdActions.appendChild(btn);
    }
    
    tr.appendChild(tdName);
    tr.appendChild(tdColor);
    tr.appendChild(tdMembers);
    tdActions.style.textAlign = 'right';
    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  
  // Bind role deletion clicks
  document.querySelectorAll('.btn-delete-role').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = e.currentTarget.getAttribute('data-role-id');
      const name = e.currentTarget.getAttribute('data-role-name');
      const doubleCheck = confirm(`⚠️ Are you sure you want to delete the role "${name}" from your Discord server? This cannot be undone.`);
      if (!doubleCheck) return;
      
      try {
        showToast('Deleting role from Discord...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/roles/${id}`, { method: 'DELETE' });
        if (res.ok) {
          showToast('Role deleted successfully.', 'success');
          loadServerRoles();
        } else {
          let errorMsg = 'Failed to delete role. Check bot permissions.';
          try {
            const data = await res.json();
            if (data && data.detail) {
              errorMsg = data.detail;
            }
          } catch (jsonErr) {}
          showToast(errorMsg, 'error');
        }
      } catch (err) {
        showToast('Network error deleting role.', 'error');
      }
    });
  });
}

function populateRolesDropdown() {
  const select = document.getElementById('builder-btn-role');
  if (!select) return;
  
  select.innerHTML = '<option value="">Select role...</option>';
  serverRoles.forEach(role => {
    // Exclude managed roles from self-assignment panel
    if (role.managed) return;
    const opt = document.createElement('option');
    opt.value = role.id;
    opt.textContent = role.name;
    select.appendChild(opt);
  });
}

async function fetchBuiltinTemplates() {
  const container = document.getElementById('builtin-templates-container');
  if (!container) return;

  try {
    const res = await fetch('/api/templates/builtin');
    if (!res.ok) {
      container.innerHTML = '<p class="text-danger">Failed to load built-in templates.</p>';
      return;
    }
    const templates = await res.json();
    
    // Group templates by category
    const categories = ["Gaming", "Community", "Creator", "Anime", "Economy", "Utility", "Support"];
    const grouped = {};
    categories.forEach(cat => grouped[cat] = []);
    
    templates.forEach(tpl => {
      const cat = tpl.category;
      if (grouped[cat]) {
        grouped[cat].push(tpl);
      } else {
        grouped[cat] = [tpl];
        if (!categories.includes(cat)) {
          categories.push(cat);
        }
      }
    });

    container.innerHTML = '';
    categories.forEach(catName => {
      const list = grouped[catName] || [];
      
      const catDiv = document.createElement('div');
      catDiv.className = 'builtin-category-group';
      
      let catIcon = 'fa-folder';
      if (catName === 'Gaming') catIcon = 'fa-gamepad';
      else if (catName === 'Community') catIcon = 'fa-users';
      else if (catName === 'Creator') catIcon = 'fa-laptop-code';
      else if (catName === 'Anime') catIcon = 'fa-mask';
      else if (catName === 'Economy') catIcon = 'fa-coins';
      else if (catName === 'Utility') catIcon = 'fa-screwdriver-wrench';
      else if (catName === 'Support') catIcon = 'fa-ticket';

      let cardsHtml = '';
      if (list.length === 0) {
        cardsHtml = `
          <div class="stat-card glass-inner text-center py-4 w-100" style="opacity: 0.5; border-radius: 8px; grid-column: 1 / -1;">
            <p class="text-sub font-size-08 m-0">No layouts available in this category for this release.</p>
          </div>
        `;
      } else {
        list.forEach(tpl => {
          let themeColor = 'var(--primary)';
          let btnClass = 'btn-primary';
          if (catName === 'Community') {
            themeColor = 'var(--success)';
            btnClass = 'btn-success';
          } else if (catName === 'Creator') {
            themeColor = 'var(--pink)';
            btnClass = 'btn-glow';
          } else if (catName === 'Anime') {
            themeColor = '#f59e0b';
            btnClass = 'btn-warning';
          } else if (catName === 'Utility') {
            themeColor = '#818cf8';
            btnClass = 'btn-indigo';
          } else if (catName === 'Support') {
            themeColor = '#a855f7';
            btnClass = 'btn-purple';
          }

          cardsHtml += `
            <div class="stat-card glass-inner text-center" style="display: flex; flex-direction: column; align-items: center; padding: 20px; border-radius: 12px; justify-content: space-between; min-height: 180px;">
              <div>
                <i class="fa-solid ${tpl.icon || 'fa-layer-group'}" style="font-size: 2rem; color: ${themeColor};"></i>
                <h3 class="mt-2" style="font-size: 1.05rem; font-weight: 600;">${tpl.display_name}</h3>
                <p class="text-sub mt-2 font-size-075" style="line-height: 1.4; min-height: 54px; margin: 0;">${tpl.description}</p>
              </div>
              <button class="btn ${btnClass} btn-small mt-3 w-100 btn-apply-builtin" data-preset="${tpl.name}">Apply Template</button>
            </div>
          `;
        });
      }

      catDiv.innerHTML = `
        <h3 style="font-size: 1.1rem; font-weight: 600; color: #818cf8; margin-top: 10px; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 6px; display: flex; align-items: center; gap: 8px;">
          <i class="fa-solid ${catIcon}"></i> ${catName} Layouts
        </h3>
        <div class="grid-3-col" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 15px; margin-bottom: 15px;">
          ${cardsHtml}
        </div>
      `;
      container.appendChild(catDiv);
    });

    container.querySelectorAll('.btn-apply-builtin').forEach(btn => {
      btn.addEventListener('click', () => {
        const preset = btn.getAttribute('data-preset');
        openTemplatePreview(preset);
      });
    });

  } catch (err) {
    container.innerHTML = '<p class="text-danger">Error loading built-in templates.</p>';
  }
}

async function exportCustomTemplate(name) {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  try {
    showToast(`Exporting template "${name}"...`, 'info');
    const res = await fetch(`/api/templates/${name.toLowerCase().trim()}/preview?guild_id=${activeGuildId}`);
    if (!res.ok) {
      showToast('Failed to retrieve template data for export.', 'error');
      return;
    }
    const data = await res.json();
    const templateData = data.template_data;
    
    const blob = new Blob([JSON.stringify(templateData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Template exported successfully!', 'success');
  } catch (err) {
    showToast('Error exporting template.', 'error');
  }
}

async function fetchTemplates() {
  const tbody = document.getElementById('templates-list-body');
  const empty = document.getElementById('templates-empty');
  if (!tbody || !empty) return;
  
  fetchBuiltinTemplates();

  try {
    const res = await fetch('/api/templates');
    if (!res.ok) return;
    const templates = await res.json();
    
    tbody.innerHTML = '';
    if (templates.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    
    templates.forEach(tpl => {
      const tr = document.createElement('tr');
      
      const tdName = document.createElement('td');
      tdName.textContent = tpl.name;
      
      const tdActions = document.createElement('td');
      
      const btnRestore = document.createElement('button');
      btnRestore.type = 'button';
      btnRestore.className = 'btn btn-success btn-small mr-2';
      btnRestore.innerHTML = '<i class="fa-solid fa-clock-rotate-left"></i> Restore';
      btnRestore.addEventListener('click', () => openTemplatePreview(tpl.name));
      tdActions.appendChild(btnRestore);

      const btnExport = document.createElement('button');
      btnExport.type = 'button';
      btnExport.className = 'btn btn-primary btn-small mr-2';
      btnExport.innerHTML = '<i class="fa-solid fa-file-export"></i> Export';
      btnExport.addEventListener('click', () => exportCustomTemplate(tpl.name));
      tdActions.appendChild(btnExport);
      
      const btnDel = document.createElement('button');
      btnDel.type = 'button';
      btnDel.className = 'btn btn-secondary btn-small text-danger';
      btnDel.innerHTML = '<i class="fa-solid fa-trash"></i> Delete';
      btnDel.addEventListener('click', () => deleteCustomTemplate(tpl.name));
      tdActions.appendChild(btnDel);
      
      tr.appendChild(tdName);
      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Error fetching templates:", err);
  }
}

let currentPreviewTemplateName = null;
let currentPreviewTemplateData = null;

async function openTemplatePreview(name) {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  
  localStorage.setItem('template_modal_state', name);
  const safeName = name.toLowerCase().trim();
  const handling = document.querySelector('input[name="channel-handling"]:checked')?.value || 'archive';

  try {
    showToast(`Loading template preview for "${name}"...`, 'info');
    const res = await fetch(`/api/templates/${safeName}/preview?guild_id=${activeGuildId}&handling=${handling}`);
    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || 'Failed to load template preview.', 'error');
      return;
    }
    const data = await res.json();
    currentPreviewTemplateName = safeName;
    currentPreviewTemplateData = data;

    document.getElementById('template-preview-overlay').classList.remove('hidden');
    document.getElementById('template-confirm-checkbox').checked = false;
    document.getElementById('btn-deploy-template-preview').disabled = true;

    // Reset delete confirmation text input state
    const deleteContainer = document.getElementById('delete-confirmation-container');
    const deleteInput = document.getElementById('delete-confirm-input');
    if (deleteContainer) {
      if (handling === 'delete') {
        deleteContainer.classList.remove('hidden');
      } else {
        deleteContainer.classList.add('hidden');
      }
    }
    if (deleteInput) {
      deleteInput.value = '';
    }

    const sum = data.summary;
    
    let handlingHtml = '';
    if (handling === 'archive') {
      const archivedCount = sum.objects_to_modify ? sum.objects_to_modify.length : 0;
      handlingHtml = `
        <li style="grid-column: span 2; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px; margin-top: 4px; font-size: 0.85rem; color: #818cf8;">
          📦 <strong>Objects to Archive:</strong> ${archivedCount} (${sum.objects_to_modify?.join(', ') || 'None'})
        </li>
      `;
    } else if (handling === 'delete') {
      const deletedCount = sum.objects_to_delete ? sum.objects_to_delete.length : 0;
      handlingHtml = `
        <li style="grid-column: span 2; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 8px; margin-top: 4px; font-size: 0.85rem; color: #ef4444;">
          ⚠️ <strong>Objects to Delete:</strong> ${deletedCount} (${sum.objects_to_delete?.join(', ') || 'None'})
        </li>
      `;
    }

    const summaryDiv = document.getElementById('template-preview-summary');
    summaryDiv.innerHTML = `
      <h4 style="font-weight: 600; margin-bottom: 8px;"><i class="fa-solid fa-clipboard-list"></i> Deployment Summary</h4>
      <ul style="list-style: none; padding-left: 0; margin-bottom: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
        <li>🟢 <strong>Roles to Create:</strong> ${sum.roles_to_create.length} (${sum.roles_to_create.join(', ') || 'None'})</li>
        <li>⚪ <strong>Roles to Skip:</strong> ${sum.roles_to_skip.length} (${sum.roles_to_skip.join(', ') || 'None'})</li>
        <li>🟢 <strong>Categories to Create:</strong> ${sum.categories_to_create.length} (${sum.categories_to_create.join(', ') || 'None'})</li>
        <li>⚪ <strong>Categories to Skip:</strong> ${sum.categories_to_skip.length} (${sum.categories_to_skip.join(', ') || 'None'})</li>
        <li>🟢 <strong>Channels to Create:</strong> ${sum.channels_to_create.length}</li>
        <li>⚪ <strong>Channels to Skip:</strong> ${sum.channels_to_skip.length} (${sum.channels_to_skip.join(', ') || 'None'})</li>
        ${handlingHtml}
      </ul>
    `;

    const treeDiv = document.getElementById('template-tree-customizer');
    treeDiv.innerHTML = '';

    const tpl = data.template_data;
    
    // Roles Section
    if (tpl.roles && tpl.roles.length > 0) {
      const section = document.createElement('div');
      section.className = 'tree-section mb-3';
      section.innerHTML = `<h4 style="font-size: 0.95rem; font-weight: 600; color: #818cf8; margin-bottom: 6px;">Roles</h4>`;
      tpl.roles.forEach(role => {
        const item = createTreeItem(role.name, 'role', sum.roles_to_skip.includes(role.name));
        section.appendChild(item);
      });
      treeDiv.appendChild(section);
    }

    // Categories & Channels Section
    if (tpl.categories && tpl.categories.length > 0) {
      const section = document.createElement('div');
      section.className = 'tree-section mb-3';
      section.innerHTML = `<h4 style="font-size: 0.95rem; font-weight: 600; color: #818cf8; margin-bottom: 6px;">Categories & Channels</h4>`;
      
      tpl.categories.forEach(cat => {
        const catItem = createTreeItem(cat.name, 'category', sum.categories_to_skip.includes(cat.name));
        section.appendChild(catItem);

        if (cat.channels && cat.channels.length > 0) {
          const subList = document.createElement('div');
          subList.style.paddingLeft = '24px';
          cat.channels.forEach(ch => {
            const chFullName = `${ch.name} (${ch.type})`;
            const chItem = createTreeItem(ch.name, 'channel', sum.channels_to_skip.includes(chFullName));
            subList.appendChild(chItem);
          });
          section.appendChild(subList);
        }
      });
      treeDiv.appendChild(section);
    }
  } catch (err) {
    showToast('Network error loading template preview.', 'error');
  }
}

function createTreeItem(name, type, isSkipped) {
  const container = document.createElement('div');
  container.className = 'tree-item';
  container.style.display = 'flex';
  container.style.alignItems = 'center';
  container.style.gap = '10px';
  container.style.marginBottom = '6px';

  const check = document.createElement('input');
  check.type = 'checkbox';
  check.className = 'tree-item-toggle';
  check.checked = !isSkipped;
  check.style.cursor = 'pointer';
  check.setAttribute('data-original-name', name);
  check.setAttribute('data-type', type);
  container.appendChild(check);

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'tree-item-name glass-input';
  input.value = name;
  input.style.padding = '4px 8px';
  input.style.fontSize = '0.85rem';
  input.style.border = '1px solid rgba(255,255,255,0.1)';
  input.style.borderRadius = '4px';
  input.style.width = '200px';
  input.setAttribute('data-original-name', name);
  container.appendChild(input);

  const label = document.createElement('span');
  label.style.fontSize = '0.75rem';
  label.style.padding = '2px 6px';
  label.style.borderRadius = '4px';
  if (isSkipped) {
    label.textContent = 'Will Skip (Already Exists)';
    label.style.background = 'rgba(239, 68, 68, 0.2)';
    label.style.color = '#ef4444';
  } else {
    label.textContent = type.toUpperCase();
    label.style.background = 'rgba(16, 185, 129, 0.2)';
    label.style.color = '#10b981';
  }
  container.appendChild(label);

  return container;
}

async function deleteCustomTemplate(name) {
  const confirmDel = confirm(`Are you sure you want to delete template "${name}"?`);
  if (!confirmDel) return;
  
  try {
    const res = await fetch(`/api/templates/${name}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Template deleted.', 'success');
      fetchTemplates();
    } else {
      showToast('Failed to delete template.', 'error');
    }
  } catch (err) {
    showToast('Network error deleting template.', 'error');
  }
}

async function populateRolePanelChannels() {
  const select = document.getElementById('role-panel-channel');
  if (!select || !activeGuildId) return;
  
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/channels`);
    if (!res.ok) return;
    const channels = await res.json();
    
    select.innerHTML = '<option value="">Select channel...</option>';
    channels.forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.textContent = `#${ch.name}`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Error fetching role panel channels:', err);
  }
}

function renderPanelButtons() {
  const list = document.getElementById('panel-buttons-list');
  const previewContainer = document.getElementById('preview-role-buttons');
  if (!list || !previewContainer) return;
  
  list.innerHTML = '';
  previewContainer.innerHTML = '';
  
  if (rolePanelButtons.length === 0) {
    list.innerHTML = '<p class="text-sub font-size-08 text-center py-2">No buttons added yet. Build one above!</p>';
    return;
  }
  
  rolePanelButtons.forEach((btn, index) => {
    // 1. Render in configuration builder list
    const item = document.createElement('div');
    item.className = 'panel-button-item';
    
    const info = document.createElement('div');
    info.className = 'panel-button-info';
    info.innerHTML = `
      <span class="panel-button-badge style-${btn.style}">${btn.style}</span>
      <span>${btn.emoji ? btn.emoji + ' ' : ''}<strong>${escapeHtml(btn.label)}</strong> &rarr; Role: ${escapeHtml(btn.role_name)}</span>
    `;
    item.appendChild(info);
    
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'btn btn-secondary btn-small text-danger';
    delBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    delBtn.addEventListener('click', () => {
      rolePanelButtons.splice(index, 1);
      renderPanelButtons();
    });
    item.appendChild(delBtn);
    list.appendChild(item);
    
    // 2. Render in live Discord simulator preview
    const simBtn = document.createElement('button');
    simBtn.type = 'button';
    simBtn.className = `discord-emulator-btn discord-btn-${btn.style}`;
    simBtn.innerHTML = `${btn.emoji ? btn.emoji + ' ' : ''}${escapeHtml(btn.label)}`;
    simBtn.addEventListener('click', () => {
      showToast(`[Simulator Click] Toggling role: ${btn.role_name}`, 'info');
    });
    previewContainer.appendChild(simBtn);
  });
}

function syncRolePanelPreview() {
  const title = document.getElementById('role-panel-title').value;
  const desc = document.getElementById('role-panel-desc').value;
  const color = document.getElementById('role-panel-color-hex').value;
  
  const pTitle = document.getElementById('preview-role-embed-title');
  const pDesc = document.getElementById('preview-role-embed-desc');
  const pBorder = document.getElementById('preview-role-embed-border');
  
  if (pTitle) pTitle.textContent = title;
  if (pDesc) pDesc.textContent = desc;
  if (pBorder) {
    try {
      pBorder.style.borderLeftColor = color;
    } catch (e) {}
  }
}

// ==========================================================================
// WebSocket Logs Streaming
// ==========================================================================
function connectWebSocket() {
  if (socket) {
    try {
      socket.close();
    } catch (e) {}
  }
  
  let wsUrl;
  if (window.BOT_API_URL && window.BOT_API_URL !== '%%BOT_API_URL%%') {
    try {
      const urlObj = new URL(window.BOT_API_URL, window.location.href);
      const wsProtocol = urlObj.protocol === 'https:' ? 'wss:' : 'ws:';
      wsUrl = `${wsProtocol}//${urlObj.host}/ws/logs${authToken ? '?token=' + authToken : ''}`;
    } catch (e) {
      console.error("Failed to parse BOT_API_URL for WebSocket:", e);
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      wsUrl = `${protocol}//${window.location.host}/ws/logs${authToken ? '?token=' + authToken : ''}`;
    }
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsUrl = `${protocol}//${window.location.host}/ws/logs${authToken ? '?token=' + authToken : ''}`;
  }
  
  socket = new WebSocket(wsUrl);
  
  socket.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      if (parsed.type === 'stats_update') {
        const d = parsed.data;
        const msg = document.getElementById('stat-messages');
        const cmd = document.getElementById('stat-commands');
        const jt = document.getElementById('stat-joins-tickets');
        if (msg && d.messages_today !== undefined) msg.textContent = d.messages_today;
        if (cmd && d.commands_today !== undefined) cmd.textContent = d.commands_today;
        if (jt && d.joins_today !== undefined) jt.textContent = `${d.joins_today} / 0`;
        return;
      }
    } catch (e) {}
    appendLogLine(event.data);
  };
  
  socket.onclose = (event) => {
    if (event.code === 4001 || !isAuthenticated) {
      console.log('WebSocket connection closed.');
      return;
    }
    console.log('WebSocket disconnected. Reconnecting in 5 seconds...');
    setTimeout(connectWebSocket, 5000);
  };
  
  socket.onerror = (err) => {
    console.error('WebSocket log error:', err);
  };
}

function appendLogLine(line) {
  const term = document.getElementById('log-terminal');
  if (!term) return;
  
  const div = document.createElement('div');
  div.className = 'log-line';
  
  // Highlight logs based on level
  if (line.includes('[INFO]')) {
    div.classList.add('log-info');
  } else if (line.includes('[WARNING]') || line.includes('[WARN]')) {
    div.classList.add('log-warn');
  } else if (line.includes('[ERROR]')) {
    div.classList.add('log-error');
  } else {
    div.classList.add('log-system');
  }
  
  div.textContent = line;

  // Apply current search/filter to new lines
  const searchInput = document.getElementById('log-search-input');
  const levelFilter = document.getElementById('log-level-filter');
  const query = searchInput ? searchInput.value.toLowerCase() : '';
  const level = levelFilter ? levelFilter.value : 'all';
  const matchQuery = !query || line.toLowerCase().includes(query);
  const matchLevel = level === 'all' || line.includes('[' + level + ']');
  if (!matchQuery || !matchLevel) {
    div.style.display = 'none';
  }

  term.appendChild(div);
  
  // Auto scroll to bottom
  term.scrollTop = term.scrollHeight;
  
  // Cap history to 500 lines to avoid memory leak
  if (term.childNodes.length > 500) {
    term.removeChild(term.firstChild);
  }
}

// ==========================================================================
// Channels Population Endpoint Helper (Dynamic selectors)
// ==========================================================================
async function populateGuildChannels(guildId) {
  const welcomeSelect = document.getElementById('welcome-channel');
  const logSelect = document.getElementById('automod-log-channel');
  const ticketsSelect = document.getElementById('tickets-deploy-channel');
  
  const currentWelcomeId = currentConfig?.welcome_settings?.channel_id;
  const currentLogId = currentConfig?.automod_settings?.log_channel_id;
  const currentTicketId = currentConfig?.ticket_settings?.ticket_channel_id;
  
  try {
    const res = await fetch(`/api/guilds/${guildId}/channels`);
    if (!res.ok) return;
    const channels = await res.json();
    
    // Populate Welcome select
    welcomeSelect.innerHTML = '<option value="">Choose welcome channel...</option>';
    channels.forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.textContent = `#${ch.name}`;
      if (ch.id === currentWelcomeId) opt.selected = true;
      welcomeSelect.appendChild(opt);
    });
    
    // Populate Log select
    logSelect.innerHTML = '<option value="">Choose log channel...</option>';
    channels.forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.textContent = `#${ch.name}`;
      if (ch.id === currentLogId) opt.selected = true;
      logSelect.appendChild(opt);
    });

    // Populate Ticket deploy channel select
    if (ticketsSelect) {
      ticketsSelect.innerHTML = '<option value="">Select channel...</option>';
      channels.forEach(ch => {
        const opt = document.createElement('option');
        opt.value = ch.id;
        opt.textContent = `#${ch.name}`;
        if (ch.id === currentTicketId) opt.selected = true;
        ticketsSelect.appendChild(opt);
      });
    }
    
    // Populate Milestone channel select
    const milestoneSelect = document.getElementById('milestone-channel');
    if (milestoneSelect) {
      const currentMilestoneId = currentConfig?.milestone_settings?.channel_id;
      milestoneSelect.innerHTML = '<option value="">System channel (default)</option>';
      channels.forEach(ch => {
        if (ch.type !== 0) return;
        const opt = document.createElement('option');
        opt.value = ch.id;
        opt.textContent = `#${ch.name}`;
        if (ch.id === currentMilestoneId) opt.selected = true;
        milestoneSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Error fetching guild channels:', err);
  }
}

// ==========================================================================
// Event Listeners & Helpers
// ==========================================================================
function setupEventListeners() {
  // Refresh Guilds
  const btnRefreshGuilds = document.getElementById('btn-refresh-guilds');
  if (btnRefreshGuilds) {
    btnRefreshGuilds.addEventListener('click', refreshGuildsList);
  }
  
  // Server Selection
  const serverSelect = document.getElementById('server-select');
  if (serverSelect) {
    serverSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val) {
        localStorage.setItem('active_guild_id', val);
      } else {
        localStorage.removeItem('active_guild_id');
      }
      handleServerSelection(val);
    });
  }
  
  // Scan Button
  const btnRunAudit = document.getElementById('btn-run-audit');
  if (btnRunAudit) {
    btnRunAudit.addEventListener('click', runServerAudit);
  }
  
  // Health Timeline days selector
  const timelineDays = document.getElementById('timeline-days');
  if (timelineDays) {
    timelineDays.addEventListener('change', loadHealthTimeline);
  }
  
  // Optimizer Preset Cards Click
  setupPresetSelector();
  
  // Optimizer Run
  const btnExecuteOptimize = document.getElementById('btn-execute-optimize');
  if (btnExecuteOptimize) {
    btnExecuteOptimize.addEventListener('click', runOptimization);
  }
  
  // Form Saves
  const welcomeForm = document.getElementById('welcome-form');
  if (welcomeForm) {
    welcomeForm.addEventListener('submit', saveWelcomeSettings);
  }
  const milestoneForm = document.getElementById('milestone-form');
  if (milestoneForm) {
    milestoneForm.addEventListener('submit', saveMilestoneSettings);
  }
  const milestoneColorPicker = document.getElementById('milestone-color-picker');
  const milestoneColorHex = document.getElementById('milestone-color-hex');
  if (milestoneColorPicker && milestoneColorHex) {
    milestoneColorPicker.addEventListener('input', (e) => {
      milestoneColorHex.value = e.target.value.toUpperCase();
    });
    milestoneColorHex.addEventListener('input', (e) => {
      milestoneColorPicker.value = e.target.value;
    });
  }
  
  const automodForm = document.getElementById('automod-form');
  if (automodForm) {
    automodForm.addEventListener('submit', saveAutomodSettings);
  }

  // Anti-Raid Config
  const antiRaidForm = document.getElementById('anti-raid-form');
  if (antiRaidForm) {
    if (activeGuildId) {
      fetch(`/api/guilds/${activeGuildId}/anti-raid`, {
        headers: { 'Authorization': 'Bearer ' + authToken }
      }).then(r => r.json()).then(cfg => {
        document.getElementById('ar-enabled').checked = cfg.enabled || false;
        document.getElementById('ar-response-mode').value = cfg.response_mode || 'alert';
        document.getElementById('ar-join-threshold').value = cfg.join_rate_threshold || 5;
        document.getElementById('ar-window-seconds').value = cfg.join_rate_window_seconds || 30;
        document.getElementById('ar-min-age').value = cfg.min_account_age_days || 7;
        document.getElementById('ar-score-threshold').value = cfg.suspicious_score_threshold || 70;
        document.getElementById('ar-dm-owner').checked = cfg.dm_owner_on_raid !== false;
      }).catch(() => {});
    }

    antiRaidForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!activeGuildId) return;
      const cfg = {
        enabled: document.getElementById('ar-enabled').checked,
        response_mode: document.getElementById('ar-response-mode').value,
        join_rate_threshold: parseInt(document.getElementById('ar-join-threshold').value),
        join_rate_window_seconds: parseInt(document.getElementById('ar-window-seconds').value),
        min_account_age_days: parseInt(document.getElementById('ar-min-age').value),
        suspicious_score_threshold: parseInt(document.getElementById('ar-score-threshold').value),
        dm_owner_on_raid: document.getElementById('ar-dm-owner').checked,
      };
      try {
        const res = await fetch(`/api/guilds/${activeGuildId}/anti-raid`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
          body: JSON.stringify(cfg)
        });
        if (res.ok) showToast('Anti-raid settings saved!', 'success');
        else showToast('Failed to save settings.', 'error');
      } catch (err) {
        showToast('Network error.', 'error');
      }
    });
  }
  
  // Sync Welcome Embed Previews dynamically
  const welcomeTitle = document.getElementById('welcome-title');
  if (welcomeTitle) {
    welcomeTitle.addEventListener('input', syncWelcomePreview);
  }
  const welcomeDescription = document.getElementById('welcome-description');
  if (welcomeDescription) {
    welcomeDescription.addEventListener('input', syncWelcomePreview);
  }
  
  const hexInput = document.getElementById('welcome-color-hex');
  const pickerInput = document.getElementById('welcome-color-picker');
  if (hexInput && pickerInput) {
    hexInput.addEventListener('input', (e) => {
      pickerInput.value = e.target.value;
      syncWelcomePreview();
    });
    
    pickerInput.addEventListener('input', (e) => {
      hexInput.value = e.target.value.toUpperCase();
      syncWelcomePreview();
    });
  }
  
  // Clear Logs console
  const btnClearLogs = document.getElementById('btn-clear-logs');
  if (btnClearLogs) {
    btnClearLogs.addEventListener('click', () => {
      const logTerminal = document.getElementById('log-terminal');
      if (logTerminal) {
        logTerminal.innerHTML = '';
      }
    });
  }

  // Log Search & Filter
  const logSearchInput = document.getElementById('log-search-input');
  const logLevelFilter = document.getElementById('log-level-filter');
  function applyLogFilter() {
    const term = document.getElementById('log-terminal');
    if (!term) return;
    const query = (logSearchInput ? logSearchInput.value : '').toLowerCase();
    const level = logLevelFilter ? logLevelFilter.value : 'all';
    const lines = term.querySelectorAll('.log-line');
    lines.forEach(line => {
      const text = line.textContent || '';
      const matchQuery = !query || text.toLowerCase().includes(query);
      const matchLevel = level === 'all' || text.includes('[' + level + ']');
      line.style.display = (matchQuery && matchLevel) ? '' : 'none';
    });
  }
  if (logSearchInput) logSearchInput.addEventListener('input', applyLogFilter);
  if (logLevelFilter) logLevelFilter.addEventListener('change', applyLogFilter);

  // Custom Commands Form Submit
  const cmdForm = document.getElementById('command-form');
  if (cmdForm) {
    cmdForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const trigger = document.getElementById('command-trigger').value.trim();
      const response = document.getElementById('command-response').value.trim();
      
      if (!trigger || !response) {
        showToast('Please fill in both trigger and response.', 'warning');
        return;
      }
      
      if (!trigger.startsWith('!') && !trigger.startsWith('/') && !trigger.startsWith('?')) {
        showToast('Trigger must start with a prefix like !, / or ?', 'warning');
        return;
      }
      
      localCustomCommands[trigger] = response;
      renderCustomCommands();
      
      // Clear inputs
      document.getElementById('command-trigger').value = '';
      document.getElementById('command-response').value = '';
      
      showToast(`Command ${trigger} added locally. Save & Deploy to activate.`, 'success');
    });
  }
  
  // Save Commands Button
  const btnSaveCmds = document.getElementById('btn-save-commands');
  if (btnSaveCmds) {
    btnSaveCmds.addEventListener('click', async () => {
      try {
        showToast('Deploying custom commands...', 'info');
        const url = activeGuildId ? `/api/commands?guild_id=${activeGuildId}` : '/api/commands';
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(localCustomCommands)
        });
        if (res.ok) {
          showToast('Custom commands successfully deployed to bot.', 'success');
          if (currentConfig) {
            currentConfig.custom_commands = { ...localCustomCommands };
          }
        } else {
          showToast('Failed to deploy custom commands.', 'error');
        }
      } catch (e) {
        showToast('Network error deploying custom commands.', 'error');
      }
    });
  }
  
  // Tickets Form Submit
  const tktForm = document.getElementById('tickets-form');
  if (tktForm) {
    tktForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const enabled = document.getElementById('tickets-enabled').checked;
      const category_name = document.getElementById('tickets-category').value.trim();
      const staff_role_name = document.getElementById('tickets-role').value.trim();
      
      if (!category_name || !staff_role_name) {
        showToast('Category name and staff role name are required.', 'warning');
        return;
      }
      
      if (!currentConfig) return;
      if (!currentConfig.ticket_settings) {
        currentConfig.ticket_settings = {};
      }
      
      currentConfig.ticket_settings.enabled = enabled;
      currentConfig.ticket_settings.category_name = category_name;
      currentConfig.ticket_settings.staff_role_name = staff_role_name;
      
      try {
        showToast('Saving ticket configurations...', 'info');
        const url = activeGuildId ? `/api/config?guild_id=${activeGuildId}` : '/api/config';
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(currentConfig)
        });
        
        if (res.ok) {
          showToast('Ticket configurations saved.', 'success');
        } else {
          showToast('Failed to save ticket settings.', 'error');
        }
      } catch (err) {
        showToast('Network error saving ticket settings.', 'error');
      }
    });
  }
  
  // Deploy Tickets Button
  const btnDeployTkts = document.getElementById('btn-deploy-tickets');
  if (btnDeployTkts) {
    btnDeployTkts.addEventListener('click', async () => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      
      const channelSelect = document.getElementById('tickets-deploy-channel');
      const channelId = channelSelect.value;
      if (!channelId) {
        showToast('Please select a channel to deploy the panel.', 'warning');
        return;
      }
      
      try {
        showToast('Deploying ticketing panel to Discord...', 'info');
        const res = await fetch('/api/tickets/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            guild_id: activeGuildId,
            channel_id: channelId
          })
        });
        
        if (res.ok) {
          showToast('Ticket panel deployed successfully!', 'success');
        } else {
          const err = await res.json();
          showToast(`Failed to deploy panel: ${err.detail || 'Unknown error'}`, 'error');
        }
      } catch (e) {
        showToast('Network error deploying ticket panel.', 'error');
      }
    });
  }
  
  // Download Backup Button
  const btnDownloadBackup = document.getElementById('btn-download-backup');
  if (btnDownloadBackup) {
    btnDownloadBackup.addEventListener('click', async () => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      try {
        showToast('Generating server layout backup...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/backup`);
        if (!res.ok) {
          throw new Error('Backup failed');
        }
        const data = await res.json();
        
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", dataStr);
        downloadAnchor.setAttribute("download", `guild_backup_${activeGuildId}.json`);
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
        
        showToast('Server backup file downloaded successfully.', 'success');
      } catch (err) {
        showToast('Failed to create server backup. Check bot permissions.', 'error');
      }
    });
  }
  
  // Upload/Restore Backup Input
  const uploadBackupFile = document.getElementById('upload-backup-file');
  if (uploadBackupFile) {
    uploadBackupFile.addEventListener('change', async (e) => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      
      const file = e.target.files[0];
      if (!file) return;
      
      const fileInput = e.target;
      
      const check = confirm(`⚠️ CRITICAL WARNING: Are you sure you want to restore the layout from "${file.name}"? Existing channels will be moved to a backup archive category.`);
      if (!check) {
        fileInput.value = '';
        return;
      }
      
      const statusDiv = document.getElementById('restore-status');
      if (statusDiv) statusDiv.classList.remove('hidden');
      
      const reader = new FileReader();
      reader.onload = async (event) => {
        try {
          const backupData = JSON.parse(event.target.result);
          
          showToast('Restoring server layout from file...', 'info');
          const res = await fetch(`/api/guilds/${activeGuildId}/restore`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(backupData)
          });
          
          if (res.ok) {
            showToast('Server structure restored successfully!', 'success');
            setTimeout(() => {
              handleServerSelection(activeGuildId);
              runServerAudit();
            }, 2000);
          } else {
            const err = await res.json();
            showToast(`Restore failed: ${err.detail || 'Unknown error'}`, 'error');
          }
        } catch (err) {
          showToast('Invalid backup file or network error.', 'error');
        } finally {
          if (statusDiv) statusDiv.classList.add('hidden');
          fileInput.value = '';
        }
      };
      reader.readAsText(file);
    });
  }

  // Config Export Button
  const btnExportConfig = document.getElementById('btn-export-config');
  if (btnExportConfig) {
    btnExportConfig.addEventListener('click', async () => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      try {
        const res = await fetch(`/api/config/export?guild_id=${activeGuildId}`, {
          headers: { 'Authorization': 'Bearer ' + authToken }
        });
        if (!res.ok) throw new Error('Export failed');
        const data = await res.json();
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
        const anchor = document.createElement('a');
        anchor.setAttribute("href", dataStr);
        anchor.setAttribute("download", `aegis_config_${activeGuildId}.json`);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        showToast('Configuration exported successfully.', 'success');
      } catch (err) {
        showToast('Failed to export configuration.', 'error');
      }
    });
  }

  // Config Import
  const uploadConfigFile = document.getElementById('upload-config-file');
  if (uploadConfigFile) {
    uploadConfigFile.addEventListener('change', async (e) => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      const file = e.target.files[0];
      if (!file) return;
      const fileInput = e.target;
      const statusDiv = document.getElementById('config-import-status');
      if (statusDiv) statusDiv.classList.remove('hidden');
      const reader = new FileReader();
      reader.onload = async (event) => {
        try {
          const importData = JSON.parse(event.target.result);
          const payload = importData.config ? { guild_id: activeGuildId, config: importData.config } : { config: importData };
          const res = await fetch('/api/config/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
            body: JSON.stringify(payload)
          });
          if (res.ok) {
            showToast('Configuration imported successfully!', 'success');
          } else {
            const err = await res.json();
            showToast(`Import failed: ${err.detail || 'Unknown error'}`, 'error');
          }
        } catch (err) {
          showToast('Invalid config file or network error.', 'error');
        } finally {
          if (statusDiv) statusDiv.classList.add('hidden');
          fileInput.value = '';
        }
      };
      reader.readAsText(file);
    });
  }

  // ==========================================================================
  // Authentication Event Listeners
  // ==========================================================================
  
  // Auth Setup Form Submit
  const authSetupForm = document.getElementById('auth-setup-form');
  if (authSetupForm) {
    authSetupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const password = document.getElementById('setup-password').value;
      const confirmPassword = document.getElementById('setup-confirm-password').value;
      
      if (password !== confirmPassword) {
        showToast('Passwords do not match.', 'warning');
        return;
      }
      
      if (password.length < 6) {
        showToast('Password must be at least 6 characters.', 'warning');
        return;
      }
      
      try {
        const res = await fetch('/api/auth/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password })
        });
        
        if (res.ok) {
          const data = await res.json();
          authToken = data.token;
          localStorage.setItem('admin_token', authToken);
          localStorage.setItem('admin_role', 'admin');
          localStorage.setItem('admin_guild_id', 'global');
          showToast('Password set successfully. Welcome!', 'success');
          const authed = await checkAuthentication();
          if (authed) {
            initApp();
          }
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to setup password.', 'error');
        }
      } catch (err) {
        showToast('Network error setting up password.', 'error');
      }
    });
  }
  
  // Auth Login Form Submit
  const authLoginForm = document.getElementById('auth-login-form');
  if (authLoginForm) {
    authLoginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const password = document.getElementById('login-password').value;
      
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password })
        });
        
        if (res.ok) {
          const data = await res.json();
          authToken = data.token;
          localStorage.setItem('admin_token', authToken);
          localStorage.setItem('admin_role', data.role || 'guest');
          localStorage.setItem('admin_guild_id', data.guild_id || '');
          showToast('Dashboard unlocked successfully.', 'success');
          document.getElementById('login-password').value = '';
          const authed = await checkAuthentication();
          if (authed) {
            initApp();
          }
        } else {
          const err = await res.json();
          showToast(err.detail || 'Invalid password.', 'error');
        }
      } catch (err) {
        showToast('Network error during login.', 'error');
      }
    });
  }

  // Theme Toggle
  const btnThemeToggle = document.getElementById('btn-theme-toggle');
  if (btnThemeToggle) {
    const savedTheme = localStorage.getItem('aegis_theme') || 'dark';
    
    function applyThemeUI(theme) {
      if (theme === 'light') {
        document.body.classList.add('light-theme');
        btnThemeToggle.innerHTML = '<i class="fa-solid fa-sun"></i> Light';
      } else {
        document.body.classList.remove('light-theme');
        btnThemeToggle.innerHTML = '<i class="fa-solid fa-moon"></i> Dark';
      }
    }

    applyThemeUI(savedTheme);

    btnThemeToggle.addEventListener('click', () => {
      const isLight = document.body.classList.contains('light-theme');
      const nextTheme = isLight ? 'dark' : 'light';
      localStorage.setItem('aegis_theme', nextTheme);
      applyThemeUI(nextTheme);
      
      // Dynamic Chart Redraw on Theme Change
      if (typeof window.loadSmartFeatures === 'function') {
        window.loadSmartFeatures();
      }
      loadHealthTimeline();
    });
  }

  // Logout Button
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) {
    btnLogout.addEventListener('click', async () => {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (err) {}
      logoutLocalState();
      showToast('Logged out successfully.', 'info');
      checkAuthentication();
    });
  }

  // ==========================================================================
  // Role Creator Event Listeners
  // ==========================================================================
  const roleCreatorForm = document.getElementById('role-creator-form');
  if (roleCreatorForm) {
    roleCreatorForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      const name = document.getElementById('role-name').value.trim();
      const color = document.getElementById('role-color-hex').value.trim();
      const hoist = document.getElementById('role-hoist').checked;
      
      if (!name) {
        showToast('Role name is required.', 'warning');
        return;
      }
      
      try {
        showToast('Creating role in Discord...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/roles`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, color, hoist })
        });
        
        if (res.ok) {
          showToast('Role created successfully!', 'success');
          document.getElementById('role-name').value = '';
          loadServerRoles();
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to create role.', 'error');
        }
      } catch (err) {
        showToast('Network error creating role.', 'error');
      }
    });
  }

  const rHexInput = document.getElementById('role-color-hex');
  const rPickerInput = document.getElementById('role-color-picker');
  if (rHexInput && rPickerInput) {
    rHexInput.addEventListener('input', (e) => {
      rPickerInput.value = e.target.value;
    });
    rPickerInput.addEventListener('input', (e) => {
      rHexInput.value = e.target.value.toUpperCase();
    });
  }

  // ==========================================================================
  // Role Panel Event Listeners
  // ==========================================================================
  const btnAddPanelBtn = document.getElementById('btn-add-panel-button');
  if (btnAddPanelBtn) {
    btnAddPanelBtn.addEventListener('click', () => {
      const roleSelect = document.getElementById('builder-btn-role');
      const roleId = roleSelect.value;
      const roleName = roleSelect.options[roleSelect.selectedIndex]?.text;
      let label = document.getElementById('builder-btn-label').value.trim();
      const emoji = document.getElementById('builder-btn-emoji').value.trim();
      const style = document.getElementById('builder-btn-style').value;
      
      if (!roleId) {
        showToast('Please select a target role.', 'warning');
        return;
      }
      
      if (!label) {
        label = roleName;
      }
      
      rolePanelButtons.push({
        role_id: roleId,
        role_name: roleName,
        label: label,
        emoji: emoji || null,
        style: style
      });
      
      renderPanelButtons();
      
      // Clear inputs
      document.getElementById('builder-btn-label').value = '';
      document.getElementById('builder-btn-emoji').value = '';
      showToast('Button added to panel layout.', 'success');
    });
  }

  const btnClearPanel = document.getElementById('btn-clear-panel-form');
  if (btnClearPanel) {
    btnClearPanel.addEventListener('click', () => {
      rolePanelButtons = [];
      renderPanelButtons();
      showToast('Panel buttons cleared.', 'info');
    });
  }

  const rolePanelForm = document.getElementById('role-panel-form');
  if (rolePanelForm) {
    rolePanelForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      
      const channelId = document.getElementById('role-panel-channel').value;
      const title = document.getElementById('role-panel-title').value.trim();
      const description = document.getElementById('role-panel-desc').value.trim();
      const color = document.getElementById('role-panel-color-hex').value.trim();
      
      if (!channelId) {
        showToast('Please select a deployment channel.', 'warning');
        return;
      }
      if (!title || !description) {
        showToast('Panel title and description are required.', 'warning');
        return;
      }
      if (rolePanelButtons.length === 0) {
        showToast('Please add at least one button to the panel.', 'warning');
        return;
      }
      
      try {
        showToast('Deploying role selection panel to Discord...', 'info');
        const res = await fetch('/api/roles/panel/deploy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            guild_id: activeGuildId,
            channel_id: channelId,
            title: title,
            description: description,
            color: color,
            buttons: rolePanelButtons.map(btn => ({
              role_id: btn.role_id,
              label: btn.label,
              emoji: btn.emoji,
              style: btn.style
            }))
          })
        });
        
        if (res.ok) {
          showToast('Role selection panel deployed successfully!', 'success');
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to deploy role panel.', 'error');
        }
      } catch (err) {
        showToast('Network error deploying role panel.', 'error');
      }
    });
  }

  const rpTitle = document.getElementById('role-panel-title');
  const rpDesc = document.getElementById('role-panel-desc');
  const rpHex = document.getElementById('role-panel-color-hex');
  const rpPicker = document.getElementById('role-panel-color-picker');
  
  if (rpTitle) rpTitle.addEventListener('input', syncRolePanelPreview);
  if (rpDesc) rpDesc.addEventListener('input', syncRolePanelPreview);
  if (rpHex && rpPicker) {
    rpHex.addEventListener('input', (e) => {
      rpPicker.value = e.target.value;
      syncRolePanelPreview();
    });
    rpPicker.addEventListener('input', (e) => {
      rpHex.value = e.target.value.toUpperCase();
      syncRolePanelPreview();
    });
  }

  // ==========================================================================
  // Templates Manager Event Listeners
  // ==========================================================================
  const btnSaveTemplate = document.getElementById('btn-save-template');
  if (btnSaveTemplate) {
    btnSaveTemplate.addEventListener('click', async () => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      const nameInput = document.getElementById('template-save-name');
      const name = nameInput.value.trim();
      if (!name) {
        showToast('Template name is required.', 'warning');
        return;
      }
      
      const confirmSave = confirm(`Are you sure you want to capture the current server layout as "${name}"?`);
      if (!confirmSave) return;
      
      try {
        showToast('Capturing layout as template...', 'info');
        const res = await fetch('/api/templates/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            guild_id: activeGuildId,
            name: name
          })
        });
        
        if (res.ok) {
          showToast('Template layout saved successfully!', 'success');
          nameInput.value = '';
          fetchTemplates();
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to save template.', 'error');
        }
      } catch (err) {
        showToast('Network error saving template.', 'error');
      }
    });
  }

  // Open / Close Import Template Modal functions
  window.openImportTemplateModal = function() {
    const overlay = document.getElementById('template-import-overlay');
    if (overlay) {
      overlay.classList.remove('hidden');
      document.getElementById('template-import-name').value = '';
      document.getElementById('template-import-json').value = '';
    }
  };

  window.closeImportTemplateModal = function() {
    const overlay = document.getElementById('template-import-overlay');
    if (overlay) overlay.classList.add('hidden');
  };

  // Wire up JSON Import submission
  const btnSubmitImportJson = document.getElementById('btn-submit-import-json');
  if (btnSubmitImportJson) {
    btnSubmitImportJson.addEventListener('click', async () => {
      const nameInput = document.getElementById('template-import-name');
      const jsonInput = document.getElementById('template-import-json');
      const name = nameInput.value.trim();
      const rawJson = jsonInput.value.trim();
      
      if (!name) {
        showToast('Template name is required.', 'warning');
        return;
      }
      if (!rawJson) {
        showToast('Template JSON text is required.', 'warning');
        return;
      }
      
      let parsedData;
      try {
        parsedData = JSON.parse(rawJson);
      } catch (err) {
        showToast('Invalid JSON format. Please verify the syntax.', 'error');
        return;
      }
      
      if (!parsedData.categories && !parsedData.roles && !parsedData.channels) {
        showToast('Invalid layout data. Must contain roles, channels, or categories.', 'error');
        return;
      }
      
      try {
        showToast('Importing template...', 'info');
        const res = await fetch('/api/templates/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name,
            data: parsedData
          })
        });
        
        if (res.ok) {
          showToast('Template imported successfully!', 'success');
          closeImportTemplateModal();
          fetchTemplates();
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to import template.', 'error');
        }
      } catch (err) {
        showToast('Network error importing template.', 'error');
      }
    });
  }

  // Wire up File upload listener
  const templateFileInput = document.getElementById('template-file-input');
  if (templateFileInput) {
    templateFileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      
      const reader = new FileReader();
      reader.onload = async (evt) => {
        let parsedData;
        try {
          parsedData = JSON.parse(evt.target.result);
        } catch (err) {
          showToast('Invalid JSON file.', 'error');
          return;
        }
        
        if (!parsedData.categories && !parsedData.roles && !parsedData.channels) {
          showToast('Invalid template file. Must contain roles, channels, or categories.', 'error');
          return;
        }
        
        // Use filename (without .json) as default template name
        const defaultName = file.name.replace(/\.[^/.]+$/, "");
        const name = prompt("Enter a name for the imported template:", defaultName);
        if (name === null) return; // User cancelled
        const finalName = name.trim() || defaultName;
        
        try {
          showToast('Importing template...', 'info');
          const res = await fetch('/api/templates/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: finalName,
              data: parsedData
            })
          });
          
          if (res.ok) {
            showToast('Template file imported successfully!', 'success');
            fetchTemplates();
          } else {
            const err = await res.json();
            showToast(err.detail || 'Failed to import template file.', 'error');
          }
        } catch (err) {
          showToast('Network error importing template file.', 'error');
        }
      };
      reader.readAsText(file);
      // Clear input so same file can be selected again
      templateFileInput.value = '';
    });
  }

  // Template Preview & Deployment Listeners
  const cancelTemplatePreviewBtn = document.getElementById('btn-cancel-template-preview');
  if (cancelTemplatePreviewBtn) {
    cancelTemplatePreviewBtn.addEventListener('click', () => {
      document.getElementById('template-preview-overlay').classList.add('hidden');
      localStorage.removeItem('template_modal_state');
    });
  }

  const templateConfirmCheckbox = document.getElementById('template-confirm-checkbox');
  const deleteConfirmInput = document.getElementById('delete-confirm-input');
  const deployTemplatePreviewBtn = document.getElementById('btn-deploy-template-preview');

  const updateDeployButtonState = () => {
    if (!templateConfirmCheckbox || !deployTemplatePreviewBtn) return;
    const handling = document.querySelector('input[name="channel-handling"]:checked')?.value || 'archive';
    
    if (handling === 'delete') {
      const typedDelete = deleteConfirmInput ? deleteConfirmInput.value.trim() : '';
      deployTemplatePreviewBtn.disabled = !(templateConfirmCheckbox.checked && typedDelete === 'DELETE');
    } else {
      deployTemplatePreviewBtn.disabled = !templateConfirmCheckbox.checked;
    }
  };

  if (templateConfirmCheckbox) {
    templateConfirmCheckbox.addEventListener('change', updateDeployButtonState);
  }
  if (deleteConfirmInput) {
    deleteConfirmInput.addEventListener('input', updateDeployButtonState);
  }

  // Quick Action Buttons
  const btnQuickRestore = document.getElementById('btn-quick-restore');
  if (btnQuickRestore) {
    btnQuickRestore.addEventListener('click', async () => {
      const select = document.getElementById('restore-backup-select');
      if (!select) return;
      
      try {
        const res = await fetch('/api/templates');
        if (res.ok) {
          const templates = await res.json();
          select.innerHTML = '<option value="">-- Choose Backup --</option>';
          templates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.name;
            opt.textContent = t.name;
            select.appendChild(opt);
          });
          document.getElementById('restore-backup-overlay').classList.remove('hidden');
        } else {
          showToast('Failed to load backups.', 'error');
        }
      } catch (err) {
        showToast('Error loading backups.', 'error');
      }
    });
  }

  const btnConfirmRestoreBackup = document.getElementById('btn-confirm-restore-backup');
  if (btnConfirmRestoreBackup) {
    btnConfirmRestoreBackup.addEventListener('click', () => {
      const select = document.getElementById('restore-backup-select');
      const backupName = select?.value;
      if (!backupName) {
        showToast('Please select a backup first.', 'warning');
        return;
      }
      document.getElementById('restore-backup-overlay').classList.add('hidden');
      openTemplatePreview(backupName);
    });
  }

  const btnQuickImport = document.getElementById('btn-quick-import');
  if (btnQuickImport) {
    btnQuickImport.addEventListener('click', () => {
      openImportTemplateModal();
    });
  }

  if (deployTemplatePreviewBtn) {
    deployTemplatePreviewBtn.addEventListener('click', async () => {
      if (!currentPreviewTemplateName || !activeGuildId) return;

      const disabledElements = [];
      const renames = {};

      document.querySelectorAll('#template-tree-customizer .tree-item').forEach(item => {
        const toggle = item.querySelector('.tree-item-toggle');
        const input = item.querySelector('.tree-item-name');
        const origName = toggle.getAttribute('data-original-name');
        const type = toggle.getAttribute('data-type');
        const key = `${type}:${origName}`;

        if (!toggle.checked) {
          disabledElements.push(key);
        }
        const val = input.value.trim();
        if (val !== origName) {
          renames[key] = val;
        }
      });

      const handling = document.querySelector('input[name="channel-handling"]:checked')?.value || 'archive';

      try {
        showToast(`Deploying template "${currentPreviewTemplateName}"...`, 'info');
        document.getElementById('template-preview-overlay').classList.add('hidden');

        const res = await fetch('/api/templates/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            guild_id: activeGuildId,
            name: currentPreviewTemplateName,
            confirm: true,
            handling: handling,
            customizations: {
              disabled_elements: disabledElements,
              renames: renames
            }
          })
        });

        if (res.ok) {
          showToast('Template applied successfully!', 'success');
          localStorage.removeItem('template_modal_state');
          setTimeout(() => {
            handleServerSelection(activeGuildId);
            runServerAudit();
          }, 2000);
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to apply template.', 'error');
        }
      } catch (err) {
        showToast('Network error applying template.', 'error');
      }
    });
  }

  // --- Embed Builder Pro Listeners ---
  const embedForm = document.getElementById('embed-builder-form');
  if (embedForm) {
    embedForm.addEventListener('submit', submitEmbedBuilder);
  }
  const btnEmbedAddTab = document.getElementById('btn-embed-add-tab');
  if (btnEmbedAddTab) {
    btnEmbedAddTab.addEventListener('click', addEmbedTab);
  }
  const btnEmbedDuplicateTab = document.getElementById('btn-embed-duplicate-tab');
  if (btnEmbedDuplicateTab) {
    btnEmbedDuplicateTab.addEventListener('click', duplicateEmbedTab);
  }
  const embedScheduleToggle = document.getElementById('embed-schedule-toggle');
  if (embedScheduleToggle) {
    embedScheduleToggle.addEventListener('change', () => {
      const dtGroup = document.getElementById('embed-schedule-datetime');
      const sendText = document.getElementById('btn-embed-send-text');
      if (embedScheduleToggle.checked) {
        dtGroup.classList.remove('hidden');
        dtGroup.style.display = 'flex';
        sendText.textContent = 'Schedule Embed';
        const now = new Date();
        now.setMinutes(now.getMinutes() + 30);
        const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        document.getElementById('embed-schedule-time').value = local;
      } else {
        dtGroup.classList.add('hidden');
        dtGroup.style.display = 'none';
        sendText.textContent = 'Send Embed';
      }
    });
  }
  const btnEmbedAddField = document.getElementById('btn-embed-add-field');
  if (btnEmbedAddField) {
    btnEmbedAddField.addEventListener('click', addEmbedField);
  }
  const btnEmbedImport = document.getElementById('btn-embed-import');
  if (btnEmbedImport) {
    btnEmbedImport.addEventListener('click', importEmbedJSON);
  }
  const btnEmbedExport = document.getElementById('btn-embed-export');
  if (btnEmbedExport) {
    btnEmbedExport.addEventListener('click', exportEmbedJSON);
  }
  const btnEmbedSaveDraft = document.getElementById('btn-embed-save-draft');
  if (btnEmbedSaveDraft) {
    btnEmbedSaveDraft.addEventListener('click', saveEmbedDraft);
  }
  const btnEmbedLoadDraft = document.getElementById('btn-embed-load-draft');
  if (btnEmbedLoadDraft) {
    btnEmbedLoadDraft.addEventListener('click', loadEmbedDraft);
  }
  // Event listeners for embed preview live sync
  const embedSyncInputs = [
    'embed-plain-text', 'embed-author-name', 'embed-author-icon',
    'embed-title', 'embed-description-text', 'embed-thumbnail',
    'embed-image', 'embed-footer-text', 'embed-footer-icon',
    'embed-color-hex', 'embed-timestamp'
  ];
  embedSyncInputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', updateEmbedPreview);
  });
  const embedColorPicker = document.getElementById('embed-color-picker');
  const embedColorHex = document.getElementById('embed-color-hex');
  if (embedColorPicker && embedColorHex) {
    embedColorPicker.addEventListener('input', (e) => {
      embedColorHex.value = e.target.value.toUpperCase();
      updateEmbedPreview();
    });
    embedColorHex.addEventListener('input', (e) => {
      embedColorPicker.value = e.target.value;
      updateEmbedPreview();
    });
  }

  document.querySelectorAll('.color-swatch').forEach(swatch => {
    swatch.addEventListener('click', () => {
      const color = swatch.getAttribute('data-color');
      if (embedColorHex) embedColorHex.value = color;
      if (embedColorPicker) embedColorPicker.value = color;
      updateEmbedPreview();
    });
  });

  // --- Music Player Listeners ---
  const musicPlayForm = document.getElementById('music-play-form');
  if (musicPlayForm) {
    musicPlayForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const query = document.getElementById('music-search-query').value.trim();
      if (query) playMusicTrack(query);
    });
  }
  const btnMusicToggle = document.getElementById('btn-music-toggle');
  if (btnMusicToggle) {
    btnMusicToggle.addEventListener('click', toggleMusic);
  }
  const btnMusicStop = document.getElementById('btn-music-stop');
  if (btnMusicStop) {
    btnMusicStop.addEventListener('click', stopMusic);
  }
  const btnMusicSkip = document.getElementById('btn-music-skip');
  if (btnMusicSkip) {
    btnMusicSkip.addEventListener('click', skipMusic);
  }
  const musicVolumeSlider = document.getElementById('music-volume-slider');
  if (musicVolumeSlider) {
    musicVolumeSlider.addEventListener('input', (e) => {
      const vol = e.target.value;
      document.getElementById('music-volume-label').textContent = `${vol}%`;
      setMusicVolume(vol / 100);
    });
  }
  const btnMusicJoin = document.getElementById('btn-music-join-channel');
  if (btnMusicJoin) {
    btnMusicJoin.addEventListener('click', () => {
      const channelId = document.getElementById('music-voice-select').value;
      if (channelId) joinMusicVoiceChannel(channelId);
      else showToast('Please select a voice channel.', 'warning');
    });
  }
  const btnMusicShuffle = document.getElementById('btn-music-shuffle');
  if (btnMusicShuffle) {
    btnMusicShuffle.addEventListener('click', shuffleMusicQueue);
  }

  // Custom Bot Invite Generator Click
  const btnGenBotInvite = document.getElementById('btn-generate-bot-invite');
  if (btnGenBotInvite) {
    btnGenBotInvite.addEventListener('click', () => {
      const clientId = document.getElementById('custom-bot-client-id').value.trim();
      const perms = document.getElementById('custom-bot-perms').value;
      if (!clientId) {
        showToast('Please enter a valid Bot Client ID.', 'warning');
        return;
      }
      if (!/^\d+$/.test(clientId)) {
        showToast('Client ID must contain digits only.', 'warning');
        return;
      }
      const inviteUrl = `https://discord.com/oauth2/authorize?client_id=${clientId}&permissions=${perms}&scope=bot%20applications.commands`;
      window.open(inviteUrl, '_blank');
      showToast('Invite link generated and opened in a new tab!', 'success');
    });
  }

  // FFmpeg Install Guide Toggle
  const btnToggleFfmpegGuide = document.getElementById('btn-toggle-ffmpeg-guide');
  if (btnToggleFfmpegGuide) {
    btnToggleFfmpegGuide.addEventListener('click', () => {
      const guide = document.getElementById('ffmpeg-install-guide');
      if (guide) {
        guide.classList.toggle('hidden');
        if (guide.classList.contains('hidden')) {
          btnToggleFfmpegGuide.innerHTML = '<i class="fa-solid fa-book mr-1"></i> How to Install FFmpeg';
        } else {
          btnToggleFfmpegGuide.innerHTML = '<i class="fa-solid fa-book-open mr-1"></i> Hide Installation Guide';
        }
      }
    });
  }

  // --- Scheduler Listeners ---
  const schedulerForm = document.getElementById('scheduler-form');
  if (schedulerForm) {
    schedulerForm.addEventListener('submit', submitScheduledMessage);
  }
  const schedulerType = document.getElementById('scheduler-type');
  if (schedulerType) {
    schedulerType.addEventListener('change', (e) => {
      const type = e.target.value;
      const datetimeWrapper = document.getElementById('scheduler-datetime-wrapper');
      const recurringWrapper = document.getElementById('scheduler-recurring-wrapper');
      if (type === 'once') {
        datetimeWrapper.classList.remove('hidden');
        recurringWrapper.classList.add('hidden');
        document.getElementById('scheduler-datetime').required = true;
      } else {
        datetimeWrapper.classList.add('hidden');
        recurringWrapper.classList.remove('hidden');
        document.getElementById('scheduler-datetime').required = false;
      }
    });
  }

  // --- Leveling System Listeners ---
  const levelingForm = document.getElementById('leveling-config-form');
  if (levelingForm) {
    levelingForm.addEventListener('submit', submitLevelingConfig);
  }
  const btnLevelRoleAdd = document.getElementById('btn-level-role-add');
  if (btnLevelRoleAdd) {
    btnLevelRoleAdd.addEventListener('click', addLevelRoleMapping);
  }
  const btnLevelReset = document.getElementById('btn-level-reset');
  if (btnLevelReset) {
    btnLevelReset.addEventListener('click', resetLevelingData);
  }

  // --- Auto-Responder Listeners ---
  const autoResponderForm = document.getElementById('auto-responder-form');
  if (autoResponderForm) {
    autoResponderForm.addEventListener('submit', submitAutoResponder);
  }
  const autoRespEmbedToggle = document.getElementById('auto-resp-embed-toggle');
  if (autoRespEmbedToggle) {
    autoRespEmbedToggle.addEventListener('change', (e) => {
      const editor = document.getElementById('auto-resp-embed-editor');
      if (e.target.checked) editor.classList.remove('hidden');
      else editor.classList.add('hidden');
    });
  }

  // --- Audit Log Listeners ---
  const auditLogFilter = document.getElementById('audit-log-filter');
  if (auditLogFilter) {
    auditLogFilter.addEventListener('change', () => fetchAuditLogs());
  }
  const auditLogScope = document.getElementById('audit-log-scope');
  if (auditLogScope) {
    auditLogScope.addEventListener('change', () => fetchAuditLogs());
  }
  const btnAuditLogRefresh = document.getElementById('btn-audit-log-refresh');
  if (btnAuditLogRefresh) {
    btnAuditLogRefresh.addEventListener('click', () => fetchAuditLogs());
  }
}

// Notification Toast Utility
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  let icon = 'fa-circle-info';
  if (type === 'success') icon = 'fa-circle-check';
  if (type === 'warning') icon = 'fa-triangle-exclamation';
  if (type === 'error') icon = 'fa-circle-xmark';
  
  toast.innerHTML = `
    <i class="fa-solid ${icon}"></i>
    <span>${escapeHtml(message)}</span>
  `;
  
  container.appendChild(toast);
  
  // Remove after 4 seconds
  setTimeout(() => {
    toast.style.animation = 'fadeIn 0.3s ease reverse forwards';
    setTimeout(() => {
      container.removeChild(toast);
    }, 300);
  }, 4000);
}

// Toggle Wizard password field visibility
function togglePasswordVisibility(id) {
  const field = document.getElementById(id);
  const icon = field.nextElementSibling.querySelector('i');
  if (field.type === 'password') {
    field.type = 'text';
    icon.className = 'fa-solid fa-eye-slash';
  } else {
    field.type = 'password';
    icon.className = 'fa-solid fa-eye';
  }
}

// ==========================================================================
// Visual Embed Designer Pro Methods
// ==========================================================================
function updateCharCounters() {
  document.querySelectorAll('.char-counter[data-target]').forEach(counter => {
    const targetId = counter.getAttribute('data-target');
    const limit = parseInt(counter.getAttribute('data-limit'), 10);
    const input = document.getElementById(targetId);
    if (!input) return;
    const len = input.value.length;
    counter.textContent = `${len}/${limit}`;
    counter.classList.remove('counter-warn', 'counter-danger');
    if (len >= limit) counter.classList.add('counter-danger');
    else if (len >= limit * 0.85) counter.classList.add('counter-warn');
  });
  document.querySelectorAll('.embed-field-item').forEach(item => {
    const nameInput = item.querySelector('.field-name-input');
    const valInput = item.querySelector('.field-value-input');
    const counters = item.querySelectorAll('.char-counter');
    if (nameInput && counters[0]) {
      const len = nameInput.value.length;
      counters[0].textContent = `${len}/256`;
      counters[0].classList.remove('counter-warn', 'counter-danger');
      if (len >= 256) counters[0].classList.add('counter-danger');
      else if (len >= 218) counters[0].classList.add('counter-warn');
    }
    if (valInput && counters[1]) {
      const len = valInput.value.length;
      counters[1].textContent = `${len}/1024`;
      counters[1].classList.remove('counter-warn', 'counter-danger');
      if (len >= 1024) counters[1].classList.add('counter-danger');
      else if (len >= 870) counters[1].classList.add('counter-warn');
    }
  });
  const fieldCounter = document.getElementById('embed-field-counter');
  if (fieldCounter) {
    const count = document.querySelectorAll('.embed-field-item').length;
    fieldCounter.textContent = `${count}/25`;
    fieldCounter.classList.remove('counter-warn', 'counter-danger');
    if (count >= 25) fieldCounter.classList.add('counter-danger');
    else if (count >= 20) fieldCounter.classList.add('counter-warn');
  }
}

function renderMarkdown(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code class="discord-inline-code">$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/__(.+?)__/g, '<u>$1</u>');
  html = html.replace(/~~(.+?)~~/g, '<del>$1</del>');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="discord-link">$1</a>');
  html = html.replace(/\n/g, '<br>');
  return html;
}

function getEmbedFields() {
  const fields = [];
  const fieldItems = document.querySelectorAll('.embed-field-item');
  fieldItems.forEach(item => {
    const name = item.querySelector('.field-name-input').value.trim();
    const val = item.querySelector('.field-value-input').value.trim();
    const inline = item.querySelector('.field-inline-checkbox').checked;
    if (name && val) {
      fields.push({ name, value: val, inline });
    }
  });
  return fields;
}

function addEmbedField() {
  addEmbedFieldWithData('', '', true);
  updateEmbedPreview();
}

function addEmbedFieldWithData(name, value, inline) {
  const container = document.getElementById('embed-fields-container');
  if (!container) return;
  
  const fieldItem = document.createElement('div');
  fieldItem.className = 'embed-field-item glass-inner p-3 mb-2';
  fieldItem.innerHTML = `
    <div class="grid-2-col">
      <div class="input-group">
        <label>Field Name: <span class="char-counter" data-limit="256">0/256</span></label>
        <input type="text" class="field-name-input" placeholder="e.g. Field Title" value="${escapeHtml(name)}" maxlength="256">
      </div>
      <div class="input-group">
        <label>Field Value: <span class="char-counter" data-limit="1024">0/1024</span></label>
        <input type="text" class="field-value-input" placeholder="e.g. Field Content" value="${escapeHtml(value)}" maxlength="1024">
      </div>
    </div>
    <div class="flex-between mt-2">
      <div style="display: flex; gap: 6px;">
        <label class="toggle-group font-size-08" style="display:inline-flex; align-items:center; gap:8px; margin-right: 15px;">
          <input type="checkbox" class="field-inline-checkbox" ${inline ? 'checked' : ''}>
          <span>Inline Field</span>
        </label>
        <button type="button" class="btn btn-secondary btn-small btn-field-move-up" title="Move Up" style="padding: 2px 6px;">
          <i class="fa-solid fa-chevron-up"></i>
        </button>
        <button type="button" class="btn btn-secondary btn-small btn-field-move-down" title="Move Down" style="padding: 2px 6px;">
          <i class="fa-solid fa-chevron-down"></i>
        </button>
      </div>
      <button type="button" class="btn btn-secondary btn-small text-danger btn-remove-field">
        <i class="fa-solid fa-trash-can"></i> Remove
      </button>
    </div>
  `;
  
  fieldItem.querySelectorAll('input').forEach(input => {
    input.addEventListener('input', updateEmbedPreview);
  });
  
  fieldItem.querySelector('.btn-field-move-up').addEventListener('click', () => {
    const prev = fieldItem.previousElementSibling;
    if (prev && prev.classList.contains('embed-field-item')) {
      container.insertBefore(fieldItem, prev);
      updateEmbedPreview();
    }
  });
  
  fieldItem.querySelector('.btn-field-move-down').addEventListener('click', () => {
    const next = fieldItem.nextElementSibling;
    if (next && next.classList.contains('embed-field-item')) {
      container.insertBefore(next, fieldItem);
      updateEmbedPreview();
    }
  });
  
  fieldItem.querySelector('.btn-remove-field').addEventListener('click', () => {
    fieldItem.remove();
    updateEmbedPreview();
  });
  
  container.appendChild(fieldItem);
}

function updateEmbedPreview() {
  const plainText = document.getElementById('embed-plain-text')?.value || '';
  const authorName = document.getElementById('embed-author-name')?.value || '';
  const authorIcon = document.getElementById('embed-author-icon')?.value || '';
  const title = document.getElementById('embed-title')?.value || '';
  const desc = document.getElementById('embed-description-text')?.value || '';
  
  const hexInput = document.getElementById('embed-color-hex');
  if (hexInput && hexInput.value && !hexInput.value.startsWith('#')) {
    hexInput.value = '#' + hexInput.value;
  }
  const color = hexInput?.value || '#6366F1';
  
  const extractDirectImageUrl = (url) => {
    if (!url) return '';
    if (url.includes('google.') && url.includes('imgres')) {
      try {
        const parsedUrl = new URL(url);
        const imgUrl = parsedUrl.searchParams.get('imgurl');
        if (imgUrl) return imgUrl;
      } catch (e) {
        const match = url.match(/[?&]imgurl=([^&]+)/);
        if (match) return decodeURIComponent(match[1]);
      }
    }
    return url;
  };

  const thumbnailInput = document.getElementById('embed-thumbnail');
  if (thumbnailInput && thumbnailInput.value) {
    const cleanVal = extractDirectImageUrl(thumbnailInput.value);
    if (cleanVal !== thumbnailInput.value) {
      thumbnailInput.value = cleanVal;
    }
  }
  const imageInput = document.getElementById('embed-image');
  if (imageInput && imageInput.value) {
    const cleanVal = extractDirectImageUrl(imageInput.value);
    if (cleanVal !== imageInput.value) {
      imageInput.value = cleanVal;
    }
  }

  const thumbnail = thumbnailInput?.value || '';
  const image = imageInput?.value || '';
  const footerText = document.getElementById('embed-footer-text')?.value || '';
  const footerIcon = document.getElementById('embed-footer-icon')?.value || '';
  const includeTimestamp = document.getElementById('embed-timestamp')?.checked;
  
  updateCharCounters();
  
  const simPlainText = document.getElementById('sim-plain-text');
  if (simPlainText) {
    simPlainText.textContent = plainText;
    if (plainText) simPlainText.classList.remove('hidden');
    else simPlainText.classList.add('hidden');
  }
  
  const pEmbed = document.getElementById('preview-builder-embed');
  if (pEmbed) {
    try {
      pEmbed.style.borderLeftColor = color;
    } catch(e) {}
  }
  
  const pAuthor = document.getElementById('preview-embed-author');
  const pAuthorIcon = document.getElementById('preview-embed-author-icon');
  const pAuthorName = document.getElementById('preview-embed-author-name');
  if (pAuthor && pAuthorIcon && pAuthorName) {
    if (authorName) {
      pAuthor.classList.remove('hidden');
      pAuthorName.textContent = authorName;
      if (authorIcon) {
        pAuthorIcon.src = authorIcon;
        pAuthorIcon.classList.remove('hidden');
      } else {
        pAuthorIcon.classList.add('hidden');
      }
    } else {
      pAuthor.classList.add('hidden');
    }
  }
  
  const pTitle = document.getElementById('preview-embed-title-text');
  if (pTitle) {
    if (title) {
      pTitle.textContent = title;
      pTitle.classList.remove('hidden');
    } else {
      pTitle.classList.add('hidden');
    }
  }
  
  const pDesc = document.getElementById('preview-embed-description');
  if (pDesc) {
    if (desc) {
      pDesc.innerHTML = renderMarkdown(desc);
      pDesc.classList.remove('hidden');
    } else {
      pDesc.classList.add('hidden');
    }
  }
  
  const pThumbnail = document.getElementById('preview-embed-thumbnail-img');
  if (pThumbnail) {
    if (thumbnail) {
      pThumbnail.src = thumbnail;
      pThumbnail.classList.remove('hidden');
    } else {
      pThumbnail.classList.add('hidden');
    }
  }
  
  const pImage = document.getElementById('preview-embed-large-img');
  if (pImage) {
    if (image) {
      pImage.src = image;
      pImage.classList.remove('hidden');
    } else {
      pImage.classList.add('hidden');
    }
  }
  
  const pFooterContainer = document.getElementById('preview-embed-footer-container');
  const pFooterIcon = document.getElementById('preview-embed-footer-icon-img');
  const pFooterText = document.getElementById('preview-embed-footer-text-span');
  const pFooterTime = document.getElementById('preview-embed-footer-timestamp');
  if (pFooterContainer && pFooterIcon && pFooterText && pFooterTime) {
    if (footerText || includeTimestamp) {
      pFooterContainer.classList.remove('hidden');
      pFooterText.textContent = footerText;
      if (footerIcon) {
        pFooterIcon.src = footerIcon;
        pFooterIcon.classList.remove('hidden');
      } else {
        pFooterIcon.classList.add('hidden');
      }
      if (includeTimestamp) {
        pFooterTime.textContent = (footerText ? " • " : "") + "Today at 12:00 PM";
      } else {
        pFooterTime.textContent = "";
      }
    } else {
      pFooterContainer.classList.add('hidden');
    }
  }
  
  const pFields = document.getElementById('preview-embed-fields');
  if (pFields) {
    pFields.innerHTML = '';
    const fields = getEmbedFields();
    if (fields.length > 0) {
      pFields.classList.remove('hidden');
      fields.forEach(field => {
        const fDiv = document.createElement('div');
        fDiv.className = 'discord-embed-field';
        if (field.inline) {
          fDiv.classList.add('discord-embed-field-inline');
        }
        fDiv.innerHTML = `
          <div class="discord-embed-field-name">${renderMarkdown(field.name)}</div>
          <div class="discord-embed-field-value">${renderMarkdown(field.value)}</div>
        `;
        pFields.appendChild(fDiv);
      });
    } else {
      pFields.classList.add('hidden');
    }
  }
  
  saveEmbedBuilderState();
}

function compileEmbedJSON() {
  const authorName = document.getElementById('embed-author-name')?.value || '';
  const authorIcon = document.getElementById('embed-author-icon')?.value || '';
  const title = document.getElementById('embed-title')?.value || '';
  const desc = document.getElementById('embed-description-text')?.value || '';
  const color = document.getElementById('embed-color-hex')?.value || '#6366F1';
  const thumbnail = document.getElementById('embed-thumbnail')?.value || '';
  const image = document.getElementById('embed-image')?.value || '';
  const footerText = document.getElementById('embed-footer-text')?.value || '';
  const footerIcon = document.getElementById('embed-footer-icon')?.value || '';
  const includeTimestamp = document.getElementById('embed-timestamp')?.checked;
  
  const helperNormalizeUrl = (url) => {
    if (!url) return '';
    url = url.trim();
    if (url.startsWith('data:')) {
      return url;
    }
    if (url.includes('google.') && url.includes('imgres')) {
      try {
        const parsedUrl = new URL(url);
        const imgUrl = parsedUrl.searchParams.get('imgurl');
        if (imgUrl) {
          url = imgUrl;
        }
      } catch (e) {
        const match = url.match(/[?&]imgurl=([^&]+)/);
        if (match) {
          url = decodeURIComponent(match[1]);
        }
      }
    }
    if (url.startsWith('/')) {
      return window.location.origin + url;
    }
    if (!/^[a-zA-Z]+:\/\//.test(url)) {
      return 'https://' + url;
    }
    return url;
  };

  const embed = {};
  
  if (title) embed.title = title;
  if (desc) embed.description = desc;
  if (color) {
    try {
      embed.color = parseInt(color.replace("#", ""), 16);
    } catch(e) {}
  }
  
  if (authorName) {
    embed.author = { name: authorName };
    const normalizedAuthorIcon = helperNormalizeUrl(authorIcon);
    if (normalizedAuthorIcon) embed.author.icon_url = normalizedAuthorIcon;
  }
  
  const normalizedThumbnail = helperNormalizeUrl(thumbnail);
  if (normalizedThumbnail) {
    embed.thumbnail = { url: normalizedThumbnail };
  }
  
  const normalizedImage = helperNormalizeUrl(image);
  if (normalizedImage) {
    embed.image = { url: normalizedImage };
  }
  
  if (footerText) {
    embed.footer = { text: footerText };
    const normalizedFooterIcon = helperNormalizeUrl(footerIcon);
    if (normalizedFooterIcon) embed.footer.icon_url = normalizedFooterIcon;
  }
  
  if (includeTimestamp) {
    embed.timestamp = new Date().toISOString();
  }
  
  const fields = getEmbedFields();
  if (fields.length > 0) {
    embed.fields = fields;
  }
  
  return embed;
}

function importEmbedJSON() {
  const jsonStr = prompt("Paste your Discord embed JSON structure here:\n(Example: { \"title\": \"My Embed\", \"description\": \"Hello\" })");
  if (!jsonStr) return;
  try {
    const data = JSON.parse(jsonStr);
    
    const container = document.getElementById('embed-fields-container');
    if (container) container.innerHTML = '';
    
    document.getElementById('embed-title').value = data.title || '';
    document.getElementById('embed-description-text').value = data.description || '';
    
    if (data.color) {
      let hexColor = "";
      if (typeof data.color === 'number') {
        hexColor = "#" + data.color.toString(16).padStart(6, '0');
      } else {
        hexColor = String(data.color);
      }
      document.getElementById('embed-color-hex').value = hexColor;
      document.getElementById('embed-color-picker').value = hexColor;
    }
    
    if (data.author) {
      document.getElementById('embed-author-name').value = data.author.name || '';
      document.getElementById('embed-author-icon').value = data.author.icon_url || '';
    } else {
      document.getElementById('embed-author-name').value = '';
      document.getElementById('embed-author-icon').value = '';
    }
    
    document.getElementById('embed-thumbnail').value = data.thumbnail?.url || '';
    document.getElementById('embed-image').value = data.image?.url || '';
    
    if (data.footer) {
      document.getElementById('embed-footer-text').value = data.footer.text || '';
      document.getElementById('embed-footer-icon').value = data.footer.icon_url || '';
    } else {
      document.getElementById('embed-footer-text').value = '';
      document.getElementById('embed-footer-icon').value = '';
    }
    
    document.getElementById('embed-timestamp').checked = !!data.timestamp;
    
    if (data.fields && Array.isArray(data.fields)) {
      data.fields.forEach(field => {
        addEmbedFieldWithData(field.name, field.value, field.inline !== false);
      });
    }
    
    updateEmbedPreview();
    showToast('Embed JSON imported successfully!', 'success');
  } catch (err) {
    showToast('Invalid JSON structure. Import failed.', 'error');
  }
}

function exportEmbedJSON() {
  const embed = compileEmbedJSON();
  const jsonStr = JSON.stringify(embed, null, 2);
  
  navigator.clipboard.writeText(jsonStr).then(() => {
    showToast('Embed JSON copied to clipboard!', 'success');
  }).catch(() => {
    alert(jsonStr);
  });
}

async function populateEmbedTargetChannels(guildId) {
  const select = document.getElementById('embed-target-channel');
  const bulkContainer = document.getElementById('embed-bulk-channels');
  if (!select || !guildId) return;
  try {
    const res = await fetch(`/api/guilds/${guildId}/channels`);
    if (!res.ok) return;
    const channels = await res.json();
    
    select.innerHTML = '<option value="">Select channel...</option>';
    channels.forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.textContent = `#${ch.name}`;
      select.appendChild(opt);
    });
    
    if (bulkContainer) {
      bulkContainer.innerHTML = '';
      channels.forEach(ch => {
        if (ch.type !== 0) return;
        const label = document.createElement('label');
        label.className = 'toggle-group font-size-08';
        label.style.cssText = 'display:inline-flex; align-items:center; gap:6px; margin-right: 12px; margin-bottom: 4px;';
        label.innerHTML = `<input type="checkbox" class="bulk-channel-cb" value="${ch.id}"> <span>#${ch.name}</span>`;
        bulkContainer.appendChild(label);
      });
    }
  } catch (err) {
    console.error('Error fetching embed target channels:', err);
  }
}

async function submitEmbedBuilder(e) {
  e.preventDefault();
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  
  const channelId = document.getElementById('embed-target-channel').value;
  const plainText = document.getElementById('embed-plain-text').value.trim();
  const dmUserId = document.getElementById('embed-dm-user')?.value.trim();
  const editMessageId = document.getElementById('embed-edit-message')?.value.trim();
  
  if (!channelId && !dmUserId) {
    showToast('Please select a destination channel or enter a user ID for DM.', 'warning');
    return;
  }
  
  const isScheduled = document.getElementById('embed-schedule-toggle')?.checked;
  let scheduledAt = null;
  if (isScheduled) {
    const timeStr = document.getElementById('embed-schedule-time')?.value;
    if (!timeStr) {
      showToast('Please select a schedule time.', 'warning');
      return;
    }
    scheduledAt = new Date(timeStr).toISOString();
    if (new Date(scheduledAt) <= new Date()) {
      showToast('Schedule time must be in the future.', 'warning');
      return;
    }
  }
  
  embedTabs[activeEmbedTabIndex] = collectCurrentEmbedState();
  const embeds = [];
  for (let i = 0; i < embedTabs.length; i++) {
    const savedState = embedTabs[i];
    const prevIndex = activeEmbedTabIndex;
    activeEmbedTabIndex = i;
    loadEmbedStateIntoForm(savedState);
    const compiled = compileEmbedJSON();
    activeEmbedTabIndex = prevIndex;
    loadEmbedStateIntoForm(embedTabs[prevIndex]);
    const hasContent = compiled.title || compiled.description || (compiled.fields && compiled.fields.length > 0) || 
                       (compiled.author && compiled.author.name) || (compiled.image && compiled.image.url) || 
                       (compiled.thumbnail && compiled.thumbnail.url) || (compiled.footer && compiled.footer.text);
    if (hasContent) embeds.push(compiled);
  }
  
  if (embeds.length === 0) {
    showToast('Embed must contain at least a title, description, fields, author, footer, or a valid HTTP/HTTPS image URL.', 'warning');
    return;
  }
  
  const addReactions = document.getElementById('embed-add-reactions')?.checked || false;

  try {
    if (isScheduled) {
      showToast('Scheduling embed...', 'info');
      const res = await fetch(`/api/guilds/${activeGuildId}/embeds/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel_id: channelId,
          content: plainText || null,
          embeds: embeds,
          scheduled_at: scheduledAt,
          dm_user_id: dmUserId || null,
          add_reactions: addReactions
        })
      });
      if (res.ok) {
        showToast('Embed scheduled successfully!', 'success');
      } else {
        const err = await res.json();
        showToast(err.detail || 'Failed to schedule embed.', 'error');
      }
    } else {
      const bulkCbs = document.querySelectorAll('.bulk-channel-cb:checked');
      const bulkChannelIds = Array.from(bulkCbs).map(cb => cb.value);
      const allChannelIds = channelId ? [channelId, ...bulkChannelIds.filter(id => id !== channelId)] : bulkChannelIds;
      
      if (allChannelIds.length === 0 && !dmUserId) {
        showToast('No channels selected and no DM user specified.', 'warning');
        return;
      }
      
      let successCount = 0;
      let failCount = 0;
      let totalSends = 0;
      
      // Send DM if dmUserId is specified
      if (dmUserId) {
        totalSends++;
        try {
          const res = await fetch(`/api/guilds/${activeGuildId}/embeds/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              dm_user_id: dmUserId,
              content: plainText || null,
              embeds: embeds,
              add_reactions: addReactions
            })
          });
          if (res.ok) successCount++;
          else failCount++;
        } catch(e) {
          failCount++;
        }
      }
      
      // Send to channels
      for (const chId of allChannelIds) {
        totalSends++;
        try {
          const res = await fetch(`/api/guilds/${activeGuildId}/embeds/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              channel_id: chId,
              content: plainText || null,
              embeds: embeds,
              edit_message_id: editMessageId || null,
              add_reactions: addReactions
            })
          });
          if (res.ok) successCount++;
          else failCount++;
        } catch(e) {
          failCount++;
        }
      }
      
      if (totalSends === 1) {
        if (successCount > 0) showToast(`${embeds.length} embed(s) sent successfully!`, 'success');
        else showToast('Failed to send embed.', 'error');
      } else {
        showToast(`Sent ${successCount}/${totalSends} messages successfully. ${failCount > 0 ? failCount + ' failed.' : ''}`, successCount > 0 ? 'success' : 'error');
      }
    }
  } catch (err) {
    showToast('Network error.', 'error');
  }
}

async function saveEmbedDraft() {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  const name = prompt('Enter a name for this draft:');
  if (!name || !name.trim()) return;
  
  embedTabs[activeEmbedTabIndex] = collectCurrentEmbedState();
  const embeds = [];
  for (let i = 0; i < embedTabs.length; i++) {
    const savedState = embedTabs[i];
    const prevIndex = activeEmbedTabIndex;
    activeEmbedTabIndex = i;
    loadEmbedStateIntoForm(savedState);
    const compiled = compileEmbedJSON();
    activeEmbedTabIndex = prevIndex;
    loadEmbedStateIntoForm(embedTabs[prevIndex]);
    if (compiled.title || compiled.description || (compiled.fields && compiled.fields.length > 0)) {
      embeds.push(compiled);
    }
  }
  
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/embeds/drafts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), embeds })
    });
    if (res.ok) {
      showToast('Draft saved!', 'success');
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to save draft.', 'error');
    }
  } catch (err) {
    showToast('Network error.', 'error');
  }
}

async function loadEmbedDraft() {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/embeds/drafts`);
    if (!res.ok) return;
    const drafts = await res.json();
    if (Object.keys(drafts).length === 0) {
      showToast('No saved drafts found.', 'info');
      return;
    }
    const names = Object.keys(drafts);
    const choice = prompt('Saved drafts:\n' + names.map((n, i) => `${i + 1}. ${n}`).join('\n') + '\n\nEnter the number or name to load:');
    if (!choice) return;
    
    let selectedName = names[parseInt(choice, 10) - 1] || choice;
    const draft = drafts[selectedName];
    if (!draft || !draft.embeds) {
      showToast('Draft not found.', 'error');
      return;
    }
    
    while (embedTabs.length > 1) embedTabs.pop();
    embedTabs[0] = {};
    activeEmbedTabIndex = 0;
    
    for (let i = 0; i < draft.embeds.length; i++) {
      if (i === 0) {
        embedTabs[0] = draft.embeds[i];
      } else {
        embedTabs.push(draft.embeds[i]);
      }
    }
    
    loadEmbedStateIntoForm(embedTabs[0]);
    renderEmbedTabs();
    updateEmbedPreview();
    showToast(`Draft "${selectedName}" loaded!`, 'success');
  } catch (err) {
    showToast('Network error.', 'error');
  }
}

// ==========================================================================
// Music Player Methods
// ==========================================================================
async function populateMusicVoiceChannels(guildId) {
  const select = document.getElementById('music-voice-select');
  if (!select || !guildId) return;
  try {
    const res = await fetch(`/api/guilds/${guildId}/voice-channels`);
    if (!res.ok) return;
    const channels = await res.json();
    
    select.innerHTML = '<option value="">Choose voice channel...</option>';
    channels.forEach(ch => {
      if (ch.type === 'voice') {
        const opt = document.createElement('option');
        opt.value = ch.id;
        opt.textContent = ch.name;
        select.appendChild(opt);
      }
    });
  } catch (err) {
    console.error('Error fetching voice channels:', err);
  }
}

async function fetchMusicStatus() {
  if (!activeGuildId || !isAuthenticated) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/music/status`);
    if (!res.ok) return;
    const status = await res.json();
    
    const toggleBtn = document.getElementById('btn-music-toggle');
    if (toggleBtn) {
      if (status.is_playing) {
        toggleBtn.innerHTML = '<i class="fa-solid fa-pause"></i>';
        document.getElementById('music-eq-waves')?.classList.remove('hidden');
      } else {
        toggleBtn.innerHTML = '<i class="fa-solid fa-play"></i>';
        document.getElementById('music-eq-waves')?.classList.add('hidden');
      }
    }
    
    const trackTitle = document.getElementById('music-track-title');
    const trackThumbnail = document.getElementById('music-track-thumbnail');
    if (trackTitle && trackThumbnail) {
      if (status.current_song) {
        trackTitle.textContent = status.current_song.title;
        document.getElementById('music-track-requester').textContent = "Duration: " + formatDuration(status.current_song.duration);
        if (status.current_song.thumbnail) {
          trackThumbnail.src = status.current_song.thumbnail;
        } else {
          trackThumbnail.src = "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?q=80&w=200&auto=format&fit=crop";
        }
      } else {
        trackTitle.textContent = "No Audio Playing";
        document.getElementById('music-track-requester').textContent = "Select a song below to start streaming.";
        trackThumbnail.src = "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?q=80&w=200&auto=format&fit=crop";
      }
    }
    
    const volSlider = document.getElementById('music-volume-slider');
    const volLabel = document.getElementById('music-volume-label');
    if (volSlider && volLabel) {
      const volPct = Math.round(status.volume * 100);
      volSlider.value = volPct;
      volLabel.textContent = `${volPct}%`;
    }
    
    renderMusicQueue(status.queue);
  } catch (err) {
    console.error('Error fetching music status:', err);
  }
}

function formatDuration(sec) {
  if (!sec) return "0:00";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function renderMusicQueue(queue) {
  const tbody = document.getElementById('music-queue-list-body');
  const empty = document.getElementById('music-queue-empty');
  const stats = document.getElementById('music-queue-stats');
  if (!tbody || !empty) return;
  
  tbody.innerHTML = '';
  if (!queue || queue.length === 0) {
    empty.classList.remove('hidden');
    if (stats) stats.textContent = '0 Songs in queue';
    return;
  }
  
  empty.classList.add('hidden');
  if (stats) stats.textContent = `${queue.length} Songs in queue`;
  
  queue.forEach((song, index) => {
    const tr = document.createElement('tr');
    
    const tdIndex = document.createElement('td');
    tdIndex.textContent = index + 1;
    
    const tdTitle = document.createElement('td');
    tdTitle.textContent = song.title;
    tdTitle.title = song.title;
    
    const tdDuration = document.createElement('td');
    tdDuration.textContent = formatDuration(song.duration);
    
    const tdActions = document.createElement('td');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-secondary btn-small text-danger btn-delete-queue-item';
    btn.innerHTML = '<i class="fa-solid fa-trash"></i>';
    btn.addEventListener('click', () => deleteMusicQueueItem(index));
    tdActions.appendChild(btn);
    
    tr.appendChild(tdIndex);
    tr.appendChild(tdTitle);
    tr.appendChild(tdDuration);
    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
}

async function playMusicTrack(query) {
  if (!activeGuildId) {
    showToast('Please select a server first.', 'warning');
    return;
  }
  try {
    showToast(`Searching/Queuing track: "${query}"...`, 'info');
    const res = await fetch(`/api/guilds/${activeGuildId}/music/play`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    if (res.ok) {
      const data = await res.json();
      showToast(`Added to queue: "${data.song.title}"`, 'success');
      document.getElementById('music-search-query').value = '';
      fetchMusicStatus();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to play track. Ensure bot is in voice channel.', 'error');
    }
  } catch (err) {
    showToast('Network error playing track.', 'error');
  }
}

async function toggleMusic() {
  if (!activeGuildId) return;
  const isPlaying = !document.getElementById('music-eq-waves').classList.contains('hidden');
  const endpoint = isPlaying ? 'pause' : 'resume';
  
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/music/${endpoint}`, { method: 'POST' });
    if (res.ok) {
      showToast(isPlaying ? 'Paused playback.' : 'Resumed playback.', 'info');
      fetchMusicStatus();
    } else {
      showToast('Cannot toggle music playback.', 'warning');
    }
  } catch (err) {
    console.error('Error toggling music:', err);
  }
}

async function stopMusic() {
  if (!activeGuildId) return;
  const check = confirm('Stop playback and clear the queue?');
  if (!check) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/music/stop`, { method: 'POST' });
    if (res.ok) {
      showToast('Music player stopped & queue cleared.', 'warning');
      fetchMusicStatus();
    }
  } catch (err) {
    console.error(err);
  }
}

async function skipMusic() {
  if (!activeGuildId) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/music/skip`, { method: 'POST' });
    if (res.ok) {
      showToast('Skipped current song.', 'info');
      fetchMusicStatus();
    }
  } catch (err) {
    console.error(err);
  }
}

async function setMusicVolume(vol) {
  if (!activeGuildId) return;
  try {
    await fetch(`/api/guilds/${activeGuildId}/music/volume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume: vol })
    });
  } catch (err) {
    console.error(err);
  }
}

async function joinMusicVoiceChannel(channelId) {
  if (!activeGuildId) return;
  try {
    showToast('Connecting bot to voice channel...', 'info');
    const res = await fetch(`/api/guilds/${activeGuildId}/voice/join/${channelId}`, { method: 'POST' });
    if (res.ok) {
      showToast('Successfully joined voice channel!', 'success');
      fetchMusicStatus();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to join voice channel.', 'error');
    }
  } catch (err) {
    showToast('Network error joining voice channel.', 'error');
  }
}

async function shuffleMusicQueue() {
  if (!activeGuildId) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/music/queue/shuffle`, { method: 'POST' });
    if (res.ok) {
      showToast('Queue shuffled.', 'success');
      fetchMusicStatus();
    } else {
      showToast('Queue is too small to shuffle.', 'warning');
    }
  } catch (err) {
    console.error(err);
  }
}

async function deleteMusicQueueItem(index) {
  if (!activeGuildId) return;
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/music/queue/${index}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Removed song from queue.', 'info');
      fetchMusicStatus();
    }
  } catch (err) {
    console.error(err);
  }
}

// ==========================================================================
// Scheduled Messages Methods
// ==========================================================================
async function populateSchedulerChannels(guildId) {
  const select = document.getElementById('scheduler-channel');
  if (!select || !guildId) return;
  try {
    const res = await fetch(`/api/guilds/${guildId}/channels`);
    if (!res.ok) return;
    const channels = await res.json();
    
    select.innerHTML = '<option value="">Select channel...</option>';
    channels.forEach(ch => {
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.textContent = `#${ch.name}`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Error fetching scheduler channels:', err);
  }
}

async function fetchScheduledMessages() {
  const tbody = document.getElementById('scheduler-list-body');
  const empty = document.getElementById('scheduler-empty');
  if (!tbody || !empty) return;
  
  try {
    const res = await fetch('/api/scheduled-messages');
    if (!res.ok) return;
    const allMessages = await res.json();
    
    const messages = allMessages.filter(m => String(m.guild_id) === String(activeGuildId));
    
    tbody.innerHTML = '';
    if (messages.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    
    messages.forEach(msg => {
      const tr = document.createElement('tr');
      
      const tdChannel = document.createElement('td');
      tdChannel.textContent = `Channel ID ${msg.channel_id}`;
      
      const chSelect = document.getElementById('scheduler-channel');
      if (chSelect) {
        for (let i = 0; i < chSelect.options.length; i++) {
          if (chSelect.options[i].value === msg.channel_id) {
            tdChannel.textContent = chSelect.options[i].text;
            break;
          }
        }
      }
      
      const tdType = document.createElement('td');
      if (msg.schedule_type === 'once') {
        const dateStr = msg.datetime ? new Date(msg.datetime).toLocaleString() : 'N/A';
        tdType.innerHTML = `<span class="tag tag-pink">ONCE</span><div class="mt-1 font-size-08 text-sub">${dateStr}</div>`;
      } else {
        tdType.innerHTML = `<span class="tag tag-pink" style="background-color:rgba(16,185,129,0.12); color:var(--success); border-color:rgba(16,185,129,0.2);">RECURRING</span><div class="mt-1 font-size-08 text-sub">Every ${msg.interval_value} ${msg.interval_type}</div>`;
      }
      
      const tdStatus = document.createElement('td');
      const switchLabel = document.createElement('label');
      switchLabel.className = 'switch';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = msg.enabled !== false;
      input.addEventListener('change', (e) => toggleScheduledMessage(msg.id, e.target.checked));
      const slider = document.createElement('span');
      slider.className = 'slider round';
      switchLabel.appendChild(input);
      switchLabel.appendChild(slider);
      tdStatus.appendChild(switchLabel);
      
      const tdActions = document.createElement('td');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-small text-danger';
      btn.innerHTML = '<i class="fa-solid fa-trash"></i>';
      btn.addEventListener('click', () => deleteScheduledMessage(msg.id));
      tdActions.appendChild(btn);
      
      tr.appendChild(tdChannel);
      tr.appendChild(tdType);
      tr.appendChild(tdStatus);
      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error fetching scheduled messages:', err);
  }
}

async function submitScheduledMessage(e) {
  e.preventDefault();
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  
  const channelId = document.getElementById('scheduler-channel').value;
  const content = document.getElementById('scheduler-content').value.trim();
  const scheduleType = document.getElementById('scheduler-type').value;
  const datetime = document.getElementById('scheduler-datetime').value;
  const intervalType = document.getElementById('scheduler-interval-type').value;
  const intervalVal = parseInt(document.getElementById('scheduler-interval-val').value, 10);
  
  if (!channelId) {
    showToast('Destination channel is required.', 'warning');
    return;
  }
  if (!content) {
    showToast('Message content is required.', 'warning');
    return;
  }
  
  if (scheduleType === 'once' && !datetime) {
    showToast('Please select a date and time.', 'warning');
    return;
  }
  
  const payload = {
    guild_id: activeGuildId,
    channel_id: channelId,
    content,
    schedule_type: scheduleType,
    enabled: true
  };
  
  if (scheduleType === 'once') {
    payload.datetime = new Date(datetime).toISOString();
  } else {
    payload.interval_type = intervalType;
    payload.interval_value = intervalVal;
    payload.next_run = new Date().toISOString();
  }
  
  try {
    showToast('Deploying scheduled message...', 'info');
    const res = await fetch('/api/scheduled-messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      showToast('Scheduled message created successfully!', 'success');
      document.getElementById('scheduler-content').value = '';
      document.getElementById('scheduler-datetime').value = '';
      fetchScheduledMessages();
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to create scheduled message.', 'error');
    }
  } catch (err) {
    showToast('Network error saving scheduled message.', 'error');
  }
}

async function toggleScheduledMessage(id, enabled) {
  try {
    const res = await fetch(`/api/scheduled-messages/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(enabled)
    });
    if (res.ok) {
      showToast(enabled ? 'Scheduled message enabled.' : 'Scheduled message disabled.', 'success');
    } else {
      showToast('Failed to toggle scheduled message.', 'error');
      fetchScheduledMessages();
    }
  } catch (err) {
    showToast('Network error toggling scheduled message.', 'error');
    fetchScheduledMessages();
  }
}

async function deleteScheduledMessage(id) {
  const check = confirm('Are you sure you want to delete this scheduled message?');
  if (!check) return;
  try {
    const res = await fetch(`/api/scheduled-messages/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Scheduled message deleted.', 'success');
      fetchScheduledMessages();
    } else {
      showToast('Failed to delete scheduled message.', 'error');
    }
  } catch (err) {
    showToast('Network error deleting scheduled message.', 'error');
  }
}

// ==========================================================================
// Leveling & XP System Methods
// ==========================================================================
async function populateLevelingChannelsAndRoles(guildId) {
  const selectCh = document.getElementById('leveling-announce-channel');
  const selectR = document.getElementById('builder-lvl-role');
  if (!guildId) return;
  
  try {
    const chRes = await fetch(`/api/guilds/${guildId}/channels`);
    if (chRes.ok) {
      const channels = await chRes.json();
      if (selectCh) {
        selectCh.innerHTML = '<option value="">Post in same channel...</option>';
        channels.forEach(ch => {
          const opt = document.createElement('option');
          opt.value = ch.id;
          opt.textContent = `#${ch.name}`;
          selectCh.appendChild(opt);
        });
      }
    }
    
    const rRes = await fetch(`/api/guilds/${guildId}/roles`);
    if (rRes.ok) {
      const roles = await rRes.json();
      if (selectR) {
        selectR.innerHTML = '<option value="">Choose role...</option>';
        roles.forEach(role => {
          if (role.managed) return;
          const opt = document.createElement('option');
          opt.value = role.id;
          opt.textContent = role.name;
          selectR.appendChild(opt);
        });
      }
    }
  } catch (err) {
    console.error('Error fetching leveling setup details:', err);
  }
}

async function fetchLevelingConfig(guildId) {
  if (!guildId) return;
  try {
    const res = await fetch(`/api/guilds/${guildId}/leveling/config`);
    if (!res.ok) return;
    const config = await res.json();
    
    document.getElementById('leveling-enabled').checked = config.enabled !== false;
    document.getElementById('leveling-xp-per-msg').value = config.xp_per_message || 15;
    document.getElementById('leveling-xp-cooldown').value = config.xp_cooldown_seconds || 60;
    
    const announceCh = document.getElementById('leveling-announce-channel');
    if (announceCh) announceCh.value = config.level_up_channel || '';
    
    localLevelRoles = config.level_roles || {};
    renderLevelRolesList();
  } catch (err) {
    console.error('Error loading leveling config:', err);
  }
}

function renderLevelRolesList() {
  const tbody = document.getElementById('level-roles-list-body');
  if (!tbody) return;
  
  tbody.innerHTML = '';
  const levels = Object.keys(localLevelRoles).sort((a, b) => parseInt(a, 10) - parseInt(b, 10));
  
  if (levels.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-sub font-size-08">No level roles configured.</td></tr>';
    return;
  }
  
  levels.forEach(level => {
    const roleId = localLevelRoles[level];
    
    const tr = document.createElement('tr');
    
    const tdLvl = document.createElement('td');
    tdLvl.innerHTML = `Level <strong>${level}</strong>`;
    
    const tdRole = document.createElement('td');
    tdRole.textContent = `Role ID ${roleId}`;
    
    const roleSelect = document.getElementById('builder-lvl-role');
    if (roleSelect) {
      for (let i = 0; i < roleSelect.options.length; i++) {
        if (roleSelect.options[i].value === roleId) {
          tdRole.textContent = roleSelect.options[i].text;
          break;
        }
      }
    }
    
    const tdActions = document.createElement('td');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-secondary btn-small text-danger';
    btn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
    btn.addEventListener('click', () => removeLevelRoleMapping(level));
    tdActions.appendChild(btn);
    
    tr.appendChild(tdLvl);
    tr.appendChild(tdRole);
    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
}

function addLevelRoleMapping() {
  const lvlInput = document.getElementById('builder-lvl-target');
  const roleSelect = document.getElementById('builder-lvl-role');
  
  const level = lvlInput.value.trim();
  const roleId = roleSelect.value;
  
  if (!level || !roleId) {
    showToast('Please specify both level and role.', 'warning');
    return;
  }
  
  localLevelRoles[level] = roleId;
  renderLevelRolesList();
  
  lvlInput.value = '';
  roleSelect.value = '';
  showToast(`Mapped Level ${level} to reward role. Save to deploy.`, 'success');
}

function removeLevelRoleMapping(level) {
  delete localLevelRoles[level];
  renderLevelRolesList();
  showToast(`Removed Level ${level} reward mapping. Save to deploy.`, 'info');
}

async function submitLevelingConfig(e) {
  e.preventDefault();
  if (!activeGuildId) {
    showToast('Please select a server first.', 'warning');
    return;
  }
  
  const enabled = document.getElementById('leveling-enabled').checked;
  const xpPerMsg = parseInt(document.getElementById('leveling-xp-per-msg').value, 10);
  const cooldown = parseInt(document.getElementById('leveling-xp-cooldown').value, 10);
  const channel = document.getElementById('leveling-announce-channel').value || null;
  
  const payload = {
    enabled,
    xp_per_message: xpPerMsg,
    xp_cooldown_seconds: cooldown,
    level_up_channel: channel,
    level_roles: localLevelRoles,
    ignored_channels: currentConfig?.leveling_settings?.ignored_channels || [],
    ignored_roles: currentConfig?.leveling_settings?.ignored_roles || []
  };
  
  try {
    showToast('Saving leveling settings...', 'info');
    const res = await fetch(`/api/guilds/${activeGuildId}/leveling/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      showToast('Leveling settings successfully updated!', 'success');
      if (currentConfig) {
        currentConfig.leveling_settings = payload;
      }
    } else {
      showToast('Failed to save leveling configuration.', 'error');
    }
  } catch (err) {
    showToast('Network error saving leveling config.', 'error');
  }
}

async function resetLevelingData() {
  if (!activeGuildId) return;
  const check = confirm('⚠️ DANGER ZONE: This will completely reset all user XP, levels, and statistics for this server. This cannot be undone. Are you sure you want to proceed?');
  if (!check) return;
  
  try {
    showToast('Resetting leveling data...', 'info');
    const res = await fetch(`/api/guilds/${activeGuildId}/leveling/reset`, { method: 'POST' });
    if (res.ok) {
      showToast('Leveling and XP statistics cleared successfully.', 'warning');
      fetchLeaderboard(activeGuildId);
    } else {
      showToast('Failed to clear leveling statistics.', 'error');
    }
  } catch (err) {
    showToast('Network error during XP reset.', 'error');
  }
}

async function fetchLeaderboard(guildId) {
  const tbody = document.getElementById('level-leaderboard-list-body');
  const empty = document.getElementById('level-leaderboard-empty');
  if (!tbody || !empty) return;
  
  try {
    const res = await fetch(`/api/guilds/${guildId}/leaderboard`);
    if (!res.ok) return;
    const leaderboard = await res.json();
    
    tbody.innerHTML = '';
    if (leaderboard.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    
    leaderboard.forEach(member => {
      const tr = document.createElement('tr');
      
      const tdRank = document.createElement('td');
      tdRank.innerHTML = `<strong>#${member.rank}</strong>`;
      
      const tdUser = document.createElement('td');
      tdUser.innerHTML = `
        <div style="display:flex; align-items:center; gap:8px;">
          <img src="${member.avatar_url}" style="width:24px; height:24px; border-radius:50%;">
          <span>${escapeHtml(member.username)}</span>
        </div>
      `;
      
      const tdLvl = document.createElement('td');
      tdLvl.textContent = member.level;
      
      const tdXP = document.createElement('td');
      tdXP.textContent = member.xp;
      
      const tdMsg = document.createElement('td');
      tdMsg.textContent = member.messages;
      
      tr.appendChild(tdRank);
      tr.appendChild(tdUser);
      tr.appendChild(tdLvl);
      tr.appendChild(tdXP);
      tr.appendChild(tdMsg);
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error fetching leaderboard:', err);
  }
}

// ==========================================================================
// Auto-Responder Trigger Methods
// ==========================================================================
async function fetchAutoResponders() {
  const tbody = document.getElementById('auto-responders-list-body');
  const empty = document.getElementById('auto-responders-empty');
  if (!tbody || !empty) return;
  
  try {
    const res = await fetch('/api/auto-responders');
    if (!res.ok) return;
    const allResponders = await res.json();
    
    const responders = allResponders.filter(r => String(r.guild_id) === String(activeGuildId));
    
    tbody.innerHTML = '';
    if (responders.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    
    responders.forEach(resp => {
      const tr = document.createElement('tr');
      
      const tdRule = document.createElement('td');
      let typeBadge = '';
      if (resp.trigger_type === 'exact') typeBadge = '<span class="tag tag-pink" style="background-color:rgba(99,102,241,0.12); color:#818cf8; border-color:rgba(99,102,241,0.2);">Exact</span>';
      else if (resp.trigger_type === 'contains') typeBadge = '<span class="tag tag-pink" style="background-color:rgba(16,185,129,0.12); color:var(--success); border-color:rgba(16,185,129,0.2);">Contains</span>';
      else typeBadge = '<span class="tag tag-pink" style="background-color:rgba(236,72,153,0.12); color:var(--pink); border-color:rgba(236,72,153,0.2);">Regex</span>';
      
      tdRule.innerHTML = `${typeBadge}<div class="mt-1 font-family-mono font-size-08">"${escapeHtml(resp.trigger)}"</div>`;
      
      const tdResponse = document.createElement('td');
      tdResponse.textContent = resp.response || (resp.embed ? "[Rich Embed Card]" : "");
      tdResponse.title = tdResponse.textContent;
      
      const tdStatus = document.createElement('td');
      const switchLabel = document.createElement('label');
      switchLabel.className = 'switch';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = resp.enabled !== false;
      input.addEventListener('change', (e) => toggleAutoResponder(resp.id, e.target.checked, resp));
      const slider = document.createElement('span');
      slider.className = 'slider round';
      switchLabel.appendChild(input);
      switchLabel.appendChild(slider);
      tdStatus.appendChild(switchLabel);
      
      const tdActions = document.createElement('td');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-secondary btn-small text-danger';
      btn.innerHTML = '<i class="fa-solid fa-trash"></i>';
      btn.addEventListener('click', () => deleteAutoResponder(resp.id));
      tdActions.appendChild(btn);
      
      tr.appendChild(tdRule);
      tr.appendChild(tdResponse);
      tr.appendChild(tdStatus);
      tr.appendChild(tdActions);
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error fetching responders:', err);
  }
}

async function submitAutoResponder(e) {
  e.preventDefault();
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  
  const type = document.getElementById('auto-resp-type').value;
  const trigger = document.getElementById('auto-resp-trigger').value.trim();
  const response = document.getElementById('auto-resp-response').value.trim();
  const includeEmbed = document.getElementById('auto-resp-embed-toggle').checked;
  
  if (!trigger) {
    showToast('Trigger phrase/regex is required.', 'warning');
    return;
  }
  
  const payload = {
    guild_id: activeGuildId,
    trigger_type: type,
    trigger,
    response,
    enabled: true
  };
  
  if (includeEmbed) {
    const embedTitle = document.getElementById('auto-resp-embed-title').value.trim();
    const embedDesc = document.getElementById('auto-resp-embed-desc').value.trim();
    const embedColor = document.getElementById('auto-resp-embed-color').value;
    
    if (!embedTitle && !embedDesc) {
      showToast('Rich Embed requires at least a title or description.', 'warning');
      return;
    }
    
    payload.embed = {
      title: embedTitle || null,
      description: embedDesc || null,
      color: parseInt(embedColor.replace("#", ""), 16)
    };
  }
  
  try {
    showToast('Saving responder trigger...', 'info');
    const res = await fetch('/api/auto-responders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      showToast('Auto-responder trigger successfully registered!', 'success');
      document.getElementById('auto-resp-trigger').value = '';
      document.getElementById('auto-resp-response').value = '';
      document.getElementById('auto-resp-embed-toggle').checked = false;
      document.getElementById('auto-resp-embed-editor').classList.add('hidden');
      document.getElementById('auto-resp-embed-title').value = '';
      document.getElementById('auto-resp-embed-desc').value = '';
      fetchAutoResponders();
    } else {
      showToast('Failed to save auto-responder.', 'error');
    }
  } catch (err) {
    showToast('Network error saving responder.', 'error');
  }
}

async function toggleAutoResponder(id, enabled, data) {
  const payload = { ...data, enabled };
  try {
    const res = await fetch(`/api/auto-responders/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      showToast(enabled ? 'Responder enabled.' : 'Responder disabled.', 'success');
    } else {
      showToast('Failed to toggle responder.', 'error');
      fetchAutoResponders();
    }
  } catch (err) {
    showToast('Network error toggling responder.', 'error');
    fetchAutoResponders();
  }
}

async function deleteAutoResponder(id) {
  const check = confirm('Are you sure you want to delete this auto-responder trigger?');
  if (!check) return;
  
  try {
    const res = await fetch(`/api/auto-responders/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showToast('Auto-responder trigger deleted.', 'success');
      fetchAutoResponders();
    } else {
      showToast('Failed to delete auto-responder.', 'error');
    }
  } catch (err) {
    showToast('Network error deleting responder.', 'error');
  }
}

// ==========================================================================
// Dashboard Audit Log History Methods
// ==========================================================================
async function fetchAuditLogs() {
  const tbody = document.getElementById('audit-logs-list-body');
  const empty = document.getElementById('audit-logs-empty');
  if (!tbody || !empty) return;
  
  const category = document.getElementById('audit-log-filter').value || 'ALL';
  const scope = document.getElementById('audit-log-scope')?.value || 'GUILD';
  
  try {
    let url = `/api/audit-log?limit=100`;
    if (category && category !== 'ALL') {
      url += `&category=${category}`;
    }
    if (scope === 'GUILD' && activeGuildId) {
      url += `&guild_id=${activeGuildId}`;
    } else if (scope === 'GLOBAL') {
      url += `&guild_id=global`;
    }
    
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    
    tbody.innerHTML = '';
    if (!data.logs || data.logs.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    
    data.logs.forEach(log => {
      const tr = document.createElement('tr');
      
      const tdTime = document.createElement('td');
      tdTime.textContent = new Date(log.timestamp).toLocaleString();
      
      const tdCat = document.createElement('td');
      tdCat.innerHTML = `<span class="tag tag-pink" style="font-size:0.65rem;">${escapeHtml(log.category)}</span>`;
      
      const tdActor = document.createElement('td');
      tdActor.innerHTML = `<strong>${escapeHtml(log.actor)}</strong>`;
      
      const tdAction = document.createElement('td');
      tdAction.innerHTML = `
        <div style="font-weight:500;">${escapeHtml(log.action)}</div>
        ${log.details ? `<small class="text-muted" style="display:block; max-width:300px; white-space:normal;">${escapeHtml(log.details)}</small>` : ''}
      `;
      
      const tdTarget = document.createElement('td');
      if (log.target && log.target !== 'N/A') {
        if (log.target === 'global') {
          tdTarget.innerHTML = `<strong>Global System</strong><br><small class="text-muted" style="font-size:0.7rem;">All Servers</small>`;
        } else {
          const guildName = cachedGuildNames[log.target];
          if (guildName) {
            tdTarget.innerHTML = `<strong>${escapeHtml(guildName)}</strong><br><small class="text-muted" style="font-size:0.7rem;">${escapeHtml(log.target)}</small>`;
          } else {
            tdTarget.textContent = log.target;
          }
        }
      } else {
        tdTarget.textContent = 'N/A';
      }
      
      tr.appendChild(tdTime);
      tr.appendChild(tdCat);
      tr.appendChild(tdActor);
      tr.appendChild(tdAction);
      tr.appendChild(tdTarget);
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error fetching audit logs:', err);
  }
}

// ==========================================
// MODULE 12: GIVEAWAY SYSTEM & EMBEDS
// ==========================================

let activeGiveaways = [];
let giveawayCountdownInterval = null;

// Initialize Giveaways Event Listeners
function initGiveawaysTab() {
  const form = document.getElementById('giveaway-create-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!activeGuildId) {
        showToast('Please select a guild first.', 'error');
        return;
      }
      
      const hostInput = document.getElementById('giveaway-host');
      const payload = {
        channel_id: document.getElementById('giveaway-target-channel').value,
        prize: document.getElementById('giveaway-prize').value,
        winners_count: parseInt(document.getElementById('giveaway-winners').value, 10),
        duration: document.getElementById('giveaway-duration').value,
        host: hostInput ? hostInput.value.trim() : ''
      };
      
      try {
        showToast('Launching giveaway on Discord...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/giveaways/start`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });
        
        if (res.ok) {
          showToast('Giveaway launched successfully!', 'success');
          form.reset();
          loadGiveaways();
        } else {
          const errData = await res.json();
          showToast(errData.detail || 'Failed to start giveaway.', 'error');
        }
      } catch (err) {
        showToast('Error starting giveaway.', 'error');
      }
    });
  }

  function shouldOverwriteValue(currentVal) {
    if (!currentVal) return true;
    const val = currentVal.trim().toLowerCase();
    if (val.startsWith('http://') || val.startsWith('https://')) {
      return false;
    }
    return true;
  }

  // Setup click listeners for preset image URL badges in the Embed Builder
  document.querySelectorAll('.preset-link-thumb').forEach(badge => {
    badge.addEventListener('click', () => {
      const url = badge.getAttribute('data-url');
      const input = document.getElementById('embed-thumbnail');
      if (input && shouldOverwriteValue(input.value)) {
        input.value = url;
        input.dispatchEvent(new Event('input'));
        showToast('Thumbnail preset loaded.', 'success');
      } else {
        showToast('Preserved custom HTTP/HTTPS URL.', 'info');
      }
    });
  });

  document.querySelectorAll('.preset-link-image').forEach(badge => {
    badge.addEventListener('click', () => {
      const url = badge.getAttribute('data-url');
      const input = document.getElementById('embed-image');
      if (input && shouldOverwriteValue(input.value)) {
        input.value = url;
        input.dispatchEvent(new Event('input'));
        showToast('Large image preset loaded.', 'success');
      } else {
        showToast('Preserved custom HTTP/HTTPS URL.', 'info');
      }
    });
  });

  // Setup Embed Preset Templates Dropdown
  const embedTemplateSelect = document.getElementById('embed-template-preset');
  if (embedTemplateSelect) {
    embedTemplateSelect.addEventListener('change', () => {
      const preset = embedTemplateSelect.value;
      const deleteBtn = document.getElementById('btn-embed-delete-preset');
      if (deleteBtn) {
        deleteBtn.disabled = !preset.startsWith('custom:');
      }
      if (!preset) return;
      
      const titleInput = document.getElementById('embed-title');
      const descInput = document.getElementById('embed-description-text');
      const colorPicker = document.getElementById('embed-color-picker');
      const colorHex = document.getElementById('embed-color-hex');
      const thumbnailInput = document.getElementById('embed-thumbnail');
      const imageInput = document.getElementById('embed-image');
      const footerInput = document.getElementById('embed-footer-text');
      const footerIconInput = document.getElementById('embed-footer-icon');
      const plainTextInput = document.getElementById('embed-plain-text');
      const authorNameInput = document.getElementById('embed-author-name');
      const authorIconInput = document.getElementById('embed-author-icon');
      const timestampInput = document.getElementById('embed-timestamp');
      const addReactionsInput = document.getElementById('embed-add-reactions');
      if (addReactionsInput) addReactionsInput.checked = false;
      
      const fieldsContainer = document.getElementById('embed-fields-container');
      if (fieldsContainer) fieldsContainer.innerHTML = '';
      
      if (preset.startsWith('custom:')) {
        const name = preset.substring(7);
        const data = customPresetsMap[name];
        if (data) {
          if (titleInput) titleInput.value = data.title || '';
          if (descInput) descInput.value = data.description || '';
          if (plainTextInput) plainTextInput.value = data.plainText || '';
          if (authorNameInput) authorNameInput.value = data.authorName || '';
          if (authorIconInput) authorIconInput.value = data.authorIcon || '';
          if (colorHex) {
            colorHex.value = data.color || '#6366F1';
            if (colorPicker) colorPicker.value = colorHex.value;
          }
          if (thumbnailInput) thumbnailInput.value = data.thumbnail || '';
          if (imageInput) imageInput.value = data.image || '';
          if (footerInput) footerInput.value = data.footerText || '';
          if (footerIconInput) footerIconInput.value = data.footerIcon || '';
          if (timestampInput) timestampInput.checked = !!data.includeTimestamp;
          if (addReactionsInput) addReactionsInput.checked = !!data.addReactions;
          
          if (data.fields && Array.isArray(data.fields)) {
            data.fields.forEach(field => {
              addEmbedFieldWithData(field.name, field.value, field.inline !== false);
            });
          }
          updateEmbedPreview();
          showToast(`Custom preset "${name}" loaded successfully.`, 'success');
        }
        return;
      }
      
      if (preset === 'welcome') {
        if (titleInput) titleInput.value = '👋 Welcome to the Server!';
        if (descInput) descInput.value = 'Welcome {user}! We are thrilled to have you join our community.\n\nMake sure to head over to:\n• <#welcome> to say hello\n• <#rules> to read our community guidelines\n• <#roles> to pick your self-assignable roles!\n\nHave a wonderful time! ⚡';
        if (colorPicker) colorPicker.value = '#6366f1';
        if (colorHex) colorHex.value = '#6366F1';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '/static/bot_banner.png';
        if (footerInput) footerInput.value = 'Aegis Suite | Secure & Welcoming Server';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
      } 
      else if (preset === 'rules') {
        if (titleInput) titleInput.value = '📜 Community Rules & Regulations';
        if (descInput) descInput.value = 'Please follow these rules to ensure a fun, safe, and respectful environment for everyone.\n\n**1. Respect Everyone**\nTreat all members with respect. No harassment, sexism, racism, or hate speech will be tolerated.\n\n**2. No Spam or Self-Promotion**\nDo not spam chat channels with emojis, caps, repeated text, or unsolicited links.\n\n**3. Keep Content appropriate**\nMake sure content is posted in the relevant channels (e.g. memes in #memes).';
        if (colorPicker) colorPicker.value = '#ef4444';
        if (colorHex) colorHex.value = '#EF4444';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Moderation Team | Violations will result in warnings/kicks';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
      } 
      else if (preset === 'announcement') {
        if (titleInput) titleInput.value = '📢 SERVER ANNOUNCEMENT';
        if (descInput) descInput.value = 'Hey @everyone! We have some exciting updates coming to our server.\n\nWe are launching a new leveling system and scheduling community gaming sessions! Feel free to checkout #announcements for updates and stay tuned.';
        if (colorPicker) colorPicker.value = '#3b82f6';
        if (colorHex) colorHex.value = '#3B82F6';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '/static/bot_banner.png';
        if (footerInput) footerInput.value = 'Community Management';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '/static/bot_logo.png';
      } 
      else if (preset === 'giveaway') {
        if (titleInput) titleInput.value = '🎉 GIVEAWAY TIME 🎉';
        if (descInput) descInput.value = 'We are hosting a giveaway for our active community members!\n\nClick the button below to join the draw. Make sure to participate before the timer runs out.';
        if (colorPicker) colorPicker.value = '#10b981';
        if (colorHex) colorHex.value = '#10B981';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Giveaway Host';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
        
        addEmbedFieldPreset('🎁 Prize', 'Discord Nitro Classic (1 Month)', true);
        addEmbedFieldPreset('🏆 Winner Count', '1 Winner', true);
      } 
      else if (preset === 'support') {
        if (titleInput) titleInput.value = '🎟️ Support & Tickets Panel';
        if (descInput) descInput.value = 'Need assistance? Have a question or feedback for the staff?\n\nCreate a secure, private ticket channel where you can chat 1-on-1 with our administration team. Open a ticket using the ticketing controls below.';
        if (colorPicker) colorPicker.value = '#8b5cf6';
        if (colorHex) colorHex.value = '#8B5CF6';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Support Helpdesk';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '/static/bot_logo.png';
      }
      else if (preset === 'event') {
        if (titleInput) titleInput.value = '🎮 UPCOMING SERVER EVENT';
        if (descInput) descInput.value = 'Join us for an exciting event this weekend!\n\nWe will be hosting a community game night with prizes and giveaways. Make sure to RSVP by reacting to this message.';
        if (colorPicker) colorPicker.value = '#f59e0b';
        if (colorHex) colorHex.value = '#F59E0B';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '/static/bot_banner.png';
        if (footerInput) footerInput.value = 'Event Host | Don\'t miss out!';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '/static/bot_logo.png';
        addEmbedFieldPreset('📅 Date', 'Saturday, 8:00 PM EST', true);
        addEmbedFieldPreset('🎯 Activity', 'Among Us / Jackbox', true);
      }
      else if (preset === 'patchnotes') {
        if (titleInput) titleInput.value = '🔧 PATCH NOTES v2.1.0';
        if (descInput) descInput.value = 'We have released a major update with new features and improvements.\n\n**What\'s New:**\n• Improved auto-moderation engine\n• New embed builder with multi-embed support\n• Bug fixes and performance improvements\n\nRead the full changelog in #changelog.';
        if (colorPicker) colorPicker.value = '#06b6d4';
        if (colorHex) colorHex.value = '#06B6D4';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Aegis Suite Dev Team';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '/static/bot_logo.png';
      }
      else if (preset === 'staff') {
        if (titleInput) titleInput.value = '👋 Meet Our Staff Team';
        if (descInput) descInput.value = 'Our dedicated staff team is here to help!\n\nFeel free to reach out to any of our moderators for assistance.';
        if (colorPicker) colorPicker.value = '#ec4899';
        if (colorHex) colorHex.value = '#EC4899';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Server Management';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '/static/bot_logo.png';
        addEmbedFieldPreset('🛡️ Admin', '@Admin — Server Owner', false);
        addEmbedFieldPreset('⚡ Moderator', '@Moderator — Community Lead', false);
      }
      else if (preset === 'roles') {
        if (titleInput) titleInput.value = '🎨 Self-Assignable Roles';
        if (descInput) descInput.value = 'Choose your roles below! Click on the reactions to assign or remove roles.\n\nThese roles will give you access to specific channels and notifications.';
        if (colorPicker) colorPicker.value = '#14b8a6';
        if (colorHex) colorHex.value = '#14B8A6';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'React to assign roles';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
        addEmbedFieldPreset('🎮 Gaming', 'Access to gaming channels', true);
        addEmbedFieldPreset('🎵 Music', 'Access to music commands', true);
        addEmbedFieldPreset('📢 Announcements', 'Get notified for updates', true);
      }
      else if (preset === 'faq') {
        if (titleInput) titleInput.value = '❓ Frequently Asked Questions';
        if (descInput) descInput.value = '**Q: How do I join the server?**\nA: Click the invite link and follow the verification process.\n\n**Q: Where can I get help?**\nA: Open a ticket in #support or DM a moderator.\n\n**Q: How do I earn rewards?**\nA: Be active in chat and participate in events!';
        if (colorPicker) colorPicker.value = '#6366f1';
        if (colorHex) colorHex.value = '#6366F1';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Last updated: Today';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
      }
      else if (preset === 'poll') {
        if (addReactionsInput) addReactionsInput.checked = true;
        if (titleInput) titleInput.value = '📊 COMMUNITY POLL';
        if (descInput) descInput.value = 'We want your feedback! Vote by reacting with the corresponding emoji below.';
        if (colorPicker) colorPicker.value = '#22c55e';
        if (colorHex) colorHex.value = '#22C55E';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Poll ends in 24 hours';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
        addEmbedFieldPreset('1️⃣ Option A', 'Description of option A', false);
        addEmbedFieldPreset('2️⃣ Option B', 'Description of option B', false);
        addEmbedFieldPreset('3️⃣ Option C', 'Description of option C', false);
      }
      else if (preset === 'partner') {
        if (titleInput) titleInput.value = '🤝 SERVER PARTNERSHIP';
        if (descInput) descInput.value = 'We are excited to announce a partnership with another amazing community!\n\nCheck them out and show some love. By joining, you unlock exclusive perks in both servers.';
        if (colorPicker) colorPicker.value = '#a855f7';
        if (colorHex) colorHex.value = '#A855F7';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '/static/bot_banner.png';
        if (footerInput) footerInput.value = 'Partnership Manager';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '/static/bot_logo.png';
      }
      else if (preset === 'socials') {
        if (titleInput) titleInput.value = '🔗 Our Social Links';
        if (descInput) descInput.value = 'Stay connected with us across all platforms!';
        if (colorPicker) colorPicker.value = '#3b82f6';
        if (colorHex) colorHex.value = '#3B82F6';
        if (thumbnailInput && shouldOverwriteValue(thumbnailInput.value)) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput && shouldOverwriteValue(imageInput.value)) imageInput.value = '';
        if (footerInput) footerInput.value = 'Follow us for updates!';
        if (footerIconInput && shouldOverwriteValue(footerIconInput.value)) footerIconInput.value = '';
        addEmbedFieldPreset('🐦 Twitter', '@YourServer', true);
        addEmbedFieldPreset('📺 YouTube', 'youtube.com/YourChannel', true);
        addEmbedFieldPreset('📸 Instagram', '@YourServer', true);
        addEmbedFieldPreset('💬 TikTok', '@YourServer', true);
      }
      
      updateEmbedPreview();
      showToast('Template preset loaded successfully.', 'success');
    });
  }

  // Save Custom Preset Click Listener
  const btnSavePreset = document.getElementById('btn-embed-save-preset');
  if (btnSavePreset) {
    btnSavePreset.addEventListener('click', async () => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      const name = prompt("Enter a name for the custom embed preset:");
      if (name === null) return;
      const cleanName = name.trim();
      if (!cleanName) {
        showToast('Preset name cannot be empty.', 'warning');
        return;
      }
      
      const state = {
        plainText: document.getElementById('embed-plain-text')?.value || '',
        authorName: document.getElementById('embed-author-name')?.value || '',
        authorIcon: document.getElementById('embed-author-icon')?.value || '',
        title: document.getElementById('embed-title')?.value || '',
        description: document.getElementById('embed-description-text')?.value || '',
        color: document.getElementById('embed-color-hex')?.value || '#6366F1',
        thumbnail: document.getElementById('embed-thumbnail')?.value || '',
        image: document.getElementById('embed-image')?.value || '',
        footerText: document.getElementById('embed-footer-text')?.value || '',
        footerIcon: document.getElementById('embed-footer-icon')?.value || '',
        includeTimestamp: document.getElementById('embed-timestamp')?.checked || false,
        addReactions: document.getElementById('embed-add-reactions')?.checked || false,
        fields: getEmbedFields()
      };
      
      try {
        showToast('Saving custom preset...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/embeds/presets/${encodeURIComponent(cleanName)}`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${authToken}`
          },
          body: JSON.stringify(state)
        });
        
        if (res.ok) {
          showToast(`Custom preset "${cleanName}" saved successfully!`, 'success');
          await fetchCustomPresets(activeGuildId);
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to save custom preset.', 'error');
        }
      } catch (e) {
        showToast('Network error saving preset.', 'error');
      }
    });
  }

  // Delete Custom Preset Click Listener
  const btnDeletePreset = document.getElementById('btn-embed-delete-preset');
  if (btnDeletePreset) {
    btnDeletePreset.addEventListener('click', async () => {
      if (!activeGuildId) return;
      const select = document.getElementById('embed-template-preset');
      const preset = select.value;
      if (!preset || !preset.startsWith('custom:')) return;
      const name = preset.substring(7);
      
      const confirmDelete = confirm(`Are you sure you want to delete the custom preset "${name}"?`);
      if (!confirmDelete) return;
      
      try {
        showToast('Deleting custom preset...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/embeds/presets/${encodeURIComponent(name)}`, {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${authToken}`
          }
        });
        
        if (res.ok) {
          showToast(`Custom preset "${name}" deleted successfully!`, 'success');
          await fetchCustomPresets(activeGuildId);
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to delete custom preset.', 'error');
        }
      } catch (e) {
        showToast('Network error deleting preset.', 'error');
      }
    });
  }

  // Markdown Toolbar helper click listeners
  document.querySelectorAll('.btn-md-helper').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const prefix = btn.getAttribute('data-md');
      const suffix = btn.getAttribute('data-suffix') || '';
      const textarea = document.getElementById('embed-description-text');
      if (textarea) {
        insertAtCursor(textarea, prefix, suffix);
      }
    });
  });

  // Variable helper badges click listeners
  document.querySelectorAll('.btn-var-helper').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const variable = btn.getAttribute('data-var');
      const textarea = document.getElementById('embed-description-text');
      if (textarea) {
        insertAtCursor(textarea, variable);
      }
    });
  });
}

// Helper to append fields for presets
function addEmbedFieldPreset(name, value, inline) {
  addEmbedFieldWithData(name, value, inline);
}

// Helper to insert text at cursor position in textarea
function insertAtCursor(textarea, prefix, suffix = '') {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const text = textarea.value;
  const selected = text.substring(start, end);
  const replacement = prefix + selected + suffix;
  textarea.value = text.substring(0, start) + replacement + text.substring(end);
  textarea.focus();
  textarea.selectionStart = start + prefix.length;
  textarea.selectionEnd = start + prefix.length + selected.length;
  // trigger input event to update preview
  textarea.dispatchEvent(new Event('input'));
}

async function fetchCustomPresets(guildId) {
  const container = document.getElementById('custom-presets-group');
  const deleteBtn = document.getElementById('btn-embed-delete-preset');
  if (!container || !guildId) return;
  
  try {
    const res = await fetch(`/api/guilds/${guildId}/embeds/presets`, {
      headers: {
        'Authorization': `Bearer ${authToken}`
      }
    });
    if (!res.ok) return;
    const presets = await res.json();
    customPresetsMap = presets;
    
    container.innerHTML = '';
    
    const keys = Object.keys(presets);
    if (keys.length === 0) {
      container.innerHTML = '<option disabled>No custom presets saved</option>';
    } else {
      keys.sort().forEach(name => {
        const opt = document.createElement('option');
        opt.value = `custom:${name}`;
        opt.textContent = `⭐ ${name}`;
        container.appendChild(opt);
      });
    }
    
    document.getElementById('embed-template-preset').value = '';
    if (deleteBtn) deleteBtn.disabled = true;
  } catch (err) {
    console.error('Error fetching custom presets:', err);
  }
}

// Populate Giveaway Destination Channels Dropdown
async function populateGiveawayChannels(guildId) {
  const select = document.getElementById('giveaway-target-channel');
  if (!select) return;
  
  try {
    const res = await fetch(`/api/guilds/${guildId}/channels`);
    if (!res.ok) return;
    const channels = await res.json();
    
    select.innerHTML = '<option value="">Select channel...</option>';
    channels.forEach(ch => {
      if (ch.type === 'text') {
        const opt = document.createElement('option');
        opt.value = ch.id;
        opt.textContent = `# ${ch.name}`;
        select.appendChild(opt);
      }
    });
  } catch (err) {
    console.error('Error populating giveaway channels:', err);
  }
}

// Fetch and load giveaways status
async function loadGiveaways() {
  if (!activeGuildId || !isAuthenticated) return;
  
  try {
    const res = await fetch(`/api/guilds/${activeGuildId}/giveaways`);
    if (!res.ok) return;
    const data = await res.json();
    
    activeGiveaways = data.filter(g => !g.ended);
    const completedGiveaways = data.filter(g => g.ended);
    
    renderActiveGiveaways();
    renderGiveawayHistory(completedGiveaways);
    
    if (activeGiveaways.length > 0) {
      startGiveawaysTicker();
    } else {
      stopGiveawaysTicker();
    }
  } catch (err) {
    console.error('Error loading giveaways:', err);
  }
}

// Render active giveaways cards
function renderActiveGiveaways() {
  const container = document.getElementById('active-giveaways-container');
  const emptyState = document.getElementById('active-giveaways-empty');
  if (!container) return;
  
  container.innerHTML = '';
  
  if (activeGiveaways.length === 0) {
    if (emptyState) emptyState.classList.remove('hidden');
    return;
  }
  
  if (emptyState) emptyState.classList.add('hidden');
  
  activeGiveaways.forEach(gw => {
    const card = document.createElement('div');
    card.className = 'card glass-inner p-4 active-giveaway-card';
    card.style.border = '1px solid rgba(99, 102, 241, 0.2)';
    card.style.boxShadow = '0 0 15px rgba(99, 102, 241, 0.1)';
    card.setAttribute('data-id', gw.message_id);
    
    card.innerHTML = `
      <div class="flex-between">
        <h4 style="font-weight:700; color: #a5b4fc; font-size:1.1rem;">🎁 ${escapeHtml(gw.prize)}</h4>
        <span class="badge badge-success" style="background: rgba(16, 185, 129, 0.15); color: #34d399;">Active</span>
      </div>
      
      <div class="mt-3 font-size-0.85 text-sub">
        <p><i class="fa-solid fa-hashtag mr-1"></i> Channel: <span class="text-white">#${escapeHtml(gw.channel_id)}</span></p>
        <p><i class="fa-solid fa-users mr-1"></i> Participants: <strong class="text-primary font-size-1.1">${gw.entrants_count}</strong></p>
        <p><i class="fa-solid fa-trophy mr-1"></i> Winners: <span class="text-white">${gw.winners_count}</span></p>
      </div>
      
      <div class="mt-3 p-2 text-center glass-inner" style="border-radius: 8px; background: rgba(0,0,0,0.15);">
        <span style="font-size:0.75rem; color: var(--text-muted); display:block;">Time Remaining</span>
        <strong class="countdown-clock" data-endtime="${gw.end_time}" style="font-size:1.25rem; font-family: monospace; color: #ffd700;">--:--:--</strong>
      </div>
      
      <div class="mt-3 flex-between gap-2">
        <button type="button" class="btn btn-secondary btn-small w-100 btn-end-giveaway" data-id="${gw.message_id}">
          <i class="fa-solid fa-circle-stop mr-1"></i> End Early
        </button>
        <button type="button" class="btn btn-secondary btn-small text-danger btn-delete-giveaway" data-id="${gw.message_id}">
          <i class="fa-solid fa-trash"></i>
        </button>
      </div>
    `;
    
    container.appendChild(card);
  });
  
  container.querySelectorAll('.btn-end-giveaway').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = btn.getAttribute('data-id');
      const doubleCheck = confirm('Are you sure you want to end this giveaway early and select winners now?');
      if (!doubleCheck) return;
      
      try {
        const res = await fetch(`/api/guilds/${activeGuildId}/giveaways/${id}/end`, {
          method: 'POST'
        });
        if (res.ok) {
          showToast('Giveaway ended early!', 'success');
          loadGiveaways();
        } else {
          showToast('Failed to end giveaway.', 'error');
        }
      } catch (err) {
        showToast('Error ending giveaway.', 'error');
      }
    });
  });
  
  container.querySelectorAll('.btn-delete-giveaway').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = btn.getAttribute('data-id');
      const doubleCheck = confirm('Are you sure you want to cancel and delete this giveaway? It will NOT select winners.');
      if (!doubleCheck) return;
      
      try {
        const res = await fetch(`/api/guilds/${activeGuildId}/giveaways/${id}`, {
          method: 'DELETE'
        });
        if (res.ok) {
          showToast('Giveaway deleted.', 'success');
          loadGiveaways();
        } else {
          showToast('Failed to delete giveaway.', 'error');
        }
      } catch (err) {
        showToast('Error deleting giveaway.', 'error');
      }
    });
  });
}

// Render completed giveaways history table
function renderGiveawayHistory(history) {
  const tbody = document.getElementById('giveaway-history-list-body');
  const emptyState = document.getElementById('giveaway-history-empty');
  if (!tbody) return;
  
  tbody.innerHTML = '';
  
  if (history.length === 0) {
    if (emptyState) emptyState.classList.remove('hidden');
    return;
  }
  
  if (emptyState) emptyState.classList.add('hidden');
  
  history.forEach(gw => {
    const tr = document.createElement('tr');
    
    const tdPrize = document.createElement('td');
    tdPrize.innerHTML = `<strong>${escapeHtml(gw.prize)}</strong>`;
    
    const tdWinners = document.createElement('td');
    tdWinners.innerHTML = gw.winners.length > 0
      ? gw.winners.map(w => `<span class="tag tag-blue" style="margin-right: 4px;">@${escapeHtml(w)}</span>`).join('')
      : '<em class="text-muted">No entrants</em>';
      
    const tdEntrants = document.createElement('td');
    tdEntrants.textContent = gw.entrants_count;
    
    const tdTime = document.createElement('td');
    tdTime.textContent = new Date(gw.end_time * 1000).toLocaleString();
    
    const tdActions = document.createElement('td');
    tdActions.style.textAlign = 'right';
    tdActions.innerHTML = `
      <div style="display:flex; gap: 6px; justify-content: flex-end;">
        <button type="button" class="btn btn-secondary btn-small btn-reroll-giveaway" data-id="${gw.message_id}" ${gw.entrants_count === 0 ? 'disabled' : ''}>
          <i class="fa-solid fa-arrows-rotate mr-1"></i> Reroll
        </button>
        <button type="button" class="btn btn-secondary btn-small text-danger btn-delete-history" data-id="${gw.message_id}">
          <i class="fa-solid fa-trash"></i>
        </button>
      </div>
    `;
    
    tr.appendChild(tdPrize);
    tr.appendChild(tdWinners);
    tr.appendChild(tdEntrants);
    tr.appendChild(tdTime);
    tr.appendChild(tdActions);
    tbody.appendChild(tr);
  });
  
  tbody.querySelectorAll('.btn-reroll-giveaway').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = btn.getAttribute('data-id');
      const doubleCheck = confirm('Are you sure you want to reroll a new winner from the participants?');
      if (!doubleCheck) return;
      
      try {
        showToast('Rerolling winner...', 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/giveaways/${id}/reroll`, {
          method: 'POST'
        });
        if (res.ok) {
          showToast('Winners rerolled successfully!', 'success');
          loadGiveaways();
        } else {
          const errData = await res.json();
          showToast(errData.detail || 'Failed to reroll.', 'error');
        }
      } catch (err) {
        showToast('Error rerolling winner.', 'error');
      }
    });
  });
  
  tbody.querySelectorAll('.btn-delete-history').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const id = btn.getAttribute('data-id');
      const doubleCheck = confirm('Are you sure you want to delete this giveaway record? The message in Discord will remain but the record will be removed from dashboard.');
      if (!doubleCheck) return;
      
      try {
        const res = await fetch(`/api/guilds/${activeGuildId}/giveaways/${id}`, {
          method: 'DELETE'
        });
        if (res.ok) {
          showToast('Record deleted.', 'success');
          loadGiveaways();
        } else {
          showToast('Failed to delete record.', 'error');
        }
      } catch (err) {
        showToast('Error deleting record.', 'error');
      }
    });
  });
}

// Client-side dynamic countdown ticking
function startGiveawaysTicker() {
  if (giveawayCountdownInterval) return;
  
  giveawayCountdownInterval = setInterval(() => {
    const clocks = document.querySelectorAll('.countdown-clock');
    if (clocks.length === 0) {
      stopGiveawaysTicker();
      return;
    }
    
    clocks.forEach(clock => {
      const endTime = parseFloat(clock.getAttribute('data-endtime'));
      const now = Date.now() / 1000;
      const diff = endTime - now;
      
      if (diff <= 0) {
        clock.textContent = '00:00:00';
        clock.style.color = '#ef4444';
        return;
      }
      
      const days = Math.floor(diff / 86400);
      const hours = Math.floor((diff % 86400) / 3600);
      const minutes = Math.floor((diff % 3600) / 60);
      const seconds = Math.floor(diff % 60);
      
      let clockText = '';
      if (days > 0) clockText += `${days}d `;
      clockText += `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      clock.textContent = clockText;
    });
  }, 1000);
}

function stopGiveawaysTicker() {
  if (giveawayCountdownInterval) {
    clearInterval(giveawayCountdownInterval);
    giveawayCountdownInterval = null;
  }
}


// ==========================================================================
// Hosting Mode Selector / Badge / Settings Panel
// (Local PC vs Cloud — feature availability disclosure, admin-only switcher)
// ==========================================================================

const HOSTING_MODE_BADGE_LABELS = {
  local_pc: 'Local PC',
  cloud: 'Cloud',
  unconfigured: 'Unconfigured'
};

const HOSTING_MODE_BADGE_ICONS = {
  local_pc: 'fa-solid fa-desktop',
  cloud: 'fa-solid fa-cloud',
  unconfigured: 'fa-solid fa-circle-question'
};

const HOSTING_MODE_BADGE_ARIA = {
  local_pc: 'Local PC mode \u2014 intermittent uptime',
  cloud: 'Cloud mode \u2014 24/7 uptime',
  unconfigured: 'Hosting mode: Unconfigured'
};

const HOSTING_MODE_LABEL = {
  local_pc: 'Local PC',
  cloud: 'Cloud'
};

function _normalizeHostingModeRole(role) {
  // Treat anything other than 'admin' as tenant for badge interactivity (Req 4.5, 4.6)
  return role === 'admin' ? 'admin' : 'tenant';
}

function _hostingModeKey(mode) {
  return (mode === 'local_pc' || mode === 'cloud') ? mode : 'unconfigured';
}

function renderHostingModeBadge(mode, role) {
  let badge = document.getElementById('hosting-mode-badge');
  if (!badge) return;
  
  const key = _hostingModeKey(mode);
  const label = HOSTING_MODE_BADGE_LABELS[key];
  const iconClass = HOSTING_MODE_BADGE_ICONS[key];
  const ariaLabel = HOSTING_MODE_BADGE_ARIA[key];
  const normalizedRole = _normalizeHostingModeRole(role);
  
  // Replace <button> with <span> for tenants and vice versa as the role demands.
  // The badge MUST never be interactive for tenants (Req 4.6, Req 7.7).
  const wantTag = normalizedRole === 'admin' ? 'BUTTON' : 'SPAN';
  if (badge.tagName !== wantTag) {
    const replacement = document.createElement(wantTag === 'BUTTON' ? 'button' : 'span');
    replacement.id = 'hosting-mode-badge';
    replacement.className = badge.className;
    if (wantTag === 'BUTTON') {
      replacement.setAttribute('type', 'button');
    }
    // Move children across so the icon + text span structure is preserved
    while (badge.firstChild) {
      replacement.appendChild(badge.firstChild);
    }
    badge.parentNode.replaceChild(replacement, badge);
    badge = replacement;
  }
  
  // Visual state class — clear all variants then add the active one
  badge.classList.remove('state-local-pc', 'state-cloud', 'state-unconfigured');
  badge.classList.add(`state-${key.replace(/_/g, '-')}`);
  
  // Tooltip + accessible label (Req 4.7)
  badge.setAttribute('title', ariaLabel);
  badge.setAttribute('aria-label', ariaLabel);
  
  // Icon swap (replace inner <i>'s className)
  const iconEl = badge.querySelector('i');
  if (iconEl) {
    iconEl.className = iconClass;
  }
  
  // Text swap
  let textEl = badge.querySelector('#hosting-mode-badge-text');
  if (!textEl) {
    textEl = document.createElement('span');
    textEl.id = 'hosting-mode-badge-text';
    badge.appendChild(textEl);
  }
  textEl.textContent = label;
  
  // Wire interactivity per role
  if (normalizedRole === 'admin') {
    badge.classList.remove('read-only');
    badge.removeAttribute('tabindex');
    badge.removeAttribute('aria-disabled');
    if (badge.tagName === 'BUTTON') {
      badge.disabled = false;
    }
    // Idempotent click handler — strip any prior bound handler then bind fresh.
    // Clicking the badge re-opens the same Local PC vs Cloud chooser modal
    // the user saw on first launch, so switching is a single click.
    badge.onclick = function (e) {
      e.preventDefault();
      openHostingModeSelector();
    };
  } else {
    badge.classList.add('read-only');
    badge.setAttribute('tabindex', '-1');
    badge.setAttribute('aria-disabled', 'true');
    if (badge.tagName === 'BUTTON') {
      badge.disabled = true;
    }
    badge.onclick = null;
  }
  badge.classList.add('hidden');
}

function renderFeatureAvailabilityWarning(mode) {
  const panel = document.getElementById('feature-availability-warning');
  if (!panel) return;
  if (mode === 'local_pc') {
    panel.classList.remove('hidden');
  } else {
    panel.classList.add('hidden');
  }
}

// First-launch trigger: admin-only, opens chooser only when no value persisted (Req 1.1, 1.6, 1.7)
async function maybeShowHostingModeSelector() {
  return; // Feature is unfinished, hidden
}

function openHostingModeSelector() {
  const overlay = document.getElementById('hosting-mode-selector-overlay');
  if (!overlay) return;
  overlay.classList.remove('hidden');
  
  const cards = overlay.querySelectorAll('.option-card[data-mode]');
  const confirmBtn = document.getElementById('hosting-mode-selector-confirm');
  const errorEl = document.getElementById('hosting-mode-selector-error');
  const cancelBtn = document.getElementById('hosting-mode-selector-cancel');
  if (errorEl) {
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
  }
  
  // Pre-select the active mode so reopening the chooser shows what's
  // currently in effect. selectedMode starts as the persisted value
  // when one exists (post-first-launch reopen), or null on first launch.
  let selectedMode = (hostingMode.value === 'local_pc' || hostingMode.value === 'cloud')
    ? hostingMode.value
    : null;
  
  function _selectCard(card) {
    cards.forEach(c => {
      c.classList.remove('selected');
      c.setAttribute('aria-selected', 'false');
    });
    card.classList.add('selected');
    card.setAttribute('aria-selected', 'true');
    selectedMode = card.getAttribute('data-mode');
    if (confirmBtn) confirmBtn.disabled = false;
  }
  
  // Apply the pre-selection visually on every reopen.
  cards.forEach(card => {
    const cardMode = card.getAttribute('data-mode');
    if (cardMode === selectedMode) {
      card.classList.add('selected');
      card.setAttribute('aria-selected', 'true');
    } else {
      card.classList.remove('selected');
      card.setAttribute('aria-selected', 'false');
    }
    card.onclick = () => _selectCard(card);
    card.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        _selectCard(card);
      }
    };
    if (!card.hasAttribute('tabindex')) card.setAttribute('tabindex', '0');
    if (!card.hasAttribute('role')) card.setAttribute('role', 'radio');
  });
  
  // Show the cancel button only when a hosting mode is already configured
  // (i.e. the user is using the chooser to switch, not for first launch).
  // On first launch the chooser is mandatory and cannot be dismissed.
  if (cancelBtn) {
    if (hostingMode.value === 'local_pc' || hostingMode.value === 'cloud') {
      cancelBtn.classList.remove('hidden');
      cancelBtn.onclick = () => {
        overlay.classList.add('hidden');
      };
    } else {
      cancelBtn.classList.add('hidden');
      cancelBtn.onclick = null;
    }
  }
  
  if (confirmBtn) {
    // Enable confirm immediately when reopening with a pre-selected mode.
    confirmBtn.disabled = (selectedMode !== 'local_pc' && selectedMode !== 'cloud');
    confirmBtn.onclick = async () => {
      if (selectedMode !== 'local_pc' && selectedMode !== 'cloud') return;
      confirmBtn.disabled = true;
      try {
        const res = await fetch('/api/hosting-mode', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hosting_mode: selectedMode })
        });
        if (res.ok) {
          // Clear inline error, hide overlay, refresh badge + warning panel via the existing poller
          if (errorEl) {
            errorEl.textContent = '';
            errorEl.classList.add('hidden');
          }
          overlay.classList.add('hidden');
          checkStatus();
        } else {
          // Non-2xx — keep overlay open with inline error (Req 1.10)
          let detail = 'Failed to save hosting mode. Please try again.';
          try {
            const errBody = await res.json();
            if (errBody && errBody.detail) detail = errBody.detail;
          } catch (_) {}
          if (errorEl) {
            errorEl.textContent = detail;
            errorEl.classList.remove('hidden');
          } else {
            showToast(detail, 'error');
          }
          confirmBtn.disabled = false;
        }
      } catch (err) {
        const msg = 'Network error saving hosting mode. Please try again.';
        if (errorEl) {
          errorEl.textContent = msg;
          errorEl.classList.remove('hidden');
        } else {
          showToast(msg, 'error');
        }
        confirmBtn.disabled = false;
      }
    };
  }
  
  // The Selector must NOT be dismissable by Escape, outside-click, or back navigation
  // BEFORE first-time confirmation (Req 1.9). After a hosting mode is set,
  // the cancel button (above) provides the only dismiss path.
}

function openHostingModeSettings() {
  // Admin-only — Tenants never reach this surface (Req 7.7)
  if (localStorage.getItem('admin_role') !== 'admin') return;
  
  const panel = document.getElementById('hosting-mode-settings-panel');
  if (!panel) return;
  panel.classList.remove('hidden');
  try {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (_) {}
  
  const current = hostingMode.value;
  const currentLabel = current === 'local_pc' ? HOSTING_MODE_LABEL.local_pc
                     : current === 'cloud' ? HOSTING_MODE_LABEL.cloud
                     : 'Unconfigured';
  const currentEl = document.getElementById('hosting-mode-settings-current');
  if (currentEl) currentEl.textContent = currentLabel;
  
  const switchBtn = document.getElementById('hosting-mode-settings-switch');
  const switchLabelEl = document.getElementById('hosting-mode-settings-switch-label');
  let targetMode;
  if (current === 'local_pc') targetMode = 'cloud';
  else if (current === 'cloud') targetMode = 'local_pc';
  else targetMode = 'local_pc'; // unconfigured -> default proposal
  
  if (switchLabelEl) {
    if (current === 'local_pc' || current === 'cloud') {
      switchLabelEl.textContent = `Switch to ${HOSTING_MODE_LABEL[targetMode]}`;
    } else {
      switchLabelEl.textContent = 'Switch';
    }
  }
  
  const confirmation = document.getElementById('hosting-mode-settings-confirmation');
  const confirmBtn = document.getElementById('hosting-mode-settings-confirm');
  const cancelBtn = document.getElementById('hosting-mode-settings-cancel');
  const warningEl = document.getElementById('hosting-mode-settings-warning');
  const errorEl = document.getElementById('hosting-mode-settings-error');
  
  if (errorEl) {
    errorEl.textContent = '';
    errorEl.classList.add('hidden');
  }
  
  if (switchBtn) {
    switchBtn.onclick = () => {
      hostingMode.pendingTarget = targetMode;
      
      // Re-render the appropriate Feature_Availability_Warning content for the TARGET mode (Req 7.3)
      // The DOM content is static; reveal the canonical panel only when the target is local_pc.
      // For the in-settings preview, we mirror the same impacted/unaffected sections by toggling
      // a copy if present, otherwise reveal the existing panel as a stand-in.
      if (warningEl) {
        if (targetMode === 'local_pc') {
          warningEl.classList.remove('hidden');
        } else {
          // Switching to Cloud silences the Local-PC-only warning content (Req 3.5).
          // Render a short confirmation-of-silence message instead of the impacted list.
          warningEl.classList.remove('hidden');
        }
      }
      
      if (confirmBtn) {
        confirmBtn.textContent = `Switch to ${HOSTING_MODE_LABEL[targetMode]}`;
        confirmBtn.disabled = false;
      }
      if (confirmation) confirmation.classList.remove('hidden');
      if (errorEl) {
        errorEl.textContent = '';
        errorEl.classList.add('hidden');
      }
    };
  }
  
  if (confirmBtn) {
    confirmBtn.onclick = async () => {
      const target = hostingMode.pendingTarget;
      if (target !== 'local_pc' && target !== 'cloud') return;
      confirmBtn.disabled = true;
      try {
        const res = await fetch('/api/hosting-mode', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ hosting_mode: target })
        });
        if (res.ok) {
          if (confirmation) confirmation.classList.add('hidden');
          if (errorEl) {
            errorEl.textContent = '';
            errorEl.classList.add('hidden');
          }
          hostingMode.pendingTarget = null;
          showToast(`Hosting mode switched to ${HOSTING_MODE_LABEL[target]}.`, 'success');
          checkStatus(); // Refresh badge + warning panel
        } else {
          // Non-2xx — leave persisted state unchanged, surface inline error
          let detail = 'Failed to switch hosting mode. Please try again.';
          try {
            const errBody = await res.json();
            if (errBody && errBody.detail) detail = errBody.detail;
          } catch (_) {}
          if (errorEl) {
            errorEl.textContent = detail;
            errorEl.classList.remove('hidden');
          } else {
            showToast(detail, 'error');
          }
          confirmBtn.disabled = false;
        }
      } catch (err) {
        const msg = 'Network error switching hosting mode. Please try again.';
        if (errorEl) {
          errorEl.textContent = msg;
          errorEl.classList.remove('hidden');
        } else {
          showToast(msg, 'error');
        }
        confirmBtn.disabled = false;
      }
    };
  }
  
  if (cancelBtn) {
    cancelBtn.onclick = () => {
      // Cancel: hide confirmation, clear pending target, NO PUT call (Req 7.5)
      if (confirmation) confirmation.classList.add('hidden');
      hostingMode.pendingTarget = null;
      if (errorEl) {
        errorEl.textContent = '';
        errorEl.classList.add('hidden');
      }
    };
  }
}
