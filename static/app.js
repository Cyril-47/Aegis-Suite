// State variables
let currentBotStatus = 'stopped';
let savedClientId = '';
let activeGuildId = null;
let currentConfig = null;
let socket = null;
let localCustomCommands = {};
let rolePanelButtons = [];
let serverRoles = [];

// DOM Elements
const setupWizard = document.getElementById('setup-wizard');
const mainApp = document.getElementById('main-app');
const currentTabDesc = document.getElementById('current-tab-desc');

// Tab Descriptors
const TAB_DESCRIPTIONS = {
  'tab-overview': 'Monitor your Discord bot and manage connected servers.',
  'tab-auditor': 'Review server permissions, channels structure, and security checklist.',
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
  'tab-leveling': 'Boost chat engagement with XP rewards, ranks, and role incentives.',
  'tab-auto-responder': 'Configure custom keyword triggers and regex replies.',
  'tab-audit-log': 'Review actions and configuration changes performed on the dashboard.',
  'tab-logs': 'View real-time event logs from the bot manager and web server.'
};

// Initialize Application
let isAuthenticated = false;
let authToken = localStorage.getItem('admin_token') || '';

// Intercept fetch calls globally to inject Auth Header and handle token expiration (401)
const originalFetch = window.fetch;
window.fetch = function (url, options) {
  options = options || {};
  options.headers = options.headers || {};
  
  if (authToken) {
    options.headers['Authorization'] = `Bearer ${authToken}`;
  }
  
  if (window.BOT_API_URL && window.BOT_API_URL !== '%%BOT_API_URL%%' && typeof url === 'string' && url.startsWith('/')) {
    url = window.BOT_API_URL.replace(/\/$/, '') + url;
  }
  
  return originalFetch(url, options).then(async (response) => {
    if (response.status === 401 && !url.includes('/api/auth/')) {
      // Session expired, clear storage and show login overlay
      localStorage.removeItem('admin_token');
      authToken = '';
      isAuthenticated = false;
      showToast('Session expired. Please log in again.', 'warning');
      checkAuthentication();
    }
    return response;
  });
};

document.addEventListener('DOMContentLoaded', async () => {
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
  checkStatus();
  fetchConfig();
  fetchStats();
  
  // Refresh loop for status and stats (Tier 3.2, 3.15)
  statusInterval = setInterval(() => {
    if (document.visibilityState === 'hidden') return;
    checkStatus();
    fetchStats();
    
    // Poll music status if the music tab is active
    const activePane = document.querySelector('.tab-pane:not(.hidden)');
    if (activePane && activePane.id === 'tab-music' && activeGuildId) {
      fetchMusicStatus();
    } else if (activePane && activePane.id === 'tab-giveaways' && activeGuildId) {
      loadGiveaways();
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
      setupWizard.classList.add('hidden');
      mainApp.classList.add('hidden');
      isAuthenticated = false;
      return false;
    }
    
    if (!authToken) {
      // Show login screen
      loginOverlay.classList.remove('hidden');
      setupOverlay.classList.add('hidden');
      setupWizard.classList.add('hidden');
      mainApp.classList.add('hidden');
      isAuthenticated = false;
      
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
    if (statusCheck.status === 401) {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_role');
      localStorage.removeItem('admin_guild_id');
      authToken = '';
      loginOverlay.classList.remove('hidden');
      setupOverlay.classList.add('hidden');
      setupWizard.classList.add('hidden');
      mainApp.classList.add('hidden');
      isAuthenticated = false;
      return false;
    }
    
    try {
      const statusData = await statusCheck.json();
      if (statusData.role) {
        localStorage.setItem('admin_role', statusData.role);
      }
      if (statusData.guild_id) {
        localStorage.setItem('admin_guild_id', statusData.guild_id);
      }
    } catch (e) {
      console.error("Error parsing status JSON:", e);
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
  }
}

function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const tabPanes = document.querySelectorAll('.tab-pane');

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const targetTab = item.getAttribute('data-tab');
      
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
}

// ==========================================================================
// API Operations - Core Bot Status & Config
// ==========================================================================
async function checkStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    
    currentBotStatus = data.status;
    
    // Toggle FFmpeg warning
    const ffmpegWarning = document.getElementById('ffmpeg-warning');
    if (ffmpegWarning) {
      if (data.ffmpeg_installed === false) {
        ffmpegWarning.classList.remove('hidden');
      } else {
        ffmpegWarning.classList.add('hidden');
      }
    }
    
    // Toggle Setup Wizard or Offline Notice (Tier 5.8)
    const offlineNotice = document.getElementById('offline-notice-overlay');
    if (!data.has_token) {
      if (data.role === 'admin') {
        setupWizard.classList.remove('hidden');
        if (offlineNotice) offlineNotice.classList.add('hidden');
        mainApp.classList.add('hidden');
      } else {
        if (offlineNotice) offlineNotice.classList.remove('hidden');
        setupWizard.classList.add('hidden');
        mainApp.classList.add('hidden');
      }
      return;
    } else {
      setupWizard.classList.add('hidden');
      if (offlineNotice) offlineNotice.classList.add('hidden');
      mainApp.classList.remove('hidden');
    }
    
    // Load config if not loaded
    if (!currentConfig) {
      await fetchConfig();
    }
    
    updateBotBadge(data);
    updateOverviewCard(data);
    
    // Role-based UI filtering (Tier 5.8)
    const btnBotToggle = document.getElementById('btn-bot-toggle');
    const btnReconfigure = document.getElementById('btn-reconfigure');
    const serverSelect = document.getElementById('server-select');
    
    if (data.role === 'user') {
      if (btnBotToggle) btnBotToggle.classList.add('hidden');
      if (btnReconfigure) {
        const row = btnReconfigure.closest('.info-row');
        if (row) row.classList.add('hidden');
      }
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
    } else {
      if (btnBotToggle) btnBotToggle.classList.remove('hidden');
      if (btnReconfigure) {
        const row = btnReconfigure.closest('.info-row');
        if (row) row.classList.remove('hidden');
      }
    }
  } catch (err) {
    console.error('Error checking status:', err);
  }
}

async function fetchConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) return;
    currentConfig = await res.json();
    savedClientId = currentConfig.client_id || '';
    
    // Set invite links if client ID is set
    updateInviteLinks(savedClientId);
    
    // Populate form data
    populateWelcomeForm(currentConfig.welcome_settings);
    populateAutomodForm(currentConfig.automod_settings);
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
    botAvatar.src = 'https://discord.com/assets/c09c2a688b139c15814e578d0554c9a6.png';
  } else {
    botUsername.textContent = 'Optimizer Bot';
    botStatus.textContent = 'Offline';
    botStatus.className = 'status-offline';
    botAvatar.src = 'https://discord.com/assets/c09c2a688b139c15814e578d0554c9a6.png';
    
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
    
    // Automatically load guilds if select is empty and we are connected
    const select = document.getElementById('server-select');
    if (select.options.length <= 1) {
      refreshGuildsList();
    }
  } else {
    botOverviewAvatar.src = 'https://discord.com/assets/c09c2a688b139c15814e578d0554c9a6.png';
    botOverviewStatusText.textContent = data.status.toUpperCase();
    botOverviewStatusWrapper.classList.remove('online');
    botOverviewUsername.textContent = '-';
    botOverviewId.textContent = '-';
    botOverviewGuilds.textContent = '0';
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
// Action triggers (Start/Stop, Save Config)
// ==========================================================================
async function saveWizardCredentials() {
  const token = document.getElementById('wizard-token').value.trim();
  const clientId = document.getElementById('wizard-client-id').value.trim();
  
  if (!token || !clientId) {
    showToast('Please fill in both required fields.', 'error');
    return;
  }

  const payload = {
    bot_token: token,
    client_id: clientId,
    welcome_settings: {
      enabled: true,
      channel_name: 'welcome',
      message_title: 'Welcome to the Server, {user}!',
      message_description: "We are thrilled to have you here! Please make sure to check out the rules and have a wonderful time.",
      embed_color: '#6366F1',
      auto_assign_roles: []
    },
    automod_settings: {
      enabled: true,
      block_profanity: true,
      block_links: false,
      max_mentions: 5,
      log_channel_name: 'mod-logs',
      profanity_words: ['badword1', 'badword2']
    }
  };

  try {
    showToast('Saving configurations...', 'info');
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      showToast('Settings saved! Starting bot...', 'success');
      await startBot();
      await checkStatus();
    } else {
      showToast('Failed to save config.', 'error');
    }
  } catch (err) {
    showToast('Network error during configuration save.', 'error');
  }
}

async function startBot() {
  try {
    const res = await fetch('/api/bot/start', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'starting' || data.status === 'already_running') {
      showToast('Bot started successfully.', 'success');
    } else {
      showToast('Failed to launch bot service.', 'error');
    }
  } catch (err) {
    showToast('Error sending start command.', 'error');
  }
}

async function stopBot() {
  try {
    const res = await fetch('/api/bot/stop', { method: 'POST' });
    const data = await res.json();
    if (data.status === 'stopped' || data.status === 'already_stopped') {
      showToast('Bot stopped successfully.', 'warning');
    } else {
      showToast('Failed to stop bot service.', 'error');
    }
  } catch (err) {
    showToast('Error sending stop command.', 'error');
  }
}

// ==========================================================================
// Guilds Fetching & Selecting
// ==========================================================================
async function refreshGuildsList() {
  const select = document.getElementById('server-select');
  try {
    const res = await fetch('/api/guilds');
    if (!res.ok) return;
    
    const guilds = await res.json();
    
    // Clear and build options
    select.innerHTML = '<option value="">Select a server...</option>';
    guilds.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = `${g.name} (${g.member_count} members)`;
      select.appendChild(opt);
    });
    
    if (activeGuildId) {
      select.value = activeGuildId;
    }
    showToast('Servers list updated.', 'info');
  } catch (err) {
    console.error('Error fetching guilds:', err);
  }
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
  
  statusDiv.classList.remove('hidden');
  btn.disabled = true;
  statusText.textContent = `Applying '${selectedPreset.toUpperCase()}' layout preset...`;
  
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
    auto_assign_roles
  };
  
  try {
    const res = await fetch('/api/config', {
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
// AutoModeration Module Setup
// ==========================================================================
function populateAutomodForm(settings) {
  if (!settings) return;
  document.getElementById('automod-enabled').checked = settings.enabled;
  document.getElementById('automod-profanity').checked = settings.block_profanity;
  document.getElementById('automod-links').checked = settings.block_links;
  document.getElementById('automod-max-mentions').value = settings.max_mentions;
  document.getElementById('automod-words').value = settings.profanity_words.join(', ');
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
    profanity_words
  };
  
  try {
    const res = await fetch('/api/config', {
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
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
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

async function fetchTemplates() {
  const tbody = document.getElementById('templates-list-body');
  const empty = document.getElementById('templates-empty');
  if (!tbody || !empty) return;
  
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
      
      const btnApply = document.createElement('button');
      btnApply.type = 'button';
      btnApply.className = 'btn btn-primary btn-small mr-2 btn-apply-custom-template';
      btnApply.setAttribute('data-template', tpl.name);
      btnApply.innerHTML = '<i class="fa-solid fa-play"></i> Apply';
      btnApply.addEventListener('click', () => applyCustomTemplate(tpl.name));
      tdActions.appendChild(btnApply);
      
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

async function applyCustomTemplate(name) {
  if (!activeGuildId) {
    showToast('Please select a Discord server first.', 'warning');
    return;
  }
  const confirmApply = confirm(`⚠️ WARNING: Applying custom template "${name}" will structure your server, which will archive your current channels. Continue?`);
  if (!confirmApply) return;
  
  try {
    showToast(`Applying template "${name}"...`, 'info');
    const res = await fetch('/api/templates/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        guild_id: activeGuildId,
        name: name
      })
    });
    
    if (res.ok) {
      showToast('Template applied successfully!', 'success');
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
  } catch (err) {
    console.error('Error fetching guild channels:', err);
  }
}

// ==========================================================================
// Event Listeners & Helpers
// ==========================================================================
function setupEventListeners() {
  // Wizard Submit
  document.getElementById('btn-save-wizard').addEventListener('click', saveWizardCredentials);
  
  // Refresh Guilds
  document.getElementById('btn-refresh-guilds').addEventListener('click', refreshGuildsList);
  
  // Server Selection
  document.getElementById('server-select').addEventListener('change', (e) => {
    handleServerSelection(e.target.value);
  });
  
  // Start/Stop Toggle Button (badge)
  document.getElementById('btn-bot-toggle').addEventListener('click', async () => {
    if (currentBotStatus === 'running') {
      showToast('Stopping bot...', 'info');
      await stopBot();
    } else {
      showToast('Starting bot...', 'info');
      await startBot();
    }
    checkStatus();
  });
  
  // Reconfigure settings button
  document.getElementById('btn-reconfigure').addEventListener('click', () => {
    const reset = confirm("Are you sure you want to change credentials? This will log out the bot.");
    if (reset) {
      // Clear token in configuration to force setup wizard
      if (currentConfig) {
        currentConfig.bot_token = '';
        fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(currentConfig)
        }).then(() => checkStatus());
      }
    }
  });
  
  // Scan Button
  document.getElementById('btn-run-audit').addEventListener('click', runServerAudit);
  
  // Optimizer Preset Cards Click
  setupPresetSelector();
  
  // Optimizer Run
  document.getElementById('btn-execute-optimize').addEventListener('click', runOptimization);
  
  // Form Saves
  document.getElementById('welcome-form').addEventListener('submit', saveWelcomeSettings);
  document.getElementById('automod-form').addEventListener('submit', saveAutomodSettings);
  
  // Sync Welcome Embed Previews dynamically
  document.getElementById('welcome-title').addEventListener('input', syncWelcomePreview);
  document.getElementById('welcome-description').addEventListener('input', syncWelcomePreview);
  
  const hexInput = document.getElementById('welcome-color-hex');
  const pickerInput = document.getElementById('welcome-color-picker');
  
  hexInput.addEventListener('input', (e) => {
    pickerInput.value = e.target.value;
    syncWelcomePreview();
  });
  
  pickerInput.addEventListener('input', (e) => {
    hexInput.value = e.target.value.toUpperCase();
    syncWelcomePreview();
  });
  
  // Clear Logs console
  document.getElementById('btn-clear-logs').addEventListener('click', () => {
    document.getElementById('log-terminal').innerHTML = '';
  });

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
        const res = await fetch('/api/commands', {
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
        const res = await fetch('/api/config', {
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

  // Logout Button
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) {
    btnLogout.addEventListener('click', async () => {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch (err) {}
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

  // Built-in Presets Apply Buttons
  document.querySelectorAll('.btn-apply-builtin').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      if (!activeGuildId) {
        showToast('Please select a Discord server first.', 'warning');
        return;
      }
      const preset = e.currentTarget.getAttribute('data-preset');
      const confirmApply = confirm(`⚠️ WARNING: Applying the "${preset}" layout preset will archive your current channels. Continue?`);
      if (!confirmApply) return;
      
      try {
        showToast(`Applying "${preset}" preset...`, 'info');
        const res = await fetch(`/api/guilds/${activeGuildId}/optimize`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            preset: preset,
            handling: 'archive'
          })
        });
        
        if (res.ok) {
          showToast(`Preset layout "${preset}" applied successfully!`, 'success');
          setTimeout(() => {
            handleServerSelection(activeGuildId);
            runServerAudit();
          }, 2000);
        } else {
          const err = await res.json();
          showToast(err.detail || 'Failed to apply preset layout.', 'error');
        }
      } catch (err) {
        showToast('Network error applying preset.', 'error');
      }
    });
  });

  // --- Embed Builder Pro Listeners ---
  const embedForm = document.getElementById('embed-builder-form');
  if (embedForm) {
    embedForm.addEventListener('submit', submitEmbedBuilder);
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
        <label>Field Name:</label>
        <input type="text" class="field-name-input" placeholder="e.g. Field Title" value="${escapeHtml(name)}">
      </div>
      <div class="input-group">
        <label>Field Value:</label>
        <input type="text" class="field-value-input" placeholder="e.g. Field Content" value="${escapeHtml(value)}">
      </div>
    </div>
    <div class="flex-between mt-2">
      <label class="toggle-group font-size-08" style="display:inline-flex; align-items:center; gap:8px;">
        <input type="checkbox" class="field-inline-checkbox" ${inline ? 'checked' : ''}>
        <span>Inline Field</span>
      </label>
      <button type="button" class="btn btn-secondary btn-small text-danger btn-remove-field">
        <i class="fa-solid fa-trash-can"></i> Remove
      </button>
    </div>
  `;
  
  fieldItem.querySelectorAll('input').forEach(input => {
    input.addEventListener('input', updateEmbedPreview);
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
  const color = document.getElementById('embed-color-hex')?.value || '#6366F1';
  const thumbnail = document.getElementById('embed-thumbnail')?.value || '';
  const image = document.getElementById('embed-image')?.value || '';
  const footerText = document.getElementById('embed-footer-text')?.value || '';
  const footerIcon = document.getElementById('embed-footer-icon')?.value || '';
  const includeTimestamp = document.getElementById('embed-timestamp')?.checked;
  
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
      pDesc.textContent = desc;
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
          <div class="discord-embed-field-name">${escapeHtml(field.name)}</div>
          <div class="discord-embed-field-value">${escapeHtml(field.value)}</div>
        `;
        pFields.appendChild(fDiv);
      });
    } else {
      pFields.classList.add('hidden');
    }
  }
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
    if (authorIcon) embed.author.icon_url = authorIcon;
  }
  
  if (thumbnail) {
    embed.thumbnail = { url: thumbnail };
  }
  
  if (image) {
    embed.image = { url: image };
  }
  
  if (footerText) {
    embed.footer = { text: footerText };
    if (footerIcon) embed.footer.icon_url = footerIcon;
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
  
  if (!channelId) {
    showToast('Please select a destination channel.', 'warning');
    return;
  }
  
  const embed = compileEmbedJSON();
  if (Object.keys(embed).length === 0) {
    showToast('Embed is empty. Add a title, description, or author.', 'warning');
    return;
  }
  
  try {
    showToast('Sending embed to Discord...', 'info');
    const res = await fetch(`/api/guilds/${activeGuildId}/embeds/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel_id: channelId,
        content: plainText || null,
        embed: embed
      })
    });
    
    if (res.ok) {
      showToast('Embed message sent successfully!', 'success');
    } else {
      const err = await res.json();
      showToast(err.detail || 'Failed to send embed.', 'error');
    }
  } catch (err) {
    showToast('Network error sending embed.', 'error');
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
      const opt = document.createElement('option');
      opt.value = ch.id;
      opt.textContent = ch.name;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error('Error fetching voice channels:', err);
  }
}

async function fetchMusicStatus() {
  if (!activeGuildId) return;
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
    payload.datetime = datetime;
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
  
  try {
    let url = `/api/audit-log?limit=100`;
    if (category && category !== 'ALL') {
      url += `&category=${category}`;
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
      tdTarget.textContent = log.target || 'N/A';
      
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
      
      const payload = {
        channel_id: document.getElementById('giveaway-target-channel').value,
        prize: document.getElementById('giveaway-prize').value,
        winners_count: parseInt(document.getElementById('giveaway-winners').value, 10),
        duration: document.getElementById('giveaway-duration').value
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

  // Setup click listeners for preset image URL badges in the Embed Builder
  document.querySelectorAll('.preset-link-thumb').forEach(badge => {
    badge.addEventListener('click', () => {
      const url = badge.getAttribute('data-url');
      const input = document.getElementById('embed-thumbnail');
      if (input) {
        input.value = url;
        input.dispatchEvent(new Event('input'));
        showToast('Thumbnail preset loaded.', 'success');
      }
    });
  });

  document.querySelectorAll('.preset-link-image').forEach(badge => {
    badge.addEventListener('click', () => {
      const url = badge.getAttribute('data-url');
      const input = document.getElementById('embed-image');
      if (input) {
        input.value = url;
        input.dispatchEvent(new Event('input'));
        showToast('Large image preset loaded.', 'success');
      }
    });
  });

  // Setup Embed Preset Templates Dropdown
  const embedTemplateSelect = document.getElementById('embed-template-preset');
  if (embedTemplateSelect) {
    embedTemplateSelect.addEventListener('change', () => {
      const preset = embedTemplateSelect.value;
      if (!preset) return;
      
      const titleInput = document.getElementById('embed-title');
      const descInput = document.getElementById('embed-description-text');
      const colorPicker = document.getElementById('embed-color-picker');
      const colorHex = document.getElementById('embed-color-hex');
      const thumbnailInput = document.getElementById('embed-thumbnail');
      const imageInput = document.getElementById('embed-image');
      const footerInput = document.getElementById('embed-footer-text');
      const footerIconInput = document.getElementById('embed-footer-icon');
      
      const fieldsContainer = document.getElementById('embed-fields-container');
      if (fieldsContainer) fieldsContainer.innerHTML = '';
      
      if (preset === 'welcome') {
        if (titleInput) titleInput.value = '👋 Welcome to the Server!';
        if (descInput) descInput.value = 'Welcome {user}! We are thrilled to have you join our community.\n\nMake sure to head over to:\n• <#welcome> to say hello\n• <#rules> to read our community guidelines\n• <#roles> to pick your self-assignable roles!\n\nHave a wonderful time! ⚡';
        if (colorPicker) colorPicker.value = '#6366f1';
        if (colorHex) colorHex.value = '#6366F1';
        if (thumbnailInput) thumbnailInput.value = '/static/bot_logo.png';
        if (imageInput) imageInput.value = '/static/bot_banner.png';
        if (footerInput) footerInput.value = 'Aegis Suite | Secure & Welcoming Server';
        if (footerIconInput) footerIconInput.value = '';
      } 
      else if (preset === 'rules') {
        if (titleInput) titleInput.value = '📜 Community Rules & Regulations';
        if (descInput) descInput.value = 'Please follow these rules to ensure a fun, safe, and respectful environment for everyone.\n\n**1. Respect Everyone**\nTreat all members with respect. No harassment, sexism, racism, or hate speech will be tolerated.\n\n**2. No Spam or Self-Promotion**\nDo not spam chat channels with emojis, caps, repeated text, or unsolicited links.\n\n**3. Keep Content appropriate**\nMake sure content is posted in the relevant channels (e.g. memes in #memes).';
        if (colorPicker) colorPicker.value = '#ef4444';
        if (colorHex) colorHex.value = '#EF4444';
        if (thumbnailInput) thumbnailInput.value = 'https://i.imgur.com/V9l5Nn0.png';
        if (imageInput) imageInput.value = '';
        if (footerInput) footerInput.value = 'Moderation Team | Violations will result in warnings/kicks';
        if (footerIconInput) footerIconInput.value = '';
      } 
      else if (preset === 'announcement') {
        if (titleInput) titleInput.value = '📢 SERVER ANNOUNCEMENT';
        if (descInput) descInput.value = 'Hey @everyone! We have some exciting updates coming to our server.\n\nWe are launching a new leveling system and scheduling community gaming sessions! Feel free to checkout #announcements for updates and stay tuned.';
        if (colorPicker) colorPicker.value = '#3b82f6';
        if (colorHex) colorHex.value = '#3B82F6';
        if (thumbnailInput) thumbnailInput.value = '';
        if (imageInput) imageInput.value = '/static/bot_banner.png';
        if (footerInput) footerInput.value = 'Community Management';
        if (footerIconInput) footerIconInput.value = '/static/bot_logo.png';
      } 
      else if (preset === 'giveaway') {
        if (titleInput) titleInput.value = '🎉 GIVEAWAY TIME 🎉';
        if (descInput) descInput.value = 'We are hosting a giveaway for our active community members!\n\nClick the button below to join the draw. Make sure to participate before the timer runs out.';
        if (colorPicker) colorPicker.value = '#10b981';
        if (colorHex) colorHex.value = '#10B981';
        if (thumbnailInput) thumbnailInput.value = 'https://i.imgur.com/NlVd7s7.png';
        if (imageInput) imageInput.value = '';
        if (footerInput) footerInput.value = 'Giveaway Host';
        if (footerIconInput) footerIconInput.value = '';
        
        addEmbedFieldPreset('🎁 Prize', 'Discord Nitro Classic (1 Month)', true);
        addEmbedFieldPreset('🏆 Winner Count', '1 Winner', true);
      } 
      else if (preset === 'support') {
        if (titleInput) titleInput.value = '🎟️ Support & Tickets Panel';
        if (descInput) descInput.value = 'Need assistance? Have a question or feedback for the staff?\n\nCreate a secure, private ticket channel where you can chat 1-on-1 with our administration team. Open a ticket using the ticketing controls below.';
        if (colorPicker) colorPicker.value = '#8b5cf6';
        if (colorHex) colorHex.value = '#8B5CF6';
        if (thumbnailInput) thumbnailInput.value = '';
        if (imageInput) imageInput.value = '';
        if (footerInput) footerInput.value = 'Support Helpdesk';
        if (footerIconInput) footerIconInput.value = '/static/bot_logo.png';
      }
      
      embedTemplateSelect.value = '';
      updateEmbedPreview();
      showToast('Template preset loaded successfully.', 'success');
    });
  }
}

// Helper to append fields for presets
function addEmbedFieldPreset(name, value, inline) {
  const container = document.getElementById('embed-fields-container');
  if (!container) return;
  
  const div = document.createElement('div');
  div.className = 'embed-field-item glass-inner p-3 mb-2';
  div.style.position = 'relative';
  
  div.innerHTML = `
    <div class="grid-2-col">
      <div class="input-group">
        <label>Field Name:</label>
        <input type="text" class="field-name-input" value="${escapeHtml(name)}" placeholder="Field Name">
      </div>
      <div class="input-group">
        <label>Field Value:</label>
        <input type="text" class="field-value-input" value="${escapeHtml(value)}" placeholder="Field Value">
      </div>
    </div>
    <div class="mt-2 flex-between">
      <label class="flex-align" style="font-size:0.8rem; cursor:pointer;">
        <input type="checkbox" class="field-inline-checkbox" ${inline ? 'checked' : ''} style="margin-right:5px;"> Inline field
      </label>
      <button type="button" class="btn btn-secondary btn-xs btn-remove-embed-field text-danger">Remove</button>
    </div>
  `;
  
  div.querySelector('.btn-remove-embed-field').addEventListener('click', () => {
    div.remove();
    updateEmbedPreview();
  });
  
  div.querySelectorAll('input').forEach(input => {
    input.addEventListener('input', updateEmbedPreview);
  });
  
  container.appendChild(div);
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
