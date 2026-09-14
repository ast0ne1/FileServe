function syncTopbarHeight() {
  const topbar = document.querySelector(".topbar");
  if (!topbar) return;
  const height = Math.ceil(topbar.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--topbar-height", `${height}px`);
}
syncTopbarHeight();
window.addEventListener("resize", syncTopbarHeight);
window.addEventListener("orientationchange", syncTopbarHeight);
window.addEventListener("pageshow", syncTopbarHeight);
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", syncTopbarHeight);
}
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(syncTopbarHeight);
}
if (typeof ResizeObserver === "function") {
  const topbar = document.querySelector(".topbar");
  if (topbar) new ResizeObserver(syncTopbarHeight).observe(topbar);
}

const THEME_KEY = "fileserve-theme";
const PALETTE_KEY = "fileserve-palette";
const PALETTES = ["default", "ocean", "forest", "slate"];
const THEME_COLORS = {
  default: { light: "#f3eee4", dark: "#12100d" },
  ocean: { light: "#e7eef5", dark: "#0c141c" },
  forest: { light: "#eef1e6", dark: "#10140d" },
  slate: { light: "#ececee", dark: "#121314" },
};

function resolvedTheme(pref) {
  if (pref === "light" || pref === "dark") return pref;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function savedPalette() {
  const value = localStorage.getItem(PALETTE_KEY) || "default";
  return PALETTES.includes(value) ? value : "default";
}

function applyTheme(pref, palette) {
  const theme = resolvedTheme(pref);
  const chosen = palette || savedPalette();
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themePref = pref;
  document.documentElement.dataset.palette = chosen;
  document.documentElement.style.colorScheme = theme;
  const meta = document.querySelector("[data-theme-color]");
  if (meta) meta.setAttribute("content", THEME_COLORS[chosen][theme]);
  document.querySelectorAll("[data-theme-set]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.themeSet === pref);
  });
  document.querySelectorAll("[data-palette-set]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.paletteSet === chosen);
  });
}

const savedTheme = localStorage.getItem(THEME_KEY) || "system";
applyTheme(savedTheme);
document.querySelectorAll("[data-theme-set]").forEach((button) => {
  button.addEventListener("click", () => {
    localStorage.setItem(THEME_KEY, button.dataset.themeSet);
    applyTheme(button.dataset.themeSet);
  });
});
document.querySelectorAll("[data-palette-set]").forEach((button) => {
  button.addEventListener("click", () => {
    localStorage.setItem(PALETTE_KEY, button.dataset.paletteSet);
    applyTheme(localStorage.getItem(THEME_KEY) || "system", button.dataset.paletteSet);
  });
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if ((localStorage.getItem(THEME_KEY) || "system") === "system") applyTheme("system");
});

const toastEl = document.querySelector("[data-toast]");
const TOAST_KEY = "fileserve-toast";
const TOAST_MS = 4500;

function toast(message, kind) {
  if (!toastEl || !message) return;
  toastEl.textContent = message;
  toastEl.classList.remove("is-ok", "is-error", "is-on");
  if (kind === "error") toastEl.classList.add("is-error");
  else toastEl.classList.add("is-ok");
  toastEl.hidden = false;
  window.requestAnimationFrame(() => {
    toastEl.classList.add("is-on");
  });
  window.clearTimeout(toastEl._timer);
  toastEl._timer = window.setTimeout(() => {
    toastEl.classList.remove("is-on");
    toastEl.hidden = true;
  }, TOAST_MS);
}

function toastAfterReload(message, kind) {
  try {
    sessionStorage.setItem(TOAST_KEY, JSON.stringify({ message, kind: kind || "ok" }));
  } catch {
    toast(message, kind);
  }
}

try {
  const pending = sessionStorage.getItem(TOAST_KEY);
  if (pending) {
    sessionStorage.removeItem(TOAST_KEY);
    const data = JSON.parse(pending);
    toast(data.message, data.kind);
  }
} catch {
  /* ignore a bad stored toast */
}

async function send(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "X-Requested-With": "fetch",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (response.status === 401 && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login";
    throw new Error("Signed out");
  }
  const data = await response.json().catch(() => ({ ok: response.ok, message: response.statusText }));
  if (!response.ok) {
    throw new Error(data.message || data.detail || "Request failed");
  }
  return data;
}

function askConfirm({ title, body, okLabel }) {
  const sheet = document.querySelector("[data-confirm-sheet]");
  if (!sheet) return Promise.resolve(window.confirm(title));
  return new Promise((resolve) => {
    const titleEl = sheet.querySelector("[data-confirm-title]");
    const bodyEl = sheet.querySelector("[data-confirm-body]");
    const okBtn = sheet.querySelector("[data-confirm-ok]");
    const cancelBtn = sheet.querySelector("[data-confirm-cancel]");
    if (titleEl) titleEl.textContent = title;
    if (bodyEl) {
      bodyEl.hidden = !body;
      bodyEl.textContent = body || "";
    }
    if (okBtn) okBtn.textContent = okLabel || "Remove";
    const finish = (value) => {
      sheet.hidden = true;
      sheet.classList.remove("is-open");
      sheet.removeEventListener("click", onBackdrop);
      okBtn?.removeEventListener("click", onOk);
      cancelBtn?.removeEventListener("click", onCancel);
      document.removeEventListener("keydown", onKey);
      resolve(value);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    const onBackdrop = (event) => {
      if (event.target === sheet) finish(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") finish(false);
    };
    sheet.addEventListener("click", onBackdrop);
    okBtn?.addEventListener("click", onOk);
    cancelBtn?.addEventListener("click", onCancel);
    document.addEventListener("keydown", onKey);
    sheet.hidden = false;
    sheet.classList.add("is-open");
    okBtn?.focus();
  });
}

function showFormError(form, message) {
  const errorEl = form.querySelector("[data-form-error]");
  if (!errorEl) return;
  errorEl.textContent = message || "";
  errorEl.hidden = !message;
}

document.querySelectorAll("form").forEach((form) => {
  if (form.dataset.bound || form.dataset.native != null) return;
  form.dataset.bound = "1";
  form.addEventListener("submit", async (event) => {
    if (form.method.toLowerCase() !== "post") return;
    event.preventDefault();
    if (form.dataset.confirm) {
      const ok = await askConfirm({
        title: form.dataset.confirm,
        body: form.dataset.confirmDetail || "",
        okLabel: form.dataset.confirmOk || "Remove",
      });
      if (!ok) return;
    }
    const body = new FormData(form);
    const button = form.querySelector("[type=submit]");
    const originalLabel = button?.textContent;
    showFormError(form, "");
    if (button) {
      button.disabled = true;
      if (form.dataset.busyLabel) button.textContent = form.dataset.busyLabel;
    }
    try {
      const data = await send(form.action, { method: "POST", body });
      if (data.reauth) {
        window.location.href = "/login";
        return;
      }
      if (data.reveal) {
        try {
          sessionStorage.setItem("fileserve-reveal", JSON.stringify(data.reveal));
        } catch {
          /* ignore */
        }
      }
      toastAfterReload(data.message || "Saved", "ok");
      window.location.reload();
    } catch (error) {
      showFormError(form, error.message);
      toast(error.message, "error");
    } finally {
      if (button) {
        button.disabled = false;
        if (originalLabel) button.textContent = originalLabel;
      }
    }
  });
});

const settingsRoot = document.querySelector("[data-settings-tabs]");
if (settingsRoot) {
  const SETTINGS_SAVE_TABS = new Set(["device", "update"]);
  const settingsChips = settingsRoot.querySelectorAll("[data-settings-tab]");
  const settingsForm = settingsRoot.querySelector("[data-settings]");
  const settingsTabField = settingsRoot.querySelector("[data-settings-tab-field]");
  const settingsLede = document.querySelector("[data-settings-lede]");

  function showSettingsTab(tab) {
    const next = [...settingsChips].some((chip) => chip.dataset.settingsTab === tab) ? tab : "device";
    settingsChips.forEach((chip) => {
      const on = chip.dataset.settingsTab === next;
      chip.classList.toggle("is-active", on);
      chip.setAttribute("aria-selected", on ? "true" : "false");
    });
    settingsRoot.querySelectorAll("[data-settings-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.settingsPanel !== next;
    });
    if (settingsForm) settingsForm.hidden = !SETTINGS_SAVE_TABS.has(next);
    if (settingsTabField) settingsTabField.value = next;
    const activeChip = [...settingsChips].find((chip) => chip.dataset.settingsTab === next);
    if (settingsLede && activeChip?.dataset.settingsLede) {
      settingsLede.textContent = activeChip.dataset.settingsLede;
    }
    const url = new URL(window.location.href);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  }

  settingsChips.forEach((chip) => {
    chip.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      showSettingsTab(chip.dataset.settingsTab);
    });
  });
}

document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const input = button.closest(".password-field")?.querySelector("input");
  if (!input) return;
  const showIcon = button.querySelector("[data-icon-show]");
  const hideIcon = button.querySelector("[data-icon-hide]");
  button.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.setAttribute("aria-label", show ? "Hide password" : "Show password");
    button.title = show ? "Hide password" : "Show password";
    if (showIcon) showIcon.hidden = show;
    if (hideIcon) hideIcon.hidden = !show;
  });
});

function slugify(value) {
  return (value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[/]+/g, " ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function syncExpiryFields(root) {
  const mode = root.querySelector("[data-expiry-mode]");
  const custom = root.querySelector("[data-expiry-custom]");
  const date = root.querySelector("[data-expiry-date]");
  const on = mode?.value === "custom";
  if (custom) custom.hidden = !on;
  if (date) date.required = on;
}

function syncProtectFields(root) {
  const toggle = root.querySelector("[data-protect-toggle]");
  const fields = root.querySelector("[data-protect-fields]");
  const on = Boolean(toggle?.checked);
  if (fields) fields.hidden = !on;
  const user = root.querySelector("[name=page_username]");
  const pass = root.querySelector("[name=page_password]");
  if (user) user.required = on;
  if (pass) {
    const keep = on && fields?.dataset.hasPassword === "1";
    pass.required = on && !keep;
  }
}

function bindPageSetup(root) {
  if (!root || root.dataset.setupBound) return;
  root.dataset.setupBound = "1";
  const label = root.querySelector("[data-label-field]");
  const slug = root.querySelector("[data-slug-field]");
  const toggle = root.querySelector("[data-protect-toggle]");
  const expiry = root.querySelector("[data-expiry-mode]");
  if (label && slug && slug.dataset.slugLocked == null) {
    slug.addEventListener("input", () => {
      slug.dataset.slugDirty = slug.value.trim() ? "1" : "";
    });
    label.addEventListener("input", () => {
      if (slug.dataset.slugDirty) return;
      slug.value = slugify(label.value);
    });
    if (!slug.value) slug.value = slugify(label.value);
  }
  toggle?.addEventListener("change", () => syncProtectFields(root));
  expiry?.addEventListener("change", () => syncExpiryFields(root));
  syncProtectFields(root);
  syncExpiryFields(root);
}

document.querySelectorAll("[data-page-setup]").forEach(bindPageSetup);

const editSheet = document.querySelector("[data-edit-sheet]");
const editForm = editSheet?.querySelector("[data-edit-form]");

function closeEditSheet() {
  if (!editSheet) return;
  editSheet.hidden = true;
  editSheet.classList.remove("is-open");
}

function openEditSheet(button) {
  if (!editSheet || !editForm) return;
  const protectedOn = button.dataset.pageProtected === "1";
  editForm.action = `/admin/edit/${button.dataset.pageId}`;
  const titleEl = editSheet.querySelector("[data-edit-title]");
  if (titleEl) titleEl.textContent = `Edit ${button.dataset.pageLabel || "page"}`;
  const label = editForm.querySelector("[data-label-field]");
  const slug = editForm.querySelector("[data-slug-field]");
  const description = editForm.querySelector("[data-description-field]");
  const user = editForm.querySelector("[name=page_username]");
  const pass = editForm.querySelector("[name=page_password]");
  const toggle = editForm.querySelector("[data-protect-toggle]");
  const fields = editForm.querySelector("[data-protect-fields]");
  const expiry = editForm.querySelector("[data-expiry-mode]");
  const expiryDate = editForm.querySelector("[data-expiry-date]");
  const file = editForm.querySelector("[data-edit-file]");
  if (label) label.value = button.dataset.pageLabel || "";
  if (slug) slug.value = button.dataset.pageSlug || "";
  if (description) description.value = button.dataset.pageDescription || "";
  if (user) user.value = button.dataset.pageUsername || "";
  if (pass) {
    pass.value = "";
    pass.type = "password";
  }
  if (toggle) toggle.checked = protectedOn;
  if (fields) fields.dataset.hasPassword = protectedOn ? "1" : "";
  if (expiry) expiry.value = button.dataset.pageExpiry || "none";
  if (expiryDate) expiryDate.value = button.dataset.pageExpiryDate || "";
  if (file) {
    file.value = "";
    file.dispatchEvent(new Event("change"));
  }
  showFormError(editForm, "");
  syncProtectFields(editForm);
  syncExpiryFields(editForm);
  editSheet.hidden = false;
  editSheet.classList.add("is-open");
  label?.focus();
}

document.querySelectorAll("[data-edit-page]").forEach((button) => {
  button.addEventListener("click", () => openEditSheet(button));
});
editSheet?.querySelector("[data-close-edit]")?.addEventListener("click", closeEditSheet);
editSheet?.addEventListener("click", (event) => {
  if (event.target === editSheet) closeEditSheet();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && editSheet && !editSheet.hidden) closeEditSheet();
});

document.querySelectorAll("[data-file-picker]").forEach((input) => {
  const picker = input.closest(".file-picker");
  const nameEl = picker?.querySelector("[data-file-name]");
  const empty = nameEl?.dataset.empty || "Tap to choose a file";
  const sync = () => {
    const file = input.files && input.files[0];
    if (nameEl) nameEl.textContent = file ? file.name : empty;
    picker?.classList.toggle("has-file", Boolean(file));
  };
  input.addEventListener("change", sync);
  sync();
});

async function copyText(value) {
  const text = value || "";
  if (!text) return;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      toast("Copied", "ok");
      return;
    }
  } catch {
    /* fall through to a wider fallback */
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.left = "-9999px";
  document.body.appendChild(field);
  field.select();
  field.setSelectionRange(0, field.value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  field.remove();
  toast(ok ? "Copied" : "Could not copy", ok ? "ok" : "error");
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", () => copyText(button.dataset.copy));
});

const pageList = document.querySelector("[data-page-list]");
const searchInput = document.querySelector("[data-page-search]");
const sortSelect = document.querySelector("[data-page-sort]");
const searchEmpty = document.querySelector("[data-search-empty]");

function pageCards() {
  return [...(pageList?.querySelectorAll("[data-page-card]") || [])];
}

function applyPageFilters() {
  if (!pageList) return;
  const query = (searchInput?.value || "").trim().toLowerCase();
  const sort = sortSelect?.value || "newest";
  const cards = pageCards();
  let visible = 0;
  cards.forEach((card) => {
    const haystack = (card.dataset.search || "").toLowerCase();
    const match = !query || haystack.includes(query);
    card.hidden = !match;
    if (match) visible += 1;
  });
  const ordered = [...cards].sort((a, b) => {
    if (sort === "title") return (a.dataset.title || "").localeCompare(b.dataset.title || "");
    if (sort === "opened") return Number(b.dataset.opened || 0) - Number(a.dataset.opened || 0);
    if (sort === "opens") return Number(b.dataset.opens || 0) - Number(a.dataset.opens || 0);
    return Number(b.dataset.created || 0) - Number(a.dataset.created || 0);
  });
  ordered.forEach((card) => pageList.append(card));
  if (searchEmpty) searchEmpty.hidden = visible > 0 || !query;
}

searchInput?.addEventListener("input", applyPageFilters);
sortSelect?.addEventListener("change", applyPageFilters);
applyPageFilters();
