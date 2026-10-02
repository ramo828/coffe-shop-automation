(function () {
  "use strict";
  const supported = ["az", "tr", "en", "ru"];
  const fallback = "az";
  const dictionaries = {};
  let active = localStorage.getItem("illy_language") || fallback;

  function getValue(source, key) {
    return key.split(".").reduce((value, part) => value && value[part], source);
  }

  async function load(lang) {
    if (!supported.includes(lang)) lang = fallback;
    if (!dictionaries[lang]) {
      const response = await fetch(`/static/locales/${lang}.json?v=20260915-info-localization-1`, { cache: "no-cache" });
      if (!response.ok) throw new Error(`Locale ${lang} could not be loaded`);
      dictionaries[lang] = await response.json();
    }
    active = lang;
    localStorage.setItem("illy_language", lang);
    apply();
    return lang;
  }

  function t(key, vars = {}) {
    let value = getValue(dictionaries[active], key) ?? getValue(dictionaries[fallback], key) ?? key;
    if (typeof value !== "string") return key;
    return Object.entries(vars).reduce((result, [name, replacement]) =>
      result.replaceAll(`{{${name}}}`, String(replacement)), value);
  }

  function apply() {
    document.documentElement.lang = active;
    document.querySelectorAll("[data-i18n]").forEach((node) => {
      const value = t(node.dataset.i18n);
      const attr = node.dataset.i18nAttr;
      if (attr) node.setAttribute(attr, value);
      else node.textContent = value;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => node.placeholder = t(node.dataset.i18nPlaceholder));
    document.querySelectorAll("[data-i18n-title]").forEach((node) => node.title = t(node.dataset.i18nTitle));
    document.querySelectorAll("[data-i18n-aria-label]").forEach((node) => node.setAttribute("aria-label", t(node.dataset.i18nAriaLabel)));
    const selector = document.getElementById("language-switcher");
    if (selector) selector.value = active;
    document.dispatchEvent(new CustomEvent("illy:language-changed", { detail: { language: active } }));
  }

  window.IllyI18n = {
    get language() { return active; },
    t,
    apply,
    async setLanguage(lang) { return load(lang); },
    async init(lang) {
      try { await load(lang || active); }
      catch (error) { console.error("Language could not be loaded:", error); await load(fallback); }
    }
  };
  document.addEventListener("DOMContentLoaded", () => IllyI18n.init());
})();
