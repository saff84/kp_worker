let accessToken = "";
let currentUser = null;
let currentResults = [];
let currentStage = "idle";
let manualTargetParsedId = null;
let editingCatalogRuleId = null;

const $ = (id) => document.getElementById(id);
const STATUS_RU = {
  uploaded: "Загружено",
  parsed: "Распарсено",
  matching: "Сопоставление",
  needs_review: "Требует проверки",
  completed: "Завершено",
  new: "Новая",
  auto_matched: "Нашлось",
  needs_review: "Не найдено / нужно проверить",
  rejected: "Отклонено",
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function setProgress(percent, meta) {
  $("processProgressBar").style.width = `${Math.max(0, Math.min(100, percent))}%`;
  if (meta) $("processMeta").textContent = meta;
}

function resetSteps() {
  ["stepUpload", "stepParsing", "stepMatching", "stepResult"].forEach((id) => {
    const el = $(id);
    el.classList.remove("active", "error");
    if (id === "stepUpload") el.classList.add("done");
    else el.classList.remove("done");
  });
}

function setStage(stage, meta) {
  currentStage = stage;
  resetSteps();
  if (stage === "parsing") {
    $("stepParsing").classList.add("active");
    setProgress(30, meta || "Парсинг запущен...");
  } else if (stage === "matching") {
    $("stepParsing").classList.add("done");
    $("stepMatching").classList.add("active");
    setProgress(65, meta || "Сопоставление запущено...");
  } else if (stage === "result") {
    $("stepParsing").classList.add("done");
    $("stepMatching").classList.add("done");
    $("stepResult").classList.add("done");
    setProgress(100, meta || "Готово. Результаты загружены.");
  } else if (stage === "error") {
    if (currentStage === "parsing") $("stepParsing").classList.add("error");
    else if (currentStage === "matching") $("stepMatching").classList.add("error");
    else $("stepResult").classList.add("error");
    setProgress(100, meta || "Ошибка обработки.");
  } else {
    setProgress(0, meta || "Статус: ожидание запуска.");
  }
}

function setProcessingButtons(disabled) {
  ["processAllBtn", "loadResults", "createExport"].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = disabled;
  });
}

function switchAdminTab(tab) {
  const tabs = {
    catalog: $("adminTabCatalog"),
    competitors: $("adminTabCompetitors"),
    stopWords: $("adminTabStopWords"),
  };
  const panels = {
    catalog: $("adminPanelCatalog"),
    competitors: $("adminPanelCompetitors"),
    stopWords: $("adminPanelStopWords"),
  };
  Object.entries(tabs).forEach(([name, btn]) => {
    if (!btn) return;
    btn.classList.toggle("active", name === tab);
  });
  Object.entries(panels).forEach(([name, panel]) => {
    if (!panel) return;
    panel.classList.toggle("hidden", name !== tab);
  });
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  headers["Content-Type"] = headers["Content-Type"] || "application/json";
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const response = await fetch(`/api/v1${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw data;
  return data;
}

function fmtDate(value) {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? value : dt.toLocaleString("ru-RU");
}

function confidenceBadge(score) {
  const pct = Math.round((score || 0) * 100);
  let cls = "low";
  if (pct >= 90) cls = "high";
  else if (pct >= 70) cls = "medium";
  return `<span class="pill ${cls}">${pct}%</span>`;
}

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    accessToken = data.access_token;
    currentUser = data.user;
    $("userInfo").textContent = `${currentUser.full_name || currentUser.email} (${currentUser.roles.join(", ")})`;
    $("loginView").classList.add("hidden");
    $("appView").classList.remove("hidden");
    if ((currentUser.roles || []).includes("admin")) {
      $("adminQuickSection").classList.remove("hidden");
      switchAdminTab("catalog");
      $("loadStopWordsBtn")?.click();
      $("loadCatalogRulesBtn")?.click();
    } else {
      $("adminQuickSection").classList.add("hidden");
    }
    $("statusBox").textContent = "Загрузите КП, чтобы начать обработку.";
    loadSavedRequests();
  } catch (err) {
    alert(err?.error?.message || "Ошибка входа");
  }
});

$("createAndUploadBtn").addEventListener("click", async () => {
  const title = $("requestTitle").value;
  const file = $("createFileInput").files[0];
  if (!file) return alert("Выберите файл КП");

  const created = await api("/requests", {
    method: "POST",
    body: JSON.stringify({ title: title || file.name, source_type: "file", input_text: null }),
  });
  const requestId = created.id;

  const fd = new FormData();
  fd.append("file", file);
  const response = await fetch(`/api/v1/requests/${requestId}/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: fd,
  });
  const uploadRes = await response.json().catch(() => ({}));
  if (!response.ok) {
    return alert(uploadRes?.error?.message || "Не удалось загрузить файл");
  }

  $("activeRequestId").value = requestId;
  $("statusBox").textContent = `КП загружено.\nID заявки: ${requestId}\nДальше нажмите "Обработать КП".`;
});

$("createFromTextBtn")?.addEventListener("click", async () => {
  const title = ($("requestTitle").value || "").trim();
  const raw = $("positionsTextInput").value || "";
  const lines = raw
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean);
  if (lines.length === 0) return alert("Введите позиции текстом: одна строка = одна позиция");
  const created = await api("/requests", {
    method: "POST",
    body: JSON.stringify({
      title: title || `Текстовые позиции (${new Date().toLocaleDateString("ru-RU")})`,
      source_type: "text",
      input_text: lines.join("\n"),
    }),
  });
  const requestId = created.id;
  $("activeRequestId").value = requestId;
  $("statusBox").textContent =
    `Заявка создана из текста.\nID заявки: ${requestId}\n` +
    `Позиций передано: ${lines.length}\n` +
    `Дальше нажмите "Обработать КП".`;
});

async function processAll() {
  const rid = $("activeRequestId").value;
  if (!rid) return alert("Укажите ID заявки");
  setProcessingButtons(true);
  try {
    setStage("parsing", "Парсинг запущен...");
    $("statusBox").textContent = "Запуск парсинга...";
    await api(`/requests/${rid}/parsing/start`, { method: "POST", body: JSON.stringify({ force_reparse: false }) });

    let parseDone = false;
    for (let i = 0; i < 30; i++) {
      const parseStatus = await api(`/requests/${rid}/parsing/status`);
      $("statusBox").textContent = `Парсинг: ${parseStatus.status}\nИзвлечено: ${parseStatus.parsed_items || 0}`;
      setProgress(20 + Math.round((parseStatus.progress || 0) * 0.45), `Парсинг: ${parseStatus.status}`);
      if (parseStatus.status === "failed") {
        throw new Error(parseStatus.error || "Не удалось извлечь позиции из файла.");
      }
      if (parseStatus.status === "completed") {
        parseDone = true;
        break;
      }
      await sleep(1000);
    }
    if (!parseDone) throw new Error("Парсинг не завершился вовремя. Проверьте статус и попробуйте снова.");

    setStage("matching", "Сопоставление запущено...");
    await api(`/requests/${rid}/matching/start`, {
      method: "POST",
      body: JSON.stringify({ strategy: "default", auto_approve_threshold: 0.72 }),
    });

    let matchDone = false;
    for (let i = 0; i < 30; i++) {
      const matchStatus = await api(`/requests/${rid}/matching/status`);
      $("statusBox").textContent =
        `Парсинг: completed\nСопоставление: ${matchStatus.status}\n` +
        `Автоподбор: ${matchStatus.auto_matched || 0}, Требует проверки: ${matchStatus.needs_review || 0}`;
      setProgress(60 + Math.round((matchStatus.progress || 0) * 0.4), `Сопоставление: ${matchStatus.status}`);
      if (matchStatus.status === "completed") {
        matchDone = true;
        break;
      }
      await sleep(1000);
    }
    if (!matchDone) throw new Error("Сопоставление не завершилось вовремя. Проверьте статус и попробуйте снова.");

    await loadResults();
    await loadSavedRequests();
  } catch (e) {
    setStage("error", `Ошибка: ${e.message || "неизвестно"}`);
    alert(e.message || "Ошибка обработки");
  } finally {
    setProcessingButtons(false);
  }
}

$("processAllBtn").addEventListener("click", processAll);

function openManualSearch(parsedItemId) {
  manualTargetParsedId = parsedItemId;
  $("manualSearchModal").classList.remove("hidden");
  $("manualSearchQuery").value = "";
  $("manualSearchResults").innerHTML = "";
  $("manualSearchQuery").focus();
}

function closeManualSearch() {
  manualTargetParsedId = null;
  $("manualSearchModal").classList.add("hidden");
}

async function runManualSearch() {
  const query = ($("manualSearchQuery").value || "").trim();
  if (!query) return;
  const data = await api(`/catalog/products?query=${encodeURIComponent(query)}&limit=30`);
  const box = $("manualSearchResults");
  box.innerHTML = "";
  if (!data.items || data.items.length === 0) {
    box.innerHTML = `<div class="manual-item"><div>Ничего не найдено</div></div>`;
    return;
  }
  data.items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "manual-item";
    row.innerHTML = `
      <div>
        <div><b>${item.sku || "-"}</b> | ${item.brand || "-"}</div>
        <div class="meta">${item.name || "-"}</div>
      </div>
      <button data-pick-product="${item.id}">Выбрать</button>
    `;
    box.appendChild(row);
  });
  box.querySelectorAll("button[data-pick-product]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!manualTargetParsedId) return;
      const product = data.items.find((x) => x.id === btn.dataset.pickProduct);
      const body = $("resultsTable").querySelector("tbody");
      const sel = body.querySelector(`select[data-select="${manualTargetParsedId}"]`);
      if (!sel || !product) return;
      const option = document.createElement("option");
      option.value = product.id;
      option.textContent = `${product.sku} | ${product.brand} | ${product.name}`;
      option.selected = true;
      sel.appendChild(option);
      closeManualSearch();
    });
  });
}

async function loadResults() {
  const rid = $("activeRequestId").value;
  if (!rid) return alert("Укажите ID заявки");
  const data = await api(`/requests/${rid}/results?page=1&page_size=100`);
  currentResults = data.items || [];
  if (currentResults.length > 0) {
    setStage("result", `Готово. Загружено позиций: ${currentResults.length}`);
  } else if (currentStage !== "parsing" && currentStage !== "matching") {
    setProgress(90, "Результаты пока пустые. Нажмите «Обновить результат» через пару секунд.");
  }
  const body = $("resultsTable").querySelector("tbody");
  body.innerHTML = "";
  currentResults.forEach((r) => {
    const cand = r.match.best_candidate || {};
    const rowStatus = STATUS_RU[r.match.status] || r.match.status || "Не определен";
    const options = (r.match.candidates || []).filter((x) => x.product_id).map((c) => {
      const pct = Math.round((c.score || 0) * 100);
      const label = [c.sku || "-", c.brand || "-", c.name || c.product_id].join(" | ");
      return `<option value="${c.product_id}">${label} (${pct}%)</option>`;
    });
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${r.source.item_name || "-"}</b><br/>${r.source.article || "-"} | ${r.source.brand || "-"} | кол-во: ${r.source.quantity}</td>
      <td>${cand.sku || "-"}<br/>${cand.name || "-"}</td>
      <td>${rowStatus}</td>
      <td>${confidenceBadge(cand.score)}</td>
      <td>
        <select data-select="${r.parsed_item_id}">
          <option value="">-- выбрать из найденных --</option>
          ${options.join("")}
        </select>
        <button data-manual-search="${r.parsed_item_id}">Найти вручную</button>
      </td>
      <td>
        <button data-apply="${r.parsed_item_id}" data-product="${cand.product_id || ""}">Применить замену</button>
        <button data-reject="${r.parsed_item_id}">Не менять</button>
      </td>`;
    body.appendChild(tr);
  });
  body.querySelectorAll("button[data-manual-search]").forEach((b) => {
    b.addEventListener("click", () => openManualSearch(b.dataset.manualSearch));
  });
  body.querySelectorAll("button[data-apply]").forEach((b) => {
    b.addEventListener("click", async () => {
      const rid = $("activeRequestId").value;
      const parsedId = b.dataset.apply;
      const select = body.querySelector(`select[data-select="${parsedId}"]`);
      const productId = (select && select.value) || b.dataset.product;
      if (!productId) return alert("Нет кандидата для подтверждения");
      await api(`/requests/${rid}/results/${parsedId}`, {
        method: "PUT",
        body: JSON.stringify({ action: "approve", selected_product_id: productId, comment: "Подтверждено в UI" }),
      });
      await loadResults();
    });
  });
  body.querySelectorAll("button[data-reject]").forEach((b) => {
    b.addEventListener("click", async () => {
      const rid = $("activeRequestId").value;
      const parsedId = b.dataset.reject;
      await api(`/requests/${rid}/results/${parsedId}`, {
        method: "PUT",
        body: JSON.stringify({ action: "reject", comment: "Отклонено в UI" }),
      });
      await loadResults();
    });
  });
}

$("loadResults").addEventListener("click", loadResults);

$("createExport").addEventListener("click", async () => {
  const rid = $("activeRequestId").value;
  if (!rid) return alert("Укажите ID заявки");
  const started = await api(`/requests/${rid}/export`, { method: "POST", body: JSON.stringify({ format: "xlsx", include_unmatched: true }) });
  let ex = null;
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 500));
    ex = await api(`/requests/${rid}/export/${started.export_id}`);
    if (ex.status === "completed") break;
  }
  $("statusBox").textContent = `Экспорт: ${ex?.status || "queued"}\nСсылка: ${ex?.download_url || "еще формируется"}`;
  if (ex?.status === "completed" && ex?.download_url) {
    const response = await fetch(ex.download_url, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err?.error?.message || "Не удалось скачать экспорт");
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `export_${rid}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(objectUrl);
  }
  await loadSavedRequests();
});

async function loadSavedRequests() {
  const query = ($("savedSearch")?.value || "").trim().toLowerCase();
  const data = await api("/requests?page=1&page_size=200");
  const items = (data.items || []).filter((r) => (r.title || "").toLowerCase().includes(query));
  const body = $("savedRequestsTable").querySelector("tbody");
  body.innerHTML = "";
  items.forEach((r) => {
    const tr = document.createElement("tr");
    const ruStatus = STATUS_RU[r.status] || r.status;
    tr.innerHTML = `
      <td>${r.id}</td>
      <td>${r.title || "-"}</td>
      <td>${ruStatus}</td>
      <td>${fmtDate(r.updated_at)}</td>
      <td>${r.total_items || 0}</td>
      <td><button data-open-saved="${r.id}">Открыть и редактировать</button></td>
    `;
    body.appendChild(tr);
  });
  body.querySelectorAll("button[data-open-saved]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const requestId = btn.dataset.openSaved;
      $("activeRequestId").value = requestId;
      $("statusBox").textContent = `Открыта заявка ${requestId}. Загрузите результат для правок.`;
      await loadResults();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

$("searchSavedBtn").addEventListener("click", loadSavedRequests);
$("refreshSavedBtn").addEventListener("click", loadSavedRequests);

async function uploadAdminFile(endpoint, fileInputId) {
  const file = $(fileInputId).files[0];
  if (!file) return alert("Выберите файл");
  const fd = new FormData();
  fd.append("file", file);
  const response = await fetch(`/api/v1${endpoint}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: fd,
  });
  const data = await response.json().catch(() => ({}));
  renderImportVisualization(data);
  $("adminImportReport").textContent = JSON.stringify(data, null, 2);
  if (!response.ok) return alert(data?.error?.message || "Ошибка импорта");
  alert("Импорт выполнен");
}

function renderImportVisualization(data) {
  const box = $("adminImportViz");
  if (!box) return;
  if (!data || typeof data !== "object") {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const hasImportShape = ["total_rows", "created", "updated", "skipped"].some((k) => k in data);
  if (!hasImportShape) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const metrics = [
    { label: "Всего строк", value: data.total_rows ?? 0 },
    { label: "Создано", value: data.created ?? 0 },
    { label: "Обновлено", value: data.updated ?? 0 },
    { label: "Пропущено", value: data.skipped ?? 0 },
    { label: "Ошибок", value: (data.errors || []).length },
  ];
  const rows = (data.errors || []).slice(0, 50).map((e) => {
    const fields = Array.isArray(e.fields) ? e.fields.join(", ") : (e.fields || "");
    return `<tr><td>${e.row ?? "-"}</td><td>${e.reason || "-"}</td><td>${fields || "-"}</td><td>${e.sku || e.our_sku || "-"}</td></tr>`;
  });
  box.innerHTML = `
    <div class="import-metrics">
      ${metrics.map((m) => `<div class="import-metric"><span class="hint">${m.label}</span><b>${m.value}</b></div>`).join("")}
    </div>
    ${rows.length ? `
      <div class="import-errors">
        <table>
          <thead><tr><th>Строка</th><th>Причина</th><th>Поля</th><th>SKU</th></tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table>
      </div>
    ` : `<div class="hint" style="margin-top:8px;">Ошибок импорта нет.</div>`}
  `;
  box.classList.remove("hidden");
}

function renderCatalogRules(items) {
  const box = $("catalogRulesList");
  if (!box) return;
  box.innerHTML = "";
  if (!items || items.length === 0) {
    box.innerHTML = `<div class="rule-item">Правила пока не добавлены.</div>`;
    return;
  }
  items.forEach((rule) => {
    const row = document.createElement("div");
    row.className = "rule-item";
    const whenAll = (rule.when_all || []).map((x) => `<code>${x}</code>`).join(", ");
    const requireAny = (rule.require_any || []).map((x) => `<code>${x}</code>`).join(", ");
    row.innerHTML = `
      <div class="rule-item-head">
        <b>${rule.description || "Без аннотации"}</b>
        <div class="row">
          <button data-edit-rule="${rule.id}" class="ghost-btn" type="button">Редактировать</button>
          <button data-delete-rule="${rule.id}" class="ghost-btn" type="button">Удалить</button>
        </div>
      </div>
      <div class="hint">Если в КП есть: ${whenAll || "-"}</div>
      <div class="hint">Тогда в каталоге обязательно: ${requireAny || "-"}</div>
    `;
    box.appendChild(row);
  });
  box.querySelectorAll("button[data-edit-rule]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const rule = (items || []).find((x) => x.id === btn.dataset.editRule);
      if (!rule) return;
      editingCatalogRuleId = rule.id;
      $("ruleAnnotationInput").value = rule.description || "";
      $("ruleWhenAllInput").value = (rule.when_all || []).join(", ");
      $("ruleRequireAnyInput").value = (rule.require_any || []).join(", ");
      $("addCatalogRuleBtn").textContent = "Сохранить изменения";
      $("cancelCatalogRuleEditBtn")?.classList.remove("hidden");
    });
  });
  box.querySelectorAll("button[data-delete-rule]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Удалить правило?")) return;
      try {
        await api(`/admin/matching/catalog-rules/${btn.dataset.deleteRule}`, { method: "DELETE" });
        await loadCatalogRules();
      } catch (e) {
        alert(e?.error?.message || "Не удалось удалить правило");
      }
    });
  });
}

function resetCatalogRuleForm() {
  editingCatalogRuleId = null;
  $("ruleAnnotationInput").value = "";
  $("ruleWhenAllInput").value = "";
  $("ruleRequireAnyInput").value = "";
  $("addCatalogRuleBtn").textContent = "Добавить правило";
  $("cancelCatalogRuleEditBtn")?.classList.add("hidden");
}

async function loadCatalogRules() {
  try {
    const data = await api("/admin/matching/catalog-rules");
    renderCatalogRules(data.items || []);
    $("adminImportReport").textContent = `Загружено правил матчинга: ${data.count || 0}`;
  } catch (e) {
    alert(e?.error?.message || "Не удалось загрузить правила матчинга");
  }
}

$("importCatalogBtn").addEventListener("click", async () => {
  await uploadAdminFile("/admin/catalog/import", "catalogImportFile");
});

$("reindexCatalogBtn")?.addEventListener("click", async () => {
  const btn = $("reindexCatalogBtn");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/admin/catalog/reindex", { method: "POST" });
    renderImportVisualization(null);
    $("adminImportReport").textContent = JSON.stringify(data, null, 2);
    alert(`Реиндексация завершена. Проиндексировано позиций: ${data.indexed ?? 0}`);
  } catch (e) {
    const message = e?.error?.message || "Не удалось выполнить реиндексацию";
    $("adminImportReport").textContent = JSON.stringify(e, null, 2);
    alert(message);
  } finally {
    if (btn) btn.disabled = false;
  }
});

$("importCompetitorBtn").addEventListener("click", async () => {
  await uploadAdminFile("/admin/competitor-mappings/import", "competitorImportFile");
});

$("downloadCatalogTemplate").addEventListener("click", () => {
  window.open("/api/v1/admin/templates/catalog", "_blank");
});

$("downloadCompetitorTemplate").addEventListener("click", () => {
  window.open("/api/v1/admin/templates/competitor-mappings", "_blank");
});

$("manualSearchRun")?.addEventListener("click", runManualSearch);
$("manualSearchClose")?.addEventListener("click", closeManualSearch);
$("manualSearchQuery")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    runManualSearch();
  }
});

$("adminTabCatalog")?.addEventListener("click", () => switchAdminTab("catalog"));
$("adminTabCompetitors")?.addEventListener("click", () => switchAdminTab("competitors"));
$("adminTabStopWords")?.addEventListener("click", () => switchAdminTab("stopWords"));

$("loadStopWordsBtn")?.addEventListener("click", async () => {
  try {
    const data = await api("/admin/matching/stop-words");
    $("stopWordsInput").value = (data.items || []).join("\n");
    $("adminImportReport").textContent = `Загружено стоп-слов: ${(data.items || []).length}`;
  } catch (e) {
    alert(e?.error?.message || "Не удалось загрузить стоп-слова");
  }
});

$("saveStopWordsBtn")?.addEventListener("click", async () => {
  const words = ($("stopWordsInput").value || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  try {
    const data = await api("/admin/matching/stop-words", {
      method: "PUT",
      body: JSON.stringify({ words }),
    });
    $("stopWordsInput").value = (data.items || []).join("\n");
    $("adminImportReport").textContent = `Сохранено стоп-слов: ${data.count || 0}`;
    alert("Стоп-слова сохранены");
  } catch (e) {
    alert(e?.error?.message || "Не удалось сохранить стоп-слова");
  }
});

$("loadCatalogRulesBtn")?.addEventListener("click", loadCatalogRules);

$("addCatalogRuleBtn")?.addEventListener("click", async () => {
  const annotation = ($("ruleAnnotationInput").value || "").trim();
  const when_all = ($("ruleWhenAllInput").value || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  const require_any = ($("ruleRequireAnyInput").value || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  if (when_all.length === 0 || require_any.length === 0) {
    return alert("Заполните условия и обязательные маркеры");
  }
  try {
    const payload = { annotation, when_all, require_any };
    const path = editingCatalogRuleId
      ? `/admin/matching/catalog-rules/${editingCatalogRuleId}`
      : "/admin/matching/catalog-rules";
    const method = editingCatalogRuleId ? "PUT" : "POST";
    const data = await api(path, { method, body: JSON.stringify(payload) });
    $("adminImportReport").textContent = JSON.stringify(data, null, 2);
    resetCatalogRuleForm();
    await loadCatalogRules();
  } catch (e) {
    alert(e?.error?.message || "Не удалось сохранить правило");
  }
});

$("cancelCatalogRuleEditBtn")?.addEventListener("click", resetCatalogRuleForm);
