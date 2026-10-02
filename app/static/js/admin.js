/**
 * Admin Business Management & Operations Portal
 * Illy Specialty Coffee Management System
 */

const ADMIN_STATE = {
  currentTab: "overview",
  rawMaterials: [],
  catalog: [],
  reportPeriod: "daily",
  reportChart: "bar",
  reportRows: [],
  reportCache: new Map(),
  reportRequestId: 0,
};

document.addEventListener("illy:language-changed", updateCatalogStatusLabels);

function escapeAdminHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function adminJsString(value) {
  return `'${String(value ?? "")
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/[\r\n\u2028\u2029]/g, (char) => ({
      "\r": "\\r",
      "\n": "\\n",
      "\u2028": "\\u2028",
      "\u2029": "\\u2029",
    })[char])
    .replace(/</g, "\\u003c")}'`;
}

window.initAdminPortal = async function () {
  initSalesReportControls();
  initSectionInfoButtons();
  switchAdminTab("overview");
};

function initSectionInfoButtons() {
  document.querySelectorAll("[data-section-info]").forEach((button) => {
    button.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      window.openSectionInfo(button.dataset.sectionInfo);
    };
  });
}

function initSalesReportControls() {
  document.querySelectorAll("[data-report-period]").forEach((button) => {
    button.onclick = () => {
      ADMIN_STATE.reportPeriod = button.dataset.reportPeriod;
      document.querySelectorAll("[data-report-period]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      loadAdminSalesReport();
    };
  });
  document.querySelectorAll("[data-chart-type]").forEach((button) => {
    button.onclick = () => {
      ADMIN_STATE.reportChart = button.dataset.chartType;
      document.querySelectorAll("[data-chart-type]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderSalesReportChart(ADMIN_STATE.reportRows);
    };
  });
}

function reportPeriodDays(period) {
  return { daily: 1, weekly: 7, monthly: 30, yearly: 365, all: 3650 }[period] || 1;
}

async function loadEndOfDayReport() {
  const period = document.getElementById("eod-period")?.value || "today";
  try {
    const report = await api(`/api/reports/end-of-day?preset=${encodeURIComponent(period)}`);
    const s = report.summary || {};
    const c = report.cash_movements || {};
    const target = document.getElementById("end-of-day-report");
    if (!target) return;
    const language = window.IllyI18n?.language || "az";
    const labels = {
      az: { revenue: "Ümumi dövriyyə", discount: "Endirim", cash: "Nağd", card: "Kart", cashIn: "Kassa girişi", cashOut: "Kassa çıxışı", debt: "Borc alındı", debtPaid: "Borc ödənildi", hours: "Saat", total: "Ümumi nəticə", profit: "Xalis qazanc", expenses: "Adi xərclər", cost: "Maya dəyəri", waste: "İtkilər" },
      tr: { revenue: "Toplam ciro", discount: "İndirim", cash: "Nakit", card: "Kart", cashIn: "Kasa girişi", cashOut: "Kasa çıkışı", debt: "Borç alındı", debtPaid: "Borç ödendi", hours: "Saat", total: "Genel toplam", profit: "Net kâr", expenses: "Normal giderler", cost: "Maliyet", waste: "Kayıplar" },
      en: { revenue: "Total revenue", discount: "Discounts", cash: "Cash", card: "Card", cashIn: "Cash in", cashOut: "Cash out", debt: "Debt received", debtPaid: "Debt repaid", hours: "Hours", total: "Grand total", profit: "Net profit", expenses: "Operating expenses", cost: "Cost of goods", waste: "Waste" },
      ru: { revenue: "Общий оборот", discount: "Скидка", cash: "Наличные", card: "Карта", cashIn: "Приход в кассу", cashOut: "Расход из кассы", debt: "Полученный долг", debtPaid: "Погашенный долг", hours: "Часы", total: "Общий итог", profit: "Чистая прибыль", expenses: "Обычные расходы", cost: "Себестоимость", waste: "Потери" },
    }[language] || {};
    const tr = (key, fallback) => labels[key] || fallback;
    const movementDetails = report.cash_movement_details || [];
    const costDetails = report.cost_details || [];
    const wasteDetails = report.waste_details || [];
    const expenseDetails = report.expense_details || [];
    const detailList = (items, empty, render) => items.length ? items.map(render).join("") : `<li>${empty}</li>`;
    const movementRows = movementDetails.length
      ? movementDetails.map((movement) => {
        const direction = movement.direction === "in" ? tr("cashIn", "Kassa girişi") : tr("cashOut", "Kassa çıxışı");
        const debtType = movement.is_debt_payment ? tr("debtPaid", "Borc ödənildi") : movement.is_debt ? tr("debt", "Borc alındı") : "";
        return `<tr><td>${movement.created_at || "-"}</td><td>${direction}</td><td>${Number(movement.amount || 0).toFixed(2)} AZN</td><td>${debtType || "-"}</td><td>${escapeAdminHtml(movement.reason || "-")}</td><td>${escapeAdminHtml(movement.note || "-")}</td><td>${escapeAdminHtml(movement.user_name || movement.username || "-")}</td></tr>`;
      }).join("")
      : `<tr><td colspan="7">${language === "az" ? "Kassa hərəkəti yoxdur" : language === "tr" ? "Kasa hareketi yok" : language === "en" ? "No cash movements" : "Нет движений кассы"}</td></tr>`;
    const noData = language === "az" ? "Məlumat yoxdur" : language === "tr" ? "Veri yok" : language === "en" ? "No data" : "Нет данных";
    const baristas = (report.users || []).filter((user) => user.orders || user.cash_in || user.cash_out);
    const baristaRows = baristas.length
      ? baristas.map((user) => `<tr><td>${user.user_name || user.username}</td><td>${Number(user.hours || 0).toFixed(2)}</td><td>${user.orders || 0}</td><td>${Number(user.revenue || 0).toFixed(2)}</td><td>${Number(user.cash || 0).toFixed(2)}</td><td>${Number(user.card || 0).toFixed(2)}</td><td>${Number(user.bolt || 0).toFixed(2)}</td><td>${Number(user.wolt || 0).toFixed(2)}</td><td>${Number(user.cash_in || 0).toFixed(2)}</td><td>${Number(user.cash_out || 0).toFixed(2)}</td></tr>`).join("")
      : `<tr><td colspan="10">${language === "az" ? "Məlumat yoxdur" : language === "tr" ? "Veri yok" : language === "en" ? "No data" : "Нет данных"}</td></tr>`;
    target.innerHTML = `
      <div><strong>${tr("revenue", "Ümumi dövriyyə")}:</strong> ${Number(s.sales_revenue || 0).toFixed(2)} AZN · ${tr("discount", "Endirim")}: ${Number(s.discounts || 0).toFixed(2)} AZN</div>
      <div>${tr("cash", "Nağd")}: ${Number(report.payment_methods?.cash || 0).toFixed(2)} AZN · ${tr("card", "Kart")}: ${Number(report.payment_methods?.card || 0).toFixed(2)} AZN</div>
      <div>Bolt: ${Number(report.delivery_channels?.bolt?.amount || 0).toFixed(2)} AZN (${report.delivery_channels?.bolt?.orders || 0}) · Wolt: ${Number(report.delivery_channels?.wolt?.amount || 0).toFixed(2)} AZN (${report.delivery_channels?.wolt?.orders || 0})</div>
      <div>${tr("cashIn", "Kassa girişi")}: ${Number(c.cash_in || 0).toFixed(2)} AZN · ${tr("cashOut", "Kassa çıxışı")}: ${Number(c.cash_out || 0).toFixed(2)} AZN</div>
      <div>${tr("debt", "Borc alındı")}: ${Number(c.debt_out || 0).toFixed(2)} AZN · ${tr("debtPaid", "Borc ödənildi")}: ${Number(c.debt_payment_in || 0).toFixed(2)} AZN</div>
      <h4>${language === "az" ? "Kassa hərəkətlərinin detalları" : language === "tr" ? "Kasa hareketi detayları" : language === "en" ? "Cash movement details" : "Детали движений кассы"}</h4>
      <div class="data-table-container eod-table-wrap"><table class="data-table eod-table cash-details-table"><thead><tr><th>${language === "az" ? "Tarix və saat" : language === "tr" ? "Tarih ve saat" : language === "en" ? "Date and time" : "Дата и время"}</th><th>${language === "az" ? "Növ" : language === "tr" ? "Tür" : language === "en" ? "Type" : "Тип"}</th><th>Məbləğ</th><th>${language === "az" ? "Borc statusu" : language === "tr" ? "Borç durumu" : language === "en" ? "Debt status" : "Статус долга"}</th><th>${language === "az" ? "Səbəb" : language === "tr" ? "Sebep" : language === "en" ? "Reason" : "Причина"}</th><th>${language === "az" ? "Açıqlama" : language === "tr" ? "Açıklama" : language === "en" ? "Description" : "Описание"}</th><th>Barista</th></tr></thead><tbody>${movementRows}</tbody></table></div>
      <div class="eod-financial-summary"><strong>${tr("cost", "Maya dəyəri")}:</strong> ${Number(s.cost_of_goods || 0).toFixed(2)} AZN · <strong>${tr("waste", "İtkilər")}:</strong> ${Number(s.waste_cost || 0).toFixed(2)} AZN · <strong>${tr("expenses", "Adi xərclər")}:</strong> ${Number(s.operating_expenses || 0).toFixed(2)} AZN · <strong>${tr("profit", "Xalis qazanc")}:</strong> ${Number(s.net_profit || 0).toFixed(2)} AZN</div>
      <div class="eod-reconciliation"><h4>${language === "az" ? "Maliyyə izahı" : language === "tr" ? "Mali açıklama" : language === "en" ? "Financial reconciliation" : "Финансовая сверка"}</h4>
        <div>${tr("revenue", "Ümumi dövriyyə")} − ${tr("cost", "Maya dəyəri")} = ${Number(s.gross_profit || (s.sales_revenue - s.cost_of_goods) || 0).toFixed(2)} AZN</div>
        <div>${Number(s.gross_profit || (s.sales_revenue - s.cost_of_goods) || 0).toFixed(2)} − ${tr("waste", "İtkilər")} − ${tr("expenses", "Adi xərclər")} = <strong>${tr("profit", "Xalis qazanc")} ${Number(s.net_profit || 0).toFixed(2)} AZN</strong></div>
        <div>${tr("cash", "Nağd")} + ${tr("cashIn", "Kassa girişi")} − ${tr("cashOut", "Kassa çıxışı")} = <strong>${Number((report.cash_reconciliation || {}).closing_movement || 0).toFixed(2)} AZN</strong></div>
      </div>
      <div class="eod-detail-lists"><section><h4>${tr("cost", "Maya dəyəri")}</h4><ul>${detailList(costDetails, noData, (item) => `<li>${escapeAdminHtml(item.product_name)} / ${escapeAdminHtml(item.variant_name)}: <strong>${Number(item.cost).toFixed(2)} AZN</strong></li>`)}</ul></section><section><h4>${tr("waste", "İtkilər")}</h4><ul>${detailList(wasteDetails, noData, (item) => `<li>${escapeAdminHtml(item.name)} (${item.quantity} ${escapeAdminHtml(item.unit)}): <strong>${Number(item.cost).toFixed(2)} AZN</strong></li>`)}</ul></section><section><h4>${tr("expenses", "Adi xərclər")}</h4><ul>${detailList(expenseDetails, noData, (item) => `<li>${item.created_at}: ${escapeAdminHtml(item.reason || "-")} — ${escapeAdminHtml(item.note || "-")}: <strong>${Number(item.amount).toFixed(2)} AZN</strong></li>`)}</ul></section></div>
      <h4>${language === "az" ? "Baristaların hesabatı" : language === "tr" ? "Barista raporu" : language === "en" ? "Barista report" : "Отчёт бариста"}</h4>
      <div class="data-table-container eod-table-wrap"><table class="data-table eod-table"><thead><tr><th>Barista</th><th>${tr("hours", "Saat")}</th><th>Sifariş</th><th>${tr("revenue", "Ümumi dövriyyə")}</th><th>${tr("cash", "Nağd")}</th><th>${tr("card", "Kart")}</th><th>Bolt</th><th>Wolt</th><th>${tr("cashIn", "Kassa girişi")}</th><th>${tr("cashOut", "Kassa çıxışı")}</th></tr></thead><tbody>${baristaRows}</tbody></table></div>
      <strong>${tr("total", "Ümumi nəticə")}:</strong> ${Number(s.sales_revenue || 0).toFixed(2)} AZN · ${tr("profit", "Xalis qazanc")}: ${Number(s.net_profit || 0).toFixed(2)} AZN`;
  } catch (err) {
    const target = document.getElementById("end-of-day-report");
    if (target) {
      target.textContent = err.message || "Hesabat yüklənmədi.";
      target.classList.add("empty-state");
    }
    console.error("End-of-day report failed", err);
  }
}
window.loadEndOfDayReport = loadEndOfDayReport;
window.printEndOfDayReport = function () {
  const report = document.getElementById("end-of-day-report");
  if (!report || !report.textContent.trim()) {
    window.showToast?.("Əvvəlcə hesabatı göstərin.", "warning");
    return;
  }
  const popup = window.open("", "illy-eod-print", "width=420,height=700");
  if (!popup) return;
  const printLanguage = window.IllyI18n?.language || "az";
  const printTitle = { az: "ILLY GÜN SONU HESABATI", tr: "ILLY GÜN SONU RAPORU", en: "ILLY END-OF-DAY REPORT", ru: "ОТЧЁТ ILLY ЗА ДЕНЬ" }[printLanguage] || "ILLY GÜN SONU HESABATI";
  popup.document.write(`<html><head><title>${printTitle}</title><style>body{font:12px monospace;padding:12px;color:#111}div{border-bottom:1px solid #000;padding:4px 0}table{width:100%;border-collapse:collapse;font-size:10px;margin-top:8px}th,td{border:1px solid #555;padding:4px;text-align:left;white-space:nowrap}h4{margin:12px 0 4px}</style></head><body><h3>${printTitle}</h3>${report.innerHTML}</body></html>`);
  popup.document.close();
  popup.onload = () => { popup.focus(); popup.print(); };
  setTimeout(() => { popup.focus(); popup.print(); }, 100);
};

async function loadAdminSalesReport() {
  const period = ADMIN_STATE.reportPeriod;
  const cached = ADMIN_STATE.reportCache.get(period);
  if (cached && Date.now() - cached.timestamp < 60000) {
    ADMIN_STATE.reportRows = cached.report.series || [];
    renderSalesReportChart(ADMIN_STATE.reportRows, cached.report);
    return;
  }
  const requestId = ++ADMIN_STATE.reportRequestId;
  try {
    const report = await api(`/api/reports/sales?period=${period}`);
    if (requestId !== ADMIN_STATE.reportRequestId || period !== ADMIN_STATE.reportPeriod) return;
    ADMIN_STATE.reportCache.set(period, { timestamp: Date.now(), report });
    ADMIN_STATE.reportRows = report?.series || [];
    const total = document.getElementById("admin-report-total");
    if (total && report?.summary) {
      total.textContent = `${Number(report.summary.revenue || 0).toFixed(2)} AZN · ${report.summary.orders || 0} ${IllyI18n.t("reports.orders")}`;
    }
    const insight = document.getElementById("admin-report-insights");
    if (insight) {
      insight.textContent = report?.insights?.busiest_label
        ? IllyI18n.t("reports.busiestPeriod", { period: report.insights.busiest_label, orders: report.insights.busiest_orders })
        : "";
    }
    const breakdown = document.getElementById("admin-report-breakdown");
    if (breakdown) {
      const pay = report.payment_methods || {};
      const channels = report.delivery_channels || {};
      const tr = window.IllyI18n?.t || ((key) => key);
      breakdown.innerHTML = `${tr("pos.cashIn")}: ${Number(pay.cash?.amount || 0).toFixed(2)} AZN (${pay.cash?.orders || 0}) · ${tr("pos.card")}: ${Number(pay.card?.amount || 0).toFixed(2)} AZN (${pay.card?.orders || 0}) · Bolt: ${Number(channels.bolt?.amount || 0).toFixed(2)} AZN (${channels.bolt?.orders || 0}) · Wolt: ${Number(channels.wolt?.amount || 0).toFixed(2)} AZN (${channels.wolt?.orders || 0})`;
    }
    renderSalesReportChart(ADMIN_STATE.reportRows, report);
  } catch (error) {
    console.error("Error loading sales report:", error);
  }
}

function renderSalesReportChart(rows, report = null) {
  const period = ADMIN_STATE.reportPeriod;
  const range = document.getElementById("admin-report-range");
  const total = document.getElementById("admin-report-total");
  if (range) range.textContent = IllyI18n.t(`period.${period}`);
  if (total) {
    const revenue = Number(report?.summary?.revenue ?? (rows || []).reduce((sum, row) => sum + Number(row.revenue || 0), 0));
    total.textContent = `${revenue.toFixed(2)} AZN`;
  }
  const insight = document.getElementById("admin-report-insights");
  if (insight && report?.insights?.busiest_label) {
    insight.textContent = IllyI18n.t("reports.busiestPeriod", {
      period: report.insights.busiest_label,
      orders: report.insights.busiest_orders,
    });
  }
  const canvas = document.getElementById("admin-sales-chart");
  const pie = document.getElementById("admin-sales-pie");
  if (!canvas || !pie) return;
  const showPie = ADMIN_STATE.reportChart === "pie";
  canvas.hidden = showPie;
  pie.hidden = !showPie;
  if (showPie) drawSalesPie(rows);
  else drawSalesChart(rows, ADMIN_STATE.reportChart);
  renderSalesLegend(rows);
}

function switchAdminTab(tabName) {
  ADMIN_STATE.currentTab = tabName;
  ensureSectionInfoButton(tabName);

  const tabs = [
    "overview",
    "stock",
    "catalog",
    "shifts",
    "inventory",
    "staff",
    "retention",
  ];
  tabs.forEach((t) => {
    const tabBtn = document.getElementById(`tab-admin-${t}`);
    const panel = document.getElementById(`admin-panel-${t}`);
    if (tabBtn) tabBtn.classList.toggle("active", t === tabName);
    if (panel) panel.style.display = t === tabName ? (t === "overview" ? "grid" : "block") : "none";
  });

  if (tabName === "overview") loadAdminOverview();
  else if (tabName === "stock") loadAdminStock();
  else if (tabName === "catalog") loadAdminCatalog();
  else if (tabName === "shifts") loadAdminShifts();
  else if (tabName === "inventory") loadAdminInventory();
  else if (tabName === "staff") loadAdminStaff();
  else if (tabName === "retention") loadAdminRetention();
}

function ensureSectionInfoButton(tabName) {
  const panel = document.getElementById(`admin-panel-${tabName}`);
  if (!panel || tabName === "catalog" || panel.querySelector(".section-info-btn")) return;
  const heading = panel.querySelector("h2");
  if (!heading || !window.IllyI18n) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "section-info-btn";
  button.textContent = "i";
  button.title = IllyI18n.t("sectionInfo.open");
  button.setAttribute("aria-label", IllyI18n.t("sectionInfo.open"));
  button.dataset.sectionInfo = tabName;
  button.onclick = (event) => {
    event.preventDefault();
    event.stopPropagation();
    window.openSectionInfo(tabName);
  };
  const wrapper = heading.parentElement;
  if (wrapper) {
    wrapper.style.display = "flex";
    wrapper.style.alignItems = "center";
    wrapper.style.gap = "10px";
    wrapper.appendChild(button);
  }
}

// --- Tab 1: Business Overview & ML Recommendations ---
async function loadAdminOverview() {
  try {
    const [overview, topProds, baristas, recs] = await Promise.all([
      api("/api/reports/overview?days=7"),
      api("/api/reports/top-products"),
      api("/api/reports/baristas?days=30"),
      api("/api/ml/recommendations"),
    ]);

    // Render ML Recommendations (Section I3)
    const recsList = document.getElementById("ml-recommendations-list");
    if (recsList) {
      if (!recs || !recs.length) {
        recsList.innerHTML = `<div style="color: var(--text-muted); font-size: 13px;">${IllyI18n.t("admin.ml.empty")}</div>`;
      } else {
        recsList.innerHTML = recs
          .map(
            (r) => `
          <div class="recommendation-card ${r.urgency || "low"}">
            <div>
              <div class="recommendation-title">${r.title_key ? IllyI18n.t(r.title_key, r.title_params || {}) : r.title}</div>
              <div class="recommendation-msg">${r.message_key ? IllyI18n.t(r.message_key, r.message_params || {}) : r.message}</div>
            </div>
            ${r.raw_material_id ? `<button class="btn btn-outline btn-sm" onclick="openRestockForMaterial(${r.raw_material_id}, '${r.title || ""}', ${r.suggested_quantity || 10})">${r.action_key ? IllyI18n.t(r.action_key, r.action_params || {}) : r.action_text}</button>` : ""}
          </div>
        `,
          )
          .join("");
      }
    }

    // Render KPI Stat Cards
    const kpiEl = document.getElementById("admin-kpi-stats");
    if (kpiEl && overview) {
      kpiEl.innerHTML = `
        <div class="stat-card">
          <div class="stat-label">${IllyI18n.t("kpi.weeklyRevenue")}</div>
          <div class="stat-value">${overview.total_revenue.toFixed(2)} AZN</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${IllyI18n.t("kpi.completedOrders")}</div>
          <div class="stat-value">${overview.total_orders} ədəd</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${IllyI18n.t("kpi.averageTicket")}</div>
          <div class="stat-value">${overview.avg_ticket.toFixed(2)} AZN</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${IllyI18n.t("kpi.discounts")}</div>
          <div class="stat-value" style="color: var(--warning);">${overview.total_discounts.toFixed(2)} AZN</div>
        </div>
      `;
      kpiEl.querySelectorAll(".stat-value").forEach((el) => {
        const suffix = el.textContent.includes("ədəd") ? " ədəd" : " AZN";
        const value = parseFloat(el.textContent);
        if (Number.isNaN(value)) return;
        el.textContent = "0.00" + suffix;
        animateMetric(el, value, suffix);
      });
    }

    // Render Top Products
    const topEl = document.getElementById("admin-top-products-list");
    if (topEl && topProds) {
      topEl.innerHTML = topProds
        .map(
          (tp, idx) => `
        <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px;">
          <span>${idx + 1}. <strong>${tp.product_name}</strong> (${tp.total_quantity} ${IllyI18n.t("units.items")})</span>
          <span style="color: var(--accent); font-weight: 700;">${tp.total_revenue.toFixed(2)} AZN</span>
        </div>
      `,
        )
        .join("");
    }

    // Render Barista Performance
    const baristaEl = document.getElementById("admin-barista-performance-list");
    if (baristaEl && baristas) {
      baristaEl.innerHTML = baristas
        .map(
          (b) => `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px;">
          <div>
            <div style="font-weight: 700;">${b.full_name}</div>
            <div style="font-size: 12px; color: var(--text-muted);">${b.completed_orders} ${IllyI18n.t("orders.label")} | ${IllyI18n.t("orders.cancelled")}: ${b.cancellations_count}</div>
          </div>
          <div style="text-align: right;">
            <div style="font-weight: 700; color: var(--accent);">${b.total_revenue.toFixed(2)} AZN</div>
            <div style="font-size: 11px; color: var(--text-muted);">${IllyI18n.t("kpi.average")}: ${b.avg_ticket.toFixed(2)} ₼</div>
          </div>
        </div>
      `,
        )
        .join("");
    }
    await loadAdminSalesReport();
  } catch (err) {
    console.error("Error loading admin overview:", err);
  }
}

function animateMetric(element, target, suffix) {
  const duration = 720;
  const start = performance.now();
  const tick = (now) => {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = `${(target * eased).toFixed(2)}${suffix}`;
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function drawSalesChart(rows, chartType = "bar") {
  const canvas = document.getElementById("admin-sales-chart");
  if (!canvas) return;
  const data = (rows || []).map((row) => Number(row.revenue || 0));
  const values = data.length ? data : [0, 0, 0, 0, 0, 0, 0];
  const ctx = canvas.getContext("2d");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 600;
  const height = 220;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  const max = Math.max(...values, 1);
  const step = width / Math.max(values.length, 1);
  ctx.strokeStyle = "rgba(91, 110, 255, .18)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    const y = (height * i) / 4;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
  }
  if (chartType === "bar") {
    const gap = Math.min(12, width / Math.max(values.length * 3, 1));
    const barWidth = Math.max(4, (width - gap * (values.length + 1)) / values.length);
    values.forEach((value, index) => {
      const barHeight = (value / max) * (height - 30);
      const x = gap + index * (barWidth + gap);
      const y = height - barHeight - 12;
      ctx.fillStyle = index === values.length - 1 ? "#9ba8ff" : "rgba(113, 128, 255, .72)";
      ctx.fillRect(x, y, barWidth, barHeight);
    });
    return;
  }
  if (chartType === "line") {
    const points = values.map((value, index) => ({
      x: values.length === 1 ? width / 2 : (index / (values.length - 1)) * (width - 24) + 12,
      y: height - (value / max) * (height - 34) - 16,
    }));
    ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = "#8190ff"; ctx.lineWidth = 3; ctx.lineJoin = "round"; ctx.stroke();
    points.forEach((point) => {
      ctx.beginPath(); ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#55d6be"; ctx.fill();
      ctx.strokeStyle = "var(--surface, #fff)"; ctx.lineWidth = 2; ctx.stroke();
    });
    return;
  }
  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, "rgba(113, 128, 255, .36)");
  gradient.addColorStop(1, "rgba(113, 128, 255, 0)");
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = index * step;
    const y = height - (value / max) * (height - 24) - 12;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.lineTo(width, height); ctx.lineTo(0, height); ctx.closePath();
  ctx.fillStyle = gradient; ctx.fill();
  ctx.beginPath();
  values.forEach((value, index) => {
    const x = index * step;
    const y = height - (value / max) * (height - 24) - 12;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = "#8190ff"; ctx.lineWidth = 3; ctx.lineJoin = "round"; ctx.stroke();
}

function drawSalesPie(rows) {
  const pie = document.getElementById("admin-sales-pie");
  if (!pie) return;
  const values = (rows || []).map((row) => Number(row.revenue || 0));
  const total = values.reduce((sum, value) => sum + value, 0);
  if (!total) {
    pie.style.background = "conic-gradient(var(--border) 0 100%)";
    pie.innerHTML = `<span>${IllyI18n.t("reports.noData")}</span>`;
    return;
  }
  const colors = ["#8190ff", "#9b8cff", "#6dd6c0", "#f3b562", "#e9799e", "#72a7f8", "#b7c1ff"];
  let cursor = 0;
  const stops = values.map((value, index) => {
    const next = cursor + (value / total) * 100;
    const stop = `${colors[index % colors.length]} ${cursor}% ${next}%`;
    cursor = next;
    return stop;
  });
  pie.style.background = `conic-gradient(${stops.join(",")})`;
  pie.innerHTML = `<span>${total.toFixed(2)} AZN</span>`;
}

function renderSalesLegend(rows) {
  const legend = document.getElementById("admin-sales-legend");
  const summary = document.getElementById("admin-sales-summary");
  if (!legend || !summary) return;
  const items = (rows || []).filter((row) => Number(row.revenue || 0) > 0);
  const colors = ["#8190ff", "#9b8cff", "#6dd6c0", "#f3b562", "#e9799e", "#72a7f8", "#b7c1ff"];
  legend.innerHTML = items.slice(0, 12).map((row, index) =>
    `<span class="sales-legend-item"><i style="background:${colors[index % colors.length]}"></i><b>${escapeAdminHtml(row.label || row.date || "")}</b><span>${Number(row.revenue || 0).toFixed(2)} AZN</span></span>`
  ).join("");
  summary.textContent = items.length
    ? items.map((row) => `${row.label || row.date}: ${Number(row.revenue || 0).toFixed(2)} AZN, ${row.orders || 0} ${IllyI18n.t("reports.orders")}`).join(" · ")
    : IllyI18n.t("reports.noData");
}

// --- Tab 2: Stock & Raw Materials ---
async function loadAdminStock() {
  try {
    const [materials, depletion] = await Promise.all([
      api("/api/stock"),
      api("/api/reports/stock-depletion"),
    ]);
    ADMIN_STATE.rawMaterials = materials || [];
    const depletionById = new Map((depletion || []).map((item) => [item.id, item]));
    const alertFilter = document.getElementById("stock-alert-filter");
    const sortFilter = document.getElementById("stock-sort-filter");
    const critical = ADMIN_STATE.rawMaterials.filter((m) => Number(m.current_stock) <= Number(m.minimum_alert_threshold));
    const watch = ADMIN_STATE.rawMaterials.filter((m) => {
      const usage = depletionById.get(m.id);
      return Number(m.current_stock) > Number(m.minimum_alert_threshold) &&
        (Number(m.current_stock) <= Number(m.minimum_alert_threshold) * 1.5 ||
          (usage && usage.daily_burn_rate > 0 && usage.estimated_days_left <= 7));
    });
    if (alertFilter) {
      alertFilter.innerHTML = `
        <option value="all">${IllyI18n.t("stock.alerts.all")} (${critical.length + watch.length})</option>
        <optgroup label="${IllyI18n.t("stock.alerts.criticalGroup")}">
          ${critical.map((m) => `<option value="${m.id}">🔴 ${m.name} — ${IllyI18n.t("stock.alerts.critical")}</option>`).join("")}
        </optgroup>
        <optgroup label="${IllyI18n.t("stock.alerts.decreasing")}">
          ${watch.map((m) => `<option value="${m.id}">🟡 ${m.name} — ${IllyI18n.t("stock.alerts.decreasing")}</option>`).join("")}
        </optgroup>`;
      alertFilter.onchange = () => {
        const value = alertFilter.value;
        renderStockRows(value, sortFilter?.value || "stock-asc");
      };
    }
    const alertBox = document.getElementById("stock-alert-summary");
    if (alertBox) {
      alertBox.innerHTML = `<span class="stock-alert-inline critical">🔴 ${critical.length} kritik</span><span class="stock-alert-inline watch">🟡 ${watch.length} azalır</span><span class="stock-alert-inline healthy">🟢 ${Math.max(ADMIN_STATE.rawMaterials.length - critical.length - watch.length, 0)} normal</span>`;
    }
    const tbody = document.querySelector("#admin-stock-table tbody");
    if (!tbody) return;

    function renderStockRows(selectedId = alertFilter?.value || "all", sortMode = sortFilter?.value || "stock-asc") {
      const rows = [...ADMIN_STATE.rawMaterials].sort((a, b) => {
        if (selectedId !== "all") {
          if (String(a.id) === String(selectedId)) return -1;
          if (String(b.id) === String(selectedId)) return 1;
        }
        if (sortMode === "name-asc") return String(a.name).localeCompare(String(b.name), undefined, { sensitivity: "base" });
        if (sortMode === "name-desc") return String(b.name).localeCompare(String(a.name), undefined, { sensitivity: "base" });
        if (sortMode === "price-asc") return Number(a.cost_per_unit) - Number(b.cost_per_unit);
        if (sortMode === "price-desc") return Number(b.cost_per_unit) - Number(a.cost_per_unit);
        return Number(a.current_stock) - Number(b.current_stock);
      });
      tbody.innerHTML = rows
      .map((m) => {
        const isLow = m.current_stock <= m.minimum_alert_threshold;
        const stockRatio = Math.max(0, Math.min(100, (Number(m.current_stock) / Math.max(Number(m.minimum_alert_threshold) * 2, 1)) * 100));
        const usage = depletionById.get(m.id);
        const fastDown = usage && usage.daily_burn_rate > 0 && usage.estimated_days_left <= 7;
        const statusBadge = isLow
          ? `<span class="badge badge-warning">⚠️ ${IllyI18n.t("stock.alerts.criticalStock")}</span>`
          : fastDown
            ? `<span class="badge badge-warning">↘ ${IllyI18n.t("stock.alerts.decreasing")}</span>`
            : `<span class="badge badge-success">${IllyI18n.t("common.normal")}</span>`;

        return `
        <tr data-material-id="${m.id}">
          <td style="font-weight: 700;">${m.name}</td>
          <td>${m.category}</td>
          <td>
            <strong class="stock-quantity ${isLow ? "critical" : ""}">${Number(m.current_stock).toFixed(1)}</strong>
            <div class="stock-progress" aria-label="Qalıq səviyyəsi"><span style="width: ${stockRatio}%"></span></div>
          </td>
          <td>${m.unit}</td>
          <td>${m.minimum_alert_threshold} ${m.unit}</td>
          <td>${m.cost_per_unit.toFixed(3)} AZN</td>
          <td class="text-muted">${usage && usage.estimated_days_left < 999 ? `${usage.estimated_days_left} gün` : "—"}</td>
          <td>${statusBadge}</td>
          <td>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button class="btn btn-primary btn-sm" onclick="openRestockForMaterial(${m.id}, '${m.name}')">${IllyI18n.t("stock.actions.restock")}</button>
              <button class="btn btn-outline btn-sm" onclick="openEditStockModal(${m.id})">✏️ ${IllyI18n.t("common.edit")}</button>
              <button class="btn btn-danger btn-sm" onclick="deleteStockItem(${m.id}, '${m.name}')">🗑️ ${IllyI18n.t("common.delete")}</button>
            </div>
          </td>
        </tr>
      `;
      })
      .join("");
      document.querySelectorAll("#admin-stock-table tbody tr").forEach((row) => {
        row.classList.toggle("stock-row-muted", selectedId !== "all" && row.dataset.materialId !== String(selectedId));
        row.classList.toggle("stock-row-selected", selectedId !== "all" && row.dataset.materialId === String(selectedId));
      });
    }
    if (sortFilter) {
      sortFilter.onchange = () => renderStockRows(alertFilter?.value || "all", sortFilter.value);
    }
    renderStockRows();
  } catch (err) {}
}

function openRestockForMaterial(id, name, defQty = 0) {
  document.getElementById("restock-mat-id").value = id;
  document.getElementById("restock-material-title").textContent =
    `${name} üçün anbar artımı`;
  document.getElementById("restock-qty-input").value = defQty > 0 ? defQty : "";
  document.getElementById("restock-notes-input").value = "";
  document.getElementById("restock-waste-input").value = "0";
  document.getElementById("modal-restock").style.display = "flex";
}

function closeRestockModal() {
  document.getElementById("modal-restock").style.display = "none";
}

async function submitRestock(e) {
  e.preventDefault();
  const id = document.getElementById("restock-mat-id").value;
  const quantity = parseFloat(
    document.getElementById("restock-qty-input").value,
  );
  const notes = document.getElementById("restock-notes-input").value;
  const waste_quantity = parseFloat(document.getElementById("restock-waste-input").value || "0");

  try {
    const res = await api(`/api/stock/${id}/restock`, {
      method: "POST",
      body: JSON.stringify({ quantity, waste_quantity, notes }),
    });
    showToast(res.message || "Anbara mədaxil tamamlandı.");
    closeRestockModal();
    loadAdminStock();
  } catch (err) {}
}

function openEditStockModal(id) {
  const m = ADMIN_STATE.rawMaterials.find((x) => x.id === id);
  if (!m) return;
  document.getElementById("edit-mat-id").value = m.id;
  document.getElementById("edit-mat-name").value = m.name;
  document.getElementById("edit-mat-cat").value = m.category;
  document.getElementById("edit-mat-unit").value = m.unit;
  document.getElementById("edit-mat-stock").value = m.current_stock;
  document.getElementById("edit-mat-min").value = m.minimum_alert_threshold;
  document.getElementById("edit-mat-cost").value = m.cost_per_unit;
  document.getElementById("edit-mat-notes").value = "";
  document.getElementById("modal-edit-stock").style.display = "flex";
}

function closeEditStockModal() {
  document.getElementById("modal-edit-stock").style.display = "none";
}

async function submitEditStock(e) {
  e.preventDefault();
  const id = document.getElementById("edit-mat-id").value;
  const payload = {
    name: document.getElementById("edit-mat-name").value.trim(),
    category: document.getElementById("edit-mat-cat").value.trim(),
    unit: document.getElementById("edit-mat-unit").value,
    current_stock: parseFloat(document.getElementById("edit-mat-stock").value),
    minimum_alert_threshold: parseFloat(
      document.getElementById("edit-mat-min").value,
    ),
    cost_per_unit: parseFloat(document.getElementById("edit-mat-cost").value),
    notes:
      document.getElementById("edit-mat-notes").value.trim() ||
      "Anbar qalığı və məlumat redaktəsi",
  };

  try {
    const res = await api(`/api/stock/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    showToast(res.message || "Xammal məlumatları yeniləndi.", "success");
    closeEditStockModal();
    loadAdminStock();
  } catch (err) {}
}

async function deleteStockItem(id, name) {
  if (
    !confirm(
      `'${name}' xammal maddəsini anbardarn silmək istədiyinizdən əminsiniz?`,
    )
  ) {
    return;
  }
  try {
    const res = await api(`/api/stock/${id}`, {
      method: "DELETE",
    });
    showToast(res.message || "Xammal silindi.", "success");
    loadAdminStock();
  } catch (err) {}
}

function deleteStockFromModal() {
  const id = parseInt(document.getElementById("edit-mat-id").value);
  const name = document.getElementById("edit-mat-name").value;
  closeEditStockModal();
  deleteStockItem(id, name);
}

function openNewMaterialModal() {
  document.getElementById("mat-name-input").value = "";
  document.getElementById("mat-cat-input").value = "";
  document.getElementById("mat-stock-input").value = "100.0";
  document.getElementById("mat-min-input").value = "20.0";
  document.getElementById("mat-cost-input").value = "0.05";
  document.getElementById("modal-raw-material").style.display = "flex";
}

function closeMaterialModal() {
  document.getElementById("modal-raw-material").style.display = "none";
}

async function submitCreateMaterial(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById("mat-name-input").value,
    category: document.getElementById("mat-cat-input").value,
    unit: document.getElementById("mat-unit-input").value,
    initial_stock: parseFloat(document.getElementById("mat-stock-input").value),
    minimum_alert_threshold: parseFloat(
      document.getElementById("mat-min-input").value,
    ),
    cost_per_unit: parseFloat(document.getElementById("mat-cost-input").value),
  };

  try {
    const res = await api("/api/stock", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast(res.message || "Yeni xammal əlavə edildi.");
    closeMaterialModal();
    loadAdminStock();
  } catch (err) {}
}

// --- Tab 3: Products & Flexible Recipes ---
async function loadAdminCatalog() {
  try {
    updateCatalogStatusLabels();
    const [products, materials] = await Promise.all([
      api("/api/products"),
      api("/api/stock"),
    ]);

    ADMIN_STATE.catalog = products || [];
    ADMIN_STATE.rawMaterials = materials || [];

    const tbody = document.querySelector("#admin-catalog-table tbody");
    if (!tbody) return;

    const statusFilter = document.getElementById("catalog-status-filter")?.value || "all";
    const visibleProducts = ADMIN_STATE.catalog.filter((product) =>
      statusFilter === "all" ||
      (statusFilter === "active" && product.is_active) ||
      (statusFilter === "inactive" && !product.is_active)
    );
    tbody.innerHTML = visibleProducts
      .map((p) => {
        const variantsHtml = (p.variants || [])
          .map(
            (v) =>
              `<div class="catalog-variant-row">
                 <span><strong style="color: var(--text-main);">${escapeAdminHtml(v.name)}:</strong> <span style="color: var(--primary); font-weight: 700;">${Number(v.price).toFixed(2)} AZN</span></span>
                 <div style="display: flex; gap: 6px;">
                   <button type="button" class="btn btn-outline btn-sm" data-variant-action="recipe" data-variant-id="${v.id}" data-variant-name="${escapeAdminHtml(`${p.name} - ${v.name}`)}" style="padding: 3px 10px; font-size: 12px;">${IllyI18n.t("catalog.recipe")}</button>
                        <button type="button" class="btn btn-danger btn-sm" data-variant-action="delete" data-variant-id="${v.id}" data-variant-name="${escapeAdminHtml(`${p.name} - ${v.name}`)}" style="padding: 3px 10px; font-size: 12px;">${IllyI18n.t("common.delete")}</button>
                 </div>
               </div>`,
          )
          .join("");

        const iconUrl = p.image_url || "/static/images/icons/premium-coffee.svg";

        return `
        <tr>
          <td style="font-weight: 700;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <img src="${escapeAdminHtml(iconUrl)}" style="width: 40px; height: 40px; border-radius: 20%; object-fit: cover; border: 1px solid var(--border);" onerror="this.src='/static/images/icons/premium-coffee.svg'">
              <div>
                <div>${escapeAdminHtml(p.name)}</div>
                <div style="font-size: 12px; color: var(--text-muted); font-weight: normal;">${escapeAdminHtml(p.description)}</div>
              </div>
            </div>
          </td>
          <td>${escapeAdminHtml(p.category)}</td>
          <td>${variantsHtml || `<span style="color: var(--text-muted); font-size: 12px;">${IllyI18n.t("catalog.noVariants")}</span>`}</td>
          <td style="font-size: 12px; color: var(--text-muted);">${IllyI18n.t("catalog.variantCount", { count: (p.variants || []).length })}</td>
          <td>${p.is_active ? `<span class="badge badge-success">${getCatalogStatusLabels()[1]}</span>` : `<span class="badge badge-warning">${getCatalogStatusLabels()[2]}</span>`}</td>
          <td>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button type="button" class="btn btn-outline btn-sm" data-add-variant-product="${p.id}" data-add-variant-name="${escapeAdminHtml(p.name)}">${IllyI18n.t("catalog.addVariant")}</button>
              <button type="button" class="btn btn-outline btn-sm" onclick="openEditProductModal(${p.id})">${IllyI18n.t("catalog.edit") || "Redaktə"}</button>
              <button type="button" class="btn btn-danger btn-sm" onclick="deleteProductItem(${p.id}, ${adminJsString(p.name)})">🗑️ ${IllyI18n.t("common.delete")}</button>
            </div>
          </td>
        </tr>
      `;
      })
      .join("");
    tbody.querySelectorAll("[data-add-variant-product]").forEach((button) => {
      button.onclick = () => promptAddVariant(Number(button.dataset.addVariantProduct), button.dataset.addVariantName);
    });
    tbody.querySelectorAll("[data-variant-action]").forEach((button) => {
      button.onclick = () => button.dataset.variantAction === "delete"
        ? deleteVariantItem(Number(button.dataset.variantId), button.dataset.variantName)
        : openRecipeEditor(Number(button.dataset.variantId), button.dataset.variantName);
    });
  } catch (err) {}
}

function filterAdminCatalog() {
  loadAdminCatalog();
}

function updateCatalogStatusLabels() {
  const language = window.IllyI18n?.language || "az";
  const labels = {
    az: ["Hamısı", "Aktiv", "Passiv"],
    tr: ["Tümü", "Aktif", "Pasif"],
    en: ["All", "Active", "Inactive"],
    ru: ["Все", "Активные", "Неактивные"],
  }[language] || ["Hamısı", "Aktiv", "Passiv"];
  const filter = document.getElementById("catalog-status-filter");
  if (filter) [...filter.options].forEach((option, index) => { option.textContent = labels[index]; });
  const status = document.getElementById("edit-prod-status");
  if (status) [...status.options].forEach((option, index) => { option.textContent = labels[index + 1]; });
}

function getCatalogStatusLabels() {
  const language = window.IllyI18n?.language || "az";
  return {
    az: ["Hamısı", "Aktiv", "Passiv"],
    tr: ["Tümü", "Aktif", "Pasif"],
    en: ["All", "Active", "Inactive"],
    ru: ["Все", "Активные", "Неактивные"],
  }[language] || ["Hamısı", "Aktiv", "Passiv"];
}

function openEditProductModal(productId) {
  const product = ADMIN_STATE.catalog.find((item) => Number(item.id) === Number(productId));
  if (!product) return;
  document.getElementById("edit-prod-id").value = product.id;
  document.getElementById("edit-prod-name").value = product.name || "";
  document.getElementById("edit-prod-category").value = product.category || "";
  document.getElementById("edit-prod-description").value = product.description || "";
  document.getElementById("edit-prod-image").value = product.image_url || "";
  document.getElementById("edit-prod-status").value = product.is_active ? "1" : "0";
  document.getElementById("modal-edit-product").style.display = "flex";
}
function closeEditProductModal() {
  document.getElementById("modal-edit-product").style.display = "none";
}
async function submitEditProduct(event) {
  event.preventDefault();
  const id = document.getElementById("edit-prod-id").value;
  try {
    const result = await api(`/api/products/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        name: document.getElementById("edit-prod-name").value.trim(),
        category: document.getElementById("edit-prod-category").value.trim(),
        description: document.getElementById("edit-prod-description").value.trim(),
        image_url: document.getElementById("edit-prod-image").value.trim(),
        is_active: Number(document.getElementById("edit-prod-status").value),
      }),
    });
    showToast(result.message || "Məhsul yeniləndi.", "success");
    closeEditProductModal();
    await loadAdminCatalog();
  } catch (err) {}
}

function openNewProductModal() {
  document.getElementById("new-prod-name").value = "";
  document.getElementById("new-prod-category").value = "Espresso";
  document.getElementById("new-prod-price").value = "5.50";
  document.getElementById("new-prod-variant").value = "Standart";
  document.getElementById("new-prod-icon").value =
    "/static/images/icons/premium-espresso.svg";
  previewNewProdIcon("/static/images/icons/premium-espresso.svg");
  document.getElementById("new-prod-desc").value = "";
  document.getElementById("new-prod-upload-status").textContent = "";
  document.getElementById("modal-create-product").style.display = "flex";
}

function closeNewProductModal() {
  document.getElementById("modal-create-product").style.display = "none";
}

function previewNewProdIcon(url) {
  const preview = document.getElementById("new-prod-icon-preview");
  if (preview) preview.src = url;
}

async function uploadCustomProductImage(input) {
  if (!input.files || !input.files[0]) return;
  const formData = new FormData();
  formData.append("file", input.files[0]);

  try {
    document.getElementById("new-prod-upload-status").textContent =
      "Yüklənir...";
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${STATE.token}`,
      },
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Yükləmə xətası");

    const select = document.getElementById("new-prod-icon");
    const opt = document.createElement("option");
    opt.value = data.url;
    opt.textContent = "Fərdi Şəkil";
    opt.selected = true;
    select.appendChild(opt);
    previewNewProdIcon(data.url);
    document.getElementById("new-prod-upload-status").textContent =
      "✓ Yükləndi";
    showToast("Şəkil uğurla yükləndi!", "success");
  } catch (err) {
    document.getElementById("new-prod-upload-status").textContent = "Xəta";
    showToast(err.message, "error");
  }
}

async function submitCreateProduct(e) {
  e.preventDefault();
  const name = document.getElementById("new-prod-name").value.trim();
  const category = document.getElementById("new-prod-category").value;
  const price = parseFloat(document.getElementById("new-prod-price").value);
  const variantName =
    document.getElementById("new-prod-variant").value.trim() || "Standart";
  const iconUrl = document.getElementById("new-prod-icon").value;
  const description = document.getElementById("new-prod-desc").value.trim();

  if (!name) {
    showToast("Məhsul adı daxil edilməlidir.", "warning");
    return;
  }

  const payload = {
    name,
    category,
    description,
    image_url: iconUrl,
    variants: [{ name: variantName, price: price }],
  };

  try {
    const res = await api("/api/products", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast(res.message || "Yeni məhsul uğurla yaradıldı!", "success");
    closeNewProductModal();
    loadAdminCatalog();
  } catch (err) {}
}

async function deleteProductItem(prodId, prodName) {
  if (
    !confirm(
      `'${prodName}' məhsulunu və ona aid bütün variantları silmək istədiyinizdən əminsiniz?`,
    )
  ) {
    return;
  }
  try {
    const res = await api(`/api/products/${prodId}`, {
      method: "DELETE",
    });
    showToast(res.message || "Məhsul silindi.", "success");
    loadAdminCatalog();
  } catch (err) {}
}

async function deleteVariantItem(variantId, variantName) {
  if (
    !confirm(`'${variantName}' variantını silmək istədiyinizdən əminsiniz?`)
  ) {
    return;
  }
  try {
    const res = await api(`/api/products/variants/${variantId}`, {
      method: "DELETE",
    });
    showToast(res.message || "Variant silindi.", "success");
    loadAdminCatalog();
  } catch (err) {
    showToast(err.message || IllyI18n.t("catalog.variantDeleteFailed"), "error");
  }
}

async function promptAddVariant(prodId, prodName) {
  const values = await openQuickForm(
    IllyI18n.t("catalog.addVariantTitle", { product: prodName }),
    IllyI18n.t("catalog.addVariantHint"),
    [
    { name: "name", label: IllyI18n.t("catalog.variantName"), value: IllyI18n.t("catalog.defaultVariantName") },
    { name: "price", label: IllyI18n.t("catalog.salePrice"), type: "number", value: "6.50" },
  ]);
  if (!values) return;
  try {
    const res = await api(`/api/products/${prodId}/variants`, {
      method: "POST",
      body: JSON.stringify({ name: values.name, price: parseFloat(values.price) }),
    });
    showToast(res.message || IllyI18n.t("catalog.variantAdded"), "success");
    loadAdminCatalog();
  } catch (err) {
    showToast(err.message || IllyI18n.t("catalog.variantAddFailed"), "error");
  }
}

// Recipe Editor Modal
async function openRecipeEditor(variantId, variantTitle) {
  document.getElementById("recipe-variant-id").value = variantId;
  document.getElementById("recipe-editor-title").textContent =
    `Resept: ${variantTitle}`;

  try {
    const existingIngredients = await api(`/api/recipes/${variantId}`);
    const list = document.getElementById("recipe-ingredients-list");
    list.innerHTML = "";

    if (existingIngredients && existingIngredients.length) {
      existingIngredients.forEach((ing) =>
        addRecipeIngredientRow(ing.raw_material_id, ing.quantity, ing.waste_factor),
      );
    } else {
      addRecipeIngredientRow();
    }

    document.getElementById("modal-recipe-editor").style.display = "flex";
  } catch (err) {}
}

function addRecipeIngredientRow(selectedMatId = null, qty = 1.0, wasteFactor = 1.0) {
  const list = document.getElementById("recipe-ingredients-list");
  const row = document.createElement("div");
  row.className = "recipe-row";

  const options = ADMIN_STATE.rawMaterials
    .map(
      (m) =>
        `<option value="${m.id}" ${selectedMatId === m.id ? "selected" : ""}>${m.name} (${m.unit})</option>`,
    )
    .join("");

  row.innerHTML = `
    <label class="recipe-field recipe-material-field">
      <span>Xammal <small>stok vahidi</small></span>
      <select class="input-field recipe-mat-select" data-az-tooltip="Bu variant hazırlanarkən stokdan çıxılacaq xammalı seçin. Vahid mötərizədə göstərilir.">${options}</select>
    </label>
    <label class="recipe-field">
      <span>Miqdar <small>1 satış üçün</small></span>
      <input type="number" step="0.1" min="0.001" class="input-field recipe-qty-input" value="${qty}" placeholder="Məs: 18" data-az-tooltip="Bir ədəd bu variant üçün istifadə olunan xammal miqdarıdır. Məsələn 18 g və ya 250 ml.">
    </label>
    <label class="recipe-field">
      <span>İtki əmsalı <small>1.00 = 0%</small></span>
      <input type="number" step="0.01" min="1" class="input-field recipe-waste-input" value="${wasteFactor}" placeholder="Məs: 1.03" data-az-tooltip="Hazırlanma itkisini əlavə edir. 1.00 itkisizdir; 1.03 stokdan 3% artıq çıxılmasını bildirir.">
    </label>
    <button type="button" class="btn btn-outline btn-sm recipe-remove-btn" onclick="this.closest('.recipe-row').remove()" data-az-tooltip="Bu xammalı resept sətrindən çıxarır." aria-label="Xammal sətrini sil">✕</button>
  `;
  list.appendChild(row);
}

function closeRecipeModal() {
  document.getElementById("modal-recipe-editor").style.display = "none";
}

async function saveVariantRecipe() {
  const variantId = document.getElementById("recipe-variant-id").value;
  const rows = document.querySelectorAll(".recipe-row");
  const ingredients = [];

  rows.forEach((r) => {
    const matId = parseInt(r.querySelector(".recipe-mat-select").value);
    const qty = parseFloat(r.querySelector(".recipe-qty-input").value);
    const waste_factor = parseFloat(r.querySelector(".recipe-waste-input").value || "1");
    if (matId && Number.isFinite(qty) && qty > 0 && Number.isFinite(waste_factor) && waste_factor >= 1) {
      ingredients.push({ raw_material_id: matId, quantity: qty, waste_factor });
    }
  });

  if (ingredients.length !== rows.length) {
    showToast("Hər resept sətrində xammal, sıfırdan böyük miqdar və ən azı 1.00 itki əmsalı daxil edin.", "warning");
    return;
  }

  try {
    const res = await api(`/api/recipes/${variantId}`, {
      method: "POST",
      body: JSON.stringify({ ingredients }),
    });
    showToast(res.message || "Resept yadda saxlanıldı.", "success");
    closeRecipeModal();
  } catch (err) {}
}

async function clearWholeRecipe() {
  const variantId = document.getElementById("recipe-variant-id").value;
  if (!variantId) return;
  if (
    !confirm(
      "Bu variant üçün bütün resept inqrediyentlərini silmək istədiyinizdən əminsiniz?",
    )
  ) {
    return;
  }
  try {
    const res = await api(`/api/recipes/variant/${variantId}`, {
      method: "DELETE",
    });
    showToast(res.message || "Resept tam təmizləndi.", "info");
    closeRecipeModal();
  } catch (err) {}
}

// --- Tab 4: Shifts ---
async function loadAdminShifts() {
  try {
    const shifts = await api("/api/shifts");
    const tbody = document.querySelector("#admin-shifts-table tbody");
    if (!tbody) return;

    tbody.innerHTML = (shifts || [])
      .map((s) => {
        const statusBadge =
          s.status === "open"
            ? `<span class="badge badge-warning">Açıq</span>`
            : `<span class="badge badge-success">Bağlanıb</span>`;

        return `
        <tr>
          <td>#${s.id}</td>
          <td style="font-weight: 700;">${s.barista_name}</td>
          <td>${s.opened_at.slice(0, 16).replace("T", " ")}</td>
          <td>${s.closed_at ? s.closed_at.slice(0, 16).replace("T", " ") : "-"}</td>
          <td>${s.opening_cash.toFixed(2)} AZN</td>
          <td>${s.closing_cash ? s.closing_cash.toFixed(2) + " AZN" : "-"}</td>
          <td>${s.order_count || 0} ədəd</td>
          <td>${statusBadge}</td>
        </tr>
      `;
      })
      .join("");
  } catch (err) {}
}

async function openShiftActionModal() {
  const active = await api("/api/shifts/active");
  if (active && active.id) {
    const values = await openQuickForm(`Növbəni bağla #${active.id}`, `${active.barista_name} üçün faktiki kassa məbləği.`, [{ name: "closing_cash", label: "Faktiki kassa (AZN)", type: "number", value: active.metrics?.expected_cash?.toFixed(2) || "0.00" }]);
    if (values) {
      try {
        const res = await api(`/api/shifts/${active.id}/close`, {
          method: "POST",
          body: JSON.stringify({
            closing_cash: parseFloat(values.closing_cash),
            notes: "Admin tərəfindən bağlandı",
          }),
        });
        showToast(res.message || "Növbə bağlandı.");
        loadAdminShifts();
      } catch (err) {}
    }
  } else {
    const values = await openQuickForm("Yeni növbə aç", "İlkin kassa qalığını daxil edin.", [{ name: "opening_cash", label: "İlkin kassa (AZN)", type: "number", value: "0.00" }]);
    if (values) {
      try {
        const res = await api("/api/shifts/open", {
          method: "POST",
          body: JSON.stringify({
            opening_cash: parseFloat(values.opening_cash),
            notes: "Admin tərəfindən açıldı",
          }),
        });
        showToast(res.message || "Növbə açıldı.");
        loadAdminShifts();
      } catch (err) {}
    } else {
      return;
    }
  }
}

// --- Tab 5: Inventory Count (Physical Stock Auditing) ---
async function loadAdminInventory() {
  try {
    const sessions = await api("/api/inventory");
    const tbody = document.querySelector("#admin-inventory-table tbody");
    if (!tbody) return;

    tbody.innerHTML = (sessions || [])
      .map((s) => {
        const statusBadge =
          s.status === "confirmed"
            ? `<span class="badge badge-success">${IllyI18n.t("inventory.confirmed")}</span>`
            : `<span class="badge badge-warning">${IllyI18n.t("inventory.draft")}</span>`;

        return `
        <tr>
          <td>#${s.id}</td>
          <td style="font-weight: 700;">${s.auditor_name}</td>
          <td>${s.created_at.slice(0, 16).replace("T", " ")}</td>
          <td>${IllyI18n.t("inventory.materialCount", { count: s.total_items })}</td>
          <td style="color: ${s.discrepancy_count > 0 ? "var(--danger)" : "var(--accent)"}; font-weight: 700;">${IllyI18n.t("inventory.varianceCountLabel", { count: s.discrepancy_count })}</td>
          <td>${statusBadge}</td>
          <td>
            <button class="btn btn-outline btn-sm" onclick="openInventorySessionDetails(${s.id})">${IllyI18n.t("inventory.openCount")}</button>
          </td>
        </tr>
      `;
      })
      .join("");
  } catch (err) {}
}

async function startNewInventorySession() {
  if (
    !confirm(
      "Bütün aktiv xammal qalıqları üzrə yeni sayım sessiyası başlansın?",
    )
  )
    return;
  try {
    const res = await api("/api/inventory/start", {
      method: "POST",
      body: JSON.stringify({ notes: "Rutin dövri inventarizasiya" }),
    });
    showToast(res.message || "Sayım sessiyası başladıldı.");
    loadAdminInventory();
    if (res.id) openInventorySessionDetails(res.id);
  } catch (err) {}
}

async function openInventorySessionDetails(sessionId) {
  try {
    const session = await api(`/api/inventory/${sessionId}`);
    const isConfirmed = session.status === "confirmed";

    let html = `
      <div style="max-height: 400px; overflow-y: auto; margin-bottom: 16px;">
        <table class="data-table" style="font-size: 13px;">
          <thead>
            <tr>
              <th>Xammal</th>
              <th>Sistem Qalığı</th>
              <th>Faktiki Sayım</th>
              <th>Fərq (İtki/Artıq)</th>
            </tr>
          </thead>
          <tbody>
    `;

    (session.items || []).forEach((item) => {
      const varColor =
        item.variance < 0
          ? "var(--danger)"
          : item.variance > 0
            ? "var(--accent)"
            : "var(--text-muted)";
      html += `
        <tr>
          <td><strong>${item.material_name}</strong></td>
          <td>${item.system_quantity.toFixed(1)} ${item.material_unit}</td>
          <td>
            ${
              isConfirmed
                ? `${item.counted_quantity.toFixed(1)} ${item.material_unit}`
                : `<input type="number" step="0.1" class="input-field inv-count-input" data-id="${item.id}" value="${item.counted_quantity}" style="width: 100px; padding: 4px 8px;">`
            }
          </td>
          <td style="color: ${varColor}; font-weight: 700;">${item.variance > 0 ? "+" : ""}${item.variance.toFixed(1)} ${item.material_unit}</td>
        </tr>
      `;
    });

    html += `</tbody></table></div>`;

    if (!isConfirmed) {
      html += `
        <div style="display: flex; gap: 10px;">
          <button class="btn btn-outline" onclick="saveInventoryDraft(${sessionId})" style="flex: 1;">Qaralamanı Saxla</button>
          <button class="btn btn-primary" onclick="confirmInventoryAdjustments(${sessionId})" style="flex: 1;">Qalıqları Düzəlt və Təsdiqlə</button>
        </div>
      `;
    }

    document.getElementById("variant-modal-title").textContent =
      `Sayım Sessiyası #${session.id} (${session.status})`;
    const list = document.getElementById("variant-modal-list");
    list.innerHTML = html;
    document.getElementById("modal-variant-select").style.display = "flex";
  } catch (err) {}
}

async function saveInventoryDraft(sessionId) {
  const inputs = document.querySelectorAll(".inv-count-input");
  const items = Array.from(inputs).map((inp) => ({
    id: parseInt(inp.dataset.id),
    counted_quantity: parseFloat(inp.value),
  }));

  try {
    const res = await api(`/api/inventory/${sessionId}`, {
      method: "PUT",
      body: JSON.stringify({ items }),
    });
    showToast(res.message || "Sayım məlumatları saxlanıldı.");
    openInventorySessionDetails(sessionId);
  } catch (err) {}
}

async function confirmInventoryAdjustments(sessionId) {
  if (
    !confirm(
      "Faktiki sayım nəticələri anbar qalığına tətbiq edilsin? Bu əməliyyat rəsmi audit qeydi yaradacaq.",
    )
  )
    return;
  try {
    const res = await api(`/api/inventory/${sessionId}/confirm`, {
      method: "POST",
      body: JSON.stringify({ notes: "Sayım fərqləri qəbul edildi" }),
    });
    showToast(res.message || "İnventarizasiya təsdiqləndi.");
    closeVariantModal();
    loadAdminInventory();
  } catch (err) {}
}

// --- Tab 6: Staff Management ---
async function loadAdminStaff() {
  try {
    const users = await api("/api/users");
    const mail = await api("/api/admin/mail-settings");
    if (mail) {
      document.getElementById("smtp-host").value = mail.smtp_host || "";
      document.getElementById("smtp-port").value = mail.smtp_port || 587;
      document.getElementById("smtp-username").value = mail.smtp_username || "";
      document.getElementById("smtp-from").value = mail.smtp_from || "";
      document.getElementById("smtp-tls").checked = mail.smtp_use_tls !== false;
    }
    const tbody = document.querySelector("#admin-staff-table tbody");
    if (!tbody) return;

    tbody.innerHTML = (users || [])
      .map(
        (u) => `
      <tr>
        <td><img src="${escapeAdminHtml(u.avatar_url || "/static/images/avatar-user.svg")}" class="user-avatar-sm" alt="Avatar"></td>
        <td style="font-weight: 700;">${escapeAdminHtml(u.full_name)}</td>
        <td>@${escapeAdminHtml(u.username)}</td>
        <td>${escapeAdminHtml(u.email || "-")}</td>
        <td><span class="badge badge-${u.role === "admin" ? "admin" : "barista"}">${u.role.toUpperCase()}</span></td>
        <td>${u.is_active ? '<span class="badge badge-success">Aktiv</span>' : `<span class="badge badge-warning">İşdən çıxarılıb</span><small class="report-muted">${u.employment_end_at ? ` · ${String(u.employment_end_at).slice(0, 10)}` : ""}</small>`}</td>
        <td>
          <button class="btn btn-primary btn-sm" onclick="openEmployeeReport(${u.id})">${IllyI18n.t("reports.employee")}</button>
          <button class="btn btn-outline btn-sm" onclick="promptResetStaffPassword(${u.id}, ${adminJsString(u.full_name)})">${IllyI18n.t("staff.resetPassword")}</button>
          <button class="btn btn-outline btn-sm" style="color: var(--danger);" onclick="deleteStaffAccount(${u.id}, ${adminJsString(u.full_name)})">${IllyI18n.t("common.delete")}</button>
        </td>
      </tr>
    `,
      )
      .join("");
  } catch (err) {}
}

async function saveMailSettings() {
  const res = await api("/api/admin/mail-settings", {
    method: "POST",
    body: JSON.stringify({
      smtp_host: document.getElementById("smtp-host").value,
      smtp_port: document.getElementById("smtp-port").value,
      smtp_username: document.getElementById("smtp-username").value,
      smtp_password: document.getElementById("smtp-password").value,
      smtp_from: document.getElementById("smtp-from").value,
      smtp_use_tls: document.getElementById("smtp-tls").checked,
    }),
  });
  showToast(res.message || "SMTP ayarları saxlanıldı.");
  document.getElementById("smtp-password").value = "";
}

function openNewStaffModal() {
  openDeveloperNewUser("barista");
}

async function promptResetStaffPassword(userId, fullName) {
  const users = await api("/api/users");
  const user = (users || []).find((item) => item.id === userId);
  if (user && typeof openUserEditModal === "function") openUserEditModal(userId, user);
}

async function deleteStaffAccount(userId, fullName) {
  if (!(await requestActionConfirmation(`'${fullName}' hesabını silmək istədiyinizdən əminsiniz?`))) return;
  api(`/api/users/${userId}`, {
    method: "DELETE",
  }).then((res) => {
    showToast(res.message || "İstifadəçi silindi.");
    loadAdminStaff();
  });
}

// --- Tab 7: Retention Policy ---
async function loadAdminRetention() {
  try {
    const res = await api("/api/retention");
    if (res && res.policy) {
      document.getElementById("retention-policy-select").value = res.policy;
    }
  } catch (err) {}
}

async function saveRetentionPolicy() {
  const policy = document.getElementById("retention-policy-select").value;
  try {
    const res = await api("/api/retention", {
      method: "POST",
      body: JSON.stringify({ policy }),
    });
    showToast(res.message || "Saxlama siyasəti saxlanıldı.");
  } catch (err) {}
}

async function runRetentionCleanupNow() {
  if (!(await requestActionConfirmation("Köhnə əməliyyat arxivinin təmizlənməsi icra edilsin? ML modelləri və əsas xammallar qorunacaq."))) return;
  try {
    const res = await api("/api/retention/run", { method: "POST" });
    showToast(res.message || "Təmizləmə tamamlandı.");
  } catch (err) {}
}
