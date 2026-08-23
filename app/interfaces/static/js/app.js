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
  allTasks: []
};

// UI Initialization
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initTheme();
  initSearch();
  initDropdownData();
  loadCurrentView();
});

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

function switchTab(tabName) {
  state.currentTab = tabName;
  document.querySelectorAll('.nav-item button').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`.nav-item button[data-target="${tabName}"]`);
  if (activeBtn) activeBtn.classList.add('active');

  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  const activeSec = document.getElementById(`section-${tabName}`);
  if (activeSec) activeSec.classList.add('active');

  document.getElementById('page-title').innerText = tabName.charAt(0).toUpperCase() + tabName.slice(1);
  loadCurrentView();
}

function loadCurrentView() {
  switch (state.currentTab) {
    case 'dashboard': loadDashboardView(); break;
    case 'tasks': loadTasksView(); break;
    case 'projects': loadProjectsView(); break;
    case 'habits': loadHabitsView(); break;
    case 'pomodoro': loadPomodoroView(); break;
    case 'schedule': loadScheduleView(); break;
    case 'reminders': loadRemindersView(); break;
    case 'notifications': loadNotificationsView(); break;
    case 'settings': break;
  }
  updateNotificationDot();
}

// Theme Handling
function initTheme() {
  const theme = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', theme);
  const select = document.getElementById('setting-theme-select');
  if (select) select.value = theme;

  document.getElementById('theme-toggle-btn').addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    changeTheme(next);
  });
}

function changeTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
  const select = document.getElementById('setting-theme-select');
  if (select) select.value = theme;
}

// Search
function initSearch() {
  const input = document.getElementById('global-search-input');
  input.addEventListener('keypress', e => {
    if (e.key === 'Enter') {
      const q = input.value.trim();
      if (q) {
        switchTab('tasks');
        document.getElementById('tasks-list-container').innerHTML = `<p>Searching for "${escapeHTML(q)}"...</p>`;
        api(`/tasks?search=${encodeURIComponent(q)}`).then(tasks => renderTaskList(tasks, 'tasks-list-container'));
      }
    }
  });
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
async function loadTasksView() {
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
  if (!confirm('Are you sure you want to delete this task?')) return;
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
        <div>
          <button class="btn btn-secondary btn-sm" onclick="openEditProjectModal(${p.id})">Edit</button>
          ${!p.archived_at ? `<button class="btn btn-danger btn-sm" onclick="archiveProject(${p.id})">Archive</button>` : ''}
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
          ${!isArchived ? `<button class="btn btn-secondary btn-sm" onclick="archiveHabit(${h.id})">Archive</button>` : ''}
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
      </div>
    `;
  }).join('');
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
  if (!confirm('Delete schedule item?')) return;
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
  if (!confirm('Delete reminder?')) return;
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
  depsList.innerHTML = deps.map(d => `<div class="item-card"><div class="item-title">Depends on Task #${d.depends_on_task_id}</div><button class="btn btn-danger btn-sm" onclick="removeDependency(${taskId}, ${d.depends_on_task_id})">Remove</button></div>`).join('') || '<p style="color:var(--text-muted);">No direct dependencies.</p>';

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
