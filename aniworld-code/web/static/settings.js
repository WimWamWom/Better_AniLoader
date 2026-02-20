// Download path settings
const downloadPathInput = document.getElementById('downloadPath');
const langSeparationCb = document.getElementById('langSeparation');
const disableEnglishSubCb = document.getElementById('disableEnglishSub');

async function loadSettings() {
  try {
    const resp = await fetch('/api/settings');
    const data = await resp.json();
    downloadPathInput.value = data.download_path || '';
    if (langSeparationCb) langSeparationCb.checked = data.lang_separation === '1';
    if (disableEnglishSubCb) disableEnglishSubCb.checked = data.disable_english_sub === '1';
  } catch (e) {
    showToast('Failed to load settings: ' + e.message);
  }
}

async function saveLangSeparation() {
  try {
    const resp = await fetch('/api/settings', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        download_path: downloadPathInput.value.trim(),
        lang_separation: langSeparationCb.checked
      })
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error); return; }
    showToast('Language separation ' + (langSeparationCb.checked ? 'enabled' : 'disabled'));
  } catch (e) {
    showToast('Failed to save setting: ' + e.message);
  }
}

async function saveDisableEnglishSub() {
  try {
    const resp = await fetch('/api/settings', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        download_path: downloadPathInput.value.trim(),
        disable_english_sub: disableEnglishSubCb.checked
      })
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error); return; }
    showToast('English Sub downloads ' + (disableEnglishSubCb.checked ? 'disabled' : 'enabled'));
  } catch (e) {
    showToast('Failed to save setting: ' + e.message);
  }
}

async function saveDownloadPath() {
  const download_path = downloadPathInput.value.trim();
  try {
    const resp = await fetch('/api/settings', {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({download_path})
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error); return; }
    showToast('Download path saved');
  } catch (e) {
    showToast('Failed to save settings: ' + e.message);
  }
}

loadSettings();

// User management (only runs if the user table exists)
const userTableBody = document.getElementById('userTableBody');

if (userTableBody) {
  loadUsers();
}

async function loadUsers() {
  if (!userTableBody) return;
  try {
    const resp = await fetch('/admin/api/users');
    const data = await resp.json();
    renderUsers(data.users || []);
  } catch (e) {
    showToast('Failed to load users: ' + e.message);
  }
}

function renderUsers(users) {
  const adminCount = users.filter(u => u.role === 'admin').length;
  userTableBody.innerHTML = '';
  users.forEach(u => {
    const isLastAdmin = u.role === 'admin' && adminCount <= 1;
    const tr = document.createElement('tr');
    const authMethod = u.auth_method || 'local';
    const authBadge = authMethod === 'oidc'
      ? '<span class="auth-badge auth-sso">SSO</span>'
      : '<span class="auth-badge auth-local">Local</span>';
    tr.innerHTML =
      `<td>${u.id}</td>` +
      `<td>${esc(u.username)}</td>` +
      `<td>
        <select onchange="changeRole(${u.id}, this.value)" ${isLastAdmin ? 'disabled' : ''}>
          <option value="user" ${u.role === 'user' ? 'selected' : ''}>User</option>
          <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
        </select>
      </td>` +
      `<td>${authBadge}</td>` +
      `<td>${esc(u.created_at)}</td>` +
      `<td>${isLastAdmin
        ? '<span style="color:#555">protected</span>'
        : `<button class="btn-del" onclick="deleteUser(${u.id})">Delete</button>`
      }</td>`;
    userTableBody.appendChild(tr);
  });
}

async function addUser() {
  const username = document.getElementById('newUsername').value.trim();
  const password = document.getElementById('newPassword').value;
  const role = document.getElementById('newRole').value;

  if (!username || !password) { showToast('Username and password required'); return; }

  try {
    const resp = await fetch('/admin/api/users', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username, password, role})
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error); return; }
    document.getElementById('newUsername').value = '';
    document.getElementById('newPassword').value = '';
    showToast('User created');
    loadUsers();
  } catch (e) {
    showToast('Failed to create user: ' + e.message);
  }
}

async function deleteUser(id) {
  if (!confirm('Delete this user?')) return;
  try {
    const resp = await fetch(`/admin/api/users/${id}`, {method: 'DELETE'});
    const data = await resp.json();
    if (data.error) { showToast(data.error); return; }
    showToast('User deleted');
    loadUsers();
  } catch (e) {
    showToast('Failed to delete user: ' + e.message);
  }
}

async function changeRole(id, newRole) {
  try {
    const resp = await fetch(`/admin/api/users/${id}/role`, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({role: newRole})
    });
    const data = await resp.json();
    if (data.error) { showToast(data.error); loadUsers(); return; }
    showToast('Role updated');
    loadUsers();
  } catch (e) {
    showToast('Failed to update role: ' + e.message);
  }
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 4000);
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
