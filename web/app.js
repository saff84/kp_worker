let accessToken = "";
let currentUser = null;
let currentResults = [];
let currentStage = "idle";
let manualTargetParsedId = null;
let editingCatalogRuleId = null;
let ocrPreviewPage = 1;
let ocrPreviewTotal = 1;

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

let ocrTimerInterval = null;
let ocrTimerStartedAtMs = null;

function formatDuration(sec) {
  const s = Math.max(0, Math.floor(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

function updateOcrTimerTick() {
  if (!ocrTimerStartedAtMs) return;
  const elapsed = Math.floor((Date.now() - ocrTimerStartedAtMs) / 1000);
  $("ocrTimerDisplay").textContent = formatDuration(elapsed);
  const bar = $("ocrTimingBar");
  if (bar) bar.style.width = `${Math.min(100, Math.round((elapsed / 300) * 100))}%`;
  const hint = $("ocrTimerHint");
  if (hint) {
    if (elapsed < 60) hint.textContent = "Обычно 1–5 минут в зависимости от числа страниц.";
    else if (elapsed < 180) hint.textContent = "Идёт распознавание… Большие сканы занимают больше времени.";
    else hint.textContent = "OCR всё ещё работает. Можно подождать или проверить логи worker на сервере.";
  }
}

function showOcrTimingModal(st) {
  const modal = $("ocrTimingModal");
  if (!modal) return;
  if (st?.ocr_started_at) {
    const serverMs = Date.parse(st.ocr_started_at);
    if (!Number.isNaN(serverMs)) ocrTimerStartedAtMs = serverMs;
  }
  if (!ocrTimerStartedAtMs) ocrTimerStartedAtMs = Date.now();
  if (typeof st?.ocr_elapsed_sec === "number") {
    ocrTimerStartedAtMs = Date.now() - st.ocr_elapsed_sec * 1000;
  }
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  const meta = $("ocrTimerMeta");
  if (meta) meta.textContent = "Статус: OCR активен на сервере";
  updateOcrTimerTick();
  if (!ocrTimerInterval) {
    ocrTimerInterval = setInterval(updateOcrTimerTick, 1000);
  }
}

function hideOcrTimingModal() {
  const modal = $("ocrTimingModal");
  if (modal) {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
  }
  if (ocrTimerInterval) {
    clearInterval(ocrTimerInterval);
    ocrTimerInterval = null;
  }
  ocrTimerStartedAtMs = null;
  const bar = $("ocrTimingBar");
  if (bar) bar.style.width = "0%";
  $("ocrTimerDisplay").textContent = "00:00";
}

function syncOcrTimingModal(st, _tick, { trackOcr = false } = {}) {
  if (!trackOcr) return;
  if (st?.ocr_active) {
    showOcrTimingModal(st);
    return;
  }
  if (st?.status === "completed" || st?.status === "failed") {
    hideOcrTimingModal();
  }
}

/** Ожидание фоновой задачи (парсинг OCR на скане может занять несколько минут). */
async function waitJobStatus(statusUrl, { maxSeconds = 360, label = "Задача", formatBox, trackOcr = false }) {
  try {
    for (let i = 0; i < maxSeconds; i++) {
      const st = await api(statusUrl);
      syncOcrTimingModal(st, i, { trackOcr });
      if (formatBox) formatBox(st, i);
      if (st.status === "failed") {
        throw new Error(st.error || `${label}: не удалось выполнить.`);
      }
      if (st.status === "completed") {
        return st;
      }
      await sleep(1000);
    }
    throw new Error(
      `${label} не завершилась за ${maxSeconds} с. ` +
        "Возможно, идёт OCR скана PDF — проверьте логи worker и нажмите «Обработать КП» ещё раз через минуту."
    );
  } finally {
    if (trackOcr) hideOcrTimingModal();
  }
}

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
    ocr: $("adminTabOcr"),
  };
  const panels = {
    catalog: $("adminPanelCatalog"),
    competitors: $("adminPanelCompetitors"),
    stopWords: $("adminPanelStopWords"),
    ocr: $("adminPanelOcr"),
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
      loadOcrCalibration();
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
    await api(`/requests/${rid}/parsing/start`, {
      method: "POST",
      body: JSON.stringify({ force_reparse: true }),
    });

    await waitJobStatus(`/requests/${rid}/parsing/status`, {
      maxSeconds: 360,
      label: "Парсинг",
      trackOcr: true,
      formatBox: (parseStatus) => {
        const ocrLine = parseStatus.ocr_active ? "\nOCR: идёт распознавание скана…" : "";
        $("statusBox").textContent =
          `Парсинг: ${parseStatus.status}\nИзвлечено: ${parseStatus.parsed_items || 0}${ocrLine}`;
        const meta = parseStatus.ocr_active
          ? `Парсинг: OCR (${formatDuration(parseStatus.ocr_elapsed_sec ?? 0)})`
          : `Парсинг: ${parseStatus.status}`;
        setProgress(
          parseStatus.ocr_active ? 28 : 20 + Math.round((parseStatus.progress || 0) * 0.45),
          meta
        );
      },
    });

    setStage("matching", "Сопоставление запущено...");
    await api(`/requests/${rid}/matching/start`, {
      method: "POST",
      body: JSON.stringify({ strategy: "default", auto_approve_threshold: 0.72 }),
    });

    await waitJobStatus(`/requests/${rid}/matching/status`, {
      maxSeconds: 180,
      label: "Сопоставление",
      formatBox: (matchStatus) => {
        $("statusBox").textContent =
          `Парсинг: completed\nСопоставление: ${matchStatus.status}\n` +
          `Автоподбор: ${matchStatus.auto_matched || 0}, Требует проверки: ${matchStatus.needs_review || 0}`;
        setProgress(60 + Math.round((matchStatus.progress || 0) * 0.4), `Сопоставление: ${matchStatus.status}`);
      },
    });

    await loadResults();
    await loadSavedRequests();
  } catch (e) {
    setStage("error", `Ошибка: ${e.message || "неизвестно"}`);
    alert(e.message || "Ошибка обработки");
  } finally {
    hideOcrTimingModal();
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

function getOcrCalibrationFromUi() {
  return {
    name_col: [Number($("ocrNameX1").value), Number($("ocrNameX2").value)],
    qty_col: [Number($("ocrQtyX1").value), Number($("ocrQtyX2").value)],
    table_y: [Number($("ocrY1").value), Number($("ocrY2").value)],
  };
}

function clampPair(pair, fallback) {
  const left = Number.isFinite(pair?.[0]) ? pair[0] : fallback[0];
  const right = Number.isFinite(pair?.[1]) ? pair[1] : fallback[1];
  const a = Math.max(0, Math.min(1, left));
  const b = Math.max(0, Math.min(1, right));
  if (b <= a) return fallback;
  return [a, b];
}

function applyOcrCalibrationToUi(cal) {
  const name = clampPair(cal?.name_col, [0.06, 0.47]);
  const qty = clampPair(cal?.qty_col, [0.72, 0.84]);
  const y = clampPair(cal?.table_y, [0.08, 0.94]);
  $("ocrNameX1").value = String(name[0]);
  $("ocrNameX2").value = String(name[1]);
  $("ocrQtyX1").value = String(qty[0]);
  $("ocrQtyX2").value = String(qty[1]);
  $("ocrY1").value = String(y[0]);
  $("ocrY2").value = String(y[1]);
  renderOcrOverlay();
}

function renderOcrOverlay() {
  const img = $("ocrPreviewImage");
  const nameOverlay = $("ocrNameOverlay");
  const qtyOverlay = $("ocrQtyOverlay");
  if (!img || img.classList.contains("hidden")) return;
  const data = getOcrCalibrationFromUi();
  const name = clampPair(data.name_col, [0.06, 0.47]);
  const qty = clampPair(data.qty_col, [0.72, 0.84]);
  const y = clampPair(data.table_y, [0.08, 0.94]);
  const toPct = (v) => `${(v * 100).toFixed(2)}%`;
  [nameOverlay, qtyOverlay].forEach((x) => x.classList.remove("hidden"));

  nameOverlay.style.left = toPct(name[0]);
  nameOverlay.style.width = toPct(name[1] - name[0]);
  nameOverlay.style.top = toPct(y[0]);
  nameOverlay.style.height = toPct(y[1] - y[0]);

  qtyOverlay.style.left = toPct(qty[0]);
  qtyOverlay.style.width = toPct(qty[1] - qty[0]);
  qtyOverlay.style.top = toPct(y[0]);
  qtyOverlay.style.height = toPct(y[1] - y[0]);

  $("ocrCalibrationDebug").textContent = JSON.stringify(data, null, 2);
}

async function loadOcrCalibration() {
  try {
    const cal = await api("/admin/ocr-calibration");
    applyOcrCalibrationToUi(cal);
  } catch (e) {
    $("adminImportReport").textContent = `OCR calibration load error: ${JSON.stringify(e, null, 2)}`;
  }
}

async function loadOcrPreview(page) {
  const requestId = ($("ocrCalRequestId").value || "").trim();
  if (!requestId) return alert("Введите ID заявки");
  const safePage = Math.max(1, page || 1);
  const meta = await api(`/admin/ocr-calibration/request/${requestId}`);
  const normalizedPage = Math.min(safePage, Math.max(1, meta.page_count || 1));
  const preview = await api(`/admin/ocr-calibration/preview/${requestId}?page=${normalizedPage}`);
  ocrPreviewPage = preview.page || normalizedPage;
  ocrPreviewTotal = preview.page_count || meta.page_count || 1;
  $("ocrPageInput").value = String(ocrPreviewPage);
  $("ocrPageMeta").textContent = `Страница: ${ocrPreviewPage} / ${ocrPreviewTotal}`;
  const img = $("ocrPreviewImage");
  img.src = preview.image_data_url;
  img.classList.remove("hidden");
  img.onload = () => renderOcrOverlay();
  renderOcrOverlay();
}

async function saveOcrCalibration() {
  const payload = getOcrCalibrationFromUi();
  if (payload.name_col[1] <= payload.name_col[0] || payload.qty_col[1] <= payload.qty_col[0] || payload.table_y[1] <= payload.table_y[0]) {
    return alert("Проверьте диапазоны: правая граница должна быть больше левой.");
  }
  const data = await api("/admin/ocr-calibration", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  applyOcrCalibrationToUi(data);
  $("adminImportReport").textContent = `OCR calibration saved:\n${JSON.stringify(data, null, 2)}`;
  alert("Калибровка OCR сохранена");
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
$("adminTabOcr")?.addEventListener("click", () => switchAdminTab("ocr"));

$("ocrLoadPreviewBtn")?.addEventListener("click", async () => {
  try {
    const page = Number($("ocrPageInput").value || "1");
    await loadOcrPreview(page);
  } catch (e) {
    alert(e?.error?.message || "Не удалось загрузить OCR предпросмотр");
  }
});

$("ocrPrevPageBtn")?.addEventListener("click", async () => {
  try {
    await loadOcrPreview(Math.max(1, ocrPreviewPage - 1));
  } catch (e) {
    alert(e?.error?.message || "Не удалось открыть страницу");
  }
});

$("ocrNextPageBtn")?.addEventListener("click", async () => {
  try {
    await loadOcrPreview(Math.min(ocrPreviewTotal, ocrPreviewPage + 1));
  } catch (e) {
    alert(e?.error?.message || "Не удалось открыть страницу");
  }
});

$("ocrPageInput")?.addEventListener("change", async () => {
  try {
    const page = Number($("ocrPageInput").value || "1");
    await loadOcrPreview(page);
  } catch (e) {
    alert(e?.error?.message || "Не удалось открыть страницу");
  }
});

["ocrNameX1", "ocrNameX2", "ocrQtyX1", "ocrQtyX2", "ocrY1", "ocrY2"].forEach((id) => {
  $(id)?.addEventListener("input", renderOcrOverlay);
});

$("ocrSaveCalibrationBtn")?.addEventListener("click", async () => {
  try {
    await saveOcrCalibration();
  } catch (e) {
    alert(e?.error?.message || "Не удалось сохранить OCR калибровку");
  }
});

$("ocrResetDefaultsBtn")?.addEventListener("click", () => {
  applyOcrCalibrationToUi({
    name_col: [0.06, 0.47],
    qty_col: [0.72, 0.84],
    table_y: [0.08, 0.94],
  });
});

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
