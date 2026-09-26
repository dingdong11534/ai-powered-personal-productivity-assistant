/**
 * Personal Productivity Assistant - Single Page Application Core
 */

// Global State
const state = {
  currentTab: 'dashboard',
  activePomodoro: null,
  pomodoroInterval: null,
  allProjects: [],
  allTags: [],
  allTasks: [],
  responseTimes: [],
  chatTimerInterval: null,
  pendingDestructiveAction: false,
  aiStatus: null
};

// UI Initialization
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initTheme();
  initSearch();
  initDropdownData();
  loadCurrentView();
  loadAIMode();

  // Auto-refresh when tab/window regains focus to eliminate stale data
  window.addEventListener('focus', () => {
    if (state.currentTab !== 'assistant') {
      loadCurrentView();
    }
    initDropdownData();
    loadAIMode();
  });
});

// AI Mode Management
async function loadAIMode() {
  try {
    const status = await api('/ai/mode');
    updateAIModeUI(status);
  } catch (e) {}
}

function updateAIModeUI(status) {
  if (!status) return;
  state.aiStatus = status;
  const isOnline = status.mode === 'online';
  const labelText = isOnline
    ? `🌐 Online (${status.active_provider === 'groq' ? 'Groq' : 'Cloud'})`
    : `💻 Offline (${status.active_model || 'Ollama'})`;
  const btnClass = isOnline ? 'ai-mode-switch-btn mode-online' : 'ai-mode-switch-btn mode-offline';
  const tooltip = isOnline
    ? `Online Mode Active: ${status.active_model} via ${status.active_provider}. Click to switch to Offline (Local Ollama).`
    : `Offline Mode Active: ${status.active_model} via local Ollama. Click to switch to Online (Cloud API).`;

  const globalBtn = document.getElementById('global-ai-mode-btn');
  const globalText = document.getElementById('global-ai-mode-text');
  if (globalBtn && globalText) {
    globalBtn.className = btnClass;
    globalBtn.title = tooltip;
    globalText.innerText = labelText;
  }

  const asstBtn = document.getElementById('assistant-ai-mode-btn');
  const asstText = document.getElementById('assistant-ai-mode-text');
  if (asstBtn && asstText) {
    asstBtn.className = btnClass;
    asstBtn.title = tooltip;
    asstText.innerText = labelText;
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
    showToast(newMode === 'online' ? 'Switched to 🌐 Online Mode (Groq)' : 'Switched to 💻 Offline Mode (Local Ollama)', 'success');
  } catch (err) {
    showToast('Failed to switch AI mode', 'error');
  }
}

// Toast Notifications
function showToast(message, type = 'error') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
    <span>${escapeHTML(message)}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
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
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  try {
    const res = await fetch(path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const errorMsg = data.detail || `Request failed with status ${res.status}`;
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
      switchTab(target);
    });
  });
}

function switchTab(tabName, param) {
  state.currentTab = tabName;
  document.querySelectorAll('.nav-item button').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`.nav-item button[data-target="${tabName}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  const activeSec = document.getElementById(`section-${tabName}`);
  if (activeSec) activeSec.classList.add('active');

  document.getElementById('page-title').innerText = tabName.charAt(0).toUpperCase() + tabName.slice(1);
  loadCurrentView(param);
}

function loadCurrentView(param) {
  switch (state.currentTab) {
    case 'dashboard': loadDashboardView(); break;
    case 'tasks': loadTasksView(param); break;
    case 'projects': loadProjectsView(); break;
    case 'habits': loadHabitsView(); break;
    case 'pomodoro': loadPomodoroView(); break;
    case 'schedule': loadScheduleView(); break;
    case 'reminders': loadRemindersView(); break;
    case 'notifications': loadNotificationsView(); break;
    case 'memories': loadMemoriesView(); break;
    case 'assistant': loadAssistantView(); break;
    case 'settings': break;
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
    debounceTimer = setTimeout(() => performSearch(q, dropdown), 250);
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const q = input.value.trim();
      if (q) {
        dropdown.style.display = 'none';
        switchTab('tasks', q);
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

async function performSearch(q, dropdown) {
  try {
    const encoded = encodeURIComponent(q);
    const [tasks, projects, memories] = await Promise.all([
      api(`/tasks?search=${encoded}`).catch(() => []),
      api('/projects?include_archived=false').catch(() => []),
      api('/memories?include_archived=false').catch(() => [])
    ]);

    const qLower = q.toLowerCase();
    const matchedProjects = (projects || []).filter(p =>
      (p.name || '').toLowerCase().includes(qLower) ||
      (p.description || '').toLowerCase().includes(qLower)
    );
    const matchedMemories = (memories || []).filter(m =>
      (m.content || '').toLowerCase().includes(qLower) ||
      (m.category || '').toLowerCase().includes(qLower)
    );

    const totalResults = (tasks || []).length + matchedProjects.length + matchedMemories.length;
    if (totalResults === 0) {
      dropdown.innerHTML = `<div class="search-no-results">No results for "${escapeHTML(q)}"</div>`;
      dropdown.style.display = 'block';
      return;
    }

    let html = '';
    if (tasks && tasks.length > 0) {
      html += `<div class="search-section-label">Tasks (${tasks.length})</div>`;
      html += tasks.slice(0, 5).map(t => `
        <div class="search-result-item" onclick="switchTab('tasks', '${escapeHTML(t.title)}'); document.getElementById('global-search-dropdown').style.display='none'; document.getElementById('global-search-input').value=''">
          <span class="search-result-icon">✏️</span>
          <div>
            <div class="search-result-title">${escapeHTML(t.title)}</div>
            <div class="search-result-sub">${escapeHTML(t.status)} · Priority ${t.priority}</div>
          </div>
        </div>
      `).join('');
    }
    if (matchedProjects.length > 0) {
      html += `<div class="search-section-label">Projects (${matchedProjects.length})</div>`;
      html += matchedProjects.slice(0, 3).map(p => `
        <div class="search-result-item" onclick="switchTab('projects'); document.getElementById('global-search-dropdown').style.display='none'; document.getElementById('global-search-input').value=''">
          <span class="search-result-icon">📁</span>
          <div>
            <div class="search-result-title">${escapeHTML(p.name)}</div>
            <div class="search-result-sub">${escapeHTML(p.description || 'No description')}</div>
          </div>
        </div>
      `).join('');
    }
    if (matchedMemories.length > 0) {
      html += `<div class="search-section-label">Memories (${matchedMemories.length})</div>`;
      html += matchedMemories.slice(0, 3).map(m => `
        <div class="search-result-item" onclick="switchTab('memories'); document.getElementById('global-search-dropdown').style.display='none'; document.getElementById('global-search-input').value=''">
          <span class="search-result-icon">🧠</span>
          <div>
            <div class="search-result-title">${escapeHTML((m.content || '').slice(0, 60))}${(m.content || '').length > 60 ? '…' : ''}</div>
            <div class="search-result-sub">${escapeHTML(m.category || 'memory')}</div>
          </div>
        </div>
      `).join('');
    }

    dropdown.innerHTML = html;
    dropdown.style.display = 'block';
  } catch (e) {
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
    const [tasks, habits, reminders, scheduleItems] = await Promise.all([
      api('/tasks'),
      api('/habits?include_archived=false'),
      api('/reminders?upcoming=true'),
      api('/schedule')
    ]);

    const pendingTasks = tasks.filter(t => t.status !== 'done' && t.status !== 'cancelled');
    document.getElementById('dash-tasks-pending-count').innerText = pendingTasks.length;
    document.getElementById('dash-habits-active-count').innerText = habits.length;
    document.getElementById('dash-reminders-due-count').innerText = reminders.length;
    document.getElementById('dash-schedule-count').innerText = scheduleItems.length;

    renderTaskList(pendingTasks.slice(0, 5), 'dash-todays-tasks-list');
    renderRemindersDashboardList(reminders.slice(0, 5));

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
  } catch (e) {}
}

function renderRemindersDashboardList(reminders) {
  const container = document.getElementById('dash-reminders-list');
  if (reminders.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No upcoming reminders.</p></div>';
    return;
  }
  container.innerHTML = reminders.map(r => `
    <div class="item-card">
      <div class="item-main">
        <div>
          <div class="item-title">${escapeHTML(r.message)}</div>
          <div class="item-subtitle">Remind at: ${new Date(r.remind_at).toLocaleString()}</div>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="fireReminder(${r.id})">Fire</button>
    </div>
  `).join('');
}

// 2. TASKS VIEW
async function loadTasksView(searchQuery) {
  await initDropdownData();
  const status = document.getElementById('task-filter-status').value;
  const priority = document.getElementById('task-filter-priority').value;
  const projectId = document.getElementById('task-filter-project').value;
  const tagId = document.getElementById('task-filter-tag').value;

  let query = '/tasks?';
  if (status) query += `status=${status}&`;
  if (priority) query += `priority=${priority}&`;
  if (projectId) query += `project_id=${projectId}&`;
  if (tagId) query += `tag_id=${tagId}&`;
  if (searchQuery) query += `search=${encodeURIComponent(searchQuery)}&`;

  const tasks = await api(query);
  renderTaskList(tasks, 'tasks-list-container');
}

function renderTaskList(tasks, containerId) {
  const container = document.getElementById(containerId);
  if (tasks.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No tasks found.</p></div>';
    return;
  }

  const priorityLabels = { 1: 'Critical', 2: 'High', 3: 'Medium', 4: 'Low' };

  container.innerHTML = tasks.map(t => {
    const isDone = t.status === 'done';
    const proj = state.allProjects.find(p => p.id === t.project_id);
    return `
      <div class="item-card">
        <div class="item-main">
          <input type="checkbox" ${isDone ? 'checked' : ''} onchange="toggleTaskComplete(${t.id}, ${!isDone})" style="width:18px; height:18px; cursor:pointer;">
          <div>
            <div class="item-title" style="${isDone ? 'text-decoration:line-through; opacity:0.6;' : ''}">
              ${escapeHTML(t.title)}
            </div>
            <div class="item-subtitle">
              <span class="badge badge-priority-${t.priority}">${priorityLabels[t.priority]}</span>
              <span class="badge badge-status-${t.status}">${t.status.replace('_', ' ')}</span>
              ${proj ? `<span class="tag-pill">📁 ${escapeHTML(proj.name)}</span>` : ''}
              ${t.deadline ? `<span style="margin-left:0.5rem; color:var(--text-muted);">⏰ ${new Date(t.deadline).toLocaleString()}</span>` : ''}
            </div>
            ${t.description ? `<p style="font-size:0.85rem; color:var(--text-secondary); margin-top:0.2rem;">${escapeHTML(t.description)}</p>` : ''}
          </div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="openTaskDepsModal(${t.id})">Deps/Tags</button>
          <button class="btn btn-secondary btn-sm" onclick="openEditTaskModal(${t.id})">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteTask(${t.id})">Delete</button>
        </div>
      </div>
    `;
  }).join('');
}

async function toggleTaskComplete(taskId, markDone) {
  try {
    const newStatus = markDone ? 'done' : 'todo';
    await api(`/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify({ status: newStatus })
    });
    showToast(`Task status updated to ${newStatus}`, 'success');
    loadCurrentView();
  } catch (e) {}
}

async function deleteTask(taskId) {
  if (!confirm('Are you sure you want to delete this task? This cannot be undone.')) return;
  try {
    await api(`/tasks/${taskId}`, { method: 'DELETE' });
    showToast('Task deleted', 'success');
    loadCurrentView();
  } catch (e) {}
}

// 3. PROJECTS VIEW
async function loadProjectsView() {
  const includeArchived = document.getElementById('projects-include-archived').checked;
  const projects = await api(`/projects?include_archived=${includeArchived}`);
  state.allProjects = projects;

  const container = document.getElementById('projects-grid-container');
  if (projects.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No projects found.</p></div>';
    return;
  }

  container.innerHTML = projects.map(p => `
    <div class="card" style="border-left: 4px solid ${p.color || 'var(--accent-primary)'};">
      <div class="page-header" style="margin-bottom:0.5rem;">
        <h3 style="font-size:1.1rem;">${escapeHTML(p.name)}</h3>
        ${p.archived_at ? '<span class="badge badge-status-cancelled">Archived</span>' : ''}
      </div>
      <p class="card-desc">${escapeHTML(p.description || 'No description.')}</p>
      <div style="margin-top:1.5rem; display:flex; justify-content:space-between; align-items:center;">
        <button class="btn btn-secondary btn-sm" onclick="viewProjectTasks(${p.id}, '${escapeHTML(p.name)}')">View Tasks</button>
        <div style="display:flex; gap:0.4rem;">
          <button class="btn btn-secondary btn-sm" onclick="openEditProjectModal(${p.id})">Edit</button>
          ${!p.archived_at ? `<button class="btn btn-secondary btn-sm" onclick="archiveProject(${p.id})">Archive</button>` : `<button class="btn btn-secondary btn-sm" onclick="unarchiveProject(${p.id})">Unarchive</button>`}
          <button class="btn btn-danger btn-sm" onclick="deleteProject(${p.id})">Delete</button>
        </div>
      </div>
    </div>
  `).join('');
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
    loadProjectsView();
  } catch (e) {}
}

async function unarchiveProject(id) {
  try {
    await api(`/projects/${id}/unarchive`, { method: 'POST' });
    showToast('Project restored to active', 'success');
    loadProjectsView();
  } catch (e) {}
}

async function deleteProject(id) {
  if (!confirm('Are you sure you want to delete this project? Associated tasks will be kept and unlinked. This cannot be undone.')) return;
  try {
    await api(`/projects/${id}`, { method: 'DELETE' });
    showToast('Project deleted', 'success');
    loadProjectsView();
    initDropdownData();
  } catch (e) {}
}

// 4. HABITS VIEW
async function loadHabitsView() {
  const includeArchived = document.getElementById('habits-include-archived').checked;
  const habits = await api(`/habits?include_archived=${includeArchived}`);

  const container = document.getElementById('habits-list-container');
  if (habits.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No habits created yet.</p></div>';
    return;
  }

  const habitCardsHtml = await Promise.all(habits.map(async h => {
    const stats = await api(`/habits/${h.id}/statistics`).catch(() => ({ current_streak: 0, completion_rate: 0, total_completions: 0 }));
    const isArchived = h.archived_at != null;

    return `
      <div class="item-card">
        <div class="item-main">
          <div>
            <div class="item-title">${escapeHTML(h.name)} ${isArchived ? '<span class="badge badge-status-cancelled">Archived</span>' : ''}</div>
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
}

async function recordHabitCompletion(habitId) {
  try {
    await api(`/habits/${habitId}/complete`, { method: 'POST', body: JSON.stringify({}) });
    showToast('Habit completion recorded!', 'success');
    loadHabitsView();
  } catch (e) {}
}

async function archiveHabit(habitId) {
  if (!confirm('Archive this habit?')) return;
  try {
    await api(`/habits/${habitId}/archive`, { method: 'POST' });
    showToast('Habit archived', 'success');
    loadHabitsView();
  } catch (e) {}
}

async function unarchiveHabit(habitId) {
  try {
    await api(`/habits/${habitId}/unarchive`, { method: 'POST' });
    showToast('Habit restored to active', 'success');
    loadHabitsView();
  } catch (e) {}
}

async function deleteHabit(habitId) {
  if (!confirm('Are you sure you want to delete this habit and all its completions? This cannot be undone.')) return;
  try {
    await api(`/habits/${habitId}`, { method: 'DELETE' });
    showToast('Habit deleted', 'success');
    loadHabitsView();
  } catch (e) {}
}

// 5. POMODORO VIEW
async function loadPomodoroView() {
  const sessions = await api('/pomodoro');
  const activeSession = sessions.find(s => s.ended_at === null);

  state.activePomodoro = activeSession;
  updatePomodoroUI();

  const historyContainer = document.getElementById('pomodoro-history-list');
  const pastSessions = sessions.filter(s => s.ended_at !== null).reverse();

  if (pastSessions.length === 0) {
    historyContainer.innerHTML = '<p style="color:var(--text-muted);">No past sessions.</p>';
    return;
  }

  historyContainer.innerHTML = pastSessions.map(s => {
    const mins = Math.floor((s.duration_seconds || 0) / 60);
    const secs = (s.duration_seconds || 0) % 60;
    return `
      <div class="item-card">
        <div>
          <div class="item-title">Session #${s.id} ${s.interrupted ? '<span class="badge badge-status-cancelled">Interrupted</span>' : '<span class="badge badge-status-done">Completed</span>'}</div>
          <div class="item-subtitle">Started: ${new Date(s.started_at).toLocaleTimeString()} | Duration: ${mins}m ${secs}s</div>
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
    loadPomodoroView();
  } catch (e) {}
}

function updatePomodoroUI() {
  const timerDisplay = document.getElementById('pomodoro-timer-display');
  const statusText = document.getElementById('pomodoro-status-text');
  const startBtn = document.getElementById('pomo-start-btn');
  const endBtn = document.getElementById('pomo-end-btn');
  const interruptBtn = document.getElementById('pomo-interrupt-btn');

  if (state.pomodoroInterval) clearInterval(state.pomodoroInterval);

  if (!state.activePomodoro) {
    timerDisplay.innerText = '25:00';
    statusText.innerText = 'No active session';
    startBtn.style.display = 'inline-flex';
    endBtn.style.display = 'none';
    interruptBtn.style.display = 'none';
  } else {
    startBtn.style.display = 'none';
    endBtn.style.display = 'inline-flex';
    interruptBtn.style.display = 'inline-flex';

    const startTime = new Date(state.activePomodoro.started_at).getTime();
    const durationMs = 25 * 60 * 1000;

    const updateClock = () => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, durationMs - elapsed);

      const mins = String(Math.floor(remaining / 60000)).padStart(2, '0');
      const secs = String(Math.floor((remaining % 60000) / 1000)).padStart(2, '0');

      timerDisplay.innerText = `${mins}:${secs}`;
      statusText.innerText = `Focus Session #${state.activePomodoro.id} in progress`;
    };

    updateClock();
    state.pomodoroInterval = setInterval(updateClock, 1000);
  }
}

async function startPomodoroSession() {
  try {
    const session = await api('/pomodoro', { method: 'POST', body: JSON.stringify({}) });
    state.activePomodoro = session;
    showToast('Pomodoro focus session started!', 'success');
    loadPomodoroView();
  } catch (e) {}
}

async function endPomodoroSession(interrupted = false) {
  if (!state.activePomodoro) return;
  try {
    await api(`/pomodoro/${state.activePomodoro.id}/end`, {
      method: 'POST',
      body: JSON.stringify({ interrupted })
    });
    showToast(interrupted ? 'Session interrupted' : 'Session complete! Great work!', interrupted ? 'error' : 'success');
    state.activePomodoro = null;
    loadPomodoroView();
  } catch (e) {}
}

// 6. SCHEDULE VIEW
async function loadScheduleView() {
  const [items, conflicts] = await Promise.all([
    api('/schedule'),
    api('/schedule/conflicts')
  ]);

  const notice = document.getElementById('schedule-conflicts-notice');
  if (conflicts.length > 0) {
    notice.innerHTML = `<div class="card" style="border-color:var(--accent-warning); background:rgba(245,158,11,0.1);">
      <strong style="color:var(--accent-warning);">⚠️ Warning: ${conflicts.length} schedule conflict(s) detected.</strong>
    </div>`;
  } else {
    notice.innerHTML = '';
  }

  const container = document.getElementById('schedule-list-container');
  if (items.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No schedule items.</p></div>';
    return;
  }

  container.innerHTML = items.map(s => `
    <div class="item-card">
      <div class="item-main">
        <div>
          <div class="item-title">${escapeHTML(s.title)}</div>
          <div class="item-subtitle">📅 ${new Date(s.starts_at).toLocaleString()} ➔ ${new Date(s.ends_at).toLocaleString()}</div>
        </div>
      </div>
      <div class="item-actions">
        <button class="btn btn-secondary btn-sm" onclick="openEditScheduleModal(${s.id})">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="deleteScheduleItem(${s.id})">Delete</button>
      </div>
    </div>
  `).join('');
}

async function deleteScheduleItem(id) {
  if (!confirm('Are you sure you want to delete this schedule item? This cannot be undone.')) return;
  try {
    await api(`/schedule/${id}`, { method: 'DELETE' });
    showToast('Schedule item deleted', 'success');
    loadScheduleView();
  } catch (e) {}
}

// 7. REMINDERS VIEW
async function loadRemindersView() {
  const reminders = await api('/reminders');
  const container = document.getElementById('reminders-list-container');
  if (reminders.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No reminders found.</p></div>';
    return;
  }

  container.innerHTML = reminders.map(r => `
    <div class="item-card">
      <div class="item-main">
        <div>
          <div class="item-title">${escapeHTML(r.message)} ${r.fired_at ? '<span class="badge badge-status-done">Fired</span>' : '<span class="badge badge-status-todo">Pending</span>'}</div>
          <div class="item-subtitle">Remind at: ${new Date(r.remind_at).toLocaleString()}</div>
        </div>
      </div>
      <div class="item-actions">
        ${!r.fired_at ? `<button class="btn btn-primary btn-sm" onclick="fireReminder(${r.id})">Fire Now</button>` : ''}
        <button class="btn btn-danger btn-sm" onclick="deleteReminder(${r.id})">Delete</button>
      </div>
    </div>
  `).join('');
}

async function fireReminder(id) {
  try {
    await api(`/reminders/${id}/fire`, { method: 'POST' });
    showToast('Reminder fired!', 'success');
    loadCurrentView();
  } catch (e) {}
}

async function deleteReminder(id) {
  if (!confirm('Are you sure you want to delete this reminder? This cannot be undone.')) return;
  try {
    await api(`/reminders/${id}`, { method: 'DELETE' });
    showToast('Reminder deleted', 'success');
    loadRemindersView();
  } catch (e) {}
}

// 8. NOTIFICATIONS VIEW
async function loadNotificationsView() {
  const unreadOnly = document.getElementById('notifications-unread-only').checked;
  const notifications = await api(`/notifications?unread_only=${unreadOnly}`);

  const container = document.getElementById('notifications-list-container');
  if (notifications.length === 0) {
    container.innerHTML = '<div class="card"><p style="color:var(--text-muted);">No notifications.</p></div>';
    return;
  }

  container.innerHTML = notifications.map(n => `
    <div class="item-card">
      <div class="item-main">
        <div>
          <div class="item-title">${escapeHTML(n.title)} ${!n.read_at ? '<span class="badge badge-priority-1">Unread</span>' : ''}</div>
          <div class="item-subtitle">${escapeHTML(n.body || '')} • ${new Date(n.created_at).toLocaleString()}</div>
        </div>
      </div>
      <div class="item-actions">
        <button class="btn btn-secondary btn-sm" onclick="toggleNotificationRead(${n.id}, ${!n.read_at})">
          ${n.read_at ? 'Mark Unread' : 'Mark Read'}
        </button>
      </div>
    </div>
  `).join('');
}

async function toggleNotificationRead(id, markRead) {
  try {
    const action = markRead ? 'read' : 'unread';
    await api(`/notifications/${id}/${action}`, { method: 'POST' });
    loadNotificationsView();
  } catch (e) {}
}

async function updateNotificationDot() {
  try {
    const unread = await api('/notifications?unread_only=true');
    const dot = document.getElementById('unread-notification-dot');
    if (dot) dot.style.display = unread.length > 0 ? 'block' : 'none';
  } catch (e) {}
}

// MODAL CONTROLS & FORMS
function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('active');
}

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('active');
}

// Task Modal
function openCreateTaskModal() {
  document.getElementById('task-modal-title').innerText = 'Create Task';
  document.getElementById('task-form-id').value = '';
  document.getElementById('task-form-title').value = '';
  document.getElementById('task-form-desc').value = '';
  document.getElementById('task-form-status').value = 'todo';
  document.getElementById('task-form-priority').value = '2';
  document.getElementById('task-form-project').value = '';
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

async function selectConversation(id, lastTurnDuration) {
  state.currentConversationId = id;
  updateChatInputState();

  const conversations = await api('/conversations').catch(() => []);
  const currentConvo = conversations.find(c => c.id === id);
  const titleEl = document.getElementById('chat-active-title');
  if (titleEl) {
    titleEl.innerText = currentConvo ? (currentConvo.title || `Chat #${id}`) : 'Conversation';
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

function updateChatInputState() {
  const input = document.getElementById('chat-message-input');
  const btn = document.getElementById('chat-send-btn');
  const enabled = state.currentConversationId != null;
  if (input) input.disabled = !enabled;
  if (btn) btn.disabled = !enabled;
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

  const input = document.getElementById('chat-message-input');
  const sendBtn = document.getElementById('chat-send-btn');

  if (input) {
    input.value = '';
    input.style.height = 'auto';
    input.disabled = true;
  }
  if (sendBtn) sendBtn.disabled = true;

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
            statusTimerEl.innerHTML = `⚙️ <strong>Calling tool:</strong> <code>${escapeHTML(eventData.name)}</code>...`;
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

    // Refresh any active dashboard domain view
    loadCurrentView();
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

  // If user typed confirmation words and there is a visible confirmation box, set authorize_destructive = true
  const isConfirmWord = /^(yes|confirm|proceed|ok|delete it|do it|sure)\b/i.test(text);
  const hasConfirmationBox = !!document.querySelector('.chat-confirmation-box');
  const authorizeDestructive = isConfirmWord && hasConfirmationBox;

  await sendChatMessageText(text, authorizeDestructive);
}

// Memories Management
async function loadMemoriesView() {
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
    container.innerHTML = mems.map(m => `
      <div class="card item-card ${!m.is_active ? 'archived-item' : ''}">
        <div class="item-content">
          <div style="display:flex; gap:0.5rem; align-items:center; margin-bottom:0.4rem;">
            <span class="badge badge-info" style="text-transform:uppercase; font-size:0.75rem;">${escapeHTML(m.category)}</span>
            ${!m.is_active ? '<span class="badge badge-secondary" style="font-size:0.75rem;">Archived</span>' : ''}
            <span style="font-size:0.8rem; color:var(--text-muted);">${new Date(m.created_at).toLocaleDateString()}</span>
          </div>
          <div style="font-size:0.95rem; line-height:1.4;">${escapeHTML(m.content)}</div>
        </div>
        <div class="item-actions">
          <button class="btn btn-secondary btn-sm" onclick="openEditMemoryModal(${m.id}, '${escapeHTML(m.content).replace(/'/g, "\\'")}', '${m.category}')">Edit</button>
          ${m.is_active ? `<button class="btn btn-secondary btn-sm" onclick="archiveMemory(${m.id})">Archive</button>` : ''}
          <button class="btn btn-danger btn-sm" onclick="deleteMemory(${m.id})">Delete</button>
        </div>
      </div>
    `).join('');
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
    loadMemoriesView();
  } catch (err) {}
}

async function archiveMemory(id) {
  try {
    await api(`/memories/${id}/archive`, { method: 'POST' });
    showToast('Memory archived', 'success');
    loadMemoriesView();
  } catch (err) {}
}

async function deleteMemory(id) {
  if (!confirm('Are you sure you want to permanently delete this memory?')) return;
  try {
    await api(`/memories/${id}`, { method: 'DELETE' });
    showToast('Memory deleted', 'success');
    loadMemoriesView();
  } catch (err) {}
}


