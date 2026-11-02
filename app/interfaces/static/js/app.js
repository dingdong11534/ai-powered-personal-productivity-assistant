/**
 * Personal Productivity Assistant - Single Page Application Core
 */

// Global State
const state = {
  currentTab: 'dashboard',
  currentUser: null,
  activePomodoro: null,
  pomodoroInterval: null,
  isEndingPomodoro: false,
  allProjects: [],
  allTags: [],
  allTasks: [],
  responseTimes: [],
  chatTimerInterval: null,
  pendingDestructiveAction: false,
  aiStatus: null
};

// UI Initialization
document.addEventListener('DOMContentLoaded', async () => {
  initNavigation();
  initTheme();
  initSearch();
  initUserDropdownListener();

  // Initialize UI views and dropdowns
  initDropdownData();
  loadSettingsView();
  loadCurrentView();
  loadAIMode();
  checkActivePomodoroSession();

  // Check or prompt user authentication
  await initAuth();

  // Heartbeat for online status & token usage sync
  startHeartbeat();

  // Visibility and unload tracking for instant online/offline state
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      sendHeartbeat();
      if (state.currentTab !== 'assistant') {
        loadCurrentView();
      }
    } else {
      sendOfflineBeacon();
    }
  });

  window.addEventListener('beforeunload', () => {
    sendOfflineBeacon();
  });
  window.addEventListener('pagehide', () => {
    sendOfflineBeacon();
  });

  // Auto-refresh when tab/window regains focus to eliminate stale data
  window.addEventListener('focus', () => {
    if (state.currentTab !== 'assistant') {
      loadCurrentView();
    }
    initDropdownData();
    loadAIMode();
    checkActivePomodoroSession();
    sendHeartbeat();
  });
});

// AI Mode & Multi-Provider Management
function getProviderDisplayName(providerKey, modelName) {
  const p = (providerKey || '').toLowerCase();
  let name = 'AI';
  if (p === 'openai' || p === 'gpt' || p === 'chatgpt') name = 'ChatGPT';
  else if (p === 'gemini' || p === 'google') name = 'Gemini';
  else if (p === 'groq') name = 'Groq';
  else if (p === 'grok' || p === 'xai') name = 'Grok';
  else if (p === 'offline' || p === 'ollama') name = 'Offline Ollama';
  else name = providerKey || 'AI';
  return modelName ? `${name} (${modelName})` : name;
}

async function loadAIMode() {
  try {
    let status = await api('/ai/status');
    const stickyProvider = localStorage.getItem('sticky_ai_provider');
    const stickyModel = localStorage.getItem('sticky_ai_model');
    if (stickyProvider && (status.active_provider !== stickyProvider || (stickyModel && status.active_model !== stickyModel))) {
      try {
        const synced = await api('/ai/config', {
          method: 'POST',
          body: JSON.stringify({
            provider: stickyProvider,
            model: stickyModel || null,
            persist: true
          })
        });
        status = synced;
      } catch (syncErr) {
        console.warn('Could not restore sticky AI model:', syncErr);
      }
    }
    updateAIModeUI(status);
  } catch (e) {
    console.warn('Could not load AI status:', e);
  }
}

function updateAIModeUI(status) {
  if (!status) return;
  state.aiStatus = status;
  const isOnline = status.mode === 'online';
  const providerKey = status.active_provider || (isOnline ? 'groq' : 'ollama');
  const modelName = status.active_model || '';
  const labelText = isOnline
    ? `🌐 ${getProviderDisplayName(providerKey, modelName)}`
    : `💻 Offline (${modelName || 'Ollama'})`;
  const btnClass = isOnline ? 'ai-mode-switch-btn mode-online' : 'ai-mode-switch-btn mode-offline';
  const tooltip = `Active Model: ${getProviderDisplayName(providerKey, modelName)}. Click to change in Settings.`;

  // Topbar button (if present)
  const globalBtn = document.getElementById('global-ai-mode-btn');
  const globalText = document.getElementById('global-ai-mode-text');
  if (globalBtn && globalText) {
    globalBtn.className = btnClass;
    globalBtn.title = tooltip;
    globalText.innerText = labelText;
  }

  // Assistant header badge
  const asstBtn = document.getElementById('assistant-ai-mode-btn');
  const asstText = document.getElementById('assistant-ai-mode-text');
  if (asstBtn && asstText) {
    asstBtn.className = btnClass;
    asstBtn.title = tooltip;
    asstText.innerText = labelText;
  }

  // Settings view badge
  const settingsBadge = document.getElementById('ai-active-status-badge');
  const settingsText = document.getElementById('ai-active-status-text');
  if (settingsBadge && settingsText) {
    settingsBadge.className = btnClass;
    settingsText.innerText = labelText;
  }
}

async function loadAISettings() {
  try {
    const status = await api('/ai/status');
    updateAIModeUI(status);
    const select = document.getElementById('setting-ai-provider');
    if (!select) return;

    let activeKey = status.active_provider || 'groq';
    if (activeKey === 'ollama') activeKey = 'offline';

    if (select.querySelector(`option[value="${activeKey}"]`)) {
      select.value = activeKey;
    }
    renderAIProviderDetails(select.value);
  } catch (err) {
    console.warn('Could not load AI settings:', err);
  }
}

function renderAIProviderDetails(providerKey) {
  const status = state.aiStatus;
  const providers = status?.providers || {};
  const info = providers[providerKey] || {
    models: [],
    default_model: '',
    base_url: '',
    key_hint: '',
    has_key: false,
    key_preview: '',
    is_local: providerKey === 'offline'
  };

  const presetSelect = document.getElementById('setting-ai-model-preset');
  const customInput = document.getElementById('setting-ai-model-custom');
  const descSpan = document.getElementById('setting-ai-model-desc');

  if (presetSelect) {
    presetSelect.innerHTML = '';
    const models = info.models && info.models.length ? info.models : [info.default_model || 'default'];
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      presetSelect.appendChild(opt);
    });

    const configuredModel = info.configured_model || info.default_model;
    if (models.includes(configuredModel)) {
      presetSelect.value = configuredModel;
      if (customInput) customInput.style.display = 'none';
      presetSelect.style.display = 'block';
    } else if (configuredModel) {
      if (customInput) {
        customInput.value = configuredModel;
        customInput.style.display = 'block';
        presetSelect.style.display = 'none';
      }
    }
  }

  if (descSpan) {
    if (providerKey === 'openai') {
      descSpan.innerText = 'Recommended: gpt-4o-mini (fast & economical) or gpt-4o (high intelligence).';
    } else if (providerKey === 'gemini') {
      descSpan.innerText = 'Recommended: gemini-1.5-flash (ultra fast, large context) or gemini-2.0-flash.';
    } else if (providerKey === 'groq') {
      descSpan.innerText = 'Recommended: llama-3.3-70b-versatile for high-speed cloud inference.';
    } else if (providerKey === 'grok') {
      descSpan.innerText = 'Recommended: grok-beta or grok-2-latest from xAI.';
    } else if (providerKey === 'offline') {
      descSpan.innerText = 'Recommended: qwen2.5:1.5b or llama3.2 running on your local Ollama server.';
    }
  }

  const baseUrlInput = document.getElementById('setting-ai-base-url');
  if (baseUrlInput) {
    baseUrlInput.value = info.base_url || '';
  }

  const keyGroup = document.getElementById('setting-ai-key-group');
  const keyInput = document.getElementById('setting-ai-api-key');
  const keyStatus = document.getElementById('setting-ai-key-status');
  const keyHint = document.getElementById('setting-ai-key-hint');
  const revertBtn = document.getElementById('btn-revert-key');

  if (info.is_local || providerKey === 'offline') {
    if (keyGroup) keyGroup.style.display = 'none';
  } else {
    if (keyGroup) keyGroup.style.display = 'block';
    if (keyInput) {
      keyInput.value = '';
      if (info.has_custom_key) {
        keyInput.placeholder = `Personal key active (${info.custom_key_preview || '****'}). Enter new key or reset.`;
      } else if (info.has_key) {
        keyInput.placeholder = `Default system key active (${info.key_preview || '****'}). Paste personal key to override...`;
      } else {
        keyInput.placeholder = 'Paste your API key here...';
      }
    }
    if (revertBtn) {
      revertBtn.style.display = info.has_custom_key ? 'inline-flex' : 'none';
    }
    if (keyStatus) {
      if (info.has_custom_key) {
        keyStatus.innerHTML = `<span style="color:var(--success-color, #10b981); font-weight:600;">✓ Personal Key Active (${info.custom_key_preview})</span>`;
      } else if (info.has_key) {
        keyStatus.innerHTML = `<span style="color:#60a5fa; font-weight:600;">✓ System Default Key Active (${info.key_preview})</span>`;
      } else {
        keyStatus.innerHTML = `<span style="color:var(--warning-color, #f59e0b);">⚠️ No key configured</span>`;
      }
    }
    if (keyHint) {
      keyHint.innerText = info.has_custom_key
        ? `You are using a custom key override for ${info.label || providerKey}. Click '↺ Use Default' to restore the shared system key.`
        : (info.key_hint || `Default system key is active. You may optionally enter a custom ${info.label || providerKey} key.`);
    }
  }
}

function onAIProviderSelect(providerKey) {
  renderAIProviderDetails(providerKey);
  const resultDiv = document.getElementById('ai-test-result-indicator');
  if (resultDiv) resultDiv.style.display = 'none';
}

function onAIModelPresetChange(modelVal) {
  // Update description if needed
}

function toggleCustomModelInput() {
  const presetSelect = document.getElementById('setting-ai-model-preset');
  const customInput = document.getElementById('setting-ai-model-custom');
  if (!presetSelect || !customInput) return;
  if (customInput.style.display === 'none') {
    customInput.style.display = 'block';
    presetSelect.style.display = 'none';
    customInput.value = presetSelect.value;
    customInput.focus();
  } else {
    customInput.style.display = 'none';
    presetSelect.style.display = 'block';
  }
}

function toggleAIKeyVisibility() {
  const keyInput = document.getElementById('setting-ai-api-key');
  const btn = document.getElementById('btn-toggle-key-visibility');
  if (!keyInput) return;
  if (keyInput.type === 'password') {
    keyInput.type = 'text';
    if (btn) btn.innerText = '🙈';
  } else {
    keyInput.type = 'password';
    if (btn) btn.innerText = '👁️';
  }
}

async function revertToDefaultKey() {
  const providerSelect = document.getElementById('setting-ai-provider');
  if (!providerSelect) return;
  const provider = providerSelect.value;
  try {
    const res = await api('/ai/user-keys', {
      method: 'POST',
      body: JSON.stringify({
        provider: provider,
        api_key: null
      })
    });
    if (res.ai_status) {
      updateAIModeUI(res.ai_status);
      renderAIProviderDetails(provider);
    }
    showToast(`Reverted ${provider} to system default key!`, 'success');
  } catch (err) {
    showToast(`Failed to reset key: ${err.message || err}`, 'error');
  }
}

async function saveAISettings() {
  const providerSelect = document.getElementById('setting-ai-provider');
  if (!providerSelect) return;
  const provider = providerSelect.value;

  const customInput = document.getElementById('setting-ai-model-custom');
  const presetSelect = document.getElementById('setting-ai-model-preset');
  let model = presetSelect ? presetSelect.value : null;
  if (customInput && customInput.style.display !== 'none' && customInput.value.trim()) {
    model = customInput.value.trim();
  }

  const keyInput = document.getElementById('setting-ai-api-key');
  const apiKey = keyInput ? keyInput.value.trim() : null;

  const urlInput = document.getElementById('setting-ai-base-url');
  const baseUrl = urlInput ? urlInput.value.trim() : null;

  const saveBtn = document.getElementById('btn-save-ai-settings');
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span>⏳</span> Saving...';
  }

  try {
    if (apiKey) {
      await api('/ai/user-keys', {
        method: 'POST',
        body: JSON.stringify({
          provider: provider,
          api_key: apiKey
        })
      });
    }

    const updated = await api('/ai/config', {
      method: 'POST',
      body: JSON.stringify({
        provider: provider,
        model: model || null,
        api_key: apiKey || null,
        base_url: baseUrl || null,
        persist: true
      })
    });
    updateAIModeUI(updated);
    renderAIProviderDetails(provider);
    localStorage.setItem('sticky_ai_provider', provider);
    if (model) localStorage.setItem('sticky_ai_model', model);
    if (keyInput) keyInput.value = '';
    showToast(`Activated ${getProviderDisplayName(provider, updated.active_model)}!`, 'success');
  } catch (err) {
    showToast(`Failed to update AI configuration: ${err.message || err}`, 'error');
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<span>💾</span> Save &amp; Activate';
    }
  }
}


async function testAIConnection() {
  const providerSelect = document.getElementById('setting-ai-provider');
  if (!providerSelect) return;
  const provider = providerSelect.value;

  const customInput = document.getElementById('setting-ai-model-custom');
  const presetSelect = document.getElementById('setting-ai-model-preset');
  let model = presetSelect ? presetSelect.value : null;
  if (customInput && customInput.style.display !== 'none' && customInput.value.trim()) {
    model = customInput.value.trim();
  }

  const keyInput = document.getElementById('setting-ai-api-key');
  const apiKey = keyInput ? keyInput.value.trim() : null;

  const urlInput = document.getElementById('setting-ai-base-url');
  const baseUrl = urlInput ? urlInput.value.trim() : null;

  const testBtn = document.getElementById('btn-test-ai-settings');
  const resultDiv = document.getElementById('ai-test-result-indicator');
  if (testBtn) {
    testBtn.disabled = true;
    testBtn.innerHTML = '<span>⏳</span> Testing...';
  }
  if (resultDiv) {
    resultDiv.style.display = 'block';
    resultDiv.style.color = 'var(--text-secondary)';
    resultDiv.innerText = 'Connecting to model...';
  }

  try {
    const res = await api('/ai/test', {
      method: 'POST',
      body: JSON.stringify({
        provider: provider,
        model: model || null,
        api_key: apiKey || null,
        base_url: baseUrl || null
      })
    });
    if (res.ok) {
      if (resultDiv) {
        resultDiv.style.color = 'var(--success-color, #10b981)';
        resultDiv.innerText = `✓ Verified (${res.latency_ms}ms)`;
      }
      showToast(`Connection successful! Latency: ${res.latency_ms}ms`, 'success');
    } else {
      if (resultDiv) {
        resultDiv.style.color = 'var(--danger-color, #ef4444)';
        resultDiv.innerText = `✕ Error (${res.latency_ms}ms)`;
      }
      showToast(`Connection error: ${res.message || 'Check key and model'}`, 'error');
    }
  } catch (err) {
    if (resultDiv) {
      resultDiv.style.color = 'var(--danger-color, #ef4444)';
      resultDiv.innerText = '✕ Connection failed';
    }
    showToast(`Test failed: ${err.message || err}`, 'error');
  } finally {
    if (testBtn) {
      testBtn.disabled = false;
      testBtn.innerHTML = '<span>⚡</span> Test Selected';
    }
  }
}

async function testAllAIConnections() {
  const btn = document.getElementById('btn-test-all-ai-settings');
  const matrixContainer = document.getElementById('ai-model-matrix-container');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> Testing All Models...';
  }
  if (matrixContainer) {
    matrixContainer.style.display = 'block';
    matrixContainer.innerHTML = '<div style="padding:1rem; text-align:center; color:var(--text-secondary); font-size:0.9rem;"><span class="loading-spinner" style="display:inline-block; margin-right:0.5rem;"></span> Testing connectivity across all cloud and local models...</div>';
  }

  try {
    const data = await api('/ai/test-all');
    renderAIConnectivityMatrix(data);
    const summary = data.summary || {};
    showToast(`Model connectivity test complete: ${summary.connected || 0} Connected, ${summary.missing_key || 0} Missing Key, ${summary.error || 0} Failed`, 'info');
  } catch (err) {
    if (matrixContainer) {
      matrixContainer.innerHTML = `<div style="color:var(--danger-color, #ef4444); padding:0.75rem;">Failed to test models: ${escapeHTML(err.message || err)}</div>`;
    }
    showToast(`Test failed: ${err.message || err}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span>🔍</span> Test All Models';
    }
  }
}

function renderAIConnectivityMatrix(data) {
  const container = document.getElementById('ai-model-matrix-container');
  if (!container) return;

  const providers = data.providers || {};
  const providerDisplayNames = {
    openai: 'ChatGPT / OpenAI',
    offline: 'Offline Local LLM (Ollama)',
    gemini: 'Google Gemini',
    groq: 'Groq Cloud',
    grok: 'xAI Grok',
    mock: 'Simulator (Mock)'
  };

  const summary = data.summary || {};
  let html = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
      <h4 style="margin:0; font-size:0.95rem; font-weight:700; display:flex; align-items:center; gap:0.4rem;">
        <span>📡</span> Model Connectivity Report
      </h4>
      <div style="font-size:0.8rem; display:flex; gap:0.5rem;">
        <span style="color:#10b981; font-weight:600;">✓ ${summary.connected || 0} Connected</span>
        <span style="color:#f59e0b; font-weight:600;">⚠ ${summary.missing_key || 0} Missing Key</span>
        ${summary.error ? `<span style="color:#ef4444; font-weight:600;">✕ ${summary.error} Error</span>` : ''}
      </div>
    </div>
    <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:0.75rem;">
  `;

  for (const [key, item] of Object.entries(providers)) {
    const isConn = item.status === 'connected' || item.ok;
    const isMissingKey = item.status === 'missing_key';
    const badgeColor = isConn ? '#10b981' : (isMissingKey ? '#f59e0b' : '#ef4444');
    const badgeBg = isConn ? 'rgba(16, 185, 129, 0.12)' : (isMissingKey ? 'rgba(245, 158, 11, 0.12)' : 'rgba(239, 68, 68, 0.12)');
    const badgeText = isConn ? `Connected (${item.latency_ms}ms)` : (isMissingKey ? 'Key Required' : 'Connection Error');
    const label = providerDisplayNames[key] || key;

    html += `
      <div style="border:1px solid var(--border-color); border-radius:8px; padding:0.75rem; background:var(--bg-secondary); display:flex; flex-direction:column; justify-content:space-between; gap:0.5rem;">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
            <strong style="font-size:0.9rem;">${escapeHTML(label)}</strong>
            <span style="font-size:0.75rem; font-weight:700; color:${badgeColor}; background:${badgeBg}; padding:0.15rem 0.45rem; border-radius:4px;">
              ${escapeHTML(badgeText)}
            </span>
          </div>
          <div style="font-size:0.78rem; color:var(--text-secondary); margin-bottom:0.25rem;">
            Model: <code style="font-family:monospace; color:var(--primary-color);">${escapeHTML(item.model || 'default')}</code>
          </div>
          <div style="font-size:0.75rem; color:var(--text-muted); line-height:1.3;">
            ${escapeHTML(item.message || '')}
          </div>
        </div>
        <div style="margin-top:0.25rem; display:flex; justify-content:flex-end;">
          <button type="button" class="btn btn-secondary btn-sm" style="font-size:0.75rem; padding:0.2rem 0.5rem;" onclick="activateModelFromMatrix('${key}', '${item.model || ''}')">
            ${isConn ? '⚡ Activate' : '⚙️ Configure'}
          </button>
        </div>
      </div>
    `;
  }

  html += '</div>';
  container.innerHTML = html;
}

function activateModelFromMatrix(providerKey, modelName) {
  const providerSelect = document.getElementById('setting-ai-provider');
  if (providerSelect) {
    providerSelect.value = providerKey;
    onAIProviderSelect(providerKey);
    if (modelName) {
      const presetSelect = document.getElementById('setting-ai-model-preset');
      if (presetSelect && presetSelect.querySelector(`option[value="${modelName}"]`)) {
        presetSelect.value = modelName;
      }
    }
    const card = document.getElementById('card-ai-settings');
    if (card) card.scrollIntoView({ behavior: 'smooth' });
    showToast(`Selected ${providerKey.toUpperCase()} in Settings. Click "Save & Activate" or update your key.`, 'info');
  }
}

async function toggleAIMode() {
  const currentMode = state.aiStatus ? state.aiStatus.mode : 'online';
  const newMode = currentMode === 'online' ? 'offline' : 'online';
  try {
    const updated = await api('/ai/mode', {
      method: 'POST',
      body: JSON.stringify({ mode: newMode })
    });
    updateAIModeUI(updated);
    showToast(newMode === 'online' ? 'Switched to 🌐 Online Mode' : 'Switched to 💻 Offline Mode (Local Ollama)', 'success');
  } catch (err) {
    showToast('Failed to switch AI mode', 'error');
  }
}

function showToast(message, type = 'error') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const iconSvg = type === 'success'
    ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
    : type === 'info'
    ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';

  toast.innerHTML = `
    ${iconSvg}
    <span style="flex:1; word-break:break-word;">${escapeHTML(message)}</span>
    <button onclick="this.closest('.toast').remove()" style="background:none; border:none; color:inherit; cursor:pointer; font-size:1.15rem; line-height:1; opacity:0.6; padding:0 0.15rem; margin-left:0.5rem;" title="Dismiss">&times;</button>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 4200);
}

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Safely parse UTC ISO date strings from SQLite/FastAPI.
 * If timezone is omitted, treats as UTC (appending 'Z') so the browser
 * does not accidentally parse UTC strings as local time.
 */
function parseUTCDate(dateStr) {
  if (!dateStr) return new Date();
  if (dateStr instanceof Date) return dateStr;
  let str = String(dateStr).trim().replace(' ', 'T');
  const hasTimezone = /Z|[+-]\d{2}(:?\d{2})?$/.test(str);
  if (!hasTimezone) {
    str += 'Z';
  }
  const d = new Date(str);
  return isNaN(d.getTime()) ? new Date(dateStr) : d;
}

/**
 * Render LLM-generated markdown to safe HTML.
 * Handles the most common Qwen/Groq output patterns without any external dependency.
 * User-generated content still goes through escapeHTML — this is only for assistant replies.
 */
function renderMarkdown(str) {
  if (!str) return '';
  let s = String(str);

  // 1. Escape HTML first to prevent injection
  s = s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // 2. Fenced code blocks (``` ... ```) — must happen before inline transforms
  s = s.replace(/```([\s\S]*?)```/g, (_, code) =>
    `<pre class="md-code-block"><code>${code.trim()}</code></pre>`);

  // 3. Inline code (`code`)
  s = s.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');

  // Process line by line for block elements
  const lines = s.split('\n');
  const output = [];
  let inList = null; // 'ul' | 'ol' | null
  let inBlockquote = false;

  const closeList = () => {
    if (inList) { output.push(`</${inList}>`); inList = null; }
  };
  const closeBlockquote = () => {
    if (inBlockquote) { output.push('</blockquote>'); inBlockquote = false; }
  };

  for (const rawLine of lines) {
    let line = rawLine;

    // Horizontal rule
    if (/^\s*(---+|___+|\*\*\*+)\s*$/.test(line)) {
      closeList(); closeBlockquote();
      output.push('<hr class="md-hr">');
      continue;
    }

    // ATX headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      closeList(); closeBlockquote();
      const lvl = headingMatch[1].length;
      const hText = applyInlineMarkdown(headingMatch[2]);
      output.push(`<h${lvl} class="md-h${lvl}">${hText}</h${lvl}>`);
      continue;
    }

    // Blockquote
    const bqMatch = line.match(/^>\s*(.*)/);
    if (bqMatch) {
      closeList();
      if (!inBlockquote) { output.push('<blockquote class="md-blockquote">'); inBlockquote = true; }
      output.push(`<p>${applyInlineMarkdown(bqMatch[1])}</p>`);
      continue;
    } else {
      closeBlockquote();
    }

    // Unordered list item
    const ulMatch = line.match(/^\s*[-*+]\s+(.+)$/);
    if (ulMatch) {
      if (inList !== 'ul') { closeList(); output.push('<ul class="md-ul">'); inList = 'ul'; }
      output.push(`<li>${applyInlineMarkdown(ulMatch[1])}</li>`);
      continue;
    }

    // Ordered list item
    const olMatch = line.match(/^\s*\d+\.\s+(.+)$/);
    if (olMatch) {
      if (inList !== 'ol') { closeList(); output.push('<ol class="md-ol">'); inList = 'ol'; }
      output.push(`<li>${applyInlineMarkdown(olMatch[1])}</li>`);
      continue;
    }

    // Regular text — close any open list/blockquote
    closeList(); closeBlockquote();

    if (line.trim() === '') {
      output.push('<br>');
    } else {
      output.push(`<p class="md-p">${applyInlineMarkdown(line)}</p>`);
    }
  }

  closeList(); closeBlockquote();
  return output.join('');
}

function applyInlineMarkdown(s) {
  // Bold + italic: ***text***
  s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  // Bold: **text** or __text__
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
  // Italic: *text* or _text_
  s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  s = s.replace(/_([^_]+)_/g, '<em>$1</em>');
  // Strikethrough: ~~text~~
  s = s.replace(/~~(.+?)~~/g, '<del>$1</del>');
  // Inline code (already wrapped above but handle again for safety)
  s = s.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');
  return s;
}

// API Helper
async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  let url = path;
  if (method === 'GET') {
    const sep = url.includes('?') ? '&' : '?';
    url += `${sep}_t=${Date.now()}`;
  }
  const headers = {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache, no-store',
    'Pragma': 'no-cache',
    ...(options.headers || {})
  };

  const token = localStorage.getItem('auth_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (state.currentUser && state.currentUser.id) {
    headers['X-User-Id'] = String(state.currentUser.id);
  }

  try {
    const res = await fetch(url, { ...options, headers, cache: 'no-store' });
    let data = {};
    if (res.status !== 204) {
      data = await res.json().catch(() => ({}));
    }
    if (!res.ok) {
      const errorMsg = data.detail || `Request failed with status ${res.status}`;
      if (res.status === 401 && !path.includes('/auth/login') && !path.includes('/auth/register')) {
        handleLogout(false);
      }
      showToast(errorMsg, 'error');
      throw new Error(errorMsg);
    }
    return data;
  } catch (err) {
    console.error(`API Error on ${path}:`, err);
    throw err;
  }
}

// Navigation & Routing
function initNavigation() {
  document.querySelectorAll('.nav-item button').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.target;
      if (target) {
        switchTab(target);
      }
    });
  });
}

function toggleMobileSidebar(force) {
  const sidebar = document.querySelector('.sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (!sidebar) return;
  const shouldOpen = force !== undefined ? force : !sidebar.classList.contains('open');
  if (shouldOpen) {
    sidebar.classList.add('open');
    if (backdrop) backdrop.classList.add('open');
    document.body.classList.add('sidebar-open');
  } else {
    sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
    document.body.classList.remove('sidebar-open');
  }
}

function switchTab(tabName, param) {
  if (!tabName) return;
  state.currentTab = tabName;
  document.querySelectorAll('.nav-item button').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`.nav-item button[data-target="${tabName}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  // Sync mobile bottom navigation active state
  document.querySelectorAll('.mobile-bottom-nav-item').forEach(b => b.classList.remove('active'));
  const activeBottomBtn = document.querySelector(`.mobile-bottom-nav-item[data-target="${tabName}"]`);
  if (activeBottomBtn) activeBottomBtn.classList.add('active');

  // Auto-close mobile sidebar drawer upon selecting a tab
  toggleMobileSidebar(false);

  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  const activeSec = document.getElementById(`section-${tabName}`);
  if (activeSec) activeSec.classList.add('active');

  const titleEl = document.getElementById('page-title');
  if (titleEl) {
    titleEl.innerText = tabName === 'profile' ? 'My Profile & Directory' : (tabName.charAt(0).toUpperCase() + tabName.slice(1));
  }
  loadCurrentView(param);
}

function loadCurrentView(param) {
  switch (state.currentTab) {
    case 'dashboard': loadDashboardView(); break;
    case 'tasks': loadTasksView(param); break;
    case 'projects': loadProjectsView(param); break;
    case 'habits': loadHabitsView(param); break;
    case 'pomodoro': loadPomodoroView(); break;
    case 'schedule': loadScheduleView(param); break;
    case 'reminders': loadRemindersView(param); break;
    case 'notifications': loadNotificationsView(param); break;
    case 'memories': loadMemoriesView(param); break;
    case 'assistant': loadAssistantView(); break;
    case 'settings': loadSettingsView(); break;
    case 'profile': loadProfileView(); break;
  }

  updateNotificationDot();
}

// ──────────────────────────────────────────────────
// Sketchnote Rough.js Helper System
// ──────────────────────────────────────────────────
const Sketch = {
  getInkColor() {
    return getComputedStyle(document.documentElement).getPropertyValue('--border-color').trim() || '#2B2825';
  },

  getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  }
};

// Theme Handling (Paper / Chalkboard)
function initTheme() {
  const theme = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  const select = document.getElementById('setting-theme-select');
  if (select) select.value = theme;
  updateThemeToggleUI(theme);

  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      changeTheme(next);
    });
  }
}

function changeTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
  const select = document.getElementById('setting-theme-select');
  if (select) select.value = theme;
  updateThemeToggleUI(theme);
}

function updateThemeToggleUI(theme) {
  const btn = document.getElementById('theme-toggle-btn');
  if (!btn) return;
  const isChalkboard = theme === 'dark';
  btn.title = isChalkboard ? 'Switch to Paper (Light) Theme' : 'Switch to Chalkboard (Dark) Theme';
  btn.setAttribute('aria-label', btn.title);
  btn.innerHTML = isChalkboard
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
}

// Search
function initSearch() {
  const input = document.getElementById('global-search-input');
  const dropdown = document.getElementById('global-search-dropdown');
  let debounceTimer = null;

  if (!input || !dropdown) return;

  input.addEventListener('input', () => {
    const q = input.value.trim();
    clearTimeout(debounceTimer);
    if (!q) {
      dropdown.style.display = 'none';
      dropdown.innerHTML = '';
      return;
    }
    debounceTimer = setTimeout(() => performSearch(q, dropdown), 200);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const q = input.value.trim();
      if (q) {
        navigateTo('tasks', q);
      }
    }
    if (e.key === 'Escape') {
      dropdown.style.display = 'none';
      input.value = '';
    }
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', e => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });
}

function navigateTo(tabName, query) {
  const dropdown = document.getElementById('global-search-dropdown');
  const input = document.getElementById('global-search-input');
  if (dropdown) dropdown.style.display = 'none';
  if (input) input.value = '';
  switchTab(tabName, query);
}

async function performSearch(q, dropdown) {
  try {
    const encoded = encodeURIComponent(q);
    const [tasks, schedules, reminders, habits, projects, memories, notifications] = await Promise.all([
      api(`/tasks?search=${encoded}`).catch(() => []),
      api('/schedule').catch(() => []),
      api('/reminders').catch(() => []),
      api('/habits?include_archived=false').catch(() => []),
      api('/projects?include_archived=false').catch(() => []),
      api('/memories?include_archived=false').catch(() => []),
      api(`/notifications?search=${encoded}`).catch(() => [])
    ]);

    const qLower = q.toLowerCase();

    const matchedSchedules = (schedules || []).filter(s =>
      (s.title || '').toLowerCase().includes(qLower)
    );
    const matchedReminders = (reminders || []).filter(r =>
      (r.message || '').toLowerCase().includes(qLower)
    );
    const matchedHabits = (habits || []).filter(h =>
      (h.name || '').toLowerCase().includes(qLower)
    );
    const matchedProjects = (projects || []).filter(p =>
      (p.name || '').toLowerCase().includes(qLower) ||
      (p.description || '').toLowerCase().includes(qLower)
    );
    const matchedMemories = (memories || []).filter(m =>
      (m.content || '').toLowerCase().includes(qLower) ||
      (m.category || '').toLowerCase().includes(qLower)
    );

    const totalResults =
      (tasks || []).length +
      matchedSchedules.length +
      matchedReminders.length +
      matchedHabits.length +
      matchedProjects.length +
      matchedMemories.length +
      (notifications || []).length;

    if (totalResults === 0) {
      dropdown.innerHTML = `<div class="search-no-results">No results found for "${escapeHTML(q)}"</div>`;
      dropdown.style.display = 'block';
      return;
    }

    let html = '';

    // 1. Tasks
    if (tasks && tasks.length > 0) {
      html += `<div class="search-section-label">Tasks (${tasks.length})</div>`;
      html += tasks.slice(0, 4).map(t => `
        <div class="search-result-item" onclick="navigateTo('tasks', '${escapeHTML(t.title).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">✏️</span>
          <div>
            <div class="search-result-title">${escapeHTML(t.title)}</div>
            <div class="search-result-sub">${escapeHTML(t.status)} · Priority ${t.priority}</div>
          </div>
        </div>
      `).join('');
    }

    // 2. Schedules
    if (matchedSchedules.length > 0) {
      html += `<div class="search-section-label">Schedule (${matchedSchedules.length})</div>`;
      html += matchedSchedules.slice(0, 4).map(s => `
        <div class="search-result-item" onclick="navigateTo('schedule', '${escapeHTML(s.title).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">📅</span>
          <div>
            <div class="search-result-title">${escapeHTML(s.title)}</div>
            <div class="search-result-sub">📅 ${parseUTCDate(s.starts_at).toLocaleDateString()} ${parseUTCDate(s.starts_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})} ➔ ${parseUTCDate(s.ends_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</div>
          </div>
        </div>
      `).join('');
    }

    // 3. Reminders
    if (matchedReminders.length > 0) {
      html += `<div class="search-section-label">Reminders (${matchedReminders.length})</div>`;
      html += matchedReminders.slice(0, 4).map(r => `
        <div class="search-result-item" onclick="navigateTo('reminders', '${escapeHTML(r.message).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">⏰</span>
          <div>
            <div class="search-result-title">${escapeHTML(r.message)}</div>
            <div class="search-result-sub">⏰ ${parseUTCDate(r.remind_at).toLocaleString()} · ${r.fired_at ? 'Fired' : 'Pending'}</div>
          </div>
        </div>
      `).join('');
    }

    // 4. Habits / Hobbies
    if (matchedHabits.length > 0) {
      html += `<div class="search-section-label">Habits & Hobbies (${matchedHabits.length})</div>`;
      html += matchedHabits.slice(0, 4).map(h => `
        <div class="search-result-item" onclick="navigateTo('habits', '${escapeHTML(h.name).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">🔁</span>
          <div>
            <div class="search-result-title">${escapeHTML(h.name)}</div>
            <div class="search-result-sub">Frequency: ${escapeHTML(h.frequency)} · Target: ${h.target_count}/period</div>
          </div>
        </div>
      `).join('');
    }

    // 5. Projects
    if (matchedProjects.length > 0) {
      html += `<div class="search-section-label">Projects (${matchedProjects.length})</div>`;
      html += matchedProjects.slice(0, 3).map(p => `
        <div class="search-result-item" onclick="navigateTo('projects', '${escapeHTML(p.name).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">📁</span>
          <div>
            <div class="search-result-title">${escapeHTML(p.name)}</div>
            <div class="search-result-sub">${escapeHTML(p.description || 'No description')}</div>
          </div>
        </div>
      `).join('');
    }

    // 6. Memories
    if (matchedMemories.length > 0) {
      html += `<div class="search-section-label">Memories (${matchedMemories.length})</div>`;
      html += matchedMemories.slice(0, 3).map(m => `
        <div class="search-result-item" onclick="navigateTo('memories', '${escapeHTML(m.content).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">🧠</span>
          <div>
            <div class="search-result-title">${escapeHTML((m.content || '').slice(0, 60))}${(m.content || '').length > 60 ? '…' : ''}</div>
            <div class="search-result-sub">${escapeHTML(m.category || 'memory')}</div>
          </div>
        </div>
      `).join('');
    }

    // 7. Notifications & Activity Log
    if (notifications && notifications.length > 0) {
      html += `<div class="search-section-label">Notifications & Activity (${notifications.length})</div>`;
      html += notifications.slice(0, 4).map(n => {
        const srcIcon = {
          task: '📋',
          habit: '🎯',
          pomodoro: '⏱️',
          reminder: '⏰',
          schedule: '📅',
          project: '📁',
          memory: '🧠',
          file: '📄',
          assistant: '🤖'
        }[n.source] || '🔔';
        return `
        <div class="search-result-item" onclick="navigateTo('notifications', '${escapeHTML(n.title).replace(/'/g, "\\'")}')">
          <span class="search-result-icon">${srcIcon}</span>
          <div>
            <div class="search-result-title">${escapeHTML(n.title)} ${!n.read_at ? '<span class="badge badge-priority-1" style="font-size:0.7rem; padding:1px 5px;">Unread</span>' : ''}</div>
            <div class="search-result-sub">${escapeHTML(n.body || n.source || 'activity')} · ${parseUTCDate(n.created_at).toLocaleString()}</div>
          </div>
        </div>
      `;
      }).join('');
    }

    dropdown.innerHTML = html;
    dropdown.style.display = 'block';
  } catch (e) {
    console.error('Search error:', e);
    dropdown.style.display = 'none';
  }
}

// Global Dropdowns
async function initDropdownData() {
  try {
    const [projects, tags, tasks] = await Promise.all([
      api('/projects?include_archived=false'),
      api('/tags'),
      api('/tasks')
    ]);
    state.allProjects = projects;
    state.allTags = tags;
    state.allTasks = tasks;
    populateSelects();
  } catch (e) {}
}

function populateSelects() {
  const projSelects = ['task-filter-project', 'task-form-project'];
  projSelects.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const current = el.value;
    el.innerHTML = id.includes('filter') ? '<option value="">All Projects</option>' : '<option value="">None</option>';
    state.allProjects.forEach(p => {
      el.innerHTML += `<option value="${p.id}">${escapeHTML(p.name)}</option>`;
    });
    el.value = current;
  });

  const tagSelect = document.getElementById('task-filter-tag');
  if (tagSelect) {
    tagSelect.innerHTML = '<option value="">All Tags</option>';
    state.allTags.forEach(t => {
      tagSelect.innerHTML += `<option value="${t.id}">${escapeHTML(t.name)}</option>`;
    });
  }

  const taskSelects = ['schedule-form-task', 'reminder-form-task', 'deps-task-select'];
  taskSelects.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = id === 'deps-task-select' ? '<option value="">Select Task</option>' : '<option value="">None</option>';
    state.allTasks.forEach(t => {
      el.innerHTML += `<option value="${t.id}">#${t.id} - ${escapeHTML(t.title)}</option>`;
    });
  });
}

// 1. DASHBOARD VIEW
async function loadDashboardView() {
  try {
    const [tasks, habits, reminders, scheduleItems, pendingInvites, pendingRequests] = await Promise.all([
      api('/tasks'),
      api('/habits?include_archived=false'),
      api('/reminders'),
      api('/schedule'),
      api('/projects/invites/pending').catch(() => []),
      api('/tasks/requests/pending').catch(() => [])
    ]);

    const unfiredReminders = reminders.filter(r => !r.fired_at);
    const now = new Date();
    const dueReminders = unfiredReminders.filter(r => parseUTCDate(r.remind_at) <= now);
    const upcomingReminders = unfiredReminders.filter(r => parseUTCDate(r.remind_at) > now);

    const pendingTasks = tasks.filter(t => t.status !== 'done' && t.status !== 'cancelled');
    document.getElementById('dash-tasks-pending-count').innerText = pendingTasks.length;
    document.getElementById('dash-habits-active-count').innerText = habits.length;
    document.getElementById('dash-reminders-due-count').innerText = unfiredReminders.length;
    const descEl = document.getElementById('dash-reminders-desc');
    if (descEl) {
      descEl.innerText = `${dueReminders.length} due now · ${upcomingReminders.length} upcoming`;
    }
    document.getElementById('dash-schedule-count').innerText = scheduleItems.length;

    // Render Collaboration Invites & Task Requests on Dashboard
    renderDashboardInvites(pendingInvites);
    renderDashboardTaskRequests(pendingRequests);
    renderDashboardAssignedTasks(tasks);

    renderDailyDashboardTasks(tasks);
    renderRemindersDashboardList(reminders);

    // Check schedule conflicts
    const conflicts = await api('/schedule/conflicts');
    const banner = document.getElementById('dash-conflicts-banner');
    if (conflicts.length > 0) {
      banner.innerHTML = `<div class="card" style="border-color:var(--accent-warning); background:rgba(245,158,11,0.1);">
        <strong style="color:var(--accent-warning);">⚠️ Schedule Conflicts Detected (${conflicts.length} pairs overlapping)</strong>
      </div>`;
    } else {
      banner.innerHTML = '';
    }
  } catch (e) {
    console.error('Error loading dashboard view:', e);
  }
}

function renderDashboardInvites(invites) {
  const container = document.getElementById('dash-invites-container');
  if (!container) return;
  if (!invites || invites.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  container.innerHTML = `
    <div class="collab-banner">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem; flex-wrap:wrap; gap:0.5rem;">
        <h4 style="margin:0; font-size:0.98rem; display:flex; align-items:center; gap:0.4rem;">
          <span>📬 Project Invitations</span>
          <span class="badge badge-primary">${invites.length} Pending</span>
        </h4>
        <span style="font-size:0.75rem; color:var(--text-muted);">Collaborate with team members</span>
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${invites.map(inv => `
          <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem; padding:0.5rem 0.75rem; background:var(--bg-primary); border-radius:6px; border:1px solid var(--border-color); font-size:0.85rem; flex-wrap:wrap;">
            <div>
              <strong>📁 ${escapeHTML(inv.project_name || 'Project #' + inv.project_id)}</strong>
              <span style="font-size:0.75rem; color:var(--text-muted); margin-left:0.5rem;">Invited by User #${inv.invited_by_id}</span>
            </div>
            <div style="display:flex; gap:0.4rem;">
              <button class="btn btn-primary btn-sm" onclick="acceptProjectInvite(${inv.id})">✓ Accept</button>
              <button class="btn btn-secondary btn-sm" onclick="rejectProjectInvite(${inv.id})">✕ Decline</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderDashboardTaskRequests(requests) {
  const container = document.getElementById('dash-requests-container');
  if (!container) return;
  if (!requests || requests.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  container.innerHTML = `
    <div class="collab-banner" style="border-color:var(--accent-warning);">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem; flex-wrap:wrap; gap:0.5rem;">
        <h4 style="margin:0; font-size:0.98rem; display:flex; align-items:center; gap:0.4rem;">
          <span>🤝 Task Assignment Requests</span>
          <span class="badge badge-priority-2">${requests.length} Pending</span>
        </h4>
        <span style="font-size:0.75rem; color:var(--text-muted);">Tasks assigned to you by collaborators</span>
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${requests.map(req => `
          <div style="padding:0.55rem 0.75rem; background:var(--bg-primary); border-radius:6px; border:1px solid var(--border-color); font-size:0.85rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem; flex-wrap:wrap;">
              <div>
                <strong>📋 ${escapeHTML(req.task_title || 'Task #' + req.task_id)}</strong>
                <span style="font-size:0.75rem; color:var(--text-muted); margin-left:0.5rem;">Requested by User #${req.from_user_id} (@${escapeHTML(req.from_username)})</span>
              </div>
              <div style="display:flex; gap:0.4rem;">
                <button class="btn btn-primary btn-sm" onclick="acceptTaskRequest(${req.id})">✓ Accept Task</button>
                <button class="btn btn-danger btn-sm" onclick="rejectTaskRequest(${req.id})">✕ Reject</button>
              </div>
            </div>
            ${req.notes ? `
              <div style="margin-top:0.35rem; font-size:0.8rem; color:var(--text-secondary); background:rgba(255,255,255,0.03); padding:0.3rem 0.5rem; border-radius:4px; border-left:2px solid var(--accent-warning);">
                📝 Note: ${escapeHTML(req.notes)}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderDashboardAssignedTasks(tasks) {
  const wrapper = document.getElementById('dash-assigned-tasks-wrapper');
  const container = document.getElementById('dash-assigned-tasks-list');
  if (!wrapper || !container) return;

  const currentUserId = state.currentUser ? state.currentUser.id : null;
  const assigned = (tasks || []).filter(t => t.assigned_user_id === currentUserId && t.status !== 'done' && t.status !== 'cancelled');

  if (assigned.length === 0) {
    wrapper.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  wrapper.style.display = 'block';
  const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };

  container.innerHTML = assigned.map(t => {
    const proj = (state.allProjects || []).find(p => p.id === t.project_id);
    return `
      <div class="item-card" style="padding:0.55rem 0.75rem; margin-bottom:0.35rem; border-left: 3px solid var(--accent-primary);">
        <div class="item-main" style="display:flex; align-items:center; gap:0.6rem;">
          <input type="checkbox" onchange="toggleTaskComplete(${t.id}, true)" style="width:16px; height:16px; cursor:pointer;" title="Mark Complete">
          <div style="flex:1; min-width:0;">
            <div class="item-title" style="font-size:0.88rem;">
              ${escapeHTML(t.title)}
            </div>
            <div class="item-subtitle" style="display:flex; flex-wrap:wrap; align-items:center; gap:0.35rem; margin-top:0.2rem; font-size:0.75rem;">
              <span class="badge badge-priority-${t.priority}">${priorityLabels[t.priority] || 'P' + t.priority}</span>
              <span class="badge" style="background:rgba(99,102,241,0.15); color:var(--accent-primary);">👤 Assigned to you</span>
              ${proj ? `<span class="tag-pill">📁 ${escapeHTML(proj.name)}</span>` : ''}
              ${t.deadline ? `<span style="color:var(--text-muted);">⏰ ${parseUTCDate(t.deadline).toLocaleString()}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})" style="padding:2px 6px;">✏️</button>
        </div>
      </div>
    `;
  }).join('');
}

function openCreateTaskModalForToday() {
  openCreateTaskModal();
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const todayStr = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T18:00`;
  const deadlineEl = document.getElementById('task-form-deadline');
  if (deadlineEl) deadlineEl.value = todayStr;
}

function renderDailyDashboardTasks(tasks) {
  const container = document.getElementById('dash-todays-tasks-list');
  if (!container) return;

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  const startOfTomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const endOfTomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 23, 59, 59, 999);

  // Group tasks strictly by each day
  const overdueTasks = [];
  const todayTasks = [];
  const tomorrowTasks = [];
  const upcomingByDay = {};

  (tasks || []).forEach(t => {
    if (t.deadline) {
      const d = parseUTCDate(t.deadline);
      if (d < startOfToday) {
        if (t.status !== 'done' && t.status !== 'cancelled') {
          overdueTasks.push(t);
        }
      } else if (d >= startOfToday && d <= endOfToday) {
        todayTasks.push(t);
      } else if (d >= startOfTomorrow && d <= endOfTomorrow) {
        tomorrowTasks.push(t);
      } else if (d > endOfTomorrow) {
        const key = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
        if (!upcomingByDay[key]) upcomingByDay[key] = [];
        upcomingByDay[key].push(t);
      }
    } else {
      // If created today without a deadline, belongs to today
      if (t.created_at) {
        const c = parseUTCDate(t.created_at);
        if (c >= startOfToday && c <= endOfToday) {
          todayTasks.push(t);
        }
      }
    }
  });

  const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };

  function renderDayTaskRow(t, extraBadge = '') {
    const isDone = t.status === 'done';
    const proj = (state.allProjects || []).find(p => p.id === t.project_id);
    return `
      <div class="item-card" style="padding:0.55rem 0.75rem; margin-bottom:0.35rem; border-left: 3px solid ${isDone ? 'var(--text-muted)' : 'var(--accent-primary)'};">
        <div class="item-main" style="display:flex; align-items:center; gap:0.6rem;">
          <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleTaskComplete(${t.id}, ${!isDone})" style="width:16px; height:16px; cursor:pointer;" title="Mark Complete">
          <div style="flex:1; min-width:0;">
            <div class="item-title" style="font-size:0.88rem; ${isDone ? 'text-decoration:line-through; opacity:0.6;' : ''}">
              ${escapeHTML(t.title)}
            </div>
            <div class="item-subtitle" style="display:flex; flex-wrap:wrap; align-items:center; gap:0.35rem; margin-top:0.2rem; font-size:0.75rem;">
              <span class="badge badge-priority-${t.priority}">${priorityLabels[t.priority] || 'P' + t.priority}</span>
              <span class="badge badge-status-${t.status}">${t.status.replace('_', ' ')}</span>
              ${extraBadge}
              ${proj ? `<span class="tag-pill">📁 ${escapeHTML(proj.name)}</span>` : ''}
              ${t.deadline ? `<span style="color:var(--text-muted);">⏰ ${parseUTCDate(t.deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})" style="padding:2px 6px;">✏️</button>
        </div>
      </div>
    `;
  }

  const sections = [];

  // Overdue section
  if (overdueTasks.length > 0) {
    sections.push(`
      <div style="margin-bottom:0.85rem;">
        <div style="font-size:0.82rem; font-weight:700; color:var(--accent-danger, #ef4444); margin-bottom:0.35rem; display:flex; align-items:center; gap:0.3rem;">
          <span>⚠️ Overdue — Needs Attention Today (${overdueTasks.length})</span>
        </div>
        ${overdueTasks.map(t => renderDayTaskRow(t, '<span class="badge badge-priority-1">Overdue</span>')).join('')}
      </div>
    `);
  }

  // Today section
  sections.push(`
    <div style="margin-bottom:0.85rem;">
      <div style="font-size:0.82rem; font-weight:700; color:var(--text-primary); margin-bottom:0.35rem; display:flex; align-items:center; justify-content:space-between;">
        <span>📅 Today (${todayTasks.length})</span>
        <span style="font-size:0.75rem; color:var(--text-muted); font-weight:normal;">${now.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span>
      </div>
      ${todayTasks.length === 0 ? `
        <div class="card" style="text-align:center; padding:1rem; margin-bottom:0.4rem;">
          <p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:0.5rem;">🎉 No tasks scheduled for today! You are all caught up.</p>
          <button class="btn btn-primary btn-sm" onclick="openCreateTaskModalForToday()">+ Add Task for Today</button>
        </div>
      ` : todayTasks.map(t => renderDayTaskRow(t, '<span class="badge badge-primary">Today</span>')).join('')}
    </div>
  `);

  // Tomorrow section
  if (tomorrowTasks.length > 0) {
    sections.push(`
      <div style="margin-bottom:0.85rem;">
        <div style="font-size:0.82rem; font-weight:700; color:var(--text-secondary); margin-bottom:0.35rem;">
          <span>🗓️ Tomorrow (${tomorrowTasks.length})</span>
        </div>
        ${tomorrowTasks.map(t => renderDayTaskRow(t, '<span class="badge badge-secondary">Tomorrow</span>')).join('')}
      </div>
    `);
  }

  // Upcoming Days section
  for (const [dayName, dayTaskList] of Object.entries(upcomingByDay)) {
    sections.push(`
      <div style="margin-bottom:0.85rem;">
        <div style="font-size:0.82rem; font-weight:700; color:var(--text-secondary); margin-bottom:0.35rem;">
          <span>📆 ${dayName} (${dayTaskList.length})</span>
        </div>
        ${dayTaskList.map(t => renderDayTaskRow(t, `<span class="badge badge-secondary">${dayName}</span>`)).join('')}
      </div>
    `);
  }

  container.innerHTML = sections.join('');
}

function renderRemindersDashboardList(reminders) {
  const container = document.getElementById('dash-reminders-list');
  if (!container) return;
  
  if (!reminders || reminders.length === 0) {
    container.innerHTML = `
      <div class="card" style="text-align:center; padding:1.25rem;">
        <p style="color:var(--text-muted); margin-bottom:0.75rem;">No reminders created yet.</p>
        <button class="btn btn-primary btn-sm" onclick="openCreateReminderModal()">+ Set a Reminder</button>
      </div>`;
    return;
  }

  const now = new Date();
  // Sort: active/unfired first (due first, then upcoming), followed by fired
  const sorted = [...reminders].sort((a, b) => {
    if (!a.fired_at && b.fired_at) return -1;
    if (a.fired_at && !b.fired_at) return 1;
    return parseUTCDate(a.remind_at) - parseUTCDate(b.remind_at);
  });

  const displayList = sorted.slice(0, 8);

  container.innerHTML = displayList.map(r => {
    const isFired = !!r.fired_at;
    const rDate = parseUTCDate(r.remind_at);
    const isDue = !isFired && rDate <= now;

    let badgeClass = 'badge-secondary';
    let badgeLabel = 'Upcoming';
    if (isFired) {
      badgeClass = 'badge-status-done';
      badgeLabel = 'Fired';
    } else if (isDue) {
      badgeClass = 'badge-priority-1';
      badgeLabel = '⚠️ Due Now';
    }

    return `
      <div class="item-card" style="${isDue ? 'border-left: 4px solid var(--accent-danger, #ef4444); background: rgba(239, 68, 68, 0.05);' : (isFired ? 'opacity:0.75;' : '')}">
        <div class="item-main">
          <div>
            <div class="item-title" style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
              <span style="${isFired ? 'text-decoration:line-through;' : ''}">${escapeHTML(r.message)}</span>
              <span class="badge ${badgeClass}" style="font-size:0.72rem;">${badgeLabel}</span>
            </div>
            <div class="item-subtitle" style="font-size:0.8rem; color:var(--text-muted); margin-top:0.25rem;">
              ⏰ ${rDate.toLocaleDateString()} at ${rDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              ${isFired ? ` · <span style="color:var(--text-muted);">Triggered ${parseUTCDate(r.fired_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>` : ''}
            </div>
          </div>
        </div>
        <div class="item-actions" style="display:flex; gap:0.35rem;">
          ${!isFired ? `<button class="btn btn-secondary btn-sm" onclick="fireReminder(${r.id})" title="Trigger reminder now">Fire</button>` : ''}
          <button class="btn btn-danger btn-sm" onclick="deleteReminder(${r.id})" title="Delete reminder">🗑️</button>
        </div>
      </div>
    `;
  }).join('');
}

// 2. TASKS VIEW
async function loadTasksView(searchQuery) {
  await initDropdownData();
  const statusEl = document.getElementById('task-filter-status');
  const priorityEl = document.getElementById('task-filter-priority');
  const projectEl = document.getElementById('task-filter-project');
  const tagEl = document.getElementById('task-filter-tag');

  if (searchQuery) {
    if (statusEl) statusEl.value = '';
    if (priorityEl) priorityEl.value = '';
    if (projectEl) projectEl.value = '';
    if (tagEl) tagEl.value = '';
  }

  const status = statusEl?.value || '';
  const priority = priorityEl?.value || '';
  const projectId = projectEl?.value || '';
  const tagId = tagEl?.value || '';

  let query = '/tasks?';
  if (status) query += `status=${status}&`;
  if (priority) query += `priority=${priority}&`;
  if (projectId) query += `project_id=${projectId}&`;
  if (tagId) query += `tag_id=${tagId}&`;
  if (searchQuery) query += `search=${encodeURIComponent(searchQuery)}&`;

  const tasks = await api(query);
  renderTaskList(tasks, 'tasks-list-container', searchQuery);
}

function renderTaskList(tasks, containerId, highlightQuery) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (tasks.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No tasks found.</p></div>';
    return;
  }

  const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };
  const qLower = highlightQuery ? highlightQuery.toLowerCase() : null;

  container.innerHTML = tasks.map(t => {
    const isDone = t.status === 'done';
    const proj = (state.allProjects || []).find(p => p.id === t.project_id);
    const isMatch = qLower && (t.title.toLowerCase().includes(qLower) || (t.description && t.description.toLowerCase().includes(qLower)));
    return `
      <div class="item-card ${isMatch ? 'item-highlight' : ''}" id="task-item-${t.id}">
        <div class="item-main">
          <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleTaskComplete(${t.id}, ${!isDone})" style="width:18px; height:18px; cursor:pointer;">
          <div style="flex:1;">
            <div class="item-title" style="${isDone ? 'text-decoration:line-through; opacity:0.6;' : ''}">
              ${escapeHTML(t.title)} ${isMatch ? '<span class="badge badge-primary">Matched</span>' : ''}
            </div>
            <div class="item-subtitle" style="display:flex; flex-wrap:wrap; align-items:center; gap:0.4rem; margin-top:0.3rem;">
              <span class="badge badge-priority-${t.priority}">${priorityLabels[t.priority]}</span>
              <span class="badge badge-status-${t.status}">${t.status.replace('_', ' ')}</span>
              ${t.assigned_user_id ? `
                <span class="badge" style="background:rgba(99,102,241,0.15); color:var(--accent-primary); border:1px solid rgba(99,102,241,0.3); font-size:0.72rem;" title="Assigned to user">
                  👤 @${escapeHTML(t.assigned_username || 'User #' + t.assigned_user_id)}
                </span>
              ` : ''}
              ${t.deadline ? `<span style="color:var(--text-muted); font-size:0.8rem;">⏰ ${parseUTCDate(t.deadline).toLocaleString()}</span>` : ''}
              
              <!-- Direct project connector dropdown in Task Card -->
              <span style="display:inline-flex; align-items:center; gap:0.25rem;">
                <label style="font-size:0.75rem; color:var(--text-muted); margin:0;">📁 Project:</label>
                <select class="task-project-select" onchange="assignTaskToProject(${t.id}, this.value)" title="Connect task to project" style="max-width:140px; text-overflow:ellipsis;">
                  <option value="" ${!t.project_id ? 'selected' : ''}>-- Unassigned --</option>
                  ${(state.allProjects || []).map(p => `
                    <option value="${p.id}" ${t.project_id === p.id ? 'selected' : ''}>${escapeHTML(p.name)}</option>
                  `).join('')}
                </select>
              </span>
            </div>
            ${t.description ? `<p style="font-size:0.85rem; color:var(--text-secondary); margin-top:0.3rem; margin-bottom:0;">${escapeHTML(t.description)}</p>` : ''}
          </div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="openTaskRequestModal(${t.id}, '${escapeHTML(t.title).replace(/'/g, "\\'")}')" title="Request task assignment to user">🤝 Request</button>
          <button class="btn btn-secondary btn-sm" onclick="openTaskDepsModal(${t.id})">Deps/Tags</button>
          <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteTask(${t.id})">Delete</button>
        </div>
      </div>
    `;
  }).join('');

  if (qLower) {
    const matchedEl = container.querySelector('.item-highlight');
    if (matchedEl) {
      setTimeout(() => matchedEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    }
  }
}

async function assignTaskToProject(taskId, projectId) {
  try {
    const targetProjId = (projectId !== '' && projectId !== null && projectId !== undefined) ? parseInt(projectId, 10) : null;
    await api(`/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify({ project_id: targetProjId })
    });
    if (targetProjId) {
      const proj = (state.allProjects || []).find(p => p.id === targetProjId);
      showToast(`Task linked to project "${proj ? proj.name : targetProjId}"`, 'success');
    } else {
      showToast('Task unlinked from project', 'info');
    }
    await loadCurrentView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to assign task to project:', e);
    showToast('Failed to update task project: ' + (e.message || e), 'error');
  }
}

async function quickAddTaskToProject(event, projectId) {
  if (event) event.preventDefault();
  const inputEl = document.getElementById(`quick-task-input-${projectId}`);
  if (!inputEl) return;
  const title = inputEl.value.trim();
  if (!title) return;

  try {
    await api('/tasks', {
      method: 'POST',
      body: JSON.stringify({
        title,
        project_id: projectId,
        priority: 2,
        status: 'todo'
      })
    });
    inputEl.value = '';
    showToast('Task created and added to project!', 'success');
    await loadCurrentView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to quick add task to project:', e);
    showToast('Failed to create task: ' + (e.message || e), 'error');
  }
}

async function toggleTaskComplete(taskId, markDone) {
  try {
    const newStatus = markDone ? 'done' : 'todo';
    await api(`/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify({ status: newStatus })
    });
    showToast(`Task status updated to ${newStatus}`, 'success');
    await loadCurrentView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to update task:', e);
  }
}

async function deleteTask(taskId) {
  if (!confirm('Are you sure you want to delete this task? This cannot be undone.')) return;
  try {
    await api(`/tasks/${taskId}`, { method: 'DELETE' });
    showToast('Task deleted successfully', 'success');
    await loadCurrentView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to delete task:', e);
  }
}

// 3. PROJECTS VIEW
async function loadProjectsView(searchQuery) {
  const includeArchived = document.getElementById('projects-include-archived')?.checked || false;
  const [projects, allTasks] = await Promise.all([
    api(`/projects?include_archived=${includeArchived}`),
    api('/tasks')
  ]);
  state.allProjects = projects;
  state.allTasks = allTasks;

  const container = document.getElementById('projects-grid-container');
  if (!container) return;
  if (projects.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No projects found.</p></div>';
    return;
  }

  const qLower = searchQuery ? searchQuery.toLowerCase() : null;
  const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };

  container.innerHTML = projects.map(p => {
    const isMatch = qLower && ((p.name || '').toLowerCase().includes(qLower) || (p.description || '').toLowerCase().includes(qLower));
    const projTasks = (allTasks || []).filter(t => t.project_id === p.id);
    const doneTasks = projTasks.filter(t => t.status === 'done');
    const totalCount = projTasks.length;
    const doneCount = doneTasks.length;
    const pct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;
    const otherTasks = (allTasks || []).filter(t => t.project_id !== p.id);

    return `
      <div class="project-card ${isMatch ? 'item-highlight' : ''}" id="project-card-${p.id}" style="border-left: 5px solid ${p.color || 'var(--accent-primary)'}; box-sizing:border-box; max-width:100%; min-width:0; overflow:hidden;">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.5rem; gap:0.5rem;">
          <div style="flex:1; min-width:0;">
            <h3 style="font-size:1.15rem; margin:0; display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:100%;">${escapeHTML(p.name)}</span>
              ${isMatch ? '<span class="badge badge-primary">Matched</span>' : ''}
              ${p.archived_at ? '<span class="badge badge-status-cancelled">Archived</span>' : ''}
            </h3>
            ${p.description ? `<p class="card-desc" style="margin-top:0.35rem; margin-bottom:0; overflow:hidden; text-overflow:ellipsis;">${escapeHTML(p.description)}</p>` : ''}
          </div>
          <div style="display:flex; gap:0.3rem; flex-shrink:0;">
            <button class="btn btn-secondary btn-sm" onclick="openEditProjectModal(${p.id})" title="Edit Project">✏️</button>
            ${!p.archived_at ? `<button class="btn btn-secondary btn-sm" onclick="archiveProject(${p.id})" title="Archive Project">📦</button>` : `<button class="btn btn-secondary btn-sm" onclick="unarchiveProject(${p.id})" title="Unarchive Project">📂</button>`}
            <button class="btn btn-danger btn-sm" onclick="deleteProject(${p.id})" title="Delete Project">🗑️</button>
          </div>
        </div>

        <!-- Collaborators & Team bar -->
        <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:0.4rem; margin-bottom:0.75rem; padding:0.4rem 0.6rem; background:rgba(255,255,255,0.02); border-radius:6px; border:1px dashed var(--border-color); box-sizing:border-box; max-width:100%;">
          <div style="display:flex; align-items:center; gap:0.4rem; flex-wrap:wrap; font-size:0.78rem; flex:1; min-width:0;">
            <span style="color:var(--text-muted); font-weight:600; white-space:nowrap;">👥 Team:</span>
            <div id="project-members-${p.id}" style="display:flex; align-items:center; gap:0.35rem; flex-wrap:wrap;">
              <span style="color:var(--text-muted); font-size:0.72rem;">Loading team...</span>
            </div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="openInviteMemberModal(${p.id}, '${escapeHTML(p.name).replace(/'/g, "\\'")}')" style="font-size:0.75rem; padding:2px 7px; white-space:nowrap;" title="Invite user by unique ID">
            + Invite by ID
          </button>
        </div>

        <!-- Progress Bar -->
        <div style="margin: 0.4rem 0 0.85rem 0;">
          <div style="display:flex; justify-content:space-between; font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.25rem;">
            <span>Tasks: <strong>${doneCount}/${totalCount}</strong> completed</span>
            <span><strong>${pct}%</strong></span>
          </div>
          <div style="height:6px; background:var(--bg-secondary); border-radius:3px; overflow:hidden;">
            <div style="height:100%; width:${pct}%; background:${p.color || 'var(--accent-primary)'}; transition:width 0.3s ease;"></div>
          </div>
        </div>

        <!-- Tasks Management Bar for this Project -->
        <div style="background:var(--bg-secondary); padding:0.6rem; border-radius:8px; margin-bottom:0.85rem; border:1px solid var(--border-color); box-sizing:border-box; max-width:100%; min-width:0; overflow:hidden;">
          <form onsubmit="quickAddTaskToProject(event, ${p.id})" style="display:flex; gap:0.4rem; margin-bottom:0.5rem; flex-wrap:wrap;">
            <input type="text" id="quick-task-input-${p.id}" placeholder="Quick add task to ${escapeHTML(p.name)}..." class="form-control form-control-sm" style="flex:1; min-width:120px; font-size:0.82rem;" required />
            <button type="submit" class="btn btn-primary btn-sm" style="white-space:nowrap;">+ Add</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="openCreateTaskModal(${p.id})" title="Detailed Task Modal">Full Form</button>
          </form>
          <div style="display:flex; align-items:center; gap:0.4rem; width:100%; min-width:0; box-sizing:border-box;">
            <span style="font-size:0.75rem; color:var(--text-muted); white-space:nowrap; flex-shrink:0;">Connect task:</span>
            <div style="flex:1; min-width:0; max-width:100%;">
              <select class="task-project-select" onchange="if(this.value){ assignTaskToProject(this.value, ${p.id}); this.value=''; }" style="width:100%; max-width:100%; min-width:0; font-size:0.78rem; text-overflow:ellipsis; overflow:hidden; white-space:nowrap; box-sizing:border-box;">
                <option value="">+ Connect existing task to this project...</option>
                ${otherTasks.map(ot => `
                  <option value="${ot.id}">${escapeHTML(ot.title)} (${ot.project_id ? ((state.allProjects || []).find(pr => pr.id === ot.project_id)?.name || 'Other Project') : 'Unassigned'})</option>
                `).join('')}
              </select>
            </div>
          </div>
        </div>

        <!-- Project Tasks List -->
        <div style="flex:1; display:flex; flex-direction:column; gap:0.4rem; min-width:0; max-width:100%;">
          <div style="font-size:0.82rem; font-weight:600; color:var(--text-secondary); margin-bottom:0.2rem; display:flex; justify-content:space-between;">
            <span>Project Tasks (${projTasks.length})</span>
          </div>
          ${projTasks.length === 0 ? `
            <div style="padding:0.75rem; text-align:center; color:var(--text-muted); font-size:0.82rem; border:1px dashed var(--border-color); border-radius:6px;">
              No tasks in this project yet. Add or connect above!
            </div>
          ` : projTasks.map(t => {
            const isDone = t.status === 'done';
            return `
              <div class="project-task-row" style="display:flex; align-items:center; justify-content:space-between; gap:0.4rem; padding:0.45rem 0.6rem; border-radius:6px; background:var(--bg-primary); border:1px solid var(--border-color); font-size:0.82rem; min-width:0; max-width:100%; box-sizing:border-box;">
                <div style="display:flex; align-items:center; gap:0.4rem; flex:1; min-width:0;">
                  <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleTaskComplete(${t.id}, ${!isDone})" style="cursor:pointer;" title="Toggle Done">
                  <span style="font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; ${isDone ? 'text-decoration:line-through; opacity:0.6;' : ''}" title="${escapeHTML(t.title)}">
                    ${escapeHTML(t.title)}
                  </span>
                  <span class="badge badge-priority-${t.priority}" style="font-size:0.7rem; padding:1px 5px; flex-shrink:0;">${priorityLabels[t.priority]}</span>
                  ${t.assigned_user_id ? `
                    <span class="badge" style="background:rgba(99,102,241,0.15); color:var(--accent-primary); border:1px solid rgba(99,102,241,0.3); font-size:0.68rem; flex-shrink:0;" title="Assigned to user">
                      👤 @${escapeHTML(t.assigned_username || 'User #' + t.assigned_user_id)}
                    </span>
                  ` : ''}
                </div>
                <div style="display:flex; align-items:center; gap:0.25rem; flex-shrink:0;">
                  <button class="btn btn-secondary btn-sm" onclick="openTaskRequestModal(${t.id}, '${escapeHTML(t.title).replace(/'/g, "\\'")}')" style="padding:2px 5px; font-size:0.72rem; white-space:nowrap;" title="Assign / Request task to collaborator">
                    🤝 Assign
                  </button>
                  <select class="task-project-select" onchange="assignTaskToProject(${t.id}, this.value)" title="Move or disconnect task" style="max-width:100px; min-width:0; font-size:0.72rem; text-overflow:ellipsis;">
                    <option value="${p.id}" selected>📁 ${escapeHTML(p.name)}</option>
                    <option value="">❌ Disconnect</option>
                    ${(state.allProjects || []).filter(op => op.id !== p.id).map(op => `
                      <option value="${op.id}">📁 Move to ${escapeHTML(op.name)}</option>
                    `).join('')}
                  </select>
                  <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})" style="padding:1px 5px;" title="Edit Task">✏️</button>
                  <button class="btn btn-danger btn-sm" onclick="deleteTask(${t.id})" style="padding:1px 5px;" title="Delete Task">🗑️</button>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  }).join('');

  // Fetch team members asynchronously for each project
  projects.forEach(p => {
    loadProjectMembersUI(p.id, p.user_id);
  });

  if (qLower) {
    const matchedEl = container.querySelector('.item-highlight');
    if (matchedEl) {
      setTimeout(() => matchedEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    }
  }
}

async function viewProjectTasks(projectId, projectName) {
  const tasks = await api(`/tasks?project_id=${projectId}`);
  document.getElementById('project-detail-title').innerText = `Tasks for "${projectName}"`;
  document.getElementById('project-tasks-detail').style.display = 'block';
  renderTaskList(tasks, 'project-tasks-list');
}

function hideProjectDetail() {
  document.getElementById('project-tasks-detail').style.display = 'none';
}

async function archiveProject(id) {
  if (!confirm('Archive this project? Existing tasks will not be deleted.')) return;
  try {
    await api(`/projects/${id}/archive`, { method: 'POST' });
    showToast('Project archived', 'success');
    await loadProjectsView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to archive project:', e);
  }
}

async function unarchiveProject(id) {
  try {
    await api(`/projects/${id}/unarchive`, { method: 'POST' });
    showToast('Project restored to active', 'success');
    await loadProjectsView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to unarchive project:', e);
  }
}

async function deleteProject(id) {
  if (!confirm('Are you sure you want to delete this project? Associated tasks will be kept and unlinked. This cannot be undone.')) return;
  try {
    await api(`/projects/${id}`, { method: 'DELETE' });
    showToast('Project deleted successfully', 'success');
    await loadProjectsView();
    await initDropdownData();
  } catch (e) {
    console.error('Failed to delete project:', e);
  }
}

// 4. HABITS VIEW
async function loadHabitsView(searchQuery) {
  const includeArchived = document.getElementById('habits-include-archived')?.checked || false;
  const habits = await api(`/habits?include_archived=${includeArchived}`);

  const container = document.getElementById('habits-list-container');
  if (!container) return;
  if (habits.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No habits created yet.</p></div>';
    return;
  }

  const qLower = searchQuery ? searchQuery.toLowerCase() : null;

  const habitCardsHtml = await Promise.all(habits.map(async h => {
    const stats = await api(`/habits/${h.id}/statistics`).catch(() => ({ current_streak: 0, completion_rate: 0, total_completions: 0 }));
    const isArchived = h.archived_at != null;
    const isMatch = qLower && (h.name || '').toLowerCase().includes(qLower);

    return `
      <div class="item-card ${isMatch ? 'item-highlight' : ''}" id="habit-item-${h.id}">
        <div class="item-main">
          <div>
            <div class="item-title">${escapeHTML(h.name)} ${isMatch ? '<span class="badge badge-primary">Matched</span>' : ''} ${isArchived ? '<span class="badge badge-status-cancelled">Archived</span>' : ''}</div>
            <div class="item-subtitle">
              Frequency: <strong>${h.frequency}</strong> | Target: <strong>${h.target_count}/period</strong>
            </div>
            <div style="margin-top:0.4rem; display:flex; gap:1rem; font-size:0.85rem; color:var(--text-secondary);">
              <span>🔥 Current Streak: <strong style="color:var(--accent-warning);">${stats.current_streak}</strong></span>
              <span>🏆 Longest: <strong>${stats.longest_streak || 0}</strong></span>
              <span>📊 Rate: <strong>${(stats.completion_rate * 100).toFixed(0)}%</strong></span>
            </div>
          </div>
        </div>
        <div class="item-actions">
          ${!isArchived ? `<button class="btn btn-primary btn-sm" onclick="recordHabitCompletion(${h.id})">+ Complete Today</button>` : ''}
          ${!isArchived ? `<button class="btn btn-secondary btn-sm" onclick="archiveHabit(${h.id})">Archive</button>` : `<button class="btn btn-secondary btn-sm" onclick="unarchiveHabit(${h.id})">Unarchive</button>`}
          <button class="btn btn-danger btn-sm" onclick="deleteHabit(${h.id})">Delete</button>
        </div>
      </div>
    `;
  }));

  container.innerHTML = habitCardsHtml.join('');

  if (qLower) {
    const matchedEl = container.querySelector('.item-highlight');
    if (matchedEl) {
      setTimeout(() => matchedEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    }
  }
}

async function recordHabitCompletion(habitId) {
  try {
    await api(`/habits/${habitId}/complete`, { method: 'POST', body: JSON.stringify({}) });
    showToast('Habit completion recorded!', 'success');
    await loadHabitsView();
  } catch (e) {
    console.error('Failed to complete habit:', e);
  }
}

async function archiveHabit(habitId) {
  if (!confirm('Archive this habit?')) return;
  try {
    await api(`/habits/${habitId}/archive`, { method: 'POST' });
    showToast('Habit archived', 'success');
    await loadHabitsView();
  } catch (e) {
    console.error('Failed to archive habit:', e);
  }
}

async function unarchiveHabit(habitId) {
  try {
    await api(`/habits/${habitId}/unarchive`, { method: 'POST' });
    showToast('Habit restored to active', 'success');
    await loadHabitsView();
  } catch (e) {
    console.error('Failed to unarchive habit:', e);
  }
}

async function deleteHabit(habitId) {
  if (!confirm('Are you sure you want to delete this habit and all its completions? This cannot be undone.')) return;
  try {
    await api(`/habits/${habitId}`, { method: 'DELETE' });
    showToast('Habit deleted successfully', 'success');
    await loadHabitsView();
  } catch (e) {
    console.error('Failed to delete habit:', e);
  }
}

// 5. POMODORO VIEW & FLOATING TIMER
function playPomoChime() {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    const ctx = new AudioContextClass();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.8);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.8);
  } catch (e) {}
}

async function checkActivePomodoroSession() {
  try {
    const sessions = await api('/pomodoro');
    const active = sessions.find(s => s.ended_at === null);
    if (active) {
      if (state.activePomodoro && state.activePomodoro.id === active.id && state.activePomodoro._localStartedAtMs) {
        active._localStartedAtMs = state.activePomodoro._localStartedAtMs;
      }
      state.activePomodoro = active;
    } else {
      state.activePomodoro = null;
    }
    updatePomodoroUI();
  } catch (e) {}
}

async function loadPomodoroView() {
  const sessions = await api('/pomodoro');
  const activeSession = sessions.find(s => s.ended_at === null);

  if (activeSession) {
    if (state.activePomodoro && state.activePomodoro.id === activeSession.id && state.activePomodoro._localStartedAtMs) {
      activeSession._localStartedAtMs = state.activePomodoro._localStartedAtMs;
    }
    state.activePomodoro = activeSession;
  } else {
    state.activePomodoro = null;
  }
  updatePomodoroUI();

  const historyContainer = document.getElementById('pomodoro-history-list');
  if (!historyContainer) return;
  const pastSessions = sessions.filter(s => s.ended_at !== null).reverse();

  if (pastSessions.length === 0) {
    historyContainer.innerHTML = '<p style="color:var(--text-muted);">No past sessions recorded yet.</p>';
    return;
  }

  historyContainer.innerHTML = pastSessions.map(s => {
    const mins = Math.floor((s.duration_seconds || 0) / 60);
    const secs = (s.duration_seconds || 0) % 60;
    const sessionLabel = s.session_name
      ? `<strong>${escapeHTML(s.session_name)}</strong> <span style="font-size:0.8rem; color:var(--text-muted);">#${s.id}</span>`
      : `Session #${s.id}`;
    return `
      <div class="item-card">
        <div>
          <div class="item-title">${sessionLabel} ${s.interrupted ? '<span class="badge badge-status-cancelled">Interrupted</span>' : '<span class="badge badge-status-done">Completed</span>'}</div>
          <div class="item-subtitle">Started: ${parseUTCDate(s.started_at).toLocaleTimeString()} | Duration: ${mins}m ${secs}s (${s.duration_seconds || 0}s in DB)</div>
        </div>
        <div class="item-actions">
          <button class="btn btn-danger btn-sm" onclick="deletePomodoroSession(${s.id})">Delete</button>
        </div>
      </div>
    `;
  }).join('');
}

async function deletePomodoroSession(sessionId) {
  if (!confirm('Are you sure you want to delete this pomodoro session record? This cannot be undone.')) return;
  try {
    await api(`/pomodoro/${sessionId}`, { method: 'DELETE' });
    showToast('Pomodoro session deleted', 'success');
    await loadPomodoroView();
  } catch (e) {
    console.error('Failed to delete pomodoro session:', e);
  }
}

function getPomodoroDurationMinutes() {
  const val = parseInt(localStorage.getItem('pomodoro_duration_minutes'), 10);
  return (val && val > 0 && val <= 180) ? val : 25;
}

function savePomodoroSettings() {
  const input = document.getElementById('setting-pomodoro-duration');
  if (!input) return;
  const mins = parseInt(input.value, 10);
  if (isNaN(mins) || mins < 1 || mins > 180) {
    showToast('Please enter a duration between 1 and 180 minutes', 'error');
    return;
  }
  localStorage.setItem('pomodoro_duration_minutes', mins);
  updatePomodoroUI();
  showToast(`Pomodoro duration updated to ${mins} minutes!`, 'success');
}

function setPomodoroPreset(mins) {
  const input = document.getElementById('setting-pomodoro-duration');
  if (input) input.value = mins;
  savePomodoroSettings();
}

function loadSettingsView() {
  const input = document.getElementById('setting-pomodoro-duration');
  if (input) {
    input.value = getPomodoroDurationMinutes();
  }
  const themeSelect = document.getElementById('setting-theme-select');
  if (themeSelect) {
    themeSelect.value = localStorage.getItem('theme') || 'dark';
  }
  loadAISettings();
}

function updatePomodoroUI() {
  const timerDisplay = document.getElementById('pomodoro-timer-display');
  const statusText = document.getElementById('pomodoro-status-text');
  const startBtn = document.getElementById('pomo-start-btn');
  const endBtn = document.getElementById('pomo-end-btn');
  const interruptBtn = document.getElementById('pomo-interrupt-btn');
  const nameContainer = document.getElementById('pomo-name-input-container');

  // Floating widget elements
  const floatingWidget = document.getElementById('floating-pomo-widget');
  const floatingTitle = document.getElementById('floating-pomo-title');
  const floatingClock = document.getElementById('floating-pomo-clock');

  const durationMins = getPomodoroDurationMinutes();
  const defaultDisplayStr = `${String(durationMins).padStart(2, '0')}:00`;
  const durationLabel = document.getElementById('pomo-duration-label');
  if (durationLabel) durationLabel.innerText = durationMins;

  if (state.pomodoroInterval) {
    clearInterval(state.pomodoroInterval);
    state.pomodoroInterval = null;
  }

  if (!state.activePomodoro) {
    if (timerDisplay) timerDisplay.innerText = defaultDisplayStr;
    if (statusText) statusText.innerText = 'No active session';
    if (startBtn) startBtn.style.display = 'inline-flex';
    if (endBtn) endBtn.style.display = 'none';
    if (interruptBtn) interruptBtn.style.display = 'none';
    if (nameContainer) nameContainer.style.display = 'block';
    if (floatingWidget) floatingWidget.style.display = 'none';
  } else {
    if (startBtn) startBtn.style.display = 'none';
    if (endBtn) endBtn.style.display = 'inline-flex';
    if (interruptBtn) interruptBtn.style.display = 'inline-flex';
    if (nameContainer) nameContainer.style.display = 'none';

    const displayName = state.activePomodoro.session_name || `Session #${state.activePomodoro.id}`;
    if (floatingWidget) floatingWidget.style.display = 'flex';
    if (floatingTitle) floatingTitle.innerText = displayName;

    const serverStartTime = parseUTCDate(state.activePomodoro.started_at).getTime();
    const startTime = state.activePomodoro._localStartedAtMs || serverStartTime;
    const durationMs = durationMins * 60 * 1000;

    let hasTriggeredEnd = false;

    const updateClock = () => {
      const now = Date.now();
      const elapsed = Math.max(0, now - startTime);
      const remaining = Math.max(0, durationMs - elapsed);

      const mins = String(Math.floor(remaining / 60000)).padStart(2, '0');
      const secs = String(Math.floor((remaining % 60000) / 1000)).padStart(2, '0');
      const timeStr = `${mins}:${secs}`;

      if (timerDisplay) timerDisplay.innerText = timeStr;
      if (statusText) statusText.innerText = `Focus: ${escapeHTML(displayName)} in progress`;
      if (floatingClock) floatingClock.innerText = timeStr;

      if (remaining <= 0 && !hasTriggeredEnd) {
        hasTriggeredEnd = true;
        if (state.pomodoroInterval) {
          clearInterval(state.pomodoroInterval);
          state.pomodoroInterval = null;
        }
        playPomoChime();
        showToast(`Pomodoro session "${displayName}" completed! Duration recorded in DB.`, 'success');
        endPomodoroSession(false);
      }
    };

    updateClock();
    state.pomodoroInterval = setInterval(updateClock, 1000);
  }
}

async function startPomodoroSession() {
  const nameInput = document.getElementById('pomo-session-name');
  const sessionName = nameInput ? nameInput.value.trim() : null;
  try {
    const payload = {};
    if (sessionName) payload.session_name = sessionName;
    const session = await api('/pomodoro', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    session._localStartedAtMs = Date.now();
    state.activePomodoro = session;
    if (nameInput) nameInput.value = '';
    showToast(`Pomodoro session "${session.session_name || '#' + session.id}" started!`, 'success');
    updatePomodoroUI();
    if (state.currentTab === 'pomodoro') {
      await loadPomodoroView();
    }
  } catch (e) {
    console.error('Failed to start pomodoro session:', e);
  }
}

async function endPomodoroSession(interrupted = false) {
  if (!state.activePomodoro || state.isEndingPomodoro) return;
  state.isEndingPomodoro = true;
  const currentSession = state.activePomodoro;
  const sessionId = currentSession.id;
  const sessionName = currentSession.session_name || `#${sessionId}`;

  if (state.pomodoroInterval) {
    clearInterval(state.pomodoroInterval);
    state.pomodoroInterval = null;
  }

  try {
    const ended = await api(`/pomodoro/${sessionId}/end`, {
      method: 'POST',
      body: JSON.stringify({ interrupted })
    });
    const mins = Math.floor((ended.duration_seconds || 0) / 60);
    const secs = (ended.duration_seconds || 0) % 60;
    showToast(
      interrupted
        ? `Session "${sessionName}" interrupted after ${mins}m ${secs}s`
        : `Session "${sessionName}" complete! Saved ${mins}m ${secs}s in database.`,
      interrupted ? 'warning' : 'success'
    );
  } catch (e) {
    if (e.message && e.message.includes('already ended')) {
      console.warn(`Session ${sessionId} was already ended.`);
    } else {
      console.error('Failed to end pomodoro session:', e);
      showToast(e.message || 'Failed to end pomodoro session', 'error');
    }
  } finally {
    state.activePomodoro = null;
    state.isEndingPomodoro = false;
    updatePomodoroUI();
    if (state.currentTab === 'pomodoro') {
      await loadPomodoroView();
    }
  }
}

// 6. SCHEDULE VIEW
async function loadScheduleView(searchQuery) {
  const [items, conflicts] = await Promise.all([
    api('/schedule'),
    api('/schedule/conflicts')
  ]);

  const notice = document.getElementById('schedule-conflicts-notice');
  if (notice) {
    if (conflicts.length > 0) {
      notice.innerHTML = `<div class="card" style="border-color:var(--accent-warning); background:rgba(245,158,11,0.1);">
        <strong style="color:var(--accent-warning);">⚠️ Warning: ${conflicts.length} schedule conflict(s) detected.</strong>
      </div>`;
    } else {
      notice.innerHTML = '';
    }
  }

  const container = document.getElementById('schedule-list-container');
  if (!container) return;
  if (items.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No schedule items.</p></div>';
    return;
  }

  const qLower = searchQuery ? searchQuery.toLowerCase() : null;

  container.innerHTML = items.map(s => {
    const isMatch = qLower && (s.title || '').toLowerCase().includes(qLower);
    return `
      <div class="item-card ${isMatch ? 'item-highlight' : ''}" id="schedule-item-${s.id}">
        <div class="item-main">
          <div>
            <div class="item-title">${escapeHTML(s.title)} ${isMatch ? '<span class="badge badge-primary">Matched</span>' : ''}</div>
            <div class="item-subtitle">📅 ${parseUTCDate(s.starts_at).toLocaleString()} ➔ ${parseUTCDate(s.ends_at).toLocaleString()}</div>
          </div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="openEditScheduleModal(${s.id})">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteScheduleItem(${s.id})">Delete</button>
        </div>
      </div>
    `;
  }).join('');

  if (qLower) {
    const matchedEl = container.querySelector('.item-highlight');
    if (matchedEl) {
      setTimeout(() => matchedEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    }
  }
}

async function deleteScheduleItem(id) {
  if (!confirm('Are you sure you want to delete this schedule item? This cannot be undone.')) return;
  try {
    await api(`/schedule/${id}`, { method: 'DELETE' });
    showToast('Schedule item deleted successfully', 'success');
    await loadScheduleView();
  } catch (e) {
    console.error('Failed to delete schedule item:', e);
  }
}

// 7. REMINDERS VIEW
async function loadRemindersView(searchQuery) {
  const [reminders, pendingRequests, allTasks] = await Promise.all([
    api('/reminders'),
    api('/tasks/requests/pending').catch(() => []),
    api('/tasks').catch(() => [])
  ]);

  // Render incoming task requests in Reminders Panel
  renderRemindersTaskRequests(pendingRequests);

  // Render assigned collaborative tasks in Reminders Panel
  renderRemindersAssignedTasks(allTasks);

  const container = document.getElementById('reminders-list-container');
  if (!container) return;
  if (reminders.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No reminders found.</p></div>';
    return;
  }

  const qLower = searchQuery ? searchQuery.toLowerCase() : null;

  container.innerHTML = reminders.map(r => {
    const isMatch = qLower && (r.message || '').toLowerCase().includes(qLower);
    return `
      <div class="item-card ${isMatch ? 'item-highlight' : ''}" id="reminder-item-${r.id}">
        <div class="item-main">
          <div>
            <div class="item-title">${escapeHTML(r.message)} ${isMatch ? '<span class="badge badge-primary">Matched</span>' : ''} ${r.fired_at ? '<span class="badge badge-status-done">Fired</span>' : '<span class="badge badge-status-todo">Pending</span>'}</div>
            <div class="item-subtitle">Remind at: ${parseUTCDate(r.remind_at).toLocaleString()}</div>
          </div>
        </div>
        <div class="item-actions">
          ${!r.fired_at ? `<button class="btn btn-primary btn-sm" onclick="fireReminder(${r.id})">Fire Now</button>` : ''}
          <button class="btn btn-danger btn-sm" onclick="deleteReminder(${r.id})">Delete</button>
        </div>
      </div>
    `;
  }).join('');

  if (qLower) {
    const matchedEl = container.querySelector('.item-highlight');
    if (matchedEl) {
      setTimeout(() => matchedEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    }
  }
}

function renderRemindersTaskRequests(requests) {
  const container = document.getElementById('reminders-task-requests-container');
  if (!container) return;
  if (!requests || requests.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  container.innerHTML = `
    <div class="card" style="border-left: 4px solid var(--accent-warning); margin-bottom:1.25rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
        <h3 style="font-size:1.05rem; margin:0; display:flex; align-items:center; gap:0.5rem;">
          <span>🤝 Incoming Task Assignment Requests</span>
          <span class="badge badge-priority-2">${requests.length} Pending</span>
        </h3>
        <span style="font-size:0.8rem; color:var(--text-secondary);">Respond to collaborators</span>
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${requests.map(req => `
          <div class="item-card" style="padding:0.55rem 0.75rem; background:var(--bg-secondary); border-radius:6px; font-size:0.85rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem; flex-wrap:wrap;">
              <div>
                <strong>📋 ${escapeHTML(req.task_title || 'Task #' + req.task_id)}</strong>
                <span style="font-size:0.75rem; color:var(--text-muted); margin-left:0.5rem;">From User #${req.from_user_id} (@${escapeHTML(req.from_username)})</span>
              </div>
              <div style="display:flex; gap:0.4rem;">
                <button class="btn btn-primary btn-sm" onclick="acceptTaskRequest(${req.id})">✓ Accept</button>
                <button class="btn btn-danger btn-sm" onclick="rejectTaskRequest(${req.id})">✕ Reject</button>
              </div>
            </div>
            ${req.notes ? `
              <div style="margin-top:0.35rem; font-size:0.8rem; color:var(--text-secondary); background:rgba(0,0,0,0.1); padding:0.3rem 0.5rem; border-radius:4px; border-left:2px solid var(--accent-warning);">
                📝 Note: ${escapeHTML(req.notes)}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderRemindersAssignedTasks(tasks) {
  const container = document.getElementById('reminders-assigned-tasks-container');
  if (!container) return;
  const currentUserId = state.currentUser ? state.currentUser.id : null;
  const assigned = (tasks || []).filter(t => t.assigned_user_id === currentUserId && t.status !== 'done' && t.status !== 'cancelled');

  if (assigned.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };

  container.innerHTML = `
    <div class="card" style="border-left: 4px solid var(--accent-primary); margin-bottom:1.25rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
        <h3 style="font-size:1.05rem; margin:0; display:flex; align-items:center; gap:0.5rem;">
          <span>📥 Collaborative Tasks Assigned To You</span>
          <span class="badge badge-priority-1">${assigned.length} Active</span>
        </h3>
        <span style="font-size:0.8rem; color:var(--text-secondary);">Reminders for assigned tasks</span>
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${assigned.map(t => {
          const proj = (state.allProjects || []).find(p => p.id === t.project_id);
          return `
            <div class="item-card" style="padding:0.55rem 0.75rem; background:var(--bg-secondary); border-radius:6px; font-size:0.85rem;">
              <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem;">
                <div style="display:flex; align-items:center; gap:0.5rem; flex:1; min-width:0;">
                  <input type="checkbox" onchange="toggleTaskComplete(${t.id}, true)" style="cursor:pointer;" title="Mark Complete">
                  <span style="font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    ${escapeHTML(t.title)}
                  </span>
                  <span class="badge badge-priority-${t.priority}">${priorityLabels[t.priority] || 'P' + t.priority}</span>
                  ${proj ? `<span class="tag-pill">📁 ${escapeHTML(proj.name)}</span>` : ''}
                </div>
                <div style="display:flex; align-items:center; gap:0.4rem; flex-shrink:0;">
                  ${t.deadline ? `<span style="font-size:0.75rem; color:var(--text-muted);">⏰ ${parseUTCDate(t.deadline).toLocaleString()}</span>` : ''}
                  <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})" style="padding:2px 6px;">Edit</button>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>
  `;
}

async function fireReminder(id) {
  try {
    await api(`/reminders/${id}/fire`, { method: 'POST' });
    showToast('Reminder fired!', 'success');
    await loadCurrentView();
  } catch (e) {
    console.error('Failed to fire reminder:', e);
  }
}

async function deleteReminder(id) {
  if (!confirm('Are you sure you want to delete this reminder? This cannot be undone.')) return;
  try {
    await api(`/reminders/${id}`, { method: 'DELETE' });
    showToast('Reminder deleted successfully', 'success');
    await loadCurrentView();
  } catch (e) {
    console.error('Failed to delete reminder:', e);
  }
}

// 8. NOTIFICATIONS VIEW
function renderNotificationsInvites(invites) {
  const container = document.getElementById('notifications-invites-container');
  if (!container) return;
  if (!invites || invites.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  container.innerHTML = `
    <div class="collab-banner" style="margin-bottom:1.25rem;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem; flex-wrap:wrap; gap:0.5rem;">
        <h4 style="margin:0; font-size:1rem; display:flex; align-items:center; gap:0.4rem;">
          <span>📬 Pending Project Invitations</span>
          <span class="badge badge-primary">${invites.length}</span>
        </h4>
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${invites.map(inv => `
          <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem; padding:0.5rem 0.75rem; background:var(--bg-primary); border-radius:6px; border:1px solid var(--border-color); font-size:0.85rem; flex-wrap:wrap;">
            <div>
              <strong>📁 ${escapeHTML(inv.project_name || 'Project #' + inv.project_id)}</strong>
              <span style="font-size:0.75rem; color:var(--text-muted); margin-left:0.5rem;">Invited by User #${inv.invited_by_id}</span>
            </div>
            <div style="display:flex; gap:0.4rem;">
              <button class="btn btn-primary btn-sm" onclick="acceptProjectInvite(${inv.id})">Accept Invite</button>
              <button class="btn btn-secondary btn-sm" onclick="rejectProjectInvite(${inv.id})">Decline</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderNotificationsTaskRequests(requests) {
  const container = document.getElementById('notifications-task-requests-container');
  if (!container) return;
  if (!requests || requests.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }

  container.style.display = 'block';
  container.innerHTML = `
    <div class="collab-banner" style="margin-bottom:1.25rem; border-color:var(--accent-warning);">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.5rem; flex-wrap:wrap; gap:0.5rem;">
        <h4 style="margin:0; font-size:1rem; display:flex; align-items:center; gap:0.4rem;">
          <span>🤝 Pending Task Assignment Requests</span>
          <span class="badge badge-priority-2">${requests.length}</span>
        </h4>
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${requests.map(req => `
          <div style="padding:0.55rem 0.75rem; background:var(--bg-primary); border-radius:6px; border:1px solid var(--border-color); font-size:0.85rem;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:0.5rem; flex-wrap:wrap;">
              <div>
                <strong>📋 ${escapeHTML(req.task_title || 'Task #' + req.task_id)}</strong>
                <span style="font-size:0.75rem; color:var(--text-muted); margin-left:0.5rem;">Requested by User #${req.from_user_id} (@${escapeHTML(req.from_username)})</span>
              </div>
              <div style="display:flex; gap:0.4rem;">
                <button class="btn btn-primary btn-sm" onclick="acceptTaskRequest(${req.id})">Accept Task</button>
                <button class="btn btn-danger btn-sm" onclick="rejectTaskRequest(${req.id})">Reject</button>
              </div>
            </div>
            ${req.notes ? `
              <div style="margin-top:0.35rem; font-size:0.8rem; color:var(--text-secondary); background:rgba(255,255,255,0.03); padding:0.3rem 0.5rem; border-radius:4px; border-left:2px solid var(--accent-warning);">
                📝 Note: ${escapeHTML(req.notes)}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

let notificationsSearchDebounceTimer = null;

function onNotificationsSearchInput(event) {
  const clearBtn = document.getElementById('notifications-search-clear');
  const val = event?.target?.value || document.getElementById('notifications-search-input')?.value || '';
  if (clearBtn) clearBtn.style.display = val.trim() ? 'block' : 'none';
  clearTimeout(notificationsSearchDebounceTimer);
  notificationsSearchDebounceTimer = setTimeout(() => {
    loadNotificationsView();
  }, 200);
}

function onNotificationsSearchKeydown(event) {
  if (event.key === 'Escape') {
    clearNotificationsSearch();
  } else if (event.key === 'Enter') {
    clearTimeout(notificationsSearchDebounceTimer);
    loadNotificationsView();
  }
}

function clearNotificationsSearch() {
  const searchInput = document.getElementById('notifications-search-input');
  const clearBtn = document.getElementById('notifications-search-clear');
  if (searchInput) searchInput.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  loadNotificationsView();
}

function renderTodayTasksInNotifications(tasks, filterQuery = '') {
  const container = document.getElementById('notifications-today-tasks-container');
  if (!container) return;

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);

  const todayTasks = (tasks || []).filter(t => {
    if (t.deadline) {
      const d = parseUTCDate(t.deadline);
      if (d >= startOfToday && d <= endOfToday) return true;
      if (d < startOfToday && t.status !== 'done' && t.status !== 'cancelled') return true;
      return false;
    }
    if (t.created_at) {
      const c = parseUTCDate(t.created_at);
      if (c >= startOfToday && c <= endOfToday) return true;
    }
    return false;
  });

  // If search query is active and no today's tasks matched, hide this section completely so search results aren't pushed down
  if (filterQuery && todayTasks.length === 0) {
    container.style.display = 'none';
    container.innerHTML = '';
    return;
  }
  container.style.display = 'block';

  const pendingCount = todayTasks.filter(t => t.status !== 'done' && t.status !== 'cancelled').length;
  const doneCount = todayTasks.filter(t => t.status === 'done').length;

  container.innerHTML = `
    <div class="card" style="border-left: 4px solid var(--accent-primary, #6366f1); margin-bottom: 1.25rem; background: var(--bg-card);">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
        <div>
          <h3 style="font-size:1.05rem; margin:0; display:flex; align-items:center; gap:0.5rem;">
            <span>📋 Today's Tasks ${filterQuery ? `<span style="font-size:0.8rem; font-weight:normal; color:var(--text-muted);">(Filtered: "${escapeHTML(filterQuery)}")</span>` : ''}</span>
            <span class="badge ${pendingCount > 0 ? 'badge-priority-2' : 'badge-status-done'}" style="font-size:0.75rem;">
              ${pendingCount} Pending · ${doneCount} Done
            </span>
          </h3>
          <p style="font-size:0.8rem; color:var(--text-secondary); margin:0.25rem 0 0 0;">
            Daily tasks and deadlines scheduled for today
          </p>
        </div>
        <div style="display:flex; gap:0.5rem;">
          <button class="btn btn-primary btn-sm" onclick="openCreateTaskModalForToday()">+ Add Task</button>
          <button class="btn btn-secondary btn-sm" onclick="navigateTo('tasks')">Task View</button>
        </div>
      </div>

      ${todayTasks.length === 0 ? `
        <div style="padding:0.75rem; text-align:center; color:var(--text-muted); font-size:0.85rem; border:1px dashed var(--border-color); border-radius:6px;">
          ✨ No tasks due today. You are completely up to date!
        </div>
      ` : `
        <div style="display:flex; flex-direction:column; gap:0.4rem;">
          ${todayTasks.map(t => {
            const isDone = t.status === 'done';
            const proj = (state.allProjects || []).find(p => p.id === t.project_id);
            const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };
            const isOverdue = t.deadline && parseUTCDate(t.deadline) < startOfToday && !isDone;

            return `
              <div class="item-card" style="padding:0.5rem 0.75rem; display:flex; align-items:center; justify-content:space-between; gap:0.5rem; background:var(--bg-secondary); border-radius:6px; font-size:0.85rem;">
                <div style="display:flex; align-items:center; gap:0.6rem; flex:1; min-width:0;">
                  <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleTaskComplete(${t.id}, ${!isDone})" style="cursor:pointer; width:16px; height:16px;" title="Mark Complete">
                  <span style="font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; ${isDone ? 'text-decoration:line-through; opacity:0.6;' : ''}">
                    ${escapeHTML(t.title)}
                  </span>
                  <span class="badge badge-priority-${t.priority}" style="font-size:0.68rem; padding:1px 5px;">${priorityLabels[t.priority] || 'P' + t.priority}</span>
                  ${proj ? `<span class="tag-pill" style="font-size:0.72rem; padding:1px 6px;">📁 ${escapeHTML(proj.name)}</span>` : ''}
                  ${isOverdue ? '<span class="badge badge-priority-1" style="font-size:0.68rem;">Overdue</span>' : ''}
                </div>
                <div style="display:flex; align-items:center; gap:0.4rem; flex-shrink:0;">
                  ${t.deadline ? `<span style="font-size:0.75rem; color:var(--text-muted);">⏰ ${parseUTCDate(t.deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>` : ''}
                  <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})" style="padding:1px 6px; font-size:0.75rem;">Edit</button>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `}
    </div>
  `;
}

async function loadNotificationsView(filterQuery) {
  const searchInput = document.getElementById('notifications-search-input');
  if (typeof filterQuery === 'string' && searchInput) {
    searchInput.value = filterQuery;
  }
  const clearBtn = document.getElementById('notifications-search-clear');
  if (clearBtn && searchInput) {
    clearBtn.style.display = searchInput.value.trim() ? 'block' : 'none';
  }

  // Show "All Users" toggle for admin
  const allUsersLabel = document.getElementById('notifications-all-users-label');
  const isAdmin = state.currentUser && state.currentUser.role === 'admin';
  if (allUsersLabel) {
    allUsersLabel.style.display = isAdmin ? 'inline-flex' : 'none';
  }

  const query = searchInput ? searchInput.value.trim() : '';
  const unreadOnly = document.getElementById('notifications-unread-only')?.checked || false;
  const allUsers = (isAdmin && document.getElementById('notifications-all-users')?.checked) || false;

  let url = `/notifications?unread_only=${unreadOnly}`;
  if (query) {
    url += `&search=${encodeURIComponent(query)}`;
  }
  if (allUsers) {
    url += `&all_users=true`;
  }

  let tasksUrl = '/tasks';
  if (allUsers) {
    tasksUrl += '?all_users=true';
  }

  try {
    const [notifications, tasks, pendingInvites, pendingRequests] = await Promise.all([
      api(url).catch(() => []),
      api(tasksUrl).catch(() => []),
      api('/projects/invites/pending').catch(() => []),
      api('/tasks/requests/pending').catch(() => [])
    ]);

    const queryLower = query.toLowerCase();

    // Filter project invites by query if searching
    const filteredInvites = (pendingInvites || []).filter(inv => {
      if (!queryLower) return true;
      const name = (inv.project_name || '').toLowerCase();
      const byUser = String(inv.invited_by_id || '').toLowerCase();
      return name.includes(queryLower) || byUser.includes(queryLower);
    });
    renderNotificationsInvites(filteredInvites);

    // Filter task requests by query if searching
    const filteredRequests = (pendingRequests || []).filter(req => {
      if (!queryLower) return true;
      const title = (req.task_title || '').toLowerCase();
      const notes = (req.notes || '').toLowerCase();
      const from = (req.from_username || '').toLowerCase();
      return title.includes(queryLower) || notes.includes(queryLower) || from.includes(queryLower);
    });
    renderNotificationsTaskRequests(filteredRequests);

    // Filter today tasks by query if searching
    const filteredTasks = (tasks || []).filter(t => {
      if (!queryLower) return true;
      const title = (t.title || '').toLowerCase();
      const desc = (t.description || '').toLowerCase();
      return title.includes(queryLower) || desc.includes(queryLower);
    });
    renderTodayTasksInNotifications(filteredTasks, query);

    const container = document.getElementById('notifications-list-container');
    if (!container) return;

    if (!notifications || notifications.length === 0) {
      const emptyMsg = query
        ? `No notifications or activity found matching "${escapeHTML(query)}".`
        : (unreadOnly ? 'No unread notifications.' : 'No notifications or activity history yet.');
      container.innerHTML = `<div class="card" style="text-align:center; padding:2rem;"><p style="color:var(--text-muted);">${emptyMsg}</p></div>`;
      return;
    }

    const sourceIcons = {
      task: '📋',
      project: '📁',
      habit: '🎯',
      pomodoro: '⏱️',
      reminder: '⏰',
      schedule: '📅',
      memory: '🧠',
      file: '📄',
      assistant: '🤖'
    };

    container.innerHTML = notifications.map(n => {
      const icon = sourceIcons[n.source] || '🔔';
      const isUnread = !n.read_at;
      return `
      <div class="item-card ${isUnread ? 'notification-unread-card' : ''}" style="${isUnread ? 'border-left: 3px solid var(--accent-primary, #6366f1);' : 'opacity:0.9;'}">
        <div class="item-main" style="display:flex; align-items:flex-start; gap:0.75rem;">
          <span style="font-size:1.3rem; line-height:1; margin-top:2px;">${icon}</span>
          <div style="flex:1;">
            <div class="item-title" style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
              <span>${escapeHTML(n.title)}</span>
              ${isUnread ? '<span class="badge badge-priority-1" style="font-size:0.72rem;">Unread</span>' : ''}
              ${n.source ? `<span class="badge" style="font-size:0.7rem; background:var(--bg-secondary); color:var(--text-secondary);">${escapeHTML(n.source)}</span>` : ''}
              ${(allUsers && n.user_id) ? `<span class="badge" style="font-size:0.68rem; background:rgba(255,255,255,0.06); color:var(--text-muted);">User #${n.user_id}</span>` : ''}
            </div>
            ${n.body ? `<div class="item-subtitle" style="margin-top:0.25rem; color:var(--text-secondary);">${escapeHTML(n.body)}</div>` : ''}
            <div style="font-size:0.78rem; color:var(--text-muted); margin-top:0.35rem;">
              🕒 ${parseUTCDate(n.created_at).toLocaleString()}
            </div>
          </div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="toggleNotificationRead(${n.id}, ${isUnread})" title="${isUnread ? 'Mark as read' : 'Mark as unread'}">
            ${isUnread ? '✓ Mark Read' : '↺ Mark Unread'}
          </button>
        </div>
      </div>
    `;
    }).join('');
  } catch (err) {
    console.error('Failed to load notifications view:', err);
    showToast('Failed to load notifications', 'error');
  }
}

async function toggleNotificationRead(id, markRead) {
  try {
    const action = markRead ? 'read' : 'unread';
    await api(`/notifications/${id}/${action}`, { method: 'POST', body: '{}' });
    showToast(markRead ? 'Notification marked as read' : 'Notification marked as unread', 'info');
    loadNotificationsView();
    updateNotificationDot();
  } catch (e) {
    showToast('Failed to update notification', 'error');
  }
}

async function markAllNotificationsRead() {
  try {
    const isAdmin = state.currentUser && state.currentUser.role === 'admin';
    const allUsers = (isAdmin && document.getElementById('notifications-all-users')?.checked) || false;
    let url = '/notifications/read-all';
    if (allUsers) {
      url += '?all_users=true';
    }
    const res = await api(url, { method: 'POST', body: '{}' });
    const count = res.marked_read || 0;
    if (count > 0) {
      showToast(`Marked ${count} notification(s) as read`, 'success');
    } else {
      showToast('All notifications are already marked as read', 'info');
    }
    loadNotificationsView();
    updateNotificationDot();
  } catch (e) {
    showToast('Failed to mark notifications as read', 'error');
  }
}

async function updateNotificationDot() {
  try {
    const isAdmin = state.currentUser && state.currentUser.role === 'admin';
    const allUsers = (isAdmin && document.getElementById('notifications-all-users')?.checked) || false;
    let url = '/notifications?unread_only=true';
    if (allUsers) url += '&all_users=true';
    const unread = await api(url);
    const dot = document.getElementById('unread-notification-dot');
    if (dot) dot.style.display = (unread && unread.length > 0) ? 'block' : 'none';
  } catch (e) {}
}

// MODAL CONTROLS & FORMS
function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = 'none';
  }
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('active');
  }
}

// Global listener to close modal on backdrop click (except non-closable auth modal)
document.addEventListener('click', (e) => {
  if (e.target.classList && e.target.classList.contains('modal-overlay')) {
    if (!e.target.classList.contains('auth-modal-overlay') || document.getElementById('auth-modal-close-btn')?.style.display !== 'none') {
      e.target.classList.remove('active');
      e.target.style.display = 'none';
    }
  }
});

// ─────────────────────────────────────────────────────────────
// USER AUTHENTICATION & MULTI-USER MANAGEMENT
// ─────────────────────────────────────────────────────────────
async function initAuth() {
  const token = localStorage.getItem('auth_token');
  const storedUser = localStorage.getItem('current_user');
  if (token) {
    try {
      if (storedUser) {
        state.currentUser = JSON.parse(storedUser);
        updateUserHeaderUI();
      }
      const me = await api('/api/auth/me');
      state.currentUser = me;
      localStorage.setItem('current_user', JSON.stringify(me));
      updateUserHeaderUI();
      closeAuthModal();
      return true;
    } catch (err) {
      console.warn('Stored token invalid or expired:', err);
      localStorage.removeItem('auth_token');
      localStorage.removeItem('current_user');
      state.currentUser = null;
    }
  }
  // Not authenticated: prompt login modal
  openAuthModal(false);
  return false;
}


function updateUserHeaderUI() {
  const user = state.currentUser;
  const avatarEl = document.getElementById('topbar-user-avatar');
  const idEl = document.getElementById('topbar-user-id');
  const nameEl = document.getElementById('topbar-user-name');
  const statusEl = document.getElementById('topbar-user-status');
  const roleEl = document.getElementById('topbar-user-role');
  const dropTitle = document.getElementById('dropdown-user-title');
  const dropRole = document.getElementById('dropdown-user-role');

  if (!user) {
    if (avatarEl) avatarEl.innerText = '?';
    if (idEl) idEl.innerText = '';
    if (nameEl) nameEl.innerText = 'Log In';
    if (statusEl) {
      statusEl.className = 'badge-offline';
      statusEl.innerText = '⚪ Offline';
    }
    if (roleEl) {
      roleEl.innerText = 'Guest';
      roleEl.style.background = 'var(--domain-pomodoro-bg)';
      roleEl.style.color = 'var(--domain-pomodoro)';
    }
    if (dropTitle) dropTitle.innerText = 'Guest';
    if (dropRole) dropRole.innerText = 'Not Signed In';
    return;
  }

  const initial = (user.username || 'U').charAt(0).toUpperCase();
  if (avatarEl) avatarEl.innerText = initial;
  if (idEl) idEl.innerText = `#${user.id}`;
  if (nameEl) nameEl.innerText = user.username;
  if (statusEl) {
    statusEl.className = user.is_online ? 'badge-online' : 'badge-offline';
    statusEl.innerText = user.is_online ? '🟢 Online' : '⚪ Offline';
  }
  if (roleEl) {
    roleEl.innerText = user.role || 'user';
    roleEl.style.background = (user.role === 'admin') ? 'var(--domain-tasks-bg)' : 'var(--domain-habits-bg)';
    roleEl.style.color = (user.role === 'admin') ? 'var(--domain-tasks)' : 'var(--domain-habits)';
    roleEl.style.borderColor = (user.role === 'admin') ? 'var(--domain-tasks-border)' : 'var(--domain-habits-border)';
  }
  if (dropTitle) dropTitle.innerHTML = `${escapeHTML(user.username)} <span style="font-family:monospace; color:var(--accent-primary); font-size:0.85rem;">#${user.id}</span>`;
  if (dropRole) {
    const tokens = (user.token_usage || 0).toLocaleString();
    dropRole.innerHTML = `${user.role === 'admin' ? 'Role: Administrator' : 'Role: Standard User'}<br><span style="font-size:0.75rem; color:var(--text-muted);">Tokens: ${tokens} / 100k</span>`;
  }
}

// Online Heartbeat & Real-Time Presence
let heartbeatInterval = null;

function startHeartbeat() {
  if (heartbeatInterval) clearInterval(heartbeatInterval);
  sendHeartbeat();
  heartbeatInterval = setInterval(() => {
    if (document.visibilityState === 'visible') {
      sendHeartbeat();
    }
  }, 15000);
}

async function sendHeartbeat() {
  if (!state.currentUser) return;
  try {
    const res = await api('/api/auth/heartbeat', { method: 'POST' });
    if (res && res.user) {
      state.currentUser.token_usage = res.user.token_usage;
      state.currentUser.last_active_at = res.user.last_active_at;
      state.currentUser.is_online = res.user.is_online;
      updateUserHeaderUI();
    }
  } catch (e) {
    // silently continue on network interruptions
  }
}

function sendOfflineBeacon() {
  const token = localStorage.getItem('auth_token');
  if (!token) return;
  try {
    fetch('/auth/offline', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      keepalive: true
    }).catch(() => {});
  } catch (e) {
    // ignore beacon failure on unload
  }
}

// Quick Autofill for Login Testing
function quickFillLogin(username, password) {
  const unameInput = document.getElementById('auth-login-username');
  const pwdInput = document.getElementById('auth-login-password');
  if (unameInput) unameInput.value = username;
  if (pwdInput) pwdInput.value = password;
  const btn = document.getElementById('auth-login-submit-btn');
  if (btn) btn.focus();
  showToast(`Autofilled credentials for ${username} (password: ${password})`, 'info');
}

// Copy Unique User ID
function copyMyUserId() {
  const user = state.currentUser;
  if (!user || !user.id) {
    showToast('User ID not available', 'warning');
    return;
  }
  navigator.clipboard.writeText(String(user.id)).then(() => {
    showToast(`User ID #${user.id} copied to clipboard!`, 'success');
  }).catch(() => {
    showToast(`Your User ID is #${user.id}`, 'info');
  });
}


// Dedicated Full-Page Profile View
async function loadProfileView() {
  let user = state.currentUser;
  if (!user) {
    const stored = localStorage.getItem('current_user');
    if (stored) {
      try {
        user = JSON.parse(stored);
        state.currentUser = user;
      } catch (e) {}
    }
  }

  // Refresh profile details from API
  try {
    const me = await api('/auth/me');
    if (me) {
      state.currentUser = me;
      user = me;
      localStorage.setItem('current_user', JSON.stringify(me));
      updateUserHeaderUI();
    }
  } catch (e) {
    // fallback to stored user
  }

  if (!user) {
    showToast('Please sign in to view your profile', 'warning');
    openAuthModal(false);
    return;
  }

  // Update chat sidebar user label
  const chatLabel = document.getElementById('chat-user-label');
  if (chatLabel) chatLabel.innerText = `${user.username}'s private conversations`;

  const avatar = document.getElementById('profile-page-avatar');
  const uname = document.getElementById('profile-page-username');
  const uid = document.getElementById('profile-page-id');
  const role = document.getElementById('profile-page-role');
  const status = document.getElementById('profile-page-status');
  const tokenCount = document.getElementById('profile-page-token-count');
  const tokenBar = document.getElementById('profile-page-token-bar');

  if (avatar) avatar.innerText = (user.username || 'U').charAt(0).toUpperCase();
  if (uname) uname.innerText = user.username;
  if (uid) uid.innerText = `#${user.id}`;
  if (role) {
    role.innerText = user.role === 'admin' ? 'Administrator' : 'Standard User';
    role.className = `badge ${user.role === 'admin' ? 'badge-priority-1' : 'badge-priority-3'}`;
  }
  if (status) {
    status.className = 'badge-online';
    status.innerText = '🟢 Active Now';
  }

  const tokenUsage = user.token_usage || 0;
  const maxTokens = 100000;
  if (tokenCount) tokenCount.innerText = `${tokenUsage.toLocaleString()} / 100,000 tokens`;
  if (tokenBar) {
    const pct = Math.min(100, Math.round((tokenUsage / maxTokens) * 100));
    tokenBar.style.width = `${pct}%`;
    tokenBar.style.background = pct > 90 ? 'var(--accent-danger)' : (pct > 70 ? 'var(--accent-warning)' : 'var(--accent-primary)');
  }

  await loadUsersDirectoryPage();

  // Show admin token dashboard if admin or project leader (server will return token_usage for others)
  await loadAdminTokenDashboard();
}

// ── Admin / Project-Leader Token Usage Dashboard ──────────────────────────────
async function loadAdminTokenDashboard() {
  const dashboard = document.getElementById('admin-token-dashboard');
  const chart = document.getElementById('admin-token-chart');
  const summary = document.getElementById('admin-token-summary');
  if (!dashboard || !chart) return;

  try {
    const users = await api('/auth/users');
    // Only show the dashboard if the server returned token_usage for other users
    const hasOthersTokens = users && users.some(u => {
      const isMe = state.currentUser && u.id === state.currentUser.id;
      return !isMe && u.token_usage !== null && u.token_usage !== undefined;
    });

    if (!hasOthersTokens) {
      dashboard.style.display = 'none';
      return;
    }

    dashboard.style.display = 'block';

    const sorted = [...users].sort((a, b) => (b.token_usage || 0) - (a.token_usage || 0));
    const maxUsage = sorted[0]?.token_usage || 1;
    const totalTokens = sorted.reduce((s, u) => s + (u.token_usage || 0), 0);
    const TOKEN_CAP = 100000;

    chart.innerHTML = sorted.map(u => {
      const usage = u.token_usage || 0;
      const isMe = state.currentUser && u.id === state.currentUser.id;
      const pct = Math.min(100, Math.round((usage / TOKEN_CAP) * 100));
      const barPct = Math.max(2, Math.round((usage / Math.max(maxUsage, 1)) * 100));
      const barColor = pct > 90 ? 'var(--accent-danger)' : (pct > 70 ? 'var(--accent-warning)' : 'var(--accent-primary)');
      const onlineDot = u.is_online
        ? '<span style="width:7px;height:7px;background:var(--accent-success,#22c55e);border-radius:50%;display:inline-block;margin-right:3px;vertical-align:middle;" title="Online"></span>'
        : '<span style="width:7px;height:7px;background:var(--text-muted);border-radius:50%;display:inline-block;margin-right:3px;vertical-align:middle; opacity:0.5;" title="Offline"></span>';
      return `
        <div style="display:flex; align-items:center; gap:0.6rem; font-size:0.83rem;">
          <div style="width:110px; flex-shrink:0; display:flex; align-items:center; gap:0.3rem; overflow:hidden;">
            ${onlineDot}
            <span style="font-weight:${isMe ? '700' : '500'}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; color:${isMe ? 'var(--accent-primary)' : 'var(--text-primary)'};"
                  title="${escapeHTML(u.username)}${isMe ? ' (You)' : ''}">
              ${escapeHTML(u.username)}${isMe ? ' <span style="font-size:0.68rem;color:var(--accent-success);">(You)</span>' : ''}
            </span>
          </div>
          <div style="flex:1; background:var(--bg-secondary); border-radius:4px; height:10px; overflow:hidden; border:1px solid var(--border-color);">
            <div style="height:100%; width:${barPct}%; background:${barColor}; border-radius:4px; transition:width 0.4s ease;"></div>
          </div>
          <div style="width:120px; flex-shrink:0; text-align:right; font-family:monospace; color:var(--text-secondary);">
            <strong style="color:${barColor};">${usage.toLocaleString()}</strong>
            <span style="color:var(--text-muted); font-size:0.75rem;"> / 100k</span>
            <span style="font-size:0.72rem; color:var(--text-muted);">(${pct}%)</span>
          </div>
        </div>
      `;
    }).join('');

    if (summary) {
      summary.innerHTML = `
        <div style="background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:6px; padding:0.5rem 0.9rem; display:flex; align-items:center; gap:0.4rem;">
          <span>👥</span> <strong>${users.length}</strong>&nbsp;users
        </div>
        <div style="background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:6px; padding:0.5rem 0.9rem; display:flex; align-items:center; gap:0.4rem;">
          <span>⚡</span> Total:&nbsp;<strong style="color:var(--accent-primary); font-family:monospace;">${totalTokens.toLocaleString()}</strong>&nbsp;tokens
        </div>
        <div style="background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:6px; padding:0.5rem 0.9rem; display:flex; align-items:center; gap:0.4rem;">
          <span>📊</span> Avg:&nbsp;<strong style="font-family:monospace;">${Math.round(totalTokens / users.length).toLocaleString()}</strong>&nbsp;/ user
        </div>
      `;
    }
  } catch (err) {
    if (dashboard) dashboard.style.display = 'none';
  }
}

// Collaborator & Users Directory in Profile Section

async function loadUsersDirectoryPage() {
  const container = document.getElementById('profile-page-users-list');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-muted); font-size:0.85rem; padding:1.5rem; text-align:center; grid-column:1/-1;">Loading collaborator directory...</div>';

  try {
    const users = await api('/auth/users');
    if (!users || users.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:0.85rem; padding:1rem; text-align:center; grid-column:1/-1;">No other users found.</div>';
      return;
    }

    const note = document.getElementById('profile-token-visibility-note');
    const hasAnyTokens = users.some(u => u.token_usage !== null && u.token_usage !== undefined);
    if (note && hasAnyTokens) {
      note.innerHTML = `<span style="color:var(--accent-primary); font-weight:600;">⚡ Token Insights Active:</span> As an Admin or Project Leader, you can view real-time token usage across all collaborators.`;
    }

    container.innerHTML = users.map(u => {
      const isMe = state.currentUser && state.currentUser.id === u.id;
      const statusIcon = u.is_online ? '🟢' : '⚪';
      const statusText = u.is_online ? 'Online' : 'Offline';
      const statusBadge = `<span class="${u.is_online ? 'badge-online' : 'badge-offline'}" style="font-size:0.75rem; padding:2px 8px;">${statusIcon} ${statusText}</span>`;

      const tokenDisplay = (u.token_usage !== null && u.token_usage !== undefined)
        ? `<div style="margin-top:0.5rem; font-size:0.8rem; background:rgba(99,102,241,0.08); padding:4px 8px; border-radius:5px; display:flex; justify-content:space-between; align-items:center;">
             <span style="color:var(--text-muted);">⚡ AI Tokens:</span>
             <strong style="color:var(--accent-primary); font-family:monospace;">${u.token_usage.toLocaleString()} / 100k</strong>
           </div>`
        : '';

      return `
        <div class="card" style="padding:1rem; display:flex; flex-direction:column; justify-content:space-between; background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:8px;">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.6rem;">
              <div style="display:flex; align-items:center; gap:0.6rem;">
                <div class="user-avatar" style="width:36px; height:36px; font-size:1rem;">${(u.username || 'U').charAt(0).toUpperCase()}</div>
                <div>
                  <div style="font-weight:600; font-size:0.95rem;">
                    ${escapeHTML(u.username)}
                    ${isMe ? '<span class="badge" style="font-size:0.68rem; margin-left:0.35rem; background:rgba(16,185,129,0.15); color:var(--accent-success);">You</span>' : ''}
                  </div>
                  <div style="font-family:monospace; font-size:0.8rem; color:var(--accent-primary);">ID: #${u.id}</div>
                </div>
              </div>
              ${statusBadge}
            </div>
            ${tokenDisplay}
          </div>
          <div style="margin-top:0.8rem; display:flex; justify-content:flex-end; gap:0.4rem;">
            <button class="btn btn-secondary btn-sm" onclick="openPublicProfileModal(${u.id})" style="font-size:0.75rem; padding:3px 9px;">View Profile</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div style="color:var(--accent-danger); font-size:0.85rem; padding:1rem; grid-column:1/-1;">Failed to load users: ${escapeHTML(err.message || String(err))}</div>`;
  }
}

// User Profile Modal (Route directly to dedicated Profile section)
function openUserProfileModal() {
  switchTab('profile');
}

function openUsersDirectoryModal() {
  switchTab('profile');
}

async function loadUsersDirectory() {
  const container = document.getElementById('profile-modal-users-list');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-muted); font-size:0.82rem; text-align:center; padding:1rem;">Loading users...</div>';
  try {
    const users = await api('/auth/users');
    if (!users || users.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted); font-size:0.82rem; text-align:center; padding:0.5rem;">No other users registered.</div>';
      return;
    }
    container.innerHTML = users.map(u => {
      const isMe = state.currentUser && state.currentUser.id === u.id;
      const tokenTag = (u.token_usage !== null && u.token_usage !== undefined)
        ? `<span style="font-size:0.72rem; color:var(--accent-primary); font-family:monospace; background:rgba(99,102,241,0.1); padding:1px 5px; border-radius:4px;" title="Token Usage">⚡ ${u.token_usage.toLocaleString()}</span>`
        : '';
      return `
        <div style="display:flex; align-items:center; justify-content:space-between; padding:0.4rem 0.6rem; border-radius:6px; background:var(--bg-secondary); margin-bottom:0.35rem; font-size:0.82rem; border:1px solid var(--border-color);">
          <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
            <span style="font-family:monospace; font-weight:600; color:var(--accent-primary); background:rgba(99,102,241,0.1); padding:1px 5px; border-radius:4px;">#${u.id}</span>
            <span style="font-weight:500;">${escapeHTML(u.username)}</span>
            ${isMe ? '<span class="badge" style="font-size:0.68rem; background:rgba(16,185,129,0.15); color:var(--accent-success);">You</span>' : ''}
            <span class="${u.is_online ? 'badge-online' : 'badge-offline'}" style="font-size:0.7rem; padding:1px 5px;">
              ${u.is_online ? '🟢 Online' : '⚪ Offline'}
            </span>
            ${tokenTag}
          </div>
          <div>
            <button class="btn btn-secondary btn-sm" onclick="openPublicProfileModal(${u.id})" style="padding:2px 7px; font-size:0.75rem;">View Profile</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div style="color:var(--accent-danger); font-size:0.8rem; padding:0.5rem;">Failed to load users: ${escapeHTML(err.message || String(err))}</div>`;
  }
}

// Public Profile Modal: STRICTLY ONLY shows unique ID and online status (Privacy Kept)
async function openPublicProfileModal(userId) {
  try {
    const profile = await api(`/auth/users/${userId}/profile`);
    const modal = document.getElementById('public-profile-modal');
    if (!modal) return;
    const avatar = document.getElementById('public-avatar');
    const uname = document.getElementById('public-username');
    const uid = document.getElementById('public-id');
    const badge = document.getElementById('public-status-badge');

    if (avatar) avatar.innerText = (profile.username || 'U').charAt(0).toUpperCase();
    if (uname) uname.innerText = profile.username;
    if (uid) uid.innerText = `#${profile.id}`;
    if (badge) {
      badge.innerHTML = `<span class="${profile.is_online ? 'badge-online' : 'badge-offline'}">${profile.is_online ? '🟢 Online Now' : '⚪ Offline'}</span>`;
    }
    const tokenRow = document.getElementById('public-token-usage-row');
    const tokenCount = document.getElementById('public-token-count');
    if (tokenRow) {
      if (profile.token_usage !== null && profile.token_usage !== undefined) {
        tokenRow.style.display = 'block';
        if (tokenCount) {
          tokenCount.innerText = `${profile.token_usage.toLocaleString()} / 100,000 tokens`;
        }
      } else {
        tokenRow.style.display = 'none';
      }
    }
    openModal('public-profile-modal');
  } catch (err) {
    showToast('Failed to load user profile: ' + (err.message || err), 'error');
  }
}

// Project Invites & Collaboration Handlers
async function openInviteMemberModal(projectId, projectName) {
  const modal = document.getElementById('project-invite-modal');
  if (!modal) return;
  document.getElementById('invite-project-id').value = projectId;
  document.getElementById('invite-project-name').value = projectName || `Project #${projectId}`;
  document.getElementById('invite-target-user-id').value = '';

  const dropdown = document.getElementById('invite-user-dropdown');
  if (dropdown) {
    dropdown.innerHTML = '<option value="">-- Choose User --</option>';
    try {
      const users = await api('/auth/users');
      (users || []).forEach(u => {
        if (!state.currentUser || state.currentUser.id !== u.id) {
          const opt = document.createElement('option');
          opt.value = u.id;
          opt.innerText = `User #${u.id} - ${u.username} (${u.is_online ? 'Online' : 'Offline'})`;
          dropdown.appendChild(opt);
        }
      });
    } catch (e) {
      console.warn('Failed to populate users dropdown:', e);
    }
  }

  openModal('project-invite-modal');
}

async function handleSendProjectInvite(event) {
  if (event) event.preventDefault();
  const projectId = document.getElementById('invite-project-id').value;
  const targetUserId = parseInt(document.getElementById('invite-target-user-id').value, 10);
  if (!targetUserId) {
    showToast('Please specify a valid User ID', 'warning');
    return;
  }
  try {
    await api(`/projects/${projectId}/invite`, {
      method: 'POST',
      body: JSON.stringify({ user_id: targetUserId })
    });
    showToast(`Invitation sent to User #${targetUserId}!`, 'success');
    closeModal('project-invite-modal');
    await loadProjectsView();
  } catch (e) {
    showToast('Failed to invite user: ' + (e.message || e), 'error');
  }
}

async function removeProjectMember(projectId, userId, username) {
  if (!confirm(`Remove ${username || 'User #' + userId} from this project? Any assigned tasks will be unassigned.`)) return;
  try {
    await api(`/projects/${projectId}/members/${userId}`, { method: 'DELETE' });
    showToast(`User removed from project`, 'success');
    await loadProjectsView();
  } catch (e) {
    showToast('Failed to remove member: ' + (e.message || e), 'error');
  }
}

async function acceptProjectInvite(inviteId) {
  try {
    await api(`/projects/invites/${inviteId}/accept`, { method: 'POST' });
    showToast('Project invitation accepted!', 'success');
    await loadCurrentView();
  } catch (e) {
    showToast('Failed to accept invitation: ' + (e.message || e), 'error');
  }
}

async function rejectProjectInvite(inviteId) {
  try {
    await api(`/projects/invites/${inviteId}/reject`, { method: 'POST' });
    showToast('Project invitation declined', 'info');
    await loadCurrentView();
  } catch (e) {
    showToast('Failed to decline invitation: ' + (e.message || e), 'error');
  }
}

async function loadProjectMembersUI(projectId, ownerId) {
  const container = document.getElementById(`project-members-${projectId}`);
  if (!container) return;
  try {
    const members = await api(`/projects/${projectId}/members`);
    if (!members || members.length === 0) {
      container.innerHTML = '<span style="color:var(--text-muted); font-size:0.75rem;">Only owner</span>';
      return;
    }
    const currentUserId = state.currentUser ? state.currentUser.id : null;
    const isOwnerOrAdmin = (state.currentUser && state.currentUser.role === 'admin') || (currentUserId === ownerId);

    container.innerHTML = members.map(m => {
      const isOwner = m.role === 'owner';
      const canRemove = isOwnerOrAdmin && !isOwner;
      const statusIcon = m.is_online ? '🟢' : '⚪';
      const statusClass = m.is_online ? 'badge-online' : 'badge-offline';
      return `
        <span class="user-chip" style="display:inline-flex; align-items:center; gap:0.25rem; background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:12px; padding:2px 7px; font-size:0.75rem;">
          <span class="${statusClass}" title="${m.is_online ? 'Online' : 'Offline'}" style="cursor:pointer;" onclick="openPublicProfileModal(${m.user_id})">${statusIcon}</span>
          <span style="font-family:monospace; color:var(--accent-primary);">#${m.user_id}</span>
          <span style="font-weight:500; cursor:pointer;" onclick="openPublicProfileModal(${m.user_id})">${escapeHTML(m.username)}</span>
          ${(m.token_usage !== null && m.token_usage !== undefined) ? `<span style="font-size:0.68rem; color:var(--accent-primary); font-family:monospace; background:rgba(99,102,241,0.1); padding:1px 4px; border-radius:3px;" title="AI Token Usage">⚡${m.token_usage.toLocaleString()}</span>` : ''}
          ${isOwner ? '<span style="font-size:0.65rem; color:var(--accent-warning);">👑</span>' : ''}
          ${canRemove ? `<button class="btn-icon" onclick="removeProjectMember(${projectId}, ${m.user_id}, '${escapeHTML(m.username).replace(/'/g, "\\'")}')" title="Remove user from project" style="color:var(--accent-danger); font-size:0.75rem; line-height:1; padding:0 2px; margin-left:2px; cursor:pointer;">&times;</button>` : ''}
        </span>
      `;
    }).join('');
  } catch (e) {
    container.innerHTML = `<span style="color:var(--text-muted); font-size:0.75rem;">Error loading team</span>`;
  }
}

// Task Assignment Request Handlers (with Notes)
async function openTaskRequestModal(taskId, taskTitle) {
  const modal = document.getElementById('task-request-modal');
  if (!modal) return;
  document.getElementById('task-req-task-id').value = taskId;
  document.getElementById('task-req-task-title').value = taskTitle || `Task #${taskId}`;
  document.getElementById('task-req-target-user-id').value = '';
  document.getElementById('task-req-notes').value = '';

  const dropdown = document.getElementById('task-req-user-dropdown');
  if (dropdown) {
    dropdown.innerHTML = '<option value="">-- Select Collaborator --</option>';
    try {
      const users = await api('/auth/users');
      (users || []).forEach(u => {
        if (!state.currentUser || state.currentUser.id !== u.id) {
          const opt = document.createElement('option');
          opt.value = u.id;
          opt.innerText = `User #${u.id} - ${u.username} (${u.is_online ? 'Online' : 'Offline'})`;
          dropdown.appendChild(opt);
        }
      });
    } catch (e) {
      console.warn('Failed to populate task request users:', e);
    }
  }

  openModal('task-request-modal');
}

async function handleSendTaskRequest(event) {
  if (event) event.preventDefault();
  const taskId = document.getElementById('task-req-task-id').value;
  const toUserId = parseInt(document.getElementById('task-req-target-user-id').value, 10);
  const notes = document.getElementById('task-req-notes').value.trim();

  if (!toUserId) {
    showToast('Please enter a target User ID', 'warning');
    return;
  }

  try {
    await api(`/tasks/${taskId}/request-assign`, {
      method: 'POST',
      body: JSON.stringify({ to_user_id: toUserId, notes: notes || null })
    });
    showToast(`Task assignment request sent to User #${toUserId}!`, 'success');
    closeModal('task-request-modal');
    await loadCurrentView();
  } catch (e) {
    showToast('Failed to send task request: ' + (e.message || e), 'error');
  }
}

async function acceptTaskRequest(requestId) {
  try {
    await api(`/tasks/requests/${requestId}/accept`, { method: 'POST' });
    showToast('Task request accepted! Task assigned to you.', 'success');
    await loadCurrentView();
  } catch (e) {
    showToast('Failed to accept task request: ' + (e.message || e), 'error');
  }
}

async function rejectTaskRequest(requestId) {
  try {
    await api(`/tasks/requests/${requestId}/reject`, { method: 'POST' });
    showToast('Task request rejected', 'info');
    await loadCurrentView();
  } catch (e) {
    showToast('Failed to reject task request: ' + (e.message || e), 'error');
  }
}

function openAuthModal(canClose = true) {
  const modal = document.getElementById('auth-modal');
  const closeBtn = document.getElementById('auth-modal-close-btn');
  if (closeBtn) {
    closeBtn.style.display = canClose ? 'block' : 'none';
  }
  if (modal) {
    modal.style.display = 'flex';
    modal.classList.add('active');
  }
  // Reset error displays
  const loginErr = document.getElementById('auth-login-error');
  if (loginErr) { loginErr.style.display = 'none'; loginErr.innerText = ''; }
  const regErr = document.getElementById('auth-register-error');
  if (regErr) { regErr.style.display = 'none'; regErr.innerText = ''; }

  // Default to login tab
  switchAuthTab('login');
}

function closeAuthModal() {
  const modal = document.getElementById('auth-modal');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('active');
  }
}

function switchAuthTab(tab) {
  const loginTabBtn = document.getElementById('tab-btn-login');
  const regTabBtn = document.getElementById('tab-btn-register');
  const loginPanel = document.getElementById('auth-login-panel');
  const regPanel = document.getElementById('auth-register-panel');

  if (tab === 'login') {
    if (loginTabBtn) loginTabBtn.classList.add('active');
    if (regTabBtn) regTabBtn.classList.remove('active');
    if (loginPanel) { loginPanel.style.display = 'block'; loginPanel.classList.add('active'); }
    if (regPanel) { regPanel.style.display = 'none'; regPanel.classList.remove('active'); }
    const userInput = document.getElementById('auth-login-username');
    if (userInput && !userInput.value) userInput.focus();
  } else {
    if (regTabBtn) regTabBtn.classList.add('active');
    if (loginTabBtn) loginTabBtn.classList.remove('active');
    if (regPanel) { regPanel.style.display = 'block'; regPanel.classList.add('active'); }
    if (loginPanel) { loginPanel.style.display = 'none'; loginPanel.classList.remove('active'); }
    const regInput = document.getElementById('auth-reg-username');
    if (regInput) regInput.focus();
  }
}

function quickFillKunal() {
  // Admin credentials removed to protect admin credentials
}


async function handleLoginFormSubmit(e) {
  if (e) e.preventDefault();
  const username = document.getElementById('auth-login-username').value.trim();
  const password = document.getElementById('auth-login-password').value;
  const errEl = document.getElementById('auth-login-error');
  const submitBtn = document.getElementById('auth-login-submit-btn');

  if (errEl) { errEl.style.display = 'none'; errEl.innerText = ''; }
  if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = 'Signing In...'; }

  try {
    const res = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
    const token = res.access_token || res.token;
    localStorage.setItem('auth_token', token);
    localStorage.setItem('current_user', JSON.stringify(res.user));
    state.currentUser = res.user;

    updateUserHeaderUI();
    closeAuthModal();
    showToast(`Logged in as ${res.user.username} (${res.user.role})`, 'success');

    // Reset domain collections and reload all views for the authenticated user
    state.allTasks = [];
    state.allProjects = [];
    state.allTags = [];
    initDropdownData();
    loadCurrentView();
    loadAIMode();
    checkActivePomodoroSession();
  } catch (err) {
    if (errEl) {
      errEl.innerText = err.message || 'Invalid username or password';
      errEl.style.display = 'block';
    }
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = 'Sign In'; }
  }
}

async function handleRegisterFormSubmit(e) {
  if (e) e.preventDefault();
  const username = document.getElementById('auth-reg-username').value.trim();
  const password = document.getElementById('auth-reg-password').value;
  const errEl = document.getElementById('auth-register-error');
  const submitBtn = document.getElementById('auth-reg-submit-btn');

  if (errEl) { errEl.style.display = 'none'; errEl.innerText = ''; }
  if (submitBtn) { submitBtn.disabled = true; submitBtn.innerText = 'Creating Account...'; }

  try {
    const res = await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    });
    const token = res.access_token || res.token;
    localStorage.setItem('auth_token', token);
    localStorage.setItem('current_user', JSON.stringify(res.user));
    state.currentUser = res.user;

    updateUserHeaderUI();
    closeAuthModal();
    showToast(`Welcome ${res.user.username}! Account created.`, 'success');

    // Reset domain collections and reload all views for new user
    state.allTasks = [];
    state.allProjects = [];
    state.allTags = [];
    initDropdownData();
    loadCurrentView();
    loadAIMode();
    checkActivePomodoroSession();
  } catch (err) {
    if (errEl) {
      errEl.innerText = err.message || 'Failed to create account';
      errEl.style.display = 'block';
    }
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.innerText = 'Create Account & Sign In'; }
  }
}

function handleLogout(showToastMsg = true) {
  sendOfflineBeacon();
  localStorage.removeItem('auth_token');
  localStorage.removeItem('current_user');
  state.currentUser = null;
  updateUserHeaderUI();

  const drop = document.getElementById('user-dropdown-menu');
  if (drop) drop.style.display = 'none';

  state.allTasks = [];
  state.allProjects = [];
  state.allTags = [];

  if (showToastMsg) {
    showToast('Signed out successfully', 'info');
  }

  // Mandatory login modal without close button
  openAuthModal(false);
}

function toggleUserDropdown(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('user-dropdown-menu');
  if (!menu) return;
  menu.style.display = (menu.style.display === 'none' || !menu.style.display) ? 'block' : 'none';
}

function openSwitchUserModal() {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) menu.style.display = 'none';
  openAuthModal(true);
}

function initUserDropdownListener() {
  document.addEventListener('click', (e) => {
    const container = document.getElementById('user-profile-menu-container');
    const menu = document.getElementById('user-dropdown-menu');
    if (menu && container && !container.contains(e.target)) {
      menu.style.display = 'none';
    }
  });
}

// Task Modal
function openCreateTaskModal(defaultProjectId = null) {
  document.getElementById('task-modal-title').innerText = 'Create Task';
  document.getElementById('task-form-id').value = '';
  document.getElementById('task-form-title').value = '';
  document.getElementById('task-form-desc').value = '';
  document.getElementById('task-form-status').value = 'todo';
  document.getElementById('task-form-priority').value = '2';
  document.getElementById('task-form-project').value = defaultProjectId != null ? String(defaultProjectId) : '';
  document.getElementById('task-form-deadline').value = '';
  openModal('task-modal');
}

async function openEditTaskModal(id) {
  const t = await api(`/tasks/${id}`);
  document.getElementById('task-modal-title').innerText = 'Edit Task';
  document.getElementById('task-form-id').value = t.id;
  document.getElementById('task-form-title').value = t.title;
  document.getElementById('task-form-desc').value = t.description || '';
  document.getElementById('task-form-status').value = t.status;
  document.getElementById('task-form-priority').value = t.priority;
  document.getElementById('task-form-project').value = t.project_id || '';
  document.getElementById('task-form-deadline').value = t.deadline ? t.deadline.slice(0, 16) : '';
  openModal('task-modal');
}

async function handleTaskFormSubmit(e) {
  e.preventDefault();
  const id = document.getElementById('task-form-id').value;
  const payload = {
    title: document.getElementById('task-form-title').value.trim(),
    description: document.getElementById('task-form-desc').value.trim() || null,
    status: document.getElementById('task-form-status').value,
    priority: parseInt(document.getElementById('task-form-priority').value, 10),
    project_id: document.getElementById('task-form-project').value ? parseInt(document.getElementById('task-form-project').value, 10) : null,
    deadline: document.getElementById('task-form-deadline').value ? new Date(document.getElementById('task-form-deadline').value).toISOString() : null
  };

  try {
    if (id) {
      await api(`/tasks/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      showToast('Task updated successfully', 'success');
    } else {
      await api('/tasks', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Task created successfully', 'success');
    }
    closeModal('task-modal');
    loadCurrentView();
  } catch (err) {}
}

// Project Modal
function openCreateProjectModal() {
  document.getElementById('project-modal-title').innerText = 'New Project';
  document.getElementById('project-form-id').value = '';
  document.getElementById('project-form-name').value = '';
  document.getElementById('project-form-desc').value = '';
  document.getElementById('project-form-color').value = '';
  openModal('project-modal');
}

async function openEditProjectModal(id) {
  const p = await api(`/projects/${id}`);
  document.getElementById('project-modal-title').innerText = 'Edit Project';
  document.getElementById('project-form-id').value = p.id;
  document.getElementById('project-form-name').value = p.name;
  document.getElementById('project-form-desc').value = p.description || '';
  document.getElementById('project-form-color').value = p.color || '';
  openModal('project-modal');
}

async function handleProjectFormSubmit(e) {
  e.preventDefault();
  const id = document.getElementById('project-form-id').value;
  const payload = {
    name: document.getElementById('project-form-name').value.trim(),
    description: document.getElementById('project-form-desc').value.trim() || null,
    color: document.getElementById('project-form-color').value.trim() || null
  };

  try {
    if (id) {
      await api(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      showToast('Project updated', 'success');
    } else {
      await api('/projects', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Project created', 'success');
    }
    closeModal('project-modal');
    loadProjectsView();
  } catch (err) {}
}

// Habit Modal
function openCreateHabitModal() {
  document.getElementById('habit-form-name').value = '';
  document.getElementById('habit-form-frequency').value = 'daily';
  document.getElementById('habit-form-target').value = '1';
  openModal('habit-modal');
}

async function handleHabitFormSubmit(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('habit-form-name').value.trim(),
    frequency: document.getElementById('habit-form-frequency').value,
    target_count: parseInt(document.getElementById('habit-form-target').value, 10)
  };
  try {
    await api('/habits', { method: 'POST', body: JSON.stringify(payload) });
    showToast('Habit created', 'success');
    closeModal('habit-modal');
    loadHabitsView();
  } catch (err) {}
}

// Schedule Modal
function openCreateScheduleModal() {
  document.getElementById('schedule-modal-title').innerText = 'Schedule Block';
  document.getElementById('schedule-form-id').value = '';
  document.getElementById('schedule-form-title').value = '';
  document.getElementById('schedule-form-start').value = '';
  document.getElementById('schedule-form-end').value = '';
  document.getElementById('schedule-form-task').value = '';
  openModal('schedule-modal');
}

async function openEditScheduleModal(id) {
  const s = await api(`/schedule/${id}`);
  document.getElementById('schedule-modal-title').innerText = 'Edit Schedule Block';
  document.getElementById('schedule-form-id').value = s.id;
  document.getElementById('schedule-form-title').value = s.title;
  document.getElementById('schedule-form-start').value = s.starts_at.slice(0, 16);
  document.getElementById('schedule-form-end').value = s.ends_at.slice(0, 16);
  document.getElementById('schedule-form-task').value = s.task_id || '';
  openModal('schedule-modal');
}

async function handleScheduleFormSubmit(e) {
  e.preventDefault();
  const id = document.getElementById('schedule-form-id').value;
  const payload = {
    title: document.getElementById('schedule-form-title').value.trim(),
    starts_at: new Date(document.getElementById('schedule-form-start').value).toISOString(),
    ends_at: new Date(document.getElementById('schedule-form-end').value).toISOString(),
    task_id: document.getElementById('schedule-form-task').value ? parseInt(document.getElementById('schedule-form-task').value, 10) : null
  };

  try {
    if (id) {
      await api(`/schedule/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
      showToast('Schedule item updated', 'success');
    } else {
      await api('/schedule', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Schedule item created', 'success');
    }
    closeModal('schedule-modal');
    loadScheduleView();
  } catch (err) {}
}

// Reminder Modal
function openCreateReminderModal() {
  document.getElementById('reminder-modal-title').innerText = 'New Reminder';
  document.getElementById('reminder-form-id').value = '';
  document.getElementById('reminder-form-message').value = '';
  document.getElementById('reminder-form-time').value = '';
  document.getElementById('reminder-form-task').value = '';
  openModal('reminder-modal');
}

async function handleReminderFormSubmit(e) {
  e.preventDefault();
  const payload = {
    message: document.getElementById('reminder-form-message').value.trim(),
    remind_at: new Date(document.getElementById('reminder-form-time').value).toISOString(),
    task_id: document.getElementById('reminder-form-task').value ? parseInt(document.getElementById('reminder-form-task').value, 10) : null
  };

  try {
    await api('/reminders', { method: 'POST', body: JSON.stringify(payload) });
    showToast('Reminder set', 'success');
    closeModal('reminder-modal');
    loadRemindersView();
  } catch (err) {}
}

// Dependencies & Tags Modal
async function openTaskDepsModal(taskId) {
  document.getElementById('deps-task-id').value = taskId;
  const [tags, deps] = await Promise.all([
    api(`/tasks/${taskId}/tags`),
    api(`/tasks/${taskId}/dependencies`)
  ]);

  const tagsList = document.getElementById('deps-tags-list');
  tagsList.innerHTML = tags.map(t => `<span class="tag-pill">${escapeHTML(t.name)} <button style="background:none; border:none; color:inherit; cursor:pointer;" onclick="detachTag(${taskId}, ${t.id})">&times;</button></span>`).join('') || '<p style="color:var(--text-muted);">No tags attached.</p>';

  const depsList = document.getElementById('deps-list');
  depsList.innerHTML = deps.map(depId => `<div class="item-card"><div class="item-title">Depends on Task #${depId}</div><button class="btn btn-danger btn-sm" onclick="removeDependency(${taskId}, ${depId})">Remove</button></div>`).join('') || '<p style="color:var(--text-muted);">No direct dependencies.</p>';

  openModal('task-deps-modal');
}

async function detachTag(taskId, tagId) {
  try {
    await api(`/tasks/${taskId}/tags/${tagId}`, { method: 'DELETE' });
    openTaskDepsModal(taskId);
  } catch (e) {}
}

async function removeDependency(taskId, depId) {
  try {
    await api(`/tasks/${taskId}/dependencies/${depId}`, { method: 'DELETE' });
    openTaskDepsModal(taskId);
  } catch (e) {}
}

async function handleAttachTagSubmit(e) {
  e.preventDefault();
  const taskId = document.getElementById('deps-task-id').value;
  const tagId = document.getElementById('deps-tag-select').value;
  if (!tagId) return;
  try {
    await api(`/tasks/${taskId}/tags/${tagId}`, { method: 'POST' });
    openTaskDepsModal(taskId);
  } catch (e) {}
}

async function handleAddDependencySubmit(e) {
  e.preventDefault();
  const taskId = document.getElementById('deps-task-id').value;
  const depId = document.getElementById('deps-task-select').value;
  if (!depId) return;
  try {
    await api(`/tasks/${taskId}/dependencies`, {
      method: 'POST',
      body: JSON.stringify({ depends_on_task_id: parseInt(depId, 10) })
    });
    openTaskDepsModal(taskId);
  } catch (e) {}
}

// Tag Manager
async function openTagManagerModal() {
  const tags = await api('/tags');
  const list = document.getElementById('tag-manager-list');
  list.innerHTML = tags.map(t => `<span class="tag-pill" style="font-size:0.9rem;">${escapeHTML(t.name)}</span>`).join('') || '<p style="color:var(--text-muted);">No tags exist yet.</p>';
  openModal('tag-manager-modal');
}

async function handleCreateTagSubmit(e) {
  e.preventDefault();
  const name = document.getElementById('new-tag-name').value.trim();
  try {
    await api('/tags', { method: 'POST', body: JSON.stringify({ name }) });
    showToast('Tag created', 'success');
    document.getElementById('new-tag-name').value = '';
    openTagManagerModal();
    initDropdownData();
  } catch (e) {}
}

// AI ASSISTANT CHAT FUNCTIONS
state.currentConversationId = null;

async function loadAssistantView() {
  // Update the chat sidebar user label
  if (state.currentUser) {
    const chatLabel = document.getElementById('chat-user-label');
    if (chatLabel) chatLabel.innerText = `${state.currentUser.username}'s private conversations`;
  }

  const conversations = await api('/conversations');
  const listContainer = document.getElementById('chat-conversations-list');
  if (!listContainer) return;

  if (conversations.length === 0) {
    listContainer.innerHTML = '<p style="color:var(--text-muted); font-size:0.85rem; padding:0.5rem;">No chats yet.</p>';
    state.currentConversationId = null;
    updateChatInputState();
    return;
  }

  listContainer.innerHTML = conversations.map(c => `
    <button class="chat-convo-btn ${state.currentConversationId === c.id ? 'active' : ''}" onclick="selectConversation(${c.id})">
      <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">💬 ${escapeHTML(c.title || `Chat #${c.id}`)}</span>
    </button>
  `).join('');

  if (!state.currentConversationId && conversations.length > 0) {
    state.currentConversationId = conversations[0].id;
  }
  if (state.currentConversationId) {
    selectConversation(state.currentConversationId);
  }

  initChatTextareaEvents();
}

function initChatTextareaEvents() {
  const textarea = document.getElementById('chat-message-input');
  if (!textarea || textarea.dataset.initialized) return;
  textarea.dataset.initialized = 'true';

  textarea.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const form = document.getElementById('chat-input-form');
      if (form) form.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });

  textarea.addEventListener('input', () => {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  });
}

async function createNewConversation() {
  try {
    const conv = await api('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: `Chat ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` })
    });
    state.currentConversationId = conv.id;
    loadAssistantView();
  } catch (e) {}
}

// messageTimings: {conversationId: [duration_s_per_assistant_turn, ...]}
if (!state.messageTimings) state.messageTimings = {};

function renderToolActionCard(name, parsed, rawContent) {
  if (!parsed || parsed.success === false) return null;

  const data = parsed.data !== undefined ? parsed.data : parsed;
  if (!data || typeof data !== 'object') return null;

  let icon = '⚡';
  let title = '';
  let subtitle = '';
  let tabTarget = '';
  let searchParam = '';
  let buttonLabel = 'View Item &rarr;';
  let borderColor = 'var(--accent-success, #22c55e)';

  switch (name) {
    case 'create_task': {
      icon = '✅';
      title = `Created Task: "${escapeHTML(data.title || 'New Task')}"`;
      const pLabel = {1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low'}[data.priority] || 'High';
      subtitle = `ID #${data.id || ''} &bull; Priority: ${pLabel} &bull; Status: ${escapeHTML(data.status || 'todo')}`;
      tabTarget = 'tasks';
      searchParam = data.title || '';
      buttonLabel = 'View in Tasks &rarr;';
      break;
    }
    case 'update_task':
    case 'complete_task': {
      icon = name === 'complete_task' ? '🎉' : '✏️';
      const actionName = name === 'complete_task' ? 'Completed Task' : 'Updated Task';
      title = `${actionName}: "${escapeHTML(data.title || ('Task #' + (data.id || '')))}"`;
      const pLabel = {1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low'}[data.priority] || 'Normal';
      subtitle = `ID #${data.id || ''} &bull; Status: ${escapeHTML(data.status || 'done')} &bull; Priority: ${pLabel}`;
      tabTarget = 'tasks';
      searchParam = data.title || '';
      buttonLabel = 'View in Tasks &rarr;';
      break;
    }
    case 'delete_task': {
      icon = '🗑️';
      title = 'Deleted Task';
      subtitle = escapeHTML(data.message || 'Task removed successfully');
      tabTarget = 'tasks';
      buttonLabel = 'Go to Tasks &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'create_reminder': {
      icon = '⏰';
      title = `Created Reminder: "${escapeHTML(data.message || 'Reminder')}"`;
      const timeStr = data.remind_at ? parseUTCDate(data.remind_at).toLocaleString() : '';
      subtitle = `ID #${data.id || ''}${timeStr ? ` &bull; Remind at: ${timeStr}` : ''}`;
      tabTarget = 'reminders';
      searchParam = data.message || '';
      buttonLabel = 'View in Reminders &rarr;';
      break;
    }
    case 'delete_reminder': {
      icon = '🗑️';
      title = 'Deleted Reminder';
      subtitle = escapeHTML(data.message || 'Reminder removed successfully');
      tabTarget = 'reminders';
      buttonLabel = 'Go to Reminders &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'create_schedule_item': {
      icon = '📅';
      title = `Scheduled: "${escapeHTML(data.title || 'Schedule Block')}"`;
      const startStr = data.starts_at ? parseUTCDate(data.starts_at).toLocaleString() : '';
      const endStr = data.ends_at ? parseUTCDate(data.ends_at).toLocaleString() : '';
      subtitle = `ID #${data.id || ''}${startStr && endStr ? ` &bull; ${startStr} &rarr; ${endStr}` : ''}`;
      tabTarget = 'schedule';
      searchParam = data.title || '';
      buttonLabel = 'View in Schedule &rarr;';
      break;
    }
    case 'delete_schedule_item': {
      icon = '🗑️';
      title = 'Deleted Schedule Block';
      subtitle = escapeHTML(data.message || 'Schedule item removed');
      tabTarget = 'schedule';
      buttonLabel = 'Go to Schedule &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'create_habit': {
      icon = '🌱';
      title = `Created Habit: "${escapeHTML(data.name || 'Habit')}"`;
      subtitle = `ID #${data.id || ''} &bull; Frequency: ${escapeHTML(data.frequency || 'daily')} &bull; Target: ${data.target_count || 1}/period`;
      tabTarget = 'habits';
      searchParam = data.name || '';
      buttonLabel = 'View in Habits &rarr;';
      break;
    }
    case 'complete_habit': {
      icon = '🔥';
      const hName = data.habit_name || (data.habit_id ? `Habit #${data.habit_id}` : 'Habit');
      title = `Recorded Habit Streak: "${escapeHTML(hName)}"`;
      subtitle = 'Logged completion for today &bull; Streak updated';
      tabTarget = 'habits';
      searchParam = data.habit_name || '';
      buttonLabel = 'View in Habits &rarr;';
      break;
    }
    case 'delete_habit': {
      icon = '🗑️';
      title = 'Deleted Habit Tracker';
      subtitle = escapeHTML(data.message || 'Habit and history removed');
      tabTarget = 'habits';
      buttonLabel = 'Go to Habits &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'create_project': {
      icon = '📁';
      title = `Created Project: "${escapeHTML(data.name || 'Project')}"`;
      subtitle = `ID #${data.id || ''}${data.description ? ` &bull; ${escapeHTML(data.description)}` : ' &bull; Active Project'}`;
      tabTarget = 'projects';
      searchParam = data.name || '';
      buttonLabel = 'View in Projects &rarr;';
      break;
    }
    case 'archive_project': {
      icon = '📦';
      title = `Archived Project: "${escapeHTML(data.name || 'Project')}"`;
      subtitle = `ID #${data.id || ''} &bull; Moved to project archives`;
      tabTarget = 'projects';
      buttonLabel = 'View in Projects &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'delete_project': {
      icon = '🗑️';
      title = 'Deleted Project';
      subtitle = escapeHTML(data.message || 'Project removed');
      tabTarget = 'projects';
      buttonLabel = 'Go to Projects &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'start_pomodoro': {
      icon = '⏱️';
      title = 'Started Pomodoro Focus Session';
      subtitle = `Session #${data.id || ''} &bull; Focus timer active`;
      tabTarget = 'pomodoro';
      buttonLabel = 'Open Pomodoro &rarr;';
      break;
    }
    case 'end_pomodoro': {
      icon = '🏁';
      title = 'Pomodoro Session Ended';
      subtitle = `Session #${data.id || ''} &bull; ${data.interrupted ? 'Interrupted' : 'Session completed successfully'}`;
      tabTarget = 'pomodoro';
      buttonLabel = 'View Pomodoro &rarr;';
      break;
    }
    case 'delete_pomodoro_session': {
      icon = '🗑️';
      title = 'Deleted Pomodoro Record';
      subtitle = escapeHTML(data.message || 'Session record removed');
      tabTarget = 'pomodoro';
      buttonLabel = 'Go to Pomodoro &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    case 'remember_information':
    case 'update_memory': {
      icon = '🧠';
      const actionName = name === 'remember_information' ? 'Saved Memory' : 'Updated Memory';
      const preview = (data.content || '').slice(0, 50);
      title = `${actionName}: "${escapeHTML(preview)}${data.content && data.content.length > 50 ? '...' : ''}"`;
      subtitle = `ID #${data.id || ''} &bull; Category: ${escapeHTML(data.category || 'preference')}`;
      tabTarget = 'memories';
      searchParam = data.content ? data.content.slice(0, 30) : '';
      buttonLabel = 'View in Memories &rarr;';
      break;
    }
    case 'delete_memory': {
      icon = '🗑️';
      title = 'Removed Memory';
      subtitle = escapeHTML(data.message || 'Memory archived or deleted');
      tabTarget = 'memories';
      buttonLabel = 'Go to Memories &rarr;';
      borderColor = 'var(--accent-warning, #f59e0b)';
      break;
    }
    default:
      return null;
  }

  return `
    <div class="chat-turn chat-turn-assistant">
      <div class="tool-action-card" style="background:var(--bg-card); border:1.5px solid ${borderColor}; border-radius:8px; padding:0.75rem 1rem; margin:0.4rem 0; display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; box-shadow:0 2px 4px rgba(0,0,0,0.05);">
        <div style="display:flex; align-items:center; gap:0.6rem; min-width:200px;">
          <span style="font-size:1.35rem;">${icon}</span>
          <div>
            <strong style="color:var(--text-primary); display:block; font-size:0.95rem;">${title}</strong>
            <span style="font-size:0.8rem; color:var(--text-secondary);">${subtitle}</span>
          </div>
        </div>
        <button class="btn btn-secondary btn-sm" data-target-tab="${tabTarget}" data-target-query="${escapeHTML(searchParam || '')}" onclick="switchTab(this.dataset.targetTab, this.dataset.targetQuery || undefined)" style="white-space:nowrap; cursor:pointer;">${buttonLabel}</button>
      </div>
      <details class="chat-tool-details" style="margin-top:0.25rem;">
        <summary class="chat-tool-summary" style="font-size:0.75rem;">⚙️ Tool Execution Details (${escapeHTML(name)})</summary>
        <pre class="chat-tool-content">${escapeHTML(rawContent)}</pre>
      </details>
    </div>
  `;
}

async function selectConversation(id, lastTurnDuration) {
  state.currentConversationId = id;
  if (typeof updateChatInputState === 'function') updateChatInputState();

  const conversations = await api('/conversations').catch(() => []);
  const currentConvo = conversations.find(c => c.id === id);
  if (currentConvo) {
    const titleEl = document.getElementById('chat-active-title');
    if (titleEl) titleEl.innerText = currentConvo.title || `Chat #${currentConvo.id}`;
  }

  const listContainer = document.getElementById('chat-conversations-list');
  if (listContainer && conversations.length > 0) {
    listContainer.innerHTML = conversations.map(c => `
      <button class="chat-convo-btn ${state.currentConversationId === c.id ? 'active' : ''}" onclick="selectConversation(${c.id})">
        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">💬 ${escapeHTML(c.title || `Chat #${c.id}`)}</span>
      </button>
    `).join('');
  }

  const messages = await api(`/conversations/${id}/messages`);
  const transcript = document.getElementById('chat-messages-transcript');
  if (!transcript) return;

  if (messages.length === 0) {
    transcript.innerHTML = `
      <div class="chat-empty-state">
        <div class="chat-empty-glyph">✦</div>
        <h3>${escapeHTML(currentConvo ? (currentConvo.title || 'Personal Assistant') : 'Personal Assistant')}</h3>
        <p>Conversation started. Ask a question, plan your day, or manage your schedule.</p>
      </div>
    `;
    return;
  }

  // Persist per-turn timing from the latest send call
  if (lastTurnDuration != null) {
    if (!state.messageTimings[id]) state.messageTimings[id] = [];
    state.messageTimings[id].push(lastTurnDuration);
  }
  const timings = state.messageTimings[id] || [];
  let assistantTurnIdx = 0;

  let hasPendingDestructive = false;
  let lastToolInfo = null;

  transcript.innerHTML = messages.map((m, idx) => {
    if (m.role === 'user') {
      return `
        <div class="chat-turn chat-turn-user">
          <div class="chat-msg-user">${escapeHTML(m.content)}</div>
        </div>
      `;
    } else if (m.role === 'assistant') {
      const isFinalTurn = !m.tool_calls;
      if (isFinalTurn) {
        const dur = timings[assistantTurnIdx];
        const timingBadge = dur != null
          ? `<span class="msg-timing-badge">⏱️ ${dur.toFixed(1)}s</span>`
          : '';
        assistantTurnIdx++;
        return `
          <div class="chat-turn chat-turn-assistant">
            <div class="chat-asst-header">
              <span class="chat-asst-avatar">✦</span>
              <span>Assistant</span>
              ${timingBadge}
            </div>
            <div class="chat-msg-assistant md-content">${renderMarkdown(m.content || '')}</div>
          </div>
        `;
      } else {
        return `
          <div class="chat-turn chat-turn-assistant">
            <div class="chat-asst-header">
              <span class="chat-asst-avatar">✦</span>
              <span>Assistant (Calling Tool)</span>
            </div>
            <details class="chat-tool-details">
              <summary class="chat-tool-summary">🛠️ Tool Call Request</summary>
              <pre class="chat-tool-content">${escapeHTML(m.tool_calls)}</pre>
            </details>
          </div>
        `;
      }
    } else if (m.role === 'tool') {
      let contentParsed = null;
      try {
        contentParsed = JSON.parse(m.content);
      } catch (e) {}

      const isPermDenied = contentParsed && contentParsed.success === false &&
        typeof contentParsed.error === 'string' && contentParsed.error.includes('Permission denied');

      if (isPermDenied && idx >= messages.length - 2) {
        hasPendingDestructive = true;
        lastToolInfo = m.name || 'action';
      }

      const cardHtml = renderToolActionCard(m.name, contentParsed, m.content);
      if (cardHtml) {
        return cardHtml;
      }

      return `
        <div class="chat-turn chat-turn-assistant">
          <details class="chat-tool-details">
            <summary class="chat-tool-summary">⚙️ Tool Output: ${escapeHTML(m.name || 'tool')}</summary>
            <pre class="chat-tool-content">${escapeHTML(m.content)}</pre>
          </details>
        </div>
      `;
    }
    return '';
  }).join('');

  if (hasPendingDestructive) {
    transcript.innerHTML += `
      <div class="chat-confirmation-box">
        <strong style="color:var(--accent-danger); display:block; margin-bottom:0.4rem;">⚠️ Confirmation Required</strong>
        <p style="font-size:0.88rem; color:var(--text-secondary); margin-bottom:0.75rem;">
          A destructive action (${escapeHTML(lastToolInfo || 'delete')}) was requested. Explicit user authorization is required to proceed.
        </p>
        <div style="display:flex; gap:0.5rem;">
          <button class="btn btn-danger btn-sm" onclick="confirmPendingDestructiveAction()">Confirm & Execute</button>
          <button class="btn btn-secondary btn-sm" onclick="cancelPendingDestructiveAction()">Cancel</button>
        </div>
      </div>
    `;
  }

  const scrollViewport = document.getElementById('chat-transcript-viewport');
  if (scrollViewport) {
    scrollViewport.scrollTop = scrollViewport.scrollHeight;
  }
}

let speechRecognition = null;
let isVoiceRecording = false;

function initVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    return null;
  }
  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  recognition.onstart = () => {
    isVoiceRecording = true;
    updateVoiceUI(true);
  };

  recognition.onresult = (event) => {
    let interimTranscript = '';
    let finalTranscript = '';
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }
    const input = document.getElementById('chat-message-input');
    if (input) {
      const text = (finalTranscript || interimTranscript).trim();
      if (text) {
        input.value = text;
        input.style.height = 'auto';
        input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
      }
    }
  };

  recognition.onerror = (event) => {
    console.warn('Speech recognition error:', event.error);
    isVoiceRecording = false;
    updateVoiceUI(false);
    if (event.error === 'not-allowed') {
      showToast('Microphone permission denied', 'error');
    } else if (event.error !== 'no-speech') {
      showToast(`Voice input error: ${event.error}`, 'warning');
    }
  };

  recognition.onend = () => {
    isVoiceRecording = false;
    updateVoiceUI(false);
  };

  return recognition;
}

function updateVoiceUI(recording) {
  const micBtn = document.getElementById('chat-mic-btn');
  const hint = document.getElementById('chat-input-hint');
  if (micBtn) {
    if (recording) {
      micBtn.classList.add('recording');
      micBtn.title = 'Stop listening';
    } else {
      micBtn.classList.remove('recording');
      micBtn.title = 'Voice input (Speech-to-Text)';
    }
  }
  if (hint) {
    if (recording) {
      hint.innerHTML = '<span class="voice-recording-hint">🔴 <strong>Listening...</strong> Speak clearly (click mic again to stop)</span>';
    } else {
      hint.innerHTML = 'Press <strong>Enter</strong> to send, <strong>Shift + Enter</strong> for a new line';
    }
  }
}

function toggleVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showToast('Voice input is not supported in this browser. Please use Chrome or Edge.', 'warning');
    return;
  }

  if (isVoiceRecording && speechRecognition) {
    try { speechRecognition.stop(); } catch (e) {}
    isVoiceRecording = false;
    updateVoiceUI(false);
    return;
  }

  if (!speechRecognition) {
    speechRecognition = initVoiceInput();
  }

  if (speechRecognition) {
    try {
      speechRecognition.start();
    } catch (e) {
      console.warn('Restarting speech recognition instance:', e);
      speechRecognition = initVoiceInput();
      try { speechRecognition.start(); } catch (err) {
        showToast('Could not start microphone', 'error');
      }
    }
  }
}

function updateChatInputState() {
  const input = document.getElementById('chat-message-input');
  const btn = document.getElementById('chat-send-btn');
  const micBtn = document.getElementById('chat-mic-btn');
  const enabled = state.currentConversationId != null;
  if (input) input.disabled = !enabled;
  if (btn) btn.disabled = !enabled;
  if (micBtn) micBtn.disabled = !enabled;
}

async function confirmPendingDestructiveAction() {
  await sendChatMessageText('Yes, I confirm and authorize this deletion.', true);
}

function cancelPendingDestructiveAction() {
  showToast('Destructive action cancelled', 'info');
  const boxes = document.querySelectorAll('.chat-confirmation-box');
  boxes.forEach(b => b.remove());
}

async function sendChatMessageText(text, authorizeDestructive = false) {
  if (!state.currentConversationId || !text) return;

  if (isVoiceRecording && speechRecognition) {
    try { speechRecognition.stop(); } catch (e) {}
    isVoiceRecording = false;
    updateVoiceUI(false);
  }

  const input = document.getElementById('chat-message-input');
  const sendBtn = document.getElementById('chat-send-btn');
  const micBtn = document.getElementById('chat-mic-btn');

  if (input) {
    input.value = '';
    input.style.height = 'auto';
    input.disabled = true;
  }
  if (sendBtn) sendBtn.disabled = true;
  if (micBtn) micBtn.disabled = true;

  const transcript = document.getElementById('chat-messages-transcript');
  if (transcript) {
    transcript.innerHTML += `
      <div class="chat-turn chat-turn-user">
        <div class="chat-msg-user">${escapeHTML(text)}</div>
      </div>
    `;
  }

  // Calculate rolling average
  let avgText = '';
  if (!state.responseTimes) state.responseTimes = [];
  if (state.responseTimes.length > 0) {
    const avg = (state.responseTimes.reduce((a, b) => a + b, 0) / state.responseTimes.length).toFixed(1);
    avgText = ` | avg: ${avg}s`;
  }

  const startTime = Date.now();
  if (transcript) {
    transcript.innerHTML += `
      <div id="chat-typing-indicator" class="chat-turn chat-turn-assistant">
        <div class="chat-asst-header">
          <span class="chat-asst-avatar">✦</span>
          <span>Assistant</span>
        </div>
        <div class="typing-indicator-container">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <span id="chat-typing-timer" class="typing-timer-text">Thinking... 0.0s${avgText}</span>
        </div>
      </div>
    `;
  }

  const scrollViewport = document.getElementById('chat-transcript-viewport');
  if (scrollViewport) scrollViewport.scrollTop = scrollViewport.scrollHeight;

  const timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    const timerEl = document.getElementById('chat-typing-timer');
    if (timerEl) {
      timerEl.innerText = `Thinking... ${elapsed}s${avgText}`;
    }
  }, 100);

  try {
    const response = await fetch(`/conversations/${state.currentConversationId}/messages?stream=true`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream'
      },
      body: JSON.stringify({
        role: 'user',
        content: text,
        authorize_destructive: authorizeDestructive
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedContent = '';
    let hasStartedStreamingText = false;
    let streamingBubbleEl = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop(); // retain partial line

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;
        const jsonStr = trimmed.slice(6);
        let eventData = null;
        try {
          eventData = JSON.parse(jsonStr);
        } catch (e) {
          continue;
        }

        if (eventData.event === 'status') {
          const statusTimerEl = document.getElementById('chat-typing-timer');
          if (statusTimerEl && eventData.name) {
            statusTimerEl.innerHTML = `⚙️ <strong>Executing:</strong> <code>${escapeHTML(eventData.name)}</code>...`;
          }
        } else if (eventData.event === 'tool_result') {
          const { name, arguments: args, result } = eventData;
          if (result && result.success) {
            const data = result.data || {};
            if (name === 'create_task') {
              const taskTitle = data.title || (args && args.title) || 'Task';
              showToast(`✅ Created Task: "${escapeHTML(taskTitle)}"`, 'success');
            } else if (name === 'delete_task') {
              showToast(`🗑️ Task deleted successfully`, 'info');
            } else if (name === 'update_task' || name === 'complete_task') {
              showToast(`✅ Task updated successfully`, 'success');
            } else if (name === 'create_reminder') {
              const msg = data.message || (args && args.message) || 'Reminder';
              showToast(`⏰ Created Reminder: "${escapeHTML(msg)}"`, 'success');
            } else if (name === 'delete_reminder') {
              showToast(`🗑️ Reminder deleted successfully`, 'info');
            } else if (name === 'create_schedule_item') {
              const schedTitle = data.title || (args && args.title) || 'Schedule Block';
              showToast(`📅 Scheduled: "${escapeHTML(schedTitle)}"`, 'success');
            } else if (name === 'delete_schedule_item') {
              showToast(`🗑️ Schedule block removed`, 'info');
            } else if (name === 'create_habit') {
              const hName = data.name || (args && args.name) || 'Habit';
              showToast(`🌱 Created Habit: "${escapeHTML(hName)}"`, 'success');
            } else if (name === 'complete_habit') {
              showToast(`🔥 Habit streak updated!`, 'success');
            } else if (name === 'delete_habit') {
              showToast(`🗑️ Habit deleted successfully`, 'info');
            } else if (name === 'create_project') {
              const pName = data.name || (args && args.name) || 'Project';
              showToast(`📁 Created Project: "${escapeHTML(pName)}"`, 'success');
            } else if (name === 'archive_project') {
              showToast(`📦 Project archived`, 'info');
            } else if (name === 'delete_project') {
              showToast(`🗑️ Project deleted successfully`, 'info');
            } else if (name === 'start_pomodoro') {
              showToast(`⏱️ Pomodoro session started!`, 'success');
              checkActivePomodoroSession();
            } else if (name === 'end_pomodoro') {
              showToast(`🏁 Pomodoro session ended`, 'info');
              checkActivePomodoroSession();
            } else if (name === 'delete_pomodoro_session') {
              showToast(`🗑️ Pomodoro session deleted`, 'info');
              checkActivePomodoroSession();
            } else if (name === 'remember_information') {
              showToast(`🧠 Saved new memory`, 'success');
            } else if (name === 'update_memory') {
              showToast(`🧠 Memory updated`, 'success');
            } else if (name === 'delete_memory') {
              showToast(`🗑️ Memory removed`, 'info');
            } else {
              showToast(`⚡ Executed: ${escapeHTML(name)}`, 'info');
            }

            initDropdownData();
            loadCurrentView();
          }
        } else if (eventData.event === 'delta') {
          const deltaContent = eventData.content || '';
          if (deltaContent) {
            accumulatedContent += deltaContent;

            if (!hasStartedStreamingText) {
              hasStartedStreamingText = true;
              const typingIndicator = document.getElementById('chat-typing-indicator');
              if (typingIndicator) typingIndicator.remove();

              const streamingTurn = document.createElement('div');
              streamingTurn.id = 'chat-streaming-turn';
              streamingTurn.className = 'chat-turn chat-turn-assistant';
              streamingTurn.innerHTML = `
                <div class="chat-asst-header">
                  <span class="chat-asst-avatar">✦</span>
                  <span>Assistant</span>
                  <span id="chat-live-timing" class="msg-timing-badge" style="opacity:0.8;">⏱️ streaming...</span>
                </div>
                <div id="chat-streaming-content" class="chat-msg-assistant md-content"></div>
              `;
              transcript.appendChild(streamingTurn);
              streamingBubbleEl = document.getElementById('chat-streaming-content');
            }

            if (streamingBubbleEl) {
              streamingBubbleEl.innerHTML = renderMarkdown(accumulatedContent);
            }
            if (scrollViewport) scrollViewport.scrollTop = scrollViewport.scrollHeight;
          }
        } else if (eventData.event === 'error') {
          throw new Error(eventData.error || 'Stream error from assistant');
        }
      }
    }

    const duration = (Date.now() - startTime) / 1000;
    state.responseTimes.push(duration);
    if (state.responseTimes.length > 10) state.responseTimes.shift();

    clearInterval(timerInterval);
    const indicator = document.getElementById('chat-typing-indicator');
    if (indicator) indicator.remove();
    const streamingTurn = document.getElementById('chat-streaming-turn');
    if (streamingTurn) streamingTurn.remove();

    updateChatInputState();
    await selectConversation(state.currentConversationId, duration);

    // Refresh any active dashboard domain view and all selects/dropdowns
    loadCurrentView();
    initDropdownData();
  } catch (err) {
    clearInterval(timerInterval);
    const indicator = document.getElementById('chat-typing-indicator');
    if (indicator) indicator.remove();
    const streamingTurn = document.getElementById('chat-streaming-turn');
    if (streamingTurn) streamingTurn.remove();
    updateChatInputState();

    // Re-sync authoritative server state from DB
    await selectConversation(state.currentConversationId);

    if (transcript) {
      transcript.innerHTML += `
        <div class="chat-turn chat-turn-assistant">
          <div class="chat-asst-header">
            <span class="chat-asst-avatar">✦</span>
            <span>Assistant</span>
          </div>
          <div class="chat-msg-assistant" style="color:var(--accent-danger);">⚠️ ${escapeHTML(err.message || 'Stream interrupted. Transcript synced with server.')}</div>
        </div>
      `;
    }
    if (scrollViewport) scrollViewport.scrollTop = scrollViewport.scrollHeight;
  }
}

async function handleSendChatMessage(e) {
  e.preventDefault();
  const input = document.getElementById('chat-message-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  // If user typed confirmation words or there is a visible confirmation box, set authorize_destructive = true
  const isConfirmWord = /^(yes|confirm|proceed|ok|delete it|do it|sure|authorized?)\b/i.test(text);
  const hasConfirmationBox = !!document.querySelector('.chat-confirmation-box');
  const authorizeDestructive = isConfirmWord || hasConfirmationBox;

  await sendChatMessageText(text, authorizeDestructive);
}

// Memories Management
async function loadMemoriesView(searchQuery) {
  const container = document.getElementById('memories-list-container');
  if (!container) return;
  container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">Loading memories...</p></div>';

  const category = document.getElementById('memory-filter-category')?.value || '';
  const includeArchived = document.getElementById('memory-filter-archived')?.checked || false;

  let url = `/memories?include_archived=${includeArchived}`;
  if (category) url += `&category=${encodeURIComponent(category)}`;

  try {
    const mems = await api(url);
    if (!mems || !mems.length) {
      container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No memories found.</p></div>';
      return;
    }

    const qLower = searchQuery ? searchQuery.toLowerCase() : null;

    container.innerHTML = mems.map(m => {
      const isMatch = qLower && ((m.content || '').toLowerCase().includes(qLower) || (m.category || '').toLowerCase().includes(qLower));
      return `
        <div class="card item-card ${!m.is_active ? 'archived-item' : ''} ${isMatch ? 'item-highlight' : ''}" id="memory-card-${m.id}">
          <div class="item-content">
            <div style="display:flex; gap:0.5rem; align-items:center; margin-bottom:0.4rem;">
              <span class="badge badge-info" style="text-transform:uppercase; font-size:0.75rem;">${escapeHTML(m.category)}</span>
              ${isMatch ? '<span class="badge badge-primary">Matched</span>' : ''}
              ${!m.is_active ? '<span class="badge badge-secondary" style="font-size:0.75rem;">Archived</span>' : ''}
              <span style="font-size:0.8rem; color:var(--text-muted);">${parseUTCDate(m.created_at).toLocaleDateString()}</span>
            </div>
            <div style="font-size:0.95rem; line-height:1.4;">${escapeHTML(m.content)}</div>
          </div>
          <div class="item-actions">
            <button class="btn btn-secondary btn-sm" onclick="openEditMemoryModal(${m.id}, '${escapeHTML(m.content).replace(/'/g, "\\'")}', '${m.category}')">Edit</button>
            ${m.is_active ? `<button class="btn btn-secondary btn-sm" onclick="archiveMemory(${m.id})">Archive</button>` : ''}
            <button class="btn btn-danger btn-sm" onclick="deleteMemory(${m.id})">Delete</button>
          </div>
        </div>
      `;
    }).join('');

    if (qLower) {
      const matchedEl = container.querySelector('.item-highlight');
      if (matchedEl) {
        setTimeout(() => matchedEl.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
      }
    }
  } catch (err) {}
}

function openCreateMemoryModal() {
  document.getElementById('memory-modal-title').innerText = 'New Memory Record';
  document.getElementById('memory-form-id').value = '';
  document.getElementById('memory-form-content').value = '';
  document.getElementById('memory-form-category').value = 'preference';
  openModal('memory-modal');
}

function openEditMemoryModal(id, content, category) {
  document.getElementById('memory-modal-title').innerText = 'Edit Memory Record';
  document.getElementById('memory-form-id').value = id;
  document.getElementById('memory-form-content').value = content;
  document.getElementById('memory-form-category').value = category;
  openModal('memory-modal');
}

async function handleMemoryFormSubmit(e) {
  e.preventDefault();
  const id = document.getElementById('memory-form-id').value;
  const content = document.getElementById('memory-form-content').value.trim();
  const category = document.getElementById('memory-form-category').value;

  if (!content) return;

  try {
    if (id) {
      await api(`/memories/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ content, category })
      });
      showToast('Memory updated successfully', 'success');
    } else {
      await api('/memories', {
        method: 'POST',
        body: JSON.stringify({ content, category })
      });
      showToast('Memory created successfully', 'success');
    }
    closeModal('memory-modal');
    await loadMemoriesView();
  } catch (err) {}
}

async function archiveMemory(id) {
  try {
    await api(`/memories/${id}/archive`, { method: 'POST' });
    showToast('Memory archived', 'success');
    await loadMemoriesView();
  } catch (err) {}
}

async function deleteMemory(id) {
  if (!confirm('Are you sure you want to permanently delete this memory?')) return;
  try {
    await api(`/memories/${id}`, { method: 'DELETE' });
    showToast('Memory deleted successfully', 'success');
    await loadMemoriesView();
  } catch (err) {
    console.error('Failed to delete memory:', err);
  }
}


