/**
 * Global App Core State and Controller
 * Illy Specialty Coffee Management System
 */

const STATE = {
  token: localStorage.getItem("illy_token") || null,
  user: JSON.parse(localStorage.getItem("illy_user") || "null"),
  currentView: "login",
  inactivityRemainingSeconds: 30 * 60,
  inactivityTimerInterval: null,
  selectedLoginProfile: null,
  employeeReport: null,
};

let alertsPollTimer = null;
async function loadAlerts(showDetails = false) {
  if (!STATE.token) return;
  try {
    const result = await api("/api/alerts");
    const alerts = result.alerts || [];
    const badge = document.getElementById("notification-badge");
    if (badge) {
      badge.textContent = String(alerts.length);
      badge.style.display = alerts.length ? "inline-flex" : "none";
    }
    renderAlertPanel(alerts);
    if (showDetails) document.getElementById("alert-panel").hidden = false;
  } catch (err) {
    if (showDetails) showToast("Bildirişlər yüklənmədi.", "error");
  }
}
function renderAlertPanel(alerts) {
  const list = document.getElementById("alert-panel-list");
  if (!list) return;
  list.replaceChildren();
  if (!alerts.length) {
    const empty = document.createElement("div");
    empty.className = "alert-empty";
    empty.textContent = IllyI18n.t("alerts.empty");
    list.appendChild(empty);
    return;
  }
  alerts.forEach((alert) => {
    const item = document.createElement("div");
    item.className = `alert-item ${alert.severity || "info"}`;
    const icon = document.createElement("span");
    icon.textContent = alert.severity === "critical" ? "⛔" : alert.severity === "warning" ? "⚠️" : "ℹ️";
    const body = document.createElement("div");
    const message = document.createElement("div");
    message.className = "alert-item-message";
    message.textContent = alert.message || alert.type;
    const meta = document.createElement("small");
    meta.className = "alert-item-meta";
    meta.textContent = `${alert.entity_name || (alert.entity_id ? `${IllyI18n.t("alerts.entity")}: ${alert.entity_id}` : "")} · ${alert.created_at || ""}`;
    body.append(message, meta);
    const button = document.createElement("button");
    button.className = "btn btn-outline btn-sm";
    button.textContent = IllyI18n.t("alerts.acknowledge");
    button.onclick = () => acknowledgeAlert(alert.id);
    item.append(icon, body, button);
    list.appendChild(item);
  });
}
function toggleAlertPanel() {
  const panel = document.getElementById("alert-panel");
  if (!panel) return;
  panel.hidden = !panel.hidden;
  if (!panel.hidden) loadAlerts();
}
async function acknowledgeAlert(alertId) {
  try {
    await api(`/api/alerts/${alertId}/acknowledge`, { method: "POST" });
    await loadAlerts();
  } catch (error) { showToast(error.message || "Alert could not be resolved.", "error"); }
}
function startAlertsPolling() {
  if (alertsPollTimer) clearInterval(alertsPollTimer);
  loadAlerts();
  alertsPollTimer = setInterval(() => loadAlerts(), 60000);
}

// UI deterrent only; browser-delivered source cannot be made confidential.
document.addEventListener("contextmenu", (event) => event.preventDefault());
document.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if (
    key === "f12" ||
    (event.ctrlKey && event.shiftKey && ["i", "j", "c"].includes(key)) ||
    (event.ctrlKey && ["u", "s"].includes(key))
  ) {
    event.preventDefault();
    event.stopPropagation();
  }
});

function resolveAvatarUrl(url) {
  return typeof url === "string" && url.trim() ? url : "/static/images/avatar-user.svg";
}

function buildAvatarPreview(theme, color) {
  const decoration = {
    christmas: '<path d="M28 29L50 8l22 21Z" fill="#dc2626"/><circle cx="50" cy="8" r="5" fill="#fff"/>',
    halloween: '<path d="M22 29h56L66 10H34Z" fill="#f97316"/><circle cx="42" cy="45" r="3"/><circle cx="58" cy="45" r="3"/>',
    heart: '<path d="M50 78S18 58 18 38c0-13 17-18 32-3 15-15 32-10 32 3 0 20-32 40-32 40Z" fill="#ef4444"/>',
    star: '<path d="m50 14 7 20 21 1-16 13 5 21-17-11-17 11 5-21-16-13 21-1Z" fill="#facc15"/>',
    crown: '<path d="m23 31 7-18 20 13 20-13 7 18Z" fill="#facc15"/><path d="M25 31h50v9H25Z" fill="#eab308"/>',
    coffee: '<path d="M30 38h35v24a8 8 0 0 1-8 8H38a8 8 0 0 1-8-8Z" fill="#fff"/><path d="M65 44h7a8 8 0 0 1 0 16h-7" fill="none" stroke="#fff" stroke-width="5"/>',
  }[theme] || "";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="24" fill="${color || "#2563eb"}"/><circle cx="50" cy="52" r="25" fill="#fff" opacity=".92"/><circle cx="41" cy="49" r="3" fill="#172033"/><circle cx="59" cy="49" r="3" fill="#172033"/><path d="M40 62q10 8 20 0" fill="none" stroke="#172033" stroke-width="3" stroke-linecap="round"/>${decoration}</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function updateVisibleAvatars(url) {
  const resolved = resolveAvatarUrl(url);
  document.querySelectorAll("#header-user-avatar, #profile-avatar-preview, #modal-pwd-avatar, .current-user-avatar").forEach((image) => {
    image.src = resolved;
  });
}

// --- Toast Notifications ---
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === "success" ? "✓" : type === "error" ? "⚠️" : "ℹ️"}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

let QUICK_FORM_RESOLVE = null;

function openQuickForm(title, subtitle, fields) {
  return new Promise((resolve) => {
    QUICK_FORM_RESOLVE = resolve;
    document.getElementById("quick-form-title").textContent = title;
    document.getElementById("quick-form-subtitle").textContent = subtitle || "";
    document.getElementById("quick-form-fields").innerHTML = fields.map((field) => `
      <label class="form-field ${field.wide ? "form-field-wide" : ""}">
        <span>${field.label}</span>
        <input class="input-field" name="${field.name}" type="${field.type || "text"}"
          value="${field.value || ""}" ${field.required === false ? "" : "required"}
          step="${field.type === "number" ? "0.01" : ""}">
      </label>
    `).join("");
    document.getElementById("modal-quick-form").style.display = "flex";
  });
}

function submitQuickForm(event) {
  event.preventDefault();
  closeQuickForm(Object.fromEntries(new FormData(event.currentTarget).entries()));
}

function closeQuickForm(value) {
  document.getElementById("modal-quick-form").style.display = "none";
  if (QUICK_FORM_RESOLVE) QUICK_FORM_RESOLVE(value);
  QUICK_FORM_RESOLVE = null;
}

async function openEmployeeReport(employeeId) {
  try {
    const report = await api(`/api/reports/employees/${employeeId}`);
    const employee = report.employee;
    const requiredIds = ["employee-report-title", "employee-report-period", "employee-report-summary", "employee-report-profile", "employee-report-chart", "employee-report-operations", "employee-report-orders", "employee-report-audits", "modal-employee-report"];
    const missing = requiredIds.find((id) => !document.getElementById(id));
    if (missing) throw new Error(`Employee report UI is missing: ${missing}`);
    document.getElementById("employee-report-title").textContent = `${employee.full_name} — İşçi hesabatı`;
    document.getElementById("employee-report-period").textContent =
      `${employee.created_at || "—"} → ${employee.employment_end_at || "Bu gün"} · ${employee.is_active ? "Aktiv" : "İşdən çıxarılıb"}`;
    const summary = report.summary;
    document.getElementById("employee-report-summary").innerHTML = [
      ["Satış", `${summary.completed_orders} sifariş`, "green"],
      ["Dövriyyə", `${Number(summary.revenue).toFixed(2)} AZN`, "blue"],
      ["Ləğvlər", `${summary.cancelled_orders} sifariş`, "red"],
      ["Endirim", `${Number(summary.discounts).toFixed(2)} AZN`, "gold"],
    ].map(([label, value, tone]) => `<div class="employee-kpi ${tone}"><span>${label}</span><strong>${value}</strong></div>`).join("");
    document.getElementById("employee-report-profile").innerHTML = `
      <div class="employee-profile-line"><span>İstifadəçi adı</span><strong>@${employee.username}</strong></div>
      <div class="employee-profile-line"><span>Rol</span><strong>${employee.role.toUpperCase()}</strong></div>
      <div class="employee-profile-line"><span>E-poçt</span><strong>${employee.email || "—"}</strong></div>
      <div class="employee-profile-line"><span>İş statusu</span><strong>${employee.is_active ? "Aktiv" : "İşdən çıxarılıb"}</strong></div>
    `;
    const maxRevenue = Math.max(...(report.daily || []).map((row) => Number(row.revenue || 0)), 1);
    STATE.employeeReport = report;
    document.getElementById("employee-report-chart").innerHTML = (report.daily || []).length
      ? report.daily.map((row, index) => {
        const revenue = Number(row.revenue) || 0;
        const barHeight = maxRevenue > 0 ? Math.max(8, revenue / maxRevenue * 150) : 8;
        return `<button type="button" class="employee-chart-column" onclick="showEmployeeDayReport(${index})" title="${row.day}: ${revenue.toFixed(2)} AZN, ${row.orders} sifariş"><span class="employee-chart-bar" style="height:${barHeight}px"></span><small>${row.day.slice(5)}</small></button>`;
      }).join("")
      : `<div class="empty-state">Bu tarixçə üzrə satış yoxdur.</div>`;
    const shift = report.shift_summary;
    const stockText = (report.stock_actions || []).map((item) => `${item.reference_type}: ${item.count} əməliyyat`).join(" · ") || "Stok əməliyyatı yoxdur";
    document.getElementById("employee-report-operations").innerHTML = `
      <div class="employee-profile-line"><span>Növbələr</span><strong>${shift.shifts} (${shift.closed_shifts} bağlanıb)</strong></div>
      <div class="employee-profile-line"><span>Kassa fərqi</span><strong>${Number(shift.cash_difference).toFixed(2)} AZN</strong></div>
      <div class="employee-profile-line"><span>Alış / stok əməliyyatları</span><strong>${stockText}</strong></div>
    `;
    document.getElementById("employee-report-orders").innerHTML = (report.recent_orders || []).map((order) => `
      <tr><td>${order.order_number}</td><td>${String(order.created_at).slice(0,16).replace("T"," ")}</td>
      <td><span class="badge ${order.status === "cancelled" ? "badge-danger" : "badge-success"}">${order.status === "cancelled" ? "Ləğv" : "Tamamlandı"}</span></td>
      <td>${Number(order.final_amount).toFixed(2)} AZN${order.cancel_reason ? `<small class="report-muted"> · ${order.cancel_reason}</small>` : ""}</td></tr>
    `).join("") || `<tr><td colspan="4">Sifariş tarixçəsi yoxdur.</td></tr>`;
    document.getElementById("employee-report-audits").innerHTML = (report.audits || []).map((audit) => `
      <tr><td>${String(audit.created_at).slice(0,16).replace("T"," ")}</td><td>${audit.action}</td><td>${audit.details || "—"}</td></tr>
    `).join("") || `<tr><td colspan="3">Audit qeydi yoxdur.</td></tr>`;
    document.getElementById("modal-employee-report").style.display = "flex";
  } catch (err) {
    showToast(err.message || IllyI18n.t("reports.employeeLoadFailed"), "error");
  }
}

window.openEmployeeReport = openEmployeeReport;
window.showEmployeeDayReport = showEmployeeDayReport;

function showEmployeeDayReport(index) {
  const row = STATE.employeeReport?.daily?.[index];
  const target = document.getElementById("employee-report-day-detail");
  if (!row || !target) return;
  target.innerHTML = `<strong>${row.day}</strong><span>${row.orders} sifariş</span><span>${Number(row.revenue).toFixed(2)} AZN satış</span><span>${row.cancellations || 0} ləğv</span>`;
}

function closeEmployeeReport() {
  document.getElementById("modal-employee-report").style.display = "none";
}

const SECTION_INFO = {
  reports: { title: "sectionInfo.reportsTitle", description: "sectionInfo.reportsDescription", steps: ["sectionInfo.reportsStep1", "sectionInfo.reportsStep2"] },
  stock: { title: "sectionInfo.stockTitle", description: "sectionInfo.stockDescription", steps: ["sectionInfo.stockStep1", "sectionInfo.stockStep2"] },
  catalog: {
    title: "sectionInfo.catalogTitle",
    description: "sectionInfo.catalogDescription",
    steps: ["sectionInfo.catalogStep1", "sectionInfo.catalogStep2", "sectionInfo.catalogStep3"],
  },
  shifts: { title: "sectionInfo.shiftsTitle", description: "sectionInfo.shiftsDescription", steps: ["sectionInfo.shiftsStep1", "sectionInfo.shiftsStep2"] },
  inventory: { title: "sectionInfo.inventoryTitle", description: "sectionInfo.inventoryDescription", steps: ["sectionInfo.inventoryStep1", "sectionInfo.inventoryStep2"] },
  staff: { title: "sectionInfo.staffTitle", description: "sectionInfo.staffDescription", steps: ["sectionInfo.staffStep1", "sectionInfo.staffStep2"] },
  retention: { title: "sectionInfo.retentionTitle", description: "sectionInfo.retentionDescription", steps: ["sectionInfo.retentionStep1", "sectionInfo.retentionStep2"] },
};

function openSectionInfo(section) {
  const info = SECTION_INFO[section];
  if (!info || !window.IllyI18n) return;
  document.getElementById("section-info-title").textContent = IllyI18n.t(info.title);
  document.getElementById("section-info-description").textContent = IllyI18n.t(info.description);
  document.getElementById("section-info-steps").innerHTML = info.steps
    .map((key, index) => `<div class="section-info-step"><span>${index + 1}</span><p>${IllyI18n.t(key)}</p></div>`)
    .join("");
  document.getElementById("modal-section-info").style.display = "flex";
}

window.openSectionInfo = openSectionInfo;

function closeSectionInfo() {
  const modal = document.getElementById("modal-section-info");
  if (modal) modal.style.display = "none";
}

function requestActionConfirmation(message, title = "Təsdiq tələb olunur") {
  return new Promise((resolve) => {
    const modal = document.getElementById("modal-confirm-action");
    const titleEl = document.getElementById("confirm-action-title");
    const messageEl = document.getElementById("confirm-action-message");
    const accept = document.getElementById("confirm-action-accept");
    const cancel = document.getElementById("confirm-action-cancel");
    if (!modal || !accept || !cancel) {
      resolve(false);
      return;
    }
    const language = window.IllyI18n?.language || "az";
    const labels = {
      az: { title: "Təsdiq tələb olunur", cancel: "İmtina", accept: "Təsdiq edirəm" },
      tr: { title: "Onay gerekiyor", cancel: "İptal", accept: "Onayla" },
      en: { title: "Confirmation required", cancel: "Cancel", accept: "Confirm" },
      ru: { title: "Требуется подтверждение", cancel: "Отмена", accept: "Подтвердить" },
    }[language] || { title: "Təsdiq tələb olunur", cancel: "İmtina", accept: "Təsdiq edirəm" };
    titleEl.textContent = title === "Təsdiq tələb olunur" ? labels.title : title;
    cancel.textContent = labels.cancel;
    accept.textContent = labels.accept;
    messageEl.textContent = message;
    modal.style.display = "flex";
    const finish = (value) => {
      modal.style.display = "none";
      accept.onclick = null;
      cancel.onclick = null;
      resolve(value);
    };
    accept.onclick = () => finish(true);
    cancel.onclick = () => finish(false);
  });
}

window.requestActionConfirmation = requestActionConfirmation;

// --- API Request Helper ---
async function api(endpoint, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (STATE.token) {
    headers["Authorization"] = `Bearer ${STATE.token}`;
  }

  try {
    resetInactivityTimer();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    const resp = await fetch(endpoint, {
      credentials: "same-origin",
      signal: controller.signal,
      ...options,
      headers,
    });
    clearTimeout(timeout);
    if (resp.status === 401) {
      const data = await resp.json().catch(() => ({}));
      logout();
      if (endpoint !== "/api/auth/profiles") {
        showToast(data.error || "Sessiya təsdiqlənmədi. Yenidən daxil olun.", "error");
      }
      return null;
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(
        data.error || data.message || `Xəta statusu: ${resp.status}`,
      );
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Server cavab vermədi. Səhifəni yeniləyib yenidən cəhd edin.");
    }
    showToast(err.message, "error");
    throw err;
  }
}

// --- 30-Minute Inactivity Auto-Lock (Rule D7) ---
function resetInactivityTimer() {
  STATE.inactivityRemainingSeconds = 30 * 60;
}

function startInactivityCountdown() {
  if (STATE.inactivityTimerInterval)
    clearInterval(STATE.inactivityTimerInterval);
  STATE.inactivityTimerInterval = setInterval(() => {
    if (!STATE.user) return;
    STATE.inactivityRemainingSeconds--;

    const mins = Math.floor(STATE.inactivityRemainingSeconds / 60);
    const secs = STATE.inactivityRemainingSeconds % 60;
    const timerEl = document.getElementById("inactivity-timer");
    if (timerEl) {
      timerEl.textContent = `⏱️ ${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
    }

    if (STATE.inactivityRemainingSeconds <= 0) {
      logout();
      showToast(
        "30 dəqiqəlik hərəkətsizlik səbəbindən sistem kilidləndi.",
        "info",
      );
    }
  }, 1000);
}

// Listen to user touch and click events to reset inactivity counter
["mousedown", "keydown", "touchstart", "scroll"].forEach((evt) => {
  window.addEventListener(evt, resetInactivityTimer, { passive: true });
});

// --- View Router ---
function navigateTo(viewName) {
  STATE.currentView = viewName;

  // View sections
  document.getElementById("view-login").style.display =
    viewName === "login" ? "flex" : "none";
  document.getElementById("view-barista").style.display =
    viewName === "barista" ? "grid" : "none";
  document.getElementById("view-admin").style.display =
    viewName === "admin" ? "grid" : "none";
  document.getElementById("view-developer").style.display =
    viewName === "developer" ? "grid" : "none";

  // Header visibility
  const header = document.getElementById("main-header");
  header.style.display = viewName === "login" ? "none" : "flex";

  // Nav button highlights
  const posBtn = document.getElementById("btn-nav-pos");
  const adminBtn = document.getElementById("btn-nav-admin");
  const devBtn = document.getElementById("btn-nav-developer");

  if (posBtn)
    posBtn.className = `btn btn-sm ${viewName === "barista" ? "btn-accent" : "btn-outline"}`;
  if (adminBtn)
    adminBtn.className = `btn btn-sm ${viewName === "admin" ? "btn-accent" : "btn-outline"}`;
  if (devBtn)
    devBtn.className = `btn btn-sm ${viewName === "developer" ? "btn-accent" : "btn-outline"}`;

  // View specific loaders
  if (viewName === "barista" && window.initBaristaPOS) {
    window.initBaristaPOS();
  } else if (viewName === "admin" && window.initAdminPortal) {
    window.initAdminPortal();
  } else if (viewName === "developer" && window.initDeveloperHub) {
    window.initDeveloperHub();
  }
}

async function initSetupExperience() {
    try {
      const status = await fetch("/api/setup/status", { cache: "no-store" }).then((r) => r.json());
      if (status.available && (status.demo_mode || !status.completed)) {
        openSetupWizard(status);
      }
    } catch (err) {
      console.error("Setup status could not be loaded:", err);
    }
}

function clearSetupError() {
  const el = document.getElementById("setup-error");
  if (!el) return;
  el.textContent = "";
  el.classList.remove("visible");
}

let SETUP_STATE = { step: 1, license_key: "", users: [], logo_url: "/static/images/illy-logo.svg" };
function openSetupWizard(status) {
    const wizard = document.getElementById("setup-wizard");
    if (!wizard) return;
    document.getElementById("setup-shop-name").value = status.shop_name || "";
    document.getElementById("setup-shop-tagline").value = status.shop_tagline || "";
    const logo = status.logo_url || "/static/images/illy-logo.svg";
    SETUP_STATE.logo_url = logo;
    const choice = document.getElementById("setup-logo-choice");
    if (choice && [...choice.options].some((option) => option.value === logo)) choice.value = logo;
    selectSetupLogo(logo);
    wizard.style.display = "flex";
    document.getElementById("app-container").style.visibility = "hidden";
    document.getElementById("main-header").style.visibility = "hidden";
    renderSetupStep(1);
}
function renderSetupStep(step) {
    SETUP_STATE.step = step;
    clearSetupError();
    document.querySelectorAll(".setup-step").forEach((el) => el.classList.toggle("active", Number(el.dataset.step) === step));
    document.querySelectorAll(".setup-panel").forEach((el) => el.classList.toggle("active", Number(el.dataset.step) === step));
    const backButton = document.getElementById("setup-back");
    if (backButton) backButton.disabled = step === 1;
    const nextButton = document.getElementById("setup-next");
    if (nextButton) nextButton.textContent = step === 5 ? "Quraşdırmanı tamamla" : "Növbəti";
}
function setupError(message) {
    const el = document.getElementById("setup-error");
    if (!el) return;
    el.textContent = message;
    el.classList.add("visible");
}
function validateSetupStep() {
    const step = SETUP_STATE.step;
    if (step === 1 && !document.getElementById("setup-license-key").value.trim()) return "Lisenziya açarı mütləq daxil edilməlidir.";
    if (step === 2 && !SETUP_STATE.users.length) return "Ən azı bir istifadəçi əlavə edin.";
    if (step === 3 && !document.getElementById("setup-shop-name").value.trim()) return "Mağaza adı mütləq daxil edilməlidir.";
    return "";
}
async function setupNext() {
    const error = validateSetupStep();
    if (error) return setupError(error);
    if (SETUP_STATE.step === 1) {
      const key = document.getElementById("setup-license-key").value.trim();
      const status = await fetch("/api/license/status", { cache: "no-store" }).then((r) => r.json());
      if (key !== "DEMO-SETUP" && status.status_label !== "REAL" && !key.startsWith("ILLY-REAL-")) return setupError("Lisenziya açarı tanınmadı. Demo üçün DEMO-SETUP istifadə edin.");
      SETUP_STATE.license_key = key;
    }
    if (SETUP_STATE.step < 5) renderSetupStep(SETUP_STATE.step + 1);
    else await completeSetup();
}
function setupBack() { if (SETUP_STATE.step > 1) { clearSetupError(); renderSetupStep(SETUP_STATE.step - 1); } }
function selectSetupLogo(url) {
  const resolved = url || "/static/images/illy-logo.svg";
  SETUP_STATE.logo_url = resolved;
  const preview = document.getElementById("setup-logo-preview");
  if (preview) preview.src = resolved;
}
function uploadSetupLogo(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (file.size > 1024 * 1024) return setupError("Logo faylı 1 MB-dan böyük ola bilməz.");
  const reader = new FileReader();
  reader.onload = () => selectSetupLogo(String(reader.result));
  reader.readAsDataURL(file);
}
function addSetupUser() {
    const form = document.getElementById("setup-user-form");
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    data.username = String(data.username || "").trim().toLowerCase();
    data.full_name = String(data.full_name || "").trim();
    data.role = data.role || "barista";
    SETUP_STATE.users.push(data);
    form.reset();
    renderSetupUsers();
}
function renderSetupUsers() {
    document.getElementById("setup-users-list").innerHTML = SETUP_STATE.users.map((u, i) => `<div class="setup-user-row"><span>${u.full_name}</span><span>${u.role}</span><button type="button" class="btn btn-outline btn-sm" onclick="SETUP_STATE.users.splice(${i},1);renderSetupUsers()">Sil</button></div>`).join("");
}
async function completeSetup() {
    const payload = { license_key: SETUP_STATE.license_key, users: SETUP_STATE.users, shop_name: document.getElementById("setup-shop-name").value.trim(), shop_tagline: document.getElementById("setup-shop-tagline").value.trim(), logo_url: SETUP_STATE.logo_url };
    try {
      const response = await api("/api/setup/complete", { method: "POST", body: JSON.stringify(payload) });
      if (!response || !response.success) {
        throw new Error((response && response.message) || "Quraşdırma tamamlanmadı.");
      }
      document.getElementById("setup-wizard").style.display = "none";
      document.getElementById("app-container").style.visibility = "visible";
      document.getElementById("main-header").style.visibility = "visible";
      showToast("Quraşdırma tamamlandı. İndi giriş edə bilərsiniz.");
      loadGnomeProfilePicker();
    } catch (err) {
      setupError(err.message || "Quraşdırma tamamlanmadı.");
      showToast(err.message || "Quraşdırma tamamlanmadı.", "error");
    }
}
async function applyBranding() {
  try {
    const status = await fetch("/api/setup/status", { cache: "no-store" }).then((r) => r.json());
    const logo = status.logo_url || "/static/images/illy-logo.svg";
    document.querySelectorAll("#header-logo-image, #login-logo-image").forEach((el) => { el.src = logo; });
    if (status.shop_name) {
      document.getElementById("header-shop-name").textContent = status.shop_name;
      document.title = `${status.shop_name} - Nəzarət və İdarəetmə Sistemi`;
    }
  } catch (err) { console.warn("Branding could not be loaded:", err); }
}

// --- GNOME User Picker Profile Loader (Rule D1-D4) ---
async function loadGnomeProfilePicker() {
  const container = document.getElementById("profile-picker-grid");
  if (!container) return;
  container.innerHTML = `<div style="color: var(--text-muted); text-align: center; grid-column: 1/-1;">Profillər yüklənir...</div>`;

  try {
    const profiles = await api("/api/auth/profiles?ts=" + Date.now());
    if (!Array.isArray(profiles)) {
      throw new Error("Profil siyahısı düzgün formatda deyil.");
    }
    container.innerHTML = "";

    // 1. Render visible user profile cards (Admin and Baristas)
    profiles.forEach((p) => {
      const card = document.createElement("button");
      card.className = "profile-card";
      card.type = "button";
      card.setAttribute("aria-label", `${p.full_name} — ${p.role === "admin" ? "Admin" : "Barista"}`);
      card.onclick = () => openPasswordModal(p);

      const roleBadge =
        p.role === "admin"
          ? `<span class="badge badge-admin profile-role-badge">⭐ Admin</span>`
          : `<span class="badge badge-barista profile-role-badge">☕ Barista</span>`;

      card.innerHTML = `
        <img src="${resolveAvatarUrl(p.avatar_url)}" class="profile-avatar" alt="${p.full_name}">
        <div class="profile-name">${p.full_name}</div>
        ${roleBadge}
      `;
      container.appendChild(card);
    });

    // 2. Render "Other" / "Digər" option (Rule D4)
    // Developer logs in from there with username + password
    const otherCard = document.createElement("button");
    otherCard.className = "profile-card profile-card-other";
    otherCard.type = "button";
    otherCard.setAttribute("aria-label", "Digər giriş seçimləri");
    otherCard.onclick = openOtherLoginModal;
    otherCard.innerHTML = `
      <div class="other-icon">🔑</div>
      <div class="profile-name">Digər</div>
      <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Developer və Giriş</div>
    `;
    container.appendChild(otherCard);
  } catch (err) {
    container.innerHTML = `
      <div style="color: var(--danger); text-align: center; grid-column: 1/-1;">
        <div style="margin-bottom:10px">Xəta: ${err.message}</div>
        <button class="btn btn-outline btn-sm" type="button" onclick="loadGnomeProfilePicker()">Yenidən yoxla</button>
      </div>`;
  }
}

// --- Login & Password Modals ---
function openPasswordModal(profile) {
  STATE.selectedLoginProfile = profile;
  document.getElementById("modal-pwd-avatar").src =
    profile.avatar_url || "/static/images/avatar-user.svg";
  document.getElementById("modal-pwd-username").textContent = profile.full_name;
  document.getElementById("modal-pwd-role").textContent =
    profile.role === "admin" ? "Sistem Rəhbəri (Admin)" : "Barista";
  document.getElementById("modal-pwd-input").value = "";
  document.getElementById("modal-password-prompt").style.display = "flex";
  setTimeout(() => document.getElementById("modal-pwd-input").focus(), 100);
}

function closePasswordModal() {
  document.getElementById("modal-password-prompt").style.display = "none";
}

async function submitProfilePassword(e) {
  e.preventDefault();
  if (!STATE.selectedLoginProfile) return;
  const password = document.getElementById("modal-pwd-input").value;

  try {
    const res = await api("/api/auth/login-profile", {
      method: "POST",
      body: JSON.stringify({
        user_id: STATE.selectedLoginProfile.id,
        password,
      }),
    });

    closePasswordModal();
    await onLoginSuccess(res.user, res.token);
  } catch (err) {
    document.getElementById("modal-pwd-input").value = "";
  }
}

function openOtherLoginModal() {
  document.getElementById("other-username-input").value = "";
  document.getElementById("other-password-input").value = "";
  document.getElementById("modal-other-login").style.display = "flex";
  setTimeout(
    () => document.getElementById("other-username-input").focus(),
    100,
  );
}

function closeOtherLoginModal() {
  document.getElementById("modal-other-login").style.display = "none";
}

function openForgotPasswordModal() {
  closeOtherLoginModal();
  document.getElementById("forgot-identifier-input").value = "";
  document.getElementById("modal-forgot-password").style.display = "flex";
  setTimeout(() => document.getElementById("forgot-identifier-input").focus(), 100);
}

function closeForgotPasswordModal() {
  document.getElementById("modal-forgot-password").style.display = "none";
}

async function submitForgotPassword(e) {
  e.preventDefault();
  try {
    const res = await api("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ identifier: document.getElementById("forgot-identifier-input").value }),
    });
    closeForgotPasswordModal();
    showToast(res.message, "info");
  } catch (err) {}
}

async function submitResetPassword(e) {
  e.preventDefault();
  const token = new URLSearchParams(window.location.search).get("reset_token");
  try {
    const res = await api("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: document.getElementById("reset-password-input").value }),
    });
    document.getElementById("modal-reset-password").style.display = "none";
    window.history.replaceState({}, "", window.location.pathname);
    showToast(res.message, "success");
  } catch (err) {}
}

async function submitOtherLogin(e) {
  e.preventDefault();
  const username = document.getElementById("other-username-input").value;
  const password = document.getElementById("other-password-input").value;

  try {
    const res = await api("/api/auth/login-other", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });

    closeOtherLoginModal();
    await onLoginSuccess(res.user, res.token);
  } catch (err) {
    document.getElementById("other-password-input").value = "";
  }
}

async function onLoginSuccess(user, token) {
  STATE.user = user;
  STATE.token = token;
  localStorage.setItem("illy_token", token);
  localStorage.setItem("illy_user", JSON.stringify(user));
  if (window.IllyI18n) await IllyI18n.init(user.preferred_language || "az");
  applyUserTheme(user.preferred_theme || "soft-dark");
  applyUserFontSize(user.preferred_font_size || "normal");

  // Update Header User info
  document.getElementById("header-user-name").textContent = user.full_name;
  document.getElementById("header-user-avatar").src =
    resolveAvatarUrl(user.avatar_url);

  const roleEl = document.getElementById("header-user-role");
  roleEl.className = `badge badge-${user.role === "developer" ? "dev" : user.role === "admin" ? "admin" : "barista"}`;
  roleEl.textContent = user.role.toUpperCase();

  // Role permissions for Nav tabs (Section C2)
  document.getElementById("btn-nav-pos").style.display = "inline-flex";
  document.getElementById("btn-nav-admin").style.display =
    user.role === "admin" || user.role === "developer" ? "inline-flex" : "none";
  document.getElementById("btn-nav-developer").style.display =
    user.role === "developer" ? "inline-flex" : "none";

  startInactivityCountdown();
  startAlertsPolling();
  showToast(IllyI18n.t("login.welcomeUser", { name: user.full_name }));

  // Direct to appropriate landing view
  if (user.role === "developer") {
    navigateTo("developer");
  } else if (user.role === "admin") {
    navigateTo("admin");
  } else {
    navigateTo("barista");
  }
}

function applyUserTheme(theme) {
  const allowed = ["light", "soft-dark", "deep-dark", "midnight-glass", "warm-cream", "warm-green", "cool-graphite"];
  document.documentElement.dataset.theme = allowed.includes(theme) ? theme : "soft-dark";
}

function applyUserFontSize(size) {
  const allowed = ["small", "normal", "large"];
  const value = allowed.includes(size) ? size : "normal";
  document.documentElement.dataset.fontSize = value;
  const selector = document.getElementById("font-size-switcher");
  if (selector) selector.value = value;
}

function logout() {
  STATE.token = null;
  STATE.user = null;
  localStorage.removeItem("illy_token");
  localStorage.removeItem("illy_user");
  if (STATE.inactivityTimerInterval)
    clearInterval(STATE.inactivityTimerInterval);
  if (alertsPollTimer) {
    clearInterval(alertsPollTimer);
    alertsPollTimer = null;
  }

  navigateTo("login");
  loadGnomeProfilePicker();
}

function previewProfileAvatar(url) {
  const preview = document.getElementById("profile-avatar-preview");
  if (preview) preview.src = buildAvatarPreview(url, STATE.user?.avatar_color);
}

// User Profile Settings Modal
function openProfileSettingsModal() {
  if (!STATE.user) return;
  const select = document.getElementById("profile-avatar-select");
  if (select) select.value = STATE.user.avatar_theme || "plain";
  previewProfileAvatar(select?.value || "plain");
  const curPwd = document.getElementById("profile-current-pwd");
  if (curPwd) curPwd.value = "";
  const newPwd = document.getElementById("profile-new-pwd");
  if (newPwd) newPwd.value = "";
  const signature = document.getElementById("profile-receipt-signature");
  if (signature) signature.value = STATE.user.receipt_signature || "";
  const language = document.getElementById("language-switcher");
  if (language) language.value = STATE.user.preferred_language || "az";
  const theme = document.getElementById("theme-switcher");
  if (theme) theme.value = STATE.user.preferred_theme || "soft-dark";
  const fontSize = document.getElementById("font-size-switcher");
  if (fontSize) fontSize.value = STATE.user.preferred_font_size || "normal";
  document.getElementById("modal-profile-settings").style.display = "flex";
}

function closeProfileSettingsModal() {
  document.getElementById("modal-profile-settings").style.display = "none";
}

async function submitProfileSettings(e) {
  e.preventDefault();
  const avatar_theme = document.getElementById("profile-avatar-select").value;
  const current_password = document
    .getElementById("profile-current-pwd")
    .value.trim();
  const new_password = document.getElementById("profile-new-pwd").value.trim();
  const receipt_signature = document.getElementById("profile-receipt-signature").value.trim();
  const preferred_language = document.getElementById("language-switcher").value;
  const preferred_theme = document.getElementById("theme-switcher").value;
  const preferred_font_size = document.getElementById("font-size-switcher").value;

  const preferencesOnly = !current_password &&
    !new_password &&
    avatar_theme === (STATE.user.avatar_theme || "plain") &&
    receipt_signature === (STATE.user.receipt_signature || "");
  if (preferencesOnly) {
    try {
      const response = await api("/api/users/me/preferences", {
        method: "PUT",
        body: JSON.stringify({ preferred_language, preferred_theme, preferred_font_size }),
      });
      if (!response.success) throw new Error(response.message || "Profil tənzimləmələri yadda saxlanmadı.");
      STATE.user.preferred_language = preferred_language;
      STATE.user.preferred_theme = preferred_theme;
      STATE.user.preferred_font_size = preferred_font_size;
      localStorage.setItem("illy_user", JSON.stringify(STATE.user));
      await IllyI18n.setLanguage(preferred_language);
      applyUserTheme(preferred_theme);
      applyUserFontSize(preferred_font_size);
      showToast(IllyI18n.t("settings.preferencesSaved"), "success");
      closeProfileSettingsModal();
    } catch (error) {
      showToast(error.message || "Dil seçimi yadda saxlanmadı.", "error");
    }
    return;
  }
  if (!current_password) {
    showToast(
      "Profil dəyişikliyini təsdiqləmək üçün cari şifrənizi daxil edin.",
      "error",
    );
    return;
  }

  const payload = {
    avatar_theme,
    current_password,
    receipt_signature,
    preferred_language,
    preferred_theme,
    preferred_font_size,
  };
  if (new_password) {
    payload.new_password = new_password;
  }

  try {
    const res = await api("/api/auth/profile", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    if (res && res.success) {
      showToast(res.message || "Profil yeniləndi.", "success");
      STATE.user.avatar_theme = avatar_theme;
      STATE.user.receipt_signature = receipt_signature;
      STATE.user.preferred_language = preferred_language;
      STATE.user.preferred_theme = preferred_theme;
      STATE.user.preferred_font_size = preferred_font_size;
      localStorage.setItem("illy_user", JSON.stringify(STATE.user));
      STATE.user.avatar_url = buildAvatarPreview(avatar_theme, STATE.user.avatar_color);
      updateVisibleAvatars(STATE.user.avatar_url);
      await IllyI18n.setLanguage(preferred_language);
      applyUserTheme(preferred_theme);
      applyUserFontSize(preferred_font_size);
      closeProfileSettingsModal();
    }

  } catch (err) {
    showToast(err.message || "Profil yenilənmədi.", "error");
  }
}

async function downloadSalesReport(periodId, formatId) {
  if (!STATE.token) {
    showToast("Giriş tələb olunur.", "error");
    return;
  }
  const period = document.getElementById(periodId)?.value || "daily";
  const format = document.getElementById(formatId)?.value || "csv";
  try {
    const response = await fetch(`/api/reports/export?period=${encodeURIComponent(period)}&format=${encodeURIComponent(format)}`, {
      credentials: "same-origin",
      headers: { Authorization: `Bearer ${STATE.token}` },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "Hesabat hazırlana bilmədi.");
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `illy_sales_${period}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    showToast("Hesabat uğurla ixrac edildi.", "success");
  } catch (err) {
    showToast(err.message || "Hesabat ixrac edilə bilmədi.", "error");
  }
}

// Download developer / backup files with auth
async function downloadDeveloperFile(url, defaultFilename) {
  if (!STATE.token) {
    showToast("Giriş tələb olunur.", "error");
    return;
  }

  /*
  async function downloadSalesReport(periodId, formatId) {
    const period = document.getElementById(periodId)?.value || "daily";
    const format = document.getElementById(formatId)?.value || "csv";
    try {
      const response = await fetch(`/api/reports/export?period=${encodeURIComponent(period)}&format=${encodeURIComponent(format)}`, {
        headers: { Authorization: `Bearer ${STATE.token}` },
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Hesabat hazırlana bilmədi.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `illy_sales_${period}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
      showToast("Hesabat endirilməyə hazırdır.");
    } catch (err) {
      showToast(err.message, "error");
    }
  }
  */

  try {
    showToast("Fayl hazırlanır və endirilir...", "info");
    const res = await fetch(url, {
      headers: {
        Authorization: `Bearer ${STATE.token}`,
      },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(err.error || "Endirmə xətası baş verdi.", "error");
      return;
    }

    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;

    const disp = res.headers.get("content-disposition");
    let filename = defaultFilename;
    if (disp && disp.includes("filename=")) {
      filename = disp.split("filename=")[1].replace(/["']/g, "").trim();
    }
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => window.URL.revokeObjectURL(blobUrl), 1000);
    showToast("Fayl uğurla endirildi!", "success");
  } catch (err) {
    console.error("Download error:", err);
    showToast("Endirmə zamanı rabitə xətası baş verdi.", "error");
  }
}

// --- 3-Second Azerbaijani Hover Tooltip System ---
function initAzHoverTooltips() {
  let tooltipEl = document.getElementById("az-hover-tooltip");
  if (!tooltipEl) {
    tooltipEl = document.createElement("div");
    tooltipEl.id = "az-hover-tooltip";
    document.body.appendChild(tooltipEl);
  }

  let hoverTimer = null;
  let currentTarget = null;

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest("[data-az-tooltip]");
    if (!el) {
      clearTimeout(hoverTimer);
      tooltipEl.classList.remove("visible");
      currentTarget = null;
      return;
    }

    if (el === currentTarget) return;
    clearTimeout(hoverTimer);
    currentTarget = el;
    tooltipEl.classList.remove("visible");

    const text = el.getAttribute("data-az-tooltip");
    if (!text) return;

    hoverTimer = setTimeout(() => {
      if (currentTarget !== el) return;
      tooltipEl.textContent = text;
      const rect = el.getBoundingClientRect();

      let top = rect.top - 38;
      if (top < 10) {
        top = rect.bottom + 8;
      }
      let left = rect.left + rect.width / 2 - 120;
      if (left < 10) left = 10;
      if (left + 240 > window.innerWidth - 10) {
        left = window.innerWidth - 250;
      }

      tooltipEl.style.top = `${top}px`;
      tooltipEl.style.left = `${left}px`;
      tooltipEl.classList.add("visible");
    }, 3000); // 3 seconds hover requirement
  });

  document.addEventListener("mouseout", (e) => {
    const el = e.target.closest("[data-az-tooltip]");
    if (el && el === currentTarget) {
      clearTimeout(hoverTimer);
      tooltipEl.classList.remove("visible");
      currentTarget = null;
    }
  });

  document.addEventListener("click", () => {
    clearTimeout(hoverTimer);
    tooltipEl.classList.remove("visible");
    currentTarget = null;
  });
}

// Initialize on DOM load. The HTML shell dispatches this event after loading
// partials, while browsers may also dispatch the native event.
let appInitialized = false;
document.addEventListener("illy:language-changed", () => {
  if (!appInitialized) return;
  if (STATE.currentView === "barista" && window.initBaristaPOS) window.initBaristaPOS();
  if (STATE.currentView === "admin" && window.initAdminPortal) window.initAdminPortal();
  if (STATE.currentView === "developer" && window.initDeveloperHub) window.initDeveloperHub();
});
document.addEventListener("DOMContentLoaded", async () => {
  if (appInitialized) return;
  appInitialized = true;
  initAzHoverTooltips();
  applyBranding();
  if (STATE.token && STATE.user) {
    await onLoginSuccess(STATE.user, STATE.token);
  } else {
    navigateTo("login");
    loadGnomeProfilePicker();
  }
  if (new URLSearchParams(window.location.search).has("reset_token")) {
    document.getElementById("modal-reset-password").style.display = "flex";
  }
  initSetupExperience();
});
