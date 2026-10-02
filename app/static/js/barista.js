/**
 * Barista POS Fast Touch Ordering Interface
 * Illy Specialty Coffee Management System
 */

const POS_STATE = {
  products: [],
  categories: [],
  selectedCategory: "all",
  shortcuts: [],
  cart: [],
  discountType: "none",
  discountValue: 0.0,
  paymentMethod: "cash",
  fulfillmentType: "in_store",
  activeShift: null,
};

window.initBaristaPOS = async function () {
  await loadShiftStatus();
  await loadCatalogAndShortcuts();
  renderCart();
};

async function loadShiftStatus() {
  try {
    const shift = await api("/api/shifts/active");
    POS_STATE.activeShift = shift && shift.id ? shift : null;
  } catch (err) {
    POS_STATE.activeShift = null;
  }
}

async function loadCatalogAndShortcuts() {
  try {
    const [prods, shortcuts] = await Promise.all([
      api("/api/products?active_only=1"),
      api("/api/shortcuts"),
    ]);

    POS_STATE.products = prods || [];
    POS_STATE.shortcuts = shortcuts || [];

    // Extract unique categories
    const catSet = new Set(["all"]);
    POS_STATE.products.forEach((p) => catSet.add(p.category));
    POS_STATE.categories = Array.from(catSet);

    renderShortcuts();
    renderCategories();
    renderProducts();
  } catch (err) {
    console.error("Error loading POS catalog:", err);
  }
}

let draggedShortcutIdx = null;
let draggedShortcutId = null;
let suppressShortcutClick = false;
let draggedProductId = null;

function reorderShortcutCards(sourceId, targetId) {
  if (!sourceId || !targetId || sourceId === targetId) return false;
  const sourceIndex = POS_STATE.shortcuts.findIndex(
    (shortcut) => String(shortcut.shortcut_id) === String(sourceId),
  );
  const targetIndex = POS_STATE.shortcuts.findIndex(
    (shortcut) => String(shortcut.shortcut_id) === String(targetId),
  );
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return false;

  const [item] = POS_STATE.shortcuts.splice(sourceIndex, 1);
  POS_STATE.shortcuts.splice(targetIndex, 0, item);
  suppressShortcutClick = true;
  window.setTimeout(() => {
    suppressShortcutClick = false;
  }, 400);
  renderShortcuts();
  saveReorderedShortcuts();
  return true;
}

function getProductIcon(product) {
  const text = `${product?.name || ""} ${product?.category || ""}`.toLowerCase();
  if (text.includes("latte") || text.includes("cappuccino") || text.includes("süd"))
    return "/static/images/icons/premium-milk.svg";
  if (text.includes("americano") || text.includes("espresso") || text.includes("flat white"))
    return "/static/images/icons/premium-espresso.svg";
  if (text.includes("cold") || text.includes("buz") || text.includes("frappe") || text.includes("frapp"))
    return "/static/images/icons/premium-cold.svg";
  if (text.includes("çay") || text.includes("tea") || text.includes("matcha"))
    return "/static/images/icons/premium-tea.svg";
  if (text.includes("şirni") || text.includes("dessert") || text.includes("kruasan") || text.includes("croissant"))
    return "/static/images/icons/premium-pastry.svg";
  return "/static/images/icons/premium-coffee.svg";
}

// Render Pinned Shortcuts (Rule F1)
function renderShortcuts() {
  const container = document.getElementById("barista-shortcuts-grid");
  if (!container) return;

  if (!POS_STATE.shortcuts.length) {
    container.innerHTML = `<div style="grid-column: 1/-1; color: var(--text-muted); font-size: 14px; text-align: center; padding: 16px;">Tez satış üçün məhsul sancılmayıb. 'Tənzimlə' düyməsindən istənilən məhsulu əlavə edə bilərsiniz.</div>`;
    return;
  }

  container.innerHTML = "";
  POS_STATE.shortcuts.forEach((sc, idx) => {
    const card = document.createElement("div");
    card.className = "shortcut-card";
    card.setAttribute("draggable", "true");
    card.dataset.index = idx;
    card.dataset.shortcutId = sc.shortcut_id;

    // Click handler for order entry
    card.onclick = (e) => {
      if (e.target.closest(".shortcut-card-edit-btn")) return;
      if (suppressShortcutClick) {
        suppressShortcutClick = false;
        return;
      }
      addVariantToCart(
        {
          id: sc.variant_id,
          name: sc.variant_name,
          price: sc.price,
        },
        {
          name: sc.product_name,
        },
      );
    };

    // Drag and Drop events (Desktop)
    card.addEventListener("dragstart", (e) => {
      draggedShortcutIdx = idx;
      draggedShortcutId = String(sc.shortcut_id);
      card.classList.add("dragging");
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", draggedShortcutId);
      }
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", () => {
      card.classList.remove("drag-over");
    });

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      const sourceId = e.dataTransfer?.getData("text/plain") || draggedShortcutId;
      reorderShortcutCards(sourceId, card.dataset.shortcutId);
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      document
        .querySelectorAll(".shortcut-card")
        .forEach((c) => c.classList.remove("drag-over"));
      draggedShortcutIdx = null;
      draggedShortcutId = null;
    });

    // Touch Drag & Drop support (Touch devices / iPads)
    let touchStartX = 0;
    let touchStartY = 0;
    let touchTimer = null;
    let isTouchDragging = false;

    card.addEventListener(
      "touchstart",
      (e) => {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchTimer = setTimeout(() => {
          isTouchDragging = true;
          card.classList.add("dragging");
        }, 350); // 350ms hold to reorder
      },
      { passive: true },
    );

    card.addEventListener("touchmove", (e) => {
      if (!isTouchDragging) {
        clearTimeout(touchTimer);
        return;
      }
      e.preventDefault();
      const curX = e.touches[0].clientX;
      const curY = e.touches[0].clientY;
      const target = document.elementFromPoint(curX, curY);
      const targetCard = target ? target.closest(".shortcut-card") : null;
      document
        .querySelectorAll(".shortcut-card")
        .forEach((c) => c.classList.remove("drag-over"));
      if (targetCard && targetCard !== card) {
        targetCard.classList.add("drag-over");
      }
    });

    card.addEventListener("touchend", (e) => {
      clearTimeout(touchTimer);
      if (isTouchDragging) {
        card.classList.remove("dragging");
        isTouchDragging = false;
        const curX = e.changedTouches[0].clientX;
        const curY = e.changedTouches[0].clientY;
        const target = document.elementFromPoint(curX, curY);
        const targetCard = target ? target.closest(".shortcut-card") : null;
        if (targetCard && targetCard !== card) {
          reorderShortcutCards(
            card.dataset.shortcutId,
            targetCard.dataset.shortcutId,
          );
        }
      }
      document
        .querySelectorAll(".shortcut-card")
        .forEach((c) => c.classList.remove("drag-over"));
      draggedShortcutIdx = null;
      draggedShortcutId = null;
    });

    const iconUrl = sc.icon_url || getProductIcon({
      name: sc.product_name,
      category: sc.category,
      image_url: sc.image_url,
    });
    const label = sc.custom_label || `${sc.product_name} (${sc.variant_name})`;

    card.innerHTML = `
      <img src="${iconUrl}" class="shortcut-card-icon" alt="${sc.product_name}" onerror="this.src='/static/images/icons/premium-coffee.svg'">
      <div class="shortcut-card-name">${label}</div>
      <div class="shortcut-card-price">${sc.price.toFixed(2)} AZN</div>
      <button type="button" class="shortcut-card-edit-btn" onclick="openEditSingleShortcutModal(${sc.shortcut_id})" title="Qısayolu redaktə et">⚙️</button>
    `;
    container.appendChild(card);
  });
}

// Render Category Filter Tabs
function renderCategories() {
  const container = document.getElementById("pos-category-tabs");
  if (!container) return;
  container.innerHTML = "";

  const categoryLabels = {
    all: IllyI18n.t("pos.categories.all"),
    Espresso: IllyI18n.t("pos.categories.espresso"),
    "İsti İçkilər": IllyI18n.t("pos.categories.hotDrinks"),
    "Südlü Qəhvələr": IllyI18n.t("pos.categories.milkCoffee"),
    "Xüsusi İçkilər": IllyI18n.t("pos.categories.special"),
    Şirniyyat: IllyI18n.t("pos.categories.pastry"),
    Digər: IllyI18n.t("pos.categories.other"),
  };

  const categories = ["all", ...POS_STATE.categories.filter((cat) => cat !== "all")];
  categories.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = `category-tab ${POS_STATE.selectedCategory === cat ? "active" : ""}`;
    btn.textContent = categoryLabels[cat] || cat;
    btn.onclick = () => {
      POS_STATE.selectedCategory = cat;
      renderCategories();
      renderProducts();
    };
    container.appendChild(btn);
  });
  // Always keep the primary "Bütün Menyu" action visible after a rerender.
  container.scrollLeft = 0;
}

function updatePOSFullscreenButton() {
  const button = document.getElementById("pos-fullscreen-btn");
  if (!button) return;
  const active = Boolean(document.fullscreenElement);
  button.textContent = active ? "⛶ Tam ekrandan çıx" : "⛶ Tam ekran";
  button.title = active ? "Tam ekran rejimindən çıx" : "Kassanı tam ekran aç";
}

async function togglePOSFullscreen() {
  const fullscreenTarget = document.documentElement;
  if (!fullscreenTarget) return;
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else if (fullscreenTarget.requestFullscreen) {
      await fullscreenTarget.requestFullscreen();
    } else {
      showToast("Bu brauzer tam ekran rejimini dəstəkləmir.", "warning");
      return;
    }
    updatePOSFullscreenButton();
  } catch (err) {
    showToast("Tam ekran rejimi açıla bilmədi.", "error");
  }
}

document.addEventListener("fullscreenchange", updatePOSFullscreenButton);

// Render Adaptive Product Grid (Rule F1)
function renderProducts() {
  const grid = document.getElementById("pos-product-grid");
  if (!grid) return;
  grid.innerHTML = "";

  const filtered =
    POS_STATE.selectedCategory === "all"
      ? POS_STATE.products
      : POS_STATE.products.filter(
          (p) => p.category === POS_STATE.selectedCategory,
        );

  if (!filtered.length) {
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 40px;">Bu kateqoriyada aktiv məhsul tapılmadı.</div>`;
    return;
  }

  filtered.forEach((p) => {
    const card = document.createElement("div");
    card.className = "product-card";
    card.draggable = true;
    card.dataset.productId = p.id;
    card.onclick = (e) => {
      if (e.target.closest(".product-card-pin-btn") || card.dataset.dragMoved === "1") {
        card.dataset.dragMoved = "0";
        return;
      }
      onProductCardClicked(p);
    };

    card.addEventListener("dragstart", (event) => {
      draggedProductId = String(p.id);
      card.classList.add("product-dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", draggedProductId);
      }
    });
    card.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      card.classList.add("product-drag-over");
    });
    card.addEventListener("dragleave", () => card.classList.remove("product-drag-over"));
    card.addEventListener("drop", async (event) => {
      event.preventDefault();
      card.classList.remove("product-drag-over");
      const sourceId = event.dataTransfer?.getData("text/plain") || draggedProductId;
      if (sourceId && sourceId !== String(p.id)) {
        await reorderProductCards(sourceId, String(p.id), filtered);
        card.dataset.dragMoved = "1";
      }
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("product-dragging");
      document.querySelectorAll(".product-card").forEach((item) => item.classList.remove("product-drag-over"));
      draggedProductId = null;
    });

    const minPrice = (p.variants || []).reduce(
      (min, v) => (v.price < min ? v.price : min),
      p.variants && p.variants[0] ? p.variants[0].price : 0,
    );
    const iconUrl = getProductIcon(p);

    card.innerHTML = `
      <div class="product-card-top">
        <img src="${iconUrl}" class="product-card-icon" alt="${p.name}" onerror="this.src='/static/images/icons/premium-coffee.svg'">
        <div style="flex: 1; min-width: 0;">
          <div class="product-card-title">${p.name}</div>
          <div class="product-card-desc">${p.description || p.category}</div>
        </div>
        <button type="button" class="product-card-pin-btn" onclick="quickPinProduct(${p.id})" title="Qısayola əlavə et">⭐</button>
      </div>
      <div class="product-card-bottom">
        <span class="product-card-price">${minPrice.toFixed(2)} AZN</span>
        <span class="product-card-variants-count">${(p.variants || []).length} variant</span>
      </div>
    `;
    grid.appendChild(card);
  });
}

async function reorderProductCards(sourceId, targetId, visibleProducts) {
  const sourceIndex = visibleProducts.findIndex((product) => String(product.id) === String(sourceId));
  const targetIndex = visibleProducts.findIndex((product) => String(product.id) === String(targetId));
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return;
  const reordered = [...visibleProducts];
  const [item] = reordered.splice(sourceIndex, 1);
  reordered.splice(targetIndex, 0, item);
  const ids = reordered.map((product) => product.id);
  try {
    await api("/api/products/reorder", {
      method: "POST",
      body: JSON.stringify({ product_ids: ids }),
    });
    const orderMap = new Map(ids.map((id, index) => [id, index]));
    POS_STATE.products.sort(
      (a, b) =>
        (orderMap.get(a.id) ?? Number.MAX_SAFE_INTEGER) -
        (orderMap.get(b.id) ?? Number.MAX_SAFE_INTEGER),
    );
    renderProducts();
    showToast("Məhsul sırası yadda saxlanıldı.", "success");
  } catch (err) {
    renderProducts();
  }
}

function onProductCardClicked(product) {
  const variants = product.variants || [];
  if (variants.length === 0) {
    showToast("Bu məhsul üçün aktiv variant tapılmadı.", "warning");
    return;
  }

  // If only 1 variant, add directly for ultra-fast barista speed
  if (variants.length === 1) {
    addVariantToCart(variants[0], product);
    return;
  }

  // If multiple variants, open quick selection modal
  openVariantModal(product);
}

function openVariantModal(product) {
  document.getElementById("variant-modal-title").textContent = product.name;
  const list = document.getElementById("variant-modal-list");
  list.innerHTML = "";

  (product.variants || []).forEach((v) => {
    const btn = document.createElement("button");
    btn.className = "btn btn-outline";
    btn.style.justifyContent = "space-between";
    btn.innerHTML = `<span>${v.name}</span> <span style="color: var(--accent); font-weight: 700;">${v.price.toFixed(2)} AZN</span>`;
    btn.onclick = () => {
      addVariantToCart(v, product);
      closeVariantModal();
    };
    list.appendChild(btn);
  });

  document.getElementById("modal-variant-select").style.display = "flex";
}

function closeVariantModal() {
  document.getElementById("modal-variant-select").style.display = "none";
}

// --- Cart Operations (Rule F2) ---
function addVariantToCart(variant, product) {
  const existing = POS_STATE.cart.find(
    (item) => item.variant_id === variant.id,
  );
  if (existing) {
    existing.quantity++;
  } else {
    POS_STATE.cart.push({
      variant_id: variant.id,
      product_name: product.name,
      variant_name: variant.name,
      unit_price: variant.price,
      quantity: 1,
      notes: "",
    });
  }
  renderCart();
}

function incrementCartItem(index) {
  POS_STATE.cart[index].quantity++;
  renderCart();
}

function decrementCartItem(index) {
  POS_STATE.cart[index].quantity--;
  if (POS_STATE.cart[index].quantity <= 0) {
    POS_STATE.cart.splice(index, 1);
  }
  renderCart();
}

function clearCart() {
  POS_STATE.cart = [];
  POS_STATE.discountType = "none";
  POS_STATE.discountValue = 0.0;
  POS_STATE.paymentMethod = "cash";
  updateDiscountButtonsUI();
  updatePaymentButtonsUI();
  renderCart();
}

async function setCartDiscount(type, val = 0.0) {
  if (type === "complementary" || (type === "percent" && Number(val) >= 20) || (type === "fixed" && Number(val) >= 10)) {
    const confirmed = await requestActionConfirmation(
      IllyI18n.t("pos.discountPrompt") || "Bu böyük endirimi tətbiq etmək istədiyinizə əminsiniz?",
    );
    if (!confirmed) return;
  }
  POS_STATE.discountType = type;
  POS_STATE.discountValue = val;
  updateDiscountButtonsUI();
  renderCart();
}

function updateDiscountButtonsUI() {
  const buttons = {
    none: document.getElementById("disc-btn-none"),
    10: document.getElementById("disc-btn-10"),
    20: document.getElementById("disc-btn-20"),
    fixed: document.getElementById("disc-btn-fixed"),
    complementary: document.getElementById("disc-btn-comp"),
  };

  Object.values(buttons).forEach((b) => b && b.classList.remove("active"));

  if (POS_STATE.discountType === "none" && buttons.none)
    buttons.none.classList.add("active");
  if (
    POS_STATE.discountType === "percent" &&
    POS_STATE.discountValue === 10 &&
    buttons["10"]
  )
    buttons["10"].classList.add("active");
  if (
    POS_STATE.discountType === "percent" &&
    POS_STATE.discountValue === 20 &&
    buttons["20"]
  )
    buttons["20"].classList.add("active");
  if (POS_STATE.discountType === "fixed" && buttons.fixed)
    buttons.fixed.classList.add("active");
  if (POS_STATE.discountType === "complementary" && buttons.complementary)
    buttons.complementary.classList.add("active");
}

function setCartPayment(method) {
  POS_STATE.paymentMethod = method;
  updatePaymentButtonsUI();
}

function setCartFulfillment(type) {
  const allowed = ["in_store", "bolt", "wolt", "other_delivery"];
  POS_STATE.fulfillmentType = allowed.includes(type) ? type : "in_store";
  document.querySelectorAll("[data-fulfillment-type]").forEach((button) => {
    button.classList.toggle("active", button.dataset.fulfillmentType === POS_STATE.fulfillmentType);
  });
}

function updatePaymentButtonsUI() {
  ["cash", "card", "mixed", "other"].forEach((m) => {
    const el = document.getElementById(`pay-btn-${m}`);
    if (el) {
      if (POS_STATE.paymentMethod === m) el.classList.add("active");
      else el.classList.remove("active");
    }
  });
}

function removeCartItemWithAnimation(idx) {
  const list = document.getElementById("cart-items-list");
  if (!list) return;
  const itemEl = list.children[idx];
  if (itemEl) {
    itemEl.classList.add("removing");
    setTimeout(() => {
      POS_STATE.cart.splice(idx, 1);
      renderCart();
    }, 220);
  } else {
    POS_STATE.cart.splice(idx, 1);
    renderCart();
  }
}

function renderCart() {
  const list = document.getElementById("cart-items-list");
  const countEl = document.getElementById("cart-item-count");
  if (!list) return;

  const totalItemsCount = POS_STATE.cart.reduce(
    (sum, i) => sum + i.quantity,
    0,
  );
  if (countEl) countEl.textContent = totalItemsCount;

  if (POS_STATE.cart.length === 0) {
    list.innerHTML = `
      <div class="cart-empty-state">
        <img class="cart-empty-logo" src="/static/images/icons/illy-wide-cup-10x.svg" alt="Coffee">
        <div style="font-weight: 700;">${IllyI18n.t("pos.cart.empty")}</div>
          <div style="font-size: 13px; color: var(--text-muted);">${IllyI18n.t("pos.cart.emptyHint")}</div>
      </div>
    `;
    document.getElementById("cart-subtotal-text").textContent = "0.00 AZN";
    document.getElementById("cart-total-text").textContent = "0.00 AZN";
    document.getElementById("cart-discount-row").style.display = "none";
    return;
  }

  list.innerHTML = "";
  let subtotal = 0.0;

  POS_STATE.cart.forEach((item, idx) => {
    const lineTotal = item.unit_price * item.quantity;
    subtotal += lineTotal;

    const row = document.createElement("div");
    row.className = "cart-item";

    // Touch Swipe to delete support
    let touchStartX = 0;
    row.addEventListener(
      "touchstart",
      (e) => {
        touchStartX = e.touches[0].clientX;
      },
      { passive: true },
    );

    row.addEventListener(
      "touchmove",
      (e) => {
        const deltaX = e.touches[0].clientX - touchStartX;
        if (deltaX < -25) {
          row.style.transform = `translateX(${Math.max(deltaX, -100)}px)`;
        }
      },
      { passive: true },
    );

    row.addEventListener("touchend", (e) => {
      const deltaX = e.changedTouches[0].clientX - touchStartX;
      if (deltaX < -70) {
        removeCartItemWithAnimation(idx);
      } else {
        row.style.transform = "";
      }
    });

    row.innerHTML = `
      <div class="cart-item-info">
        <div class="cart-item-title">${item.product_name}</div>
        <div class="cart-item-subtitle">${item.variant_name} (${item.unit_price.toFixed(2)} ₼)</div>
      </div>
      <div class="cart-item-qty-box">
        <button type="button" class="cart-qty-btn" onclick="decrementCartItem(${idx})">-</button>
        <span class="cart-qty-val">${item.quantity}</span>
        <button type="button" class="cart-qty-btn" onclick="incrementCartItem(${idx})">+</button>
      </div>
      <div class="cart-item-price">${lineTotal.toFixed(2)} ₼</div>
      <button type="button" class="cart-item-del-btn" onclick="removeCartItemWithAnimation(${idx})" title="Səbətdən sil">🗑️</button>
    `;
    list.appendChild(row);
  });

  // Calculate Discounts
  let discountAmount = 0.0;
  if (POS_STATE.discountType === "complementary") {
    discountAmount = subtotal;
  } else if (POS_STATE.discountType === "percent") {
    discountAmount = subtotal * (POS_STATE.discountValue / 100.0);
  } else if (POS_STATE.discountType === "fixed") {
    discountAmount = Math.min(subtotal, POS_STATE.discountValue);
  }

  const finalTotal = Math.max(0.0, subtotal - discountAmount);

  document.getElementById("cart-subtotal-text").textContent =
    `${subtotal.toFixed(2)} AZN`;

  const discRow = document.getElementById("cart-discount-row");
  if (discountAmount > 0) {
    discRow.style.display = "flex";
    document.getElementById("cart-discount-text").textContent =
      `-${discountAmount.toFixed(2)} AZN`;
  } else {
    discRow.style.display = "none";
  }

  document.getElementById("cart-total-text").textContent =
    `${finalTotal.toFixed(2)} AZN`;
}

// Confirm Order and Deduct Stock via Recipes (Rule E, F)
async function confirmOrder() {
  if (POS_STATE.cart.length === 0) {
    showToast("Səbət boşdur!", "warning");
    return;
  }
  const confirmed = await requestActionConfirmation(
    IllyI18n.t("pos.confirmOrderPrompt") || "Bu sifarişi təsdiqləmək istədiyinizə əminsiniz?",
  );
  if (!confirmed) return;

  const btn = document.getElementById("btn-confirm-order");
  btn.disabled = true;
  btn.textContent = IllyI18n.t("pos.confirming");

  try {
    const payload = {
      items: POS_STATE.cart,
      discount_type: POS_STATE.discountType,
      discount_value: POS_STATE.discountValue,
      discount_reason:
        POS_STATE.discountType !== "none"
          ? "Kassada tətbiq olunan endirim"
          : "",
      is_complementary: POS_STATE.discountType === "complementary",
      payment_method: POS_STATE.paymentMethod,
      fulfillment_type: POS_STATE.fulfillmentType,
      shift_id: POS_STATE.activeShift ? POS_STATE.activeShift.id : null,
      language: IllyI18n.language,
    };

    const res = await api("/api/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    showToast(
      IllyI18n.t("pos.orderCompleted", { number: res.order_number }),
    );
    clearCart();

    // Show internal ticket (Rule F6)
    if (res.ticket && res.ticket.text_ticket) {
      openTicketModal(res.ticket.text_ticket);
    }
  } catch (err) {
    // Handled by api helper
  } finally {
    btn.disabled = false;
    btn.textContent = IllyI18n.t("pos.confirmOrder");
  }
}

// Internal Operational Ticket (Rule F6)
function openTicketModal(ticketText) {
  document.getElementById("ticket-text-preview").textContent = ticketText;
  document.getElementById("modal-ticket-view").style.display = "flex";
}

function closeTicketModal() {
  document.getElementById("modal-ticket-view").style.display = "none";
}

function printTicket() {
  window.print();
}

function openCashMovementModal() {
  updateCashMovementDebtOptions();
  document.getElementById("modal-cash-movement").style.display = "flex";
}
function updateCashMovementDebtOptions() {
  const type = document.getElementById("cash-movement-type");
  const debt = document.getElementById("cash-movement-debt");
  const debtPayment = document.getElementById("cash-movement-debt-payment");
  const debtLabel = document.getElementById("cash-debt-label");
  const debtPaymentLabel = document.getElementById("cash-debt-payment-label");
  if (!type || !debt || !debtPayment) return;
  const isIn = type.value === "in";
  const language = window.IllyI18n?.language || "az";
  const debtText = { az: "Borc alındı", tr: "Borç alındı", en: "Debt received", ru: "Получен долг" }[language];
  const paidText = { az: "Borc ödənildi", tr: "Borç ödendi", en: "Debt repaid", ru: "Долг погашен" }[language];
  if (debtLabel) debtLabel.lastElementChild.textContent = debtText;
  if (debtPaymentLabel) debtPaymentLabel.lastElementChild.textContent = paidText;
  debt.disabled = isIn;
  debt.checked = !isIn && debt.checked;
  debtPayment.disabled = !isIn;
  debtPayment.checked = isIn && debtPayment.checked;
  if (debtLabel) debtLabel.style.opacity = isIn ? "0.45" : "1";
  if (debtPaymentLabel) debtPaymentLabel.style.opacity = isIn ? "1" : "0.45";
}
function closeCashMovementModal() {
  document.getElementById("modal-cash-movement").style.display = "none";
}
document.addEventListener("change", (event) => {
  if (event.target?.id === "cash-movement-type") updateCashMovementDebtOptions();
});
async function submitCashMovement(event) {
  event.preventDefault();
  const payload = {
    type: document.getElementById("cash-movement-type").value,
    amount: Number(document.getElementById("cash-movement-amount").value),
    reason: document.getElementById("cash-movement-reason").value.trim(),
    note: document.getElementById("cash-movement-note").value.trim(),
    is_debt: document.getElementById("cash-movement-debt").checked,
    is_debt_payment: document.getElementById("cash-movement-debt-payment").checked,
    shift_id: POS_STATE.activeShift?.id || null,
  };
  if (!(await requestActionConfirmation(IllyI18n.t("pos.cashMovementPrompt") || "Kassa hərəkətini təsdiqləyirsiniz?"))) return;
  try {
    await api("/api/cash-movements", { method: "POST", body: JSON.stringify(payload) });
    showToast(IllyI18n.t("pos.cashMovementSaved") || "Kassa hərəkəti saxlanıldı.", "success");
    event.target.reset();
    closeCashMovementModal();
  } catch (err) {}
}

// Recent Orders & Cancel / Void Flow (Rule F3)
async function openRecentOrdersModal() {
  try {
    const orders = await api("/api/orders/recent?limit=25");
    if (!orders || !orders.length) {
      showToast("Son sifariş tapılmadı.", "info");
      return;
    }

    let ordersHtml = `<div style="max-height: 380px; overflow-y: auto; text-align: left;">`;
    orders.forEach((o) => {
      const isCancelled = o.status === "cancelled";
      const statusBadge = isCancelled
        ? `<span class="badge badge-admin">Ləğv edilib</span>`
        : `<span class="badge badge-success">Tamamlanıb</span>`;

      const cancelBtn = !isCancelled
        ? `<button class="btn btn-outline btn-sm" style="color: var(--danger);" onclick="promptCancelOrder(${o.id})">Ləğv Et</button>`
        : `<span style="font-size: 11px; color: var(--text-muted);">${o.cancel_reason || ""}</span>`;

      ordersHtml += `
        <div style="border-bottom: 1px solid var(--border); padding: 10px 0; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-weight: 700;">#${o.order_number} - ${o.final_amount.toFixed(2)} AZN (${o.payment_method})</div>
            <div style="font-size: 12px; color: var(--text-muted);">${o.created_at} | ${o.item_count} məhsul</div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            ${statusBadge}
            ${cancelBtn}
          </div>
        </div>
      `;
    });
    ordersHtml += `</div>`;

    document.getElementById("variant-modal-title").textContent =
      "Son Sifarişlər və Ləğvetmə";
    const list = document.getElementById("variant-modal-list");
    list.innerHTML = ordersHtml;
    document.getElementById("modal-variant-select").style.display = "flex";
  } catch (err) {}
}

function promptCancelOrder(orderId) {
  closeVariantModal();
  document.getElementById("cancel-order-id").value = orderId;
  document.getElementById("cancel-order-reason").value = "";
  document.getElementById("modal-cancel-order").style.display = "flex";
}

function closeCancelModal() {
  document.getElementById("modal-cancel-order").style.display = "none";
}

async function submitOrderCancel(e) {
  e.preventDefault();
  const orderId = document.getElementById("cancel-order-id").value;
  const reason = document.getElementById("cancel-order-reason").value;
  const confirmed = await requestActionConfirmation(
    IllyI18n.t("pos.cancelOrderPrompt") || "Bu sifarişi ləğv etmək istədiyinizə əminsiniz?",
  );
  if (!confirmed) return;

  try {
    const res = await api(`/api/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    showToast(
      res.message || "Sifariş ləğv edildi və anbar qalığı bərpa olundu.",
    );
    closeCancelModal();
  } catch (err) {}
}

// Save Drag and Drop Order
async function saveReorderedShortcuts() {
  const ids = POS_STATE.shortcuts.map((s) => s.shortcut_id);
  try {
    await api("/api/shortcuts/reorder", {
      method: "POST",
      body: JSON.stringify({ shortcut_ids: ids }),
    });
  } catch (err) {
    console.error("Reorder shortcuts error:", err);
  }
}

// Quick pin from catalog
function quickPinProduct(productId) {
  const prod = POS_STATE.products.find((p) => p.id === productId);
  if (!prod) return;
  openShortcutsConfigModal(prod);
}

// Shortcuts Manager Modal
function openShortcutsConfigModal(preselectProd = null) {
  const select = document.getElementById("sc-new-variant-select");
  if (!select) return;
  select.innerHTML = "";

  POS_STATE.products.forEach((p) => {
    (p.variants || []).forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.dataset.prod = p.name;
      opt.dataset.var = v.name;
      opt.dataset.icon = getProductIcon(p);
      opt.textContent = `${p.name} - ${v.name} (${v.price.toFixed(2)} AZN)`;
      if (
        preselectProd &&
        preselectProd.id === p.id &&
        select.children.length === 0
      ) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
  });

  onShortcutVariantSelected();
  renderShortcutsManagerList();
  document.getElementById("modal-shortcuts-manager").style.display = "flex";
}

function closeShortcutsManagerModal() {
  document.getElementById("modal-shortcuts-manager").style.display = "none";
}

function onShortcutVariantSelected() {
  const select = document.getElementById("sc-new-variant-select");
  const selectedOpt = select.options[select.selectedIndex];
  if (!selectedOpt) return;

  const prodName = selectedOpt.dataset.prod;
  const varName = selectedOpt.dataset.var;
  const icon = selectedOpt.dataset.icon;

  const labelInput = document.getElementById("sc-new-label-input");
  if (labelInput) {
    labelInput.value = `${prodName} (${varName})`;
  }

  const iconSelect = document.getElementById("sc-new-icon-select");
  if (iconSelect && icon) {
    iconSelect.value = icon;
    previewShortcutIcon(icon);
  }
}

function previewShortcutIcon(url) {
  const preview = document.getElementById("sc-new-icon-preview");
  if (preview) preview.src = url;
}

async function uploadShortcutIcon(input) {
  if (!input.files || !input.files[0]) return;
  const formData = new FormData();
  formData.append("file", input.files[0]);

  try {
    showToast("Şəkil yüklənir...", "info");
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${STATE.token}`,
      },
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Yükləmə xətası");

    const select = document.getElementById("sc-new-icon-select");
    const opt = document.createElement("option");
    opt.value = data.url;
    opt.textContent = "Fərdi Şəkil";
    opt.selected = true;
    select.appendChild(opt);
    previewShortcutIcon(data.url);
    showToast("Şəkil uğurla yükləndi!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function submitAddNewShortcut() {
  const variantId = parseInt(
    document.getElementById("sc-new-variant-select").value,
  );
  const customLabel = document
    .getElementById("sc-new-label-input")
    .value.trim();
  const iconUrl = document.getElementById("sc-new-icon-select").value;

  if (!variantId) {
    showToast("Variant seçilməyib.", "warning");
    return;
  }

  try {
    const res = await api("/api/shortcuts/add", {
      method: "POST",
      body: JSON.stringify({
        variant_id: variantId,
        custom_label: customLabel,
        icon_url: iconUrl,
      }),
    });
    showToast(res.message || "Qısayol əlavə edildi!", "success");
    const sc = await api("/api/shortcuts");
    POS_STATE.shortcuts = sc || [];
    renderShortcuts();
    renderShortcutsManagerList();
  } catch (err) {}
}

function renderShortcutsManagerList() {
  const container = document.getElementById("sc-current-list");
  if (!container) return;

  if (!POS_STATE.shortcuts.length) {
    container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 12px; font-size: 13px;">Hələ ki qısayol əlavə edilməyib.</div>`;
    return;
  }

  container.innerHTML = POS_STATE.shortcuts
    .map((sc, idx) => {
      const iconUrl = sc.icon_url || getProductIcon({
        name: sc.product_name,
        category: sc.category,
        image_url: sc.image_url,
      });
      const label =
        sc.custom_label || `${sc.product_name} (${sc.variant_name})`;
      return `
      <div class="shortcut-manager-item">
        <img src="${iconUrl}" class="shortcut-manager-icon" alt="${label}" onerror="this.src='/static/images/icons/premium-coffee.svg'">
        <div style="flex: 1; min-width: 0;">
          <div class="shortcut-manager-name">${label}</div>
          <div class="shortcut-manager-price">${sc.price.toFixed(2)} AZN</div>
        </div>
        <div class="shortcut-manager-actions">
          <button type="button" class="btn btn-outline btn-sm" onclick="moveShortcutIndex(${idx}, -1)" ${idx === 0 ? "disabled" : ""}>▲</button>
          <button type="button" class="btn btn-outline btn-sm" onclick="moveShortcutIndex(${idx}, 1)" ${idx === POS_STATE.shortcuts.length - 1 ? "disabled" : ""}>▼</button>
          <button type="button" class="btn btn-outline btn-sm" onclick="openEditSingleShortcutModal(${sc.shortcut_id})">✏️</button>
          <button type="button" class="btn btn-danger btn-sm" onclick="deleteShortcutFromManager(${sc.shortcut_id})">🗑️</button>
        </div>
      </div>
    `;
    })
    .join("");
}

function moveShortcutIndex(idx, direction) {
  const targetIdx = idx + direction;
  if (targetIdx < 0 || targetIdx >= POS_STATE.shortcuts.length) return;
  const item = POS_STATE.shortcuts.splice(idx, 1)[0];
  POS_STATE.shortcuts.splice(targetIdx, 0, item);
  saveReorderedShortcuts();
  renderShortcuts();
  renderShortcutsManagerList();
}

async function deleteShortcutFromManager(shortcutId) {
  try {
    const res = await api(`/api/shortcuts/${shortcutId}`, {
      method: "DELETE",
    });
    showToast(res.message || "Qısayol silindi.", "success");
    const sc = await api("/api/shortcuts");
    POS_STATE.shortcuts = sc || [];
    renderShortcuts();
    renderShortcutsManagerList();
  } catch (err) {}
}

// Edit Single Shortcut Modal
function openEditSingleShortcutModal(shortcutId) {
  const sc = POS_STATE.shortcuts.find((s) => s.shortcut_id === shortcutId);
  if (!sc) return;

  document.getElementById("edit-sc-id").value = sc.shortcut_id;
  document.getElementById("edit-sc-prod-title").textContent =
    `${sc.product_name} - ${sc.variant_name} (${sc.price.toFixed(2)} AZN)`;
  document.getElementById("edit-sc-label").value =
    sc.custom_label || `${sc.product_name} (${sc.variant_name})`;

  const iconUrl =
    sc.icon_url || sc.image_url || "/static/images/icons/premium-coffee.svg";
  const iconSelect = document.getElementById("edit-sc-icon-select");
  if (iconSelect) {
    iconSelect.value = iconUrl;
    previewEditShortcutIcon(iconUrl);
  }

  document.getElementById("modal-edit-single-shortcut").style.display = "flex";
}

function closeEditSingleShortcutModal() {
  document.getElementById("modal-edit-single-shortcut").style.display = "none";
}

function previewEditShortcutIcon(url) {
  const preview = document.getElementById("edit-sc-icon-preview");
  if (preview) preview.src = url;
}

async function uploadEditShortcutIcon(input) {
  if (!input.files || !input.files[0]) return;
  const formData = new FormData();
  formData.append("file", input.files[0]);

  try {
    showToast("Şəkil yüklənir...", "info");
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${STATE.token}`,
      },
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Yükləmə xətası");

    const select = document.getElementById("edit-sc-icon-select");
    const opt = document.createElement("option");
    opt.value = data.url;
    opt.textContent = "Fərdi Şəkil";
    opt.selected = true;
    select.appendChild(opt);
    previewEditShortcutIcon(data.url);
    showToast("Şəkil uğurla yükləndi!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function saveEditSingleShortcut() {
  const id = document.getElementById("edit-sc-id").value;
  const custom_label = document.getElementById("edit-sc-label").value.trim();
  const icon_url = document.getElementById("edit-sc-icon-select").value;

  try {
    const res = await api(`/api/shortcuts/${id}`, {
      method: "PUT",
      body: JSON.stringify({ custom_label, icon_url }),
    });
    showToast(res.message || "Qısayol yeniləndi.", "success");
    closeEditSingleShortcutModal();
    const sc = await api("/api/shortcuts");
    POS_STATE.shortcuts = sc || [];
    renderShortcuts();
    if (
      document.getElementById("modal-shortcuts-manager").style.display ===
      "flex"
    ) {
      renderShortcutsManagerList();
    }
  } catch (err) {}
}

async function deleteSingleShortcut() {
  const id = document.getElementById("edit-sc-id").value;
  try {
    const res = await api(`/api/shortcuts/${id}`, {
      method: "DELETE",
    });
    showToast(res.message || "Qısayol silindi.", "success");
    closeEditSingleShortcutModal();
    const sc = await api("/api/shortcuts");
    POS_STATE.shortcuts = sc || [];
    renderShortcuts();
    if (
      document.getElementById("modal-shortcuts-manager").style.display ===
      "flex"
    ) {
      renderShortcutsManagerList();
    }
  } catch (err) {}
}
