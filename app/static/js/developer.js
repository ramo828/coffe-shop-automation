/**
 * Developer Technical Hub & Security Management
 * Illy Specialty Coffee Management System
 */

window.initDeveloperHub = async function () {
  await Promise.all([
    loadLicenseAndDiagnostics(),
    loadSyncSettings(),
    loadDeveloperMLMetrics(),
    loadDeveloperAuditLogs(),
    loadDeveloperUsers(),
    loadDeveloperHealth(),
    loadDeveloperBackups(),
    loadDeveloperBranches(),
    loadDeveloperNetworkSettings(),
  ]);
};

async function loadDeveloperNetworkSettings() {
  try {
    const settings = await api("/api/developer/network-settings");
    document.getElementById("developer-network-host").value = settings.host;
    document.getElementById("developer-network-port").value = settings.port;
  } catch (err) {}
}

async function saveDeveloperNetworkSettings() {
  const host = document.getElementById("developer-network-host").value;
  const port = Number(document.getElementById("developer-network-port").value);
  if (!window.confirm("Server binding dəyişəcək. Tətbiq yenidən başladıldıqdan sonra qüvvəyə minəcək. Davam edilsin?")) return;
  try {
    const result = await api("/api/developer/network-settings", {
      method: "PUT",
      body: JSON.stringify({ host, port }),
    });
    showToast(result.message, "info");
  } catch (err) { showToast(err.message || "Network settings could not be saved.", "error"); }
}

async function loadDeveloperBranches() {
  try {
    const branches = await api("/api/branches");
    const target = document.getElementById("developer-branches-list");
    if (target) target.innerHTML = branches.map((branch) => `<div>${branch.name} · <strong>${branch.code}</strong></div>`).join("") || "Filial yoxdur.";
  } catch (err) {}
}

async function createDeveloperBranch() {
  const name = document.getElementById("new-branch-name")?.value.trim();
  const code = document.getElementById("new-branch-code")?.value.trim();
  if (!name || !code) {
    showToast("Filial adı və kodu daxil edin.", "warning");
    return;
  }
  try {
    await api("/api/branches", { method: "POST", body: JSON.stringify({ name, code }) });
    document.getElementById("new-branch-name").value = "";
    document.getElementById("new-branch-code").value = "";
    await loadDeveloperBranches();
    showToast("Filial əlavə edildi.", "success");
  } catch (err) {}
}

async function loadDeveloperUsers() {
  const users = await api("/api/users");
  const tbody = document.querySelector("#dev-staff-table tbody");
  if (!tbody) return;
  tbody.innerHTML = (users || []).map((u) => `
    <tr><td>${u.full_name}</td><td>@${u.username}</td><td>${u.email || "-"}</td>
    <td>${u.role}</td><td>
      ${u.role !== "developer" ? `<button class="btn btn-primary btn-sm" onclick="openEmployeeReport(${u.id})">${IllyI18n.t("reports.employee")}</button>` : ""}
      <button class="btn btn-outline btn-sm" onclick="developerEditUser(${u.id}, '${u.full_name}')">Redaktə</button>
      <button class="btn btn-danger btn-sm" onclick="developerDeleteUser(${u.id}, '${u.full_name}')">${IllyI18n.t("common.delete")}</button>
    </td></tr>`).join("");
}

function openDeveloperNewUser(defaultRole = "") {
  const form = document.getElementById("user-form");
  if (!form) return;
  form.reset();
  document.getElementById("user-form-mode").value = "create";
  document.getElementById("user-form-title").textContent = "Yeni istifadəçi";
  document.getElementById("user-form-subtitle").textContent = "Admin və ya barista hesabını təhlükəsiz şəkildə yaradın.";
  document.getElementById("user-form-password").required = true;
  document.getElementById("user-form-password").placeholder = "Ən azı 8 simvol";
  document.getElementById("user-form-role").disabled = false;
  document.getElementById("user-form-username").readOnly = false;
  document.getElementById("user-form-role").value = defaultRole || "barista";
  document.getElementById("modal-user-form").style.display = "flex";
  document.getElementById("user-form-username").focus();
}

function openUserEditModal(id, user) {
  const form = document.getElementById("user-form");
  form.reset();
  document.getElementById("user-form-mode").value = String(id);
  document.getElementById("user-form-title").textContent = `${user.full_name} məlumatlarını yenilə`;
  document.getElementById("user-form-subtitle").textContent = "Şifrəni boş saxlasanız dəyişdirilməyəcək.";
  document.getElementById("user-form-full-name").value = user.full_name;
  document.getElementById("user-form-username").value = user.username;
  document.getElementById("user-form-username").readOnly = true;
  document.getElementById("user-form-email").value = user.email || "";
  document.getElementById("user-form-role").value = user.role;
  document.getElementById("user-form-role").disabled = true;
  document.getElementById("user-form-password").required = false;
  document.getElementById("user-form-password").placeholder = "Dəyişməz saxlamaq üçün boş buraxın";
  document.getElementById("modal-user-form").style.display = "flex";
  document.getElementById("user-form-full-name").focus();
}

function closeUserFormModal() {
  document.getElementById("modal-user-form").style.display = "none";
}

async function submitUserForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const mode = document.getElementById("user-form-mode").value;
  const payload = {
    username: document.getElementById("user-form-username").value.trim(),
    full_name: document.getElementById("user-form-full-name").value.trim(),
    password: document.getElementById("user-form-password").value,
    role: document.getElementById("user-form-role").value,
    email: document.getElementById("user-form-email").value.trim(),
  };
  if (!payload.username || !payload.full_name || !["admin", "barista"].includes(payload.role)) return;
  const submit = form.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    const endpoint = mode === "create" ? "/api/users" : `/api/users/${mode}`;
    if (mode !== "create" && !payload.password) delete payload.password;
    await api(endpoint, { method: mode === "create" ? "POST" : "PUT", body: JSON.stringify(payload) });
    closeUserFormModal();
    showToast(mode === "create" ? "İstifadəçi yaradıldı." : "İstifadəçi yeniləndi.");
    await loadDeveloperUsers();
  } finally {
    submit.disabled = false;
  }
}

async function developerEditUser(id, name) {
  const users = await api("/api/users");
  const user = (users || []).find((item) => item.id === id);
  if (user) openUserEditModal(id, user);
}

async function developerDeleteUser(id, name) {
  if (!confirm(`'${name}' silinsin?`)) return;
  await api(`/api/users/${id}`, { method: "DELETE" });
  showToast("İstifadəçi silindi.");
  loadDeveloperUsers();
}

async function loadLicenseAndDiagnostics() {
  try {
    const [diag, lic] = await Promise.all([
      api("/api/developer/diagnostics"),
      api("/api/license/status"),
    ]);

    // License Badge & Message (Section L)
    const badgeEl = document.getElementById("dev-license-badge");
    const msgEl = document.getElementById("dev-license-message");

    if (lic.is_real_mode) {
      badgeEl.className = "badge badge-success";
      badgeEl.textContent = "REAL REJİM (Aktiv)";
      msgEl.textContent =
        "Sistem tam lisenziyalı REAL rejimdə işləyir. Baza ixracı və bütün funksiyalar açıqdır.";
    } else if (lic.tamper_detected) {
      badgeEl.className = "badge badge-admin";
      badgeEl.textContent = "BLOKLANIB (Saat manipulyasiyası)";
      msgEl.textContent = lic.message;
    } else {
      badgeEl.className = "badge badge-warning";
      badgeEl.textContent = `DEMO SINAQ (${lic.trial_days_left} gün qalıb)`;
      msgEl.textContent = lic.message;
    }

    // System Health (CPU, RAM, DB size)
    const healthBox = document.getElementById("dev-system-health-box");
    if (healthBox && diag) {
      const encActive = !!diag.features.encryption_enabled;
      const gzActive = !!diag.features.compression_enabled;

      healthBox.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 14px; font-size: 15px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">Baza Faylı:</span>
            <span style="font-family: monospace; font-size: 13px; font-weight: 600; color: var(--text-main); background: var(--surface-2, rgba(255,255,255,.08)); padding: 3px 8px; border-radius: 6px;">${diag.database_file}</span>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">Baza Həcmi:</span>
            <strong style="font-size: 16px; color: var(--text-main);">${diag.database_size_kb} KB</strong>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">RAM İstifadəsi:</span>
            <strong style="font-size: 16px; color: var(--text-main);">${diag.memory_usage_mb} MB</strong>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="color: var(--text-secondary);">CPU Yükü:</span>
            <strong style="font-size: 16px; color: var(--text-main);">${diag.cpu_percent}%</strong>
          </div>

          <div style="height: 1px; background: var(--border); margin: 6px 0;"></div>

          <!-- Interactive AES-256 Toggle -->
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0;"
               data-az-tooltip="Bu parametr verilənlər bazası faylının AES-256 alqoritmi ilə zərf şifrələnməsini aktiv və ya deaktiv edir">
            <div>
              <div style="font-weight: 600; color: var(--text-main); font-size: 15px;">AES-256 Şifrələmə</div>
              <div style="font-size: 13px; color: var(--text-secondary);">Baza faylının lokal şifrələnməsi</div>
            </div>
            <div style="display: flex; align-items: center; gap: 12px;">
              <span class="badge ${encActive ? "badge-success" : "badge-secondary"}">
                ${encActive ? "Aktiv" : "Deaktiv"}
              </span>
              <button type="button" class="toggle-switch ${encActive ? "active" : ""}"
                      onclick="window.toggleEncryption(${encActive})"
                      aria-label="AES-256 Şifrələmə">
                <span class="toggle-knob"></span>
              </button>
            </div>
          </div>

          <!-- Interactive GZ Compression Toggle -->
          <div style="display: flex; justify-content: space-between; align-items: center; padding: 4px 0;"
               data-az-tooltip="Bu parametr ehtiyat nüsxələrinin GZIP ilə avtomatik sıxılmasını idarə edir">
            <div>
              <div style="font-weight: 600; color: var(--text-main); font-size: 15px;">GZ Sıxılma Arxivləşdirməsi</div>
              <div style="font-size: 13px; color: var(--text-secondary);">Avtomatik GZIP sıxılması</div>
            </div>
            <div style="display: flex; align-items: center; gap: 12px;">
              <span class="badge ${gzActive ? "badge-success" : "badge-secondary"}">
                ${gzActive ? "Aktiv" : "Deaktiv"}
              </span>
              <button type="button" class="toggle-switch ${gzActive ? "active" : ""}"
                      onclick="window.toggleCompression(${gzActive})"
                      aria-label="GZ Sıxılma">
                <span class="toggle-knob"></span>
              </button>
            </div>
          </div>
        </div>
      `;
    }
  } catch (err) {
    console.error("Error loading diagnostics:", err);
  }
}

window.toggleEncryption = async function (currentVal) {
  const nextVal = !currentVal;
  try {
    const res = await api("/api/developer/encryption", {
      method: "POST",
      body: JSON.stringify({ enabled: nextVal }),
    });
    showToast(res.message || "Şifrələmə parametri yeniləndi.", "success");
    await loadLicenseAndDiagnostics();
    if (typeof loadDeveloperAuditLogs === "function") loadDeveloperAuditLogs();
  } catch (err) {}
};

window.toggleCompression = async function (currentVal) {
  const nextVal = !currentVal;
  try {
    const res = await api("/api/developer/compression", {
      method: "POST",
      body: JSON.stringify({ enabled: nextVal }),
    });
    showToast(res.message || "GZ sıxılma parametri yeniləndi.", "success");
    await loadLicenseAndDiagnostics();
    if (typeof loadDeveloperAuditLogs === "function") loadDeveloperAuditLogs();
  } catch (err) {}
};

// REAL Mode Activation (Section L2)
async function submitRealModeActivation() {
  const key = document.getElementById("dev-activation-key-input").value.trim();
  if (!key) {
    showToast("Aktivasiya açarını daxil edin.", "warning");
    return;
  }

  try {
    const res = await api("/api/license/activate", {
      method: "POST",
      body: JSON.stringify({ key }),
    });
    showToast(res.message || "REAL rejim uğurla aktivləşdirildi!");
    document.getElementById("dev-activation-key-input").value = "";
    loadLicenseAndDiagnostics();
  } catch (err) {}
}

async function generateBranchKey() {
  try {
    const res = await api("/api/developer/generate-key", {
      method: "POST",
      body: JSON.stringify({ branch_code: "ILLY-BAKU-01" }),
    });
    try {
      await navigator.clipboard.writeText(res.activation_key);
      showToast("REAL açarı yaradıldı və clipboard-a kopyalandı.");
    } catch (err) {
      showToast(`REAL açarı yaradıldı: ${res.activation_key}`, "info");
    }
  } catch (err) {}
}

// Remote Sync Settings (Section K)
async function loadSyncSettings() {
  try {
    const cfg = await api("/api/sync/config");
    if (!cfg) return;

    document.getElementById("dev-sync-mode").value = cfg.mode || "local_only";
    document.getElementById("dev-sync-url").value = cfg.url || "";
    document.getElementById("dev-sync-token").value = cfg.token || "";
  } catch (err) {}
}

async function saveSyncSettings() {
  const mode = document.getElementById("dev-sync-mode").value;
  const url = document.getElementById("dev-sync-url").value;
  const token = document.getElementById("dev-sync-token").value;

  try {
    const res = await api("/api/sync/config", {
      method: "POST",
      body: JSON.stringify({ mode, url, token }),
    });
    showToast(res.message || "Sinxronizasiya parametrləri yeniləndi.");
  } catch (err) {}
}

async function testRemoteConnection() {
  const url = document.getElementById("dev-sync-url").value;
  const token = document.getElementById("dev-sync-token").value;

  try {
    const res = await api("/api/sync/test", {
      method: "POST",
      body: JSON.stringify({ url, token }),
    });
    showToast(res.message || "Bağlantı uğurludur!");
  } catch (err) {}
}

async function triggerImmediateSync() {
  try {
    const res = await api("/api/sync/now", { method: "POST" });
    showToast(res.message || "Növbə göndərildi.");
  } catch (err) {}
}

async function triggerFullReplication() {
  if (
    !confirm("Bütün mövcud yerli məlumatlar uzaq mərkəzi serverə göndərilsin?")
  )
    return;
  try {
    const res = await api("/api/sync/all", { method: "POST" });
    showToast(res.message || "Bütün məlumatların sinxronizasiyası başladıldı.");
  } catch (err) {}
}

// Technical ML Metrics (Section I2)
async function loadDeveloperMLMetrics() {
  try {
    const ml = await api("/api/ml/metrics");
    const container = document.getElementById("dev-ml-metrics-box");
    if (!container || !ml) return;

    const lossBars = (ml.loss_history || [])
      .map(
        (val) =>
          `<div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
         <div style="width: 24px; height: ${Math.round(val * 120)}px; background: var(--accent); border-radius: 4px 4px 0 0;"></div>
         <span style="font-size: 10px; color: var(--text-muted);">${val.toFixed(2)}</span>
       </div>`,
      )
      .join("");

    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 14px; font-size: 15px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="color: var(--text-secondary);">Model Versiyası:</span>
          <strong style="color: var(--text-main); font-size: 15px;">${ml.model_name} (${ml.version})</strong>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="color: var(--text-secondary);">Öyrənmə Keyfiyyəti:</span>
          <span class="badge badge-success">${ml.learning_quality}</span>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="color: var(--text-secondary);">Dəqiqlik İndeksi:</span>
          <strong style="color: var(--primary); font-size: 18px;">${ml.accuracy_score}%</strong>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="color: var(--text-secondary);">Orta Mütləq Xəta (MAE):</span>
          <strong style="color: var(--text-main);">${ml.mean_absolute_error}</strong>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="color: var(--text-secondary);">İnference Gecikməsi:</span>
          <strong style="color: var(--text-main);">${ml.inference_latency_ms} ms</strong>
        </div>

        <div style="margin-top: 10px;">
          <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px;">Xəta Trendi (Loss Convergence History):</div>
          <div style="display: flex; align-items: flex-end; gap: 8px; height: 74px; background: rgba(255,255,255,.06); border: 1px solid var(--border); padding: 8px; border-radius: var(--radius-md);">
            ${lossBars}
          </div>
        </div>
      </div>
    `;
  } catch (err) {}
}

// Technical Audit Logs
async function loadDeveloperAuditLogs() {
  try {
    const logs = await api("/api/developer/audit-logs?limit=25");
    const tbody = document.querySelector("#dev-audit-table tbody");
    if (!tbody) return;

    tbody.innerHTML = (logs || [])
      .map(
        (l) => `
      <tr>
        <td>#${l.id}</td>
        <td>${l.created_at.slice(0, 19).replace("T", " ")}</td>
        <td style="font-family: monospace; color: var(--accent); font-weight: 700;">${l.action}</td>
        <td style="font-size: 13px;">${l.details || ""}</td>
        <td style="font-family: monospace; font-size: 12px;">${l.ip_address || "127.0.0.1"}</td>
      </tr>
    `,
      )
      .join("");
  } catch (err) {}
}
async function loadDeveloperHealth() {
  try {
    const health = await api("/api/health");
    const badge = document.getElementById("developer-health-badge");
    const details = document.getElementById("developer-health-details");
    if (badge) badge.textContent = health.status === "ok" ? "Sağlam" : "Problem";
    if (details) details.textContent = `Baza: ${health.database?.result || "—"} · Disk: ${Math.round((health.disk?.free_bytes || 0) / 1024 / 1024 / 1024)} GB boş · Son backup: ${health.last_backup?.modified_at || "yoxdur"}`;
  } catch (err) {
    const badge = document.getElementById("developer-health-badge");
    if (badge) badge.textContent = "Əlçatmaz";
  }
}

async function loadDeveloperBackups() {
  try {
    const result = await api("/api/backup");
    const list = result.backups || [];
    const target = document.getElementById("developer-backup-list");
    if (target) target.innerHTML = list.length
      ? list.slice(0, 10).map((item) => `
        <div class="backup-row">
          <span>${item.modified_at} · ${(item.size / 1024).toFixed(0)} KB</span>
          <button type="button" class="btn btn-outline btn-sm" onclick="restoreDeveloperBackup(${JSON.stringify(item.path)})">Bərpa et</button>
        </div>`).join("")
      : "Backup yoxdur.";
  } catch (err) { showToast(err.message || "Backup siyahısı yüklənmədi.", "error"); }
}

async function createDeveloperBackup() {
  try {
    await api("/api/backup", { method: "POST" });
    showToast("Backup yaradıldı.", "success");
    await loadDeveloperBackups();
  } catch (err) { showToast(err.message || "Backup yaradılmadı.", "error"); }
}

async function restoreDeveloperBackup(path) {
  if (!window.confirm("Bu backup cari bazanı əvəz edəcək. Davam edilsin?")) return;
  try {
    await api("/api/backup/restore", { method: "POST", body: JSON.stringify({ path }) });
    showToast("Backup təhlükəsiz şəkildə bərpa edildi.", "success");
    await loadDeveloperBackups();
  } catch (err) { showToast(err.message || "Backup bərpa edilə bilmədi.", "error"); }
}
