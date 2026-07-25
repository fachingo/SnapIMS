(() => {
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];
  const toast = (message, kind = "success") => {
    const node = document.createElement("div");
    node.className = `save-toast ${kind}`;
    node.textContent = message;
    document.body.append(node);
    setTimeout(() => node.remove(), 2600);
  };

  // Recognition progress remains live without making the operator refresh manually.
  const status = qs('#recognition-status[data-running="true"]');
  if (status) {
    const batch = status.dataset.batch;
    const poll = async () => {
      try {
        const response = await fetch(`/review/job/${encodeURIComponent(batch)}`);
        const data = await response.json();
        const strong = qs("strong", status);
        if (strong) strong.textContent = data.text;
        if (data.job && ["RUNNING", "IDENTIFYING"].includes(data.job.status)) {
          setTimeout(poll, 450);
        } else {
          window.location.reload();
        }
      } catch (_) {
        setTimeout(poll, 900);
      }
    };
    setTimeout(poll, 300);
  }

  // Tinder-fast Review: price is selected; Enter executes Approve & Next.
  const quickPrice = qs("#quick-price");
  const quickForm = qs("#quick-approve-form");
  const quickButton = qs("#approve-next-button");
  if (quickPrice && quickForm && quickButton) {
    requestAnimationFrame(() => {
      quickPrice.focus();
      quickPrice.select();
    });
    quickPrice.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      if (quickForm.dataset.submitting === "true") return;
      if (!quickForm.reportValidity()) return;
      quickForm.dataset.submitting = "true";
      quickButton.disabled = true;
      quickForm.requestSubmit(quickButton);
    });
  }

  qsa("form[data-prevent-double-submit]").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = qs('button[type="submit"], button:not([type])', form);
      if (button) {
        button.disabled = true;
        button.textContent = "Working…";
      }
    });
  });

  qsa("[data-requires-input]").forEach((button) => {
    const input = qs(`[name="${button.dataset.requiresInput}"]`, button.form);
    if (!input) return;
    const sync = () => { button.disabled = !input.value.trim(); };
    input.addEventListener("input", sync);
    sync();
  });

  // Global command palette.
  const palette = qs("#command-palette");
  const paletteSearch = qs("#command-search");
  const openPalette = () => {
    if (!palette) return;
    palette.showModal();
    paletteSearch?.focus();
  };
  qs("[data-command-open]")?.addEventListener("click", openPalette);
  qs("[data-command-close]")?.addEventListener("click", () => palette?.close());
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "p") {
      event.preventDefault();
      openPalette();
    }
    if (event.ctrlKey && event.key.toLowerCase() === "f" && qs("#batch-search")) {
      event.preventDefault();
      qs("#batch-search").focus();
    }
  });
  paletteSearch?.addEventListener("input", () => {
    const query = paletteSearch.value.toLowerCase();
    qsa("[data-command]", palette).forEach((command) => {
      command.hidden = !command.textContent.toLowerCase().includes(query);
    });
  });
  qsa("[data-command-action]").forEach((button) => {
    const action = button.dataset.commandAction;
    const available = action === "focus-search" ? qs("#batch-search") :
      action === "bulk-price" ? qs('[data-bulk="set_price"]') :
      action === "approve-selected" ? qs('[data-bulk="approve"]') : null;
    if (!available) {
      button.hidden = true;
      return;
    }
    button.addEventListener("click", () => {
      palette?.close();
      if (action === "focus-search") qs("#batch-search")?.focus();
      if (action === "bulk-price") qs('[data-bulk="set_price"]')?.click();
      if (action === "approve-selected") qs('[data-bulk="approve"]')?.click();
    });
  });

  // CSV diff controls.
  qsa("[data-diff-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.diffFilter;
      qsa(".diff-card").forEach((card) => {
        const match = filter === "all" ||
          (filter === "errors" && card.dataset.hasErrors === "true") ||
          (card.dataset.columns || "").includes(filter);
        card.classList.toggle("hidden", !match);
      });
    });
  });
  qs("[data-diff-expand]")?.addEventListener("click", () => qsa(".diff-card").forEach((card) => { card.open = true; }));
  qs("[data-diff-collapse]")?.addEventListener("click", () => qsa(".diff-card").forEach((card) => { card.open = false; }));

  // Diagnostics copy.
  qs("[data-copy-diagnostics]")?.addEventListener("click", async () => {
    const text = qs("#diagnostic-summary")?.value || "";
    await navigator.clipboard.writeText(text);
    toast("Diagnostic summary copied.");
  });

  // Batch Editor workstation.
  const editor = qs("[data-batch-editor]");
  if (!editor) return;

  const batchId = editor.dataset.batchId;
  const storageKey = `snapims-editor-${batchId}`;
  const itemData = JSON.parse(qs("#batch-items-json")?.textContent || "[]");
  const byId = new Map(itemData.map((item) => [item.item_id, item]));
  const grid = qs("#batch-grid");
  const rows = () => qsa("tbody tr", grid);
  const selectedRows = () => rows().filter((row) => qs(".row-select", row)?.checked);
  const saveState = qs("#editor-save-state");
  const pending = new Map();
  const undoStack = [];
  const redoStack = [];
  let lowThreshold = 0.70;
  let activeInput = null;

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const currentInputValue = (input) => input.type === "checkbox" ? input.checked : input.value;
  const setInputValue = (input, value) => {
    if (input.type === "checkbox") input.checked = Boolean(value);
    else if (input.dataset.field === "price_cents" && typeof value === "number") input.value = (value / 100).toFixed(2);
    else input.value = value ?? "";
  };

  const persistView = () => {
    const state = {
      search: qs("#batch-search")?.value || "",
      filter: qs("#batch-filter")?.value || "all",
      sort: qs("#batch-sort")?.value || "sequence",
      threshold: qs("#confidence-threshold")?.value || "70",
      scrollX: qs(".data-grid-wrap")?.scrollLeft || 0,
      scrollY: window.scrollY,
      activeItem: activeInput?.closest("tr")?.dataset.itemId || "",
      activeField: activeInput?.dataset.field || "",
    };
    localStorage.setItem(storageKey, JSON.stringify(state));
  };

  const updateSelectionCount = () => {
    const count = selectedRows().length;
    qs("#selection-count").textContent = `${count} selected`;
    rows().forEach((row) => row.classList.toggle("selected", qs(".row-select", row).checked));
  };
  qsa(".row-select", grid).forEach((box) => box.addEventListener("change", updateSelectionCount));
  qs("[data-select-all]")?.addEventListener("change", (event) => {
    rows().filter((row) => !row.classList.contains("hidden")).forEach((row) => {
      qs(".row-select", row).checked = event.target.checked;
    });
    updateSelectionCount();
  });
  qs("[data-select-visible]")?.addEventListener("click", () => {
    rows().filter((row) => !row.classList.contains("hidden")).forEach((row) => { qs(".row-select", row).checked = true; });
    updateSelectionCount();
  });
  qs("[data-clear-selection]")?.addEventListener("click", () => {
    rows().forEach((row) => { qs(".row-select", row).checked = false; });
    updateSelectionCount();
  });

  const updateHealth = (health) => {
    if (!health) return;
    Object.entries(health).forEach(([key, value]) => {
      const node = qs(`[data-health="${key}"]`);
      if (node) node.textContent = key === "readiness_percent" ? `${value}%` : value;
    });
  };

  const sendEdit = async (input, {recordUndo = true} = {}) => {
    const row = input.closest("tr");
    const itemId = row.dataset.itemId;
    const field = input.dataset.field;
    const value = currentInputValue(input);
    const item = byId.get(itemId) || {};
    const oldValue = item[field];
    input.classList.add("dirty");
    input.classList.remove("save-failed");
    saveState.textContent = "Saving…";
    try {
      const response = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({field, value, revision: Number(row.dataset.revision), reason: "Batch Editor"}),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Save failed");
      if (recordUndo && oldValue !== data.item[field]) {
        undoStack.push({itemId, field, oldValue, newValue: data.item[field]});
        redoStack.length = 0;
      }
      row.dataset.revision = data.item.record_revision;
      row.dataset.reviewStatus = data.item.review_status;
      row.dataset.confidence = data.item.display_confidence ?? -1;
      row.dataset.rare = data.item.rare;
      row.dataset.review = data.item.review;
      row.dataset.updated = data.item.updated_at || "";
      Object.assign(item, data.item);
      input.classList.remove("dirty", "save-failed");
      saveState.textContent = "Saved";
      updateHealth(data.health);
      persistView();
      return true;
    } catch (error) {
      input.classList.add("save-failed");
      saveState.textContent = "Save failed";
      toast(error.message, "error");
      return false;
    }
  };

  const inputFor = (itemId, field) => qs(`tr[data-item-id="${CSS.escape(itemId)}"] [data-field="${CSS.escape(field)}"]`, grid);
  const applyHistory = async (entry, reverse) => {
    const input = inputFor(entry.itemId, entry.field);
    if (!input) return false;
    setInputValue(input, reverse ? entry.oldValue : entry.newValue);
    input.classList.add("dirty");
    const saved = await sendEdit(input, {recordUndo: false});
    if (saved) toast(reverse ? "Undo complete." : "Redo complete.");
    return saved;
  };

  qsa("[data-field]", grid).forEach((input) => {
    input.addEventListener("focus", () => { activeInput = input; persistView(); });
    const schedule = () => {
      clearTimeout(pending.get(input));
      input.classList.add("dirty");
      pending.set(input, setTimeout(() => sendEdit(input), 450));
    };
    input.addEventListener(input.type === "checkbox" ? "change" : "input", schedule);
    input.addEventListener("blur", () => {
      clearTimeout(pending.get(input));
      if (input.classList.contains("dirty")) sendEdit(input);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        const item = byId.get(input.closest("tr").dataset.itemId);
        setInputValue(input, item?.[input.dataset.field]);
        input.classList.remove("dirty", "save-failed");
        input.blur();
      }
      if (event.key === "Enter" && input.tagName !== "TEXTAREA") {
        event.preventDefault();
        clearTimeout(pending.get(input));
        sendEdit(input).then((saved) => {
          if (!saved) return;
          const visible = rows().filter((row) => !row.classList.contains("hidden"));
          const currentIndex = visible.indexOf(input.closest("tr"));
          const next = visible[currentIndex + 1]?.querySelector(`[data-field="${input.dataset.field}"]`);
          next?.focus();
          next?.select?.();
        });
      }
      if (event.ctrlKey && event.key === "Enter" && input.tagName === "TEXTAREA") {
        event.preventDefault();
        clearTimeout(pending.get(input));
        sendEdit(input);
      }
    });
  });

  const saveAll = async () => {
    const dirty = qsa(".dirty", grid);
    let saved = 0;
    let failed = 0;
    for (const input of dirty) {
      clearTimeout(pending.get(input));
      if (await sendEdit(input)) saved += 1;
      else failed += 1;
    }
    saveState.textContent = failed ? `${saved} saved · ${failed} failed` : `${saved} saved`;
    toast(failed ? `${saved} saved · ${failed} failed` : `${saved} pending edits saved.`, failed ? "error" : "success");
    return {saved, failed};
  };
  qs("[data-save-all]")?.addEventListener("click", saveAll);

  const applyFilters = () => {
    const search = (qs("#batch-search")?.value || "").toLowerCase();
    const filter = qs("#batch-filter")?.value || "all";
    lowThreshold = Number(qs("#confidence-threshold")?.value || 70) / 100;
    rows().forEach((row) => {
      const item = byId.get(row.dataset.itemId) || {};
      const haystack = [item.title, item.suggested_title, item.description, item.sku, item.item_id, item.tags, item.shelf].join(" ").toLowerCase();
      const confidence = Number(row.dataset.confidence);
      let match = !search || haystack.includes(search);
      if (filter === "unfinished") match &&= row.dataset.reviewStatus === "UNFINISHED";
      if (filter === "approved") match &&= row.dataset.reviewStatus === "DONE";
      if (filter === "failed") match &&= row.dataset.recognitionStatus === "FAILED";
      if (filter === "low") match &&= confidence >= 0 && confidence < lowThreshold;
      if (filter === "missing-title") match &&= !(item.title || "").trim();
      if (filter === "flagged") match &&= row.dataset.review === "1";
      if (filter === "rare") match &&= row.dataset.rare === "1";
      if (filter === "recent") match &&= String(item.working_source || "IMPORT") !== "IMPORT";
      row.classList.toggle("hidden", !match);
    });
    persistView();
  };
  qs("#batch-search")?.addEventListener("input", applyFilters);
  qs("#batch-filter")?.addEventListener("change", applyFilters);
  qs("#confidence-threshold")?.addEventListener("input", applyFilters);
  qsa("[data-confidence-min],[data-confidence-max],[data-confidence-manual],[data-confidence-unknown]").forEach((button) => {
    button.addEventListener("click", () => {
      const min = button.dataset.confidenceMin ? Number(button.dataset.confidenceMin) : -1;
      const max = button.dataset.confidenceMax ? Number(button.dataset.confidenceMax) : 2;
      rows().forEach((row) => {
        const value = Number(row.dataset.confidence);
        const manual = row.dataset.valueState === "REVIEWED" && value < 0;
        const match = button.hasAttribute("data-confidence-manual") ? manual :
          button.hasAttribute("data-confidence-unknown") ? value < 0 && !manual : value >= min && value < max;
        row.classList.toggle("hidden", !match);
      });
      persistView();
    });
  });

  const sortRows = () => {
    const mode = qs("#batch-sort")?.value || "sequence";
    const body = qs("tbody", grid);
    const sorted = rows().sort((a, b) => {
      const ia = byId.get(a.dataset.itemId) || {};
      const ib = byId.get(b.dataset.itemId) || {};
      if (mode === "confidence") return Number(a.dataset.confidence) - Number(b.dataset.confidence);
      if (mode === "title") return (ia.title || ia.suggested_title || "").localeCompare(ib.title || ib.suggested_title || "");
      if (mode === "price") return Number(ia.price_cents || ia.suggested_price_cents || 0) - Number(ib.price_cents || ib.suggested_price_cents || 0);
      if (mode === "updated") return String(ib.updated_at || "").localeCompare(String(ia.updated_at || ""));
      return Number(a.dataset.sequence) - Number(b.dataset.sequence);
    });
    sorted.forEach((row) => body.append(row));
    persistView();
  };
  qs("#batch-sort")?.addEventListener("change", sortRows);

  const bulkDialog = qs("#bulk-dialog");
  let bulkAction = "";
  const actionsWithoutValue = ["flag_review", "clear_review", "mark_rare", "clear_rare", "approve"];
  qsa("[data-bulk]").forEach((button) => {
    button.addEventListener("click", () => {
      const count = selectedRows().length;
      if (!count) return toast("Select at least one row.", "error");
      bulkAction = button.dataset.bulk;
      const needsValue = !actionsWithoutValue.includes(bulkAction);
      qs("#bulk-value-label").hidden = !needsValue;
      qs("#bulk-title").textContent = button.textContent;
      qs("#bulk-summary").textContent = `${count} selected items will be affected. A rollback checkpoint will be created first.`;
      qs("#bulk-value").value = bulkAction === "round_price" ? "0.50" : "";
      bulkDialog.showModal();
      if (needsValue) qs("#bulk-value").focus();
    });
  });
  qs("#bulk-apply")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const itemIds = selectedRows().map((row) => row.dataset.itemId);
    const value = qs("#bulk-value").value;
    const reason = qs("#bulk-reason").value;
    if (!actionsWithoutValue.includes(bulkAction) && !value.trim()) return toast("Enter a bulk value.", "error");
    button.disabled = true;
    button.textContent = "Applying…";
    try {
      const requestId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      const response = await fetch(`/api/batches/${encodeURIComponent(batchId)}/bulk`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({item_ids: itemIds, action: bulkAction, value, reason, request_id: requestId}),
      });
      const data = await response.json();
      if (!response.ok || !data.ok || data.failed) throw new Error(data.error || (data.errors || ["Bulk edit failed"])[0]);
      bulkDialog.close();
      toast(`✓ ${data.changed} changed · ${data.unchanged} unchanged · checkpoint ${data.checkpoint_id}`);
      setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      toast(error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = "Preview and apply";
    }
  });

  qs("[data-fill-down]")?.addEventListener("click", async () => {
    if (!activeInput) return toast("Focus the source cell first.", "error");
    const field = activeInput.dataset.field;
    const map = {
      title: "set_title", price_cents: "set_price", discount_percent: "set_discount",
      description: "set_description", shelf: "set_location",
    };
    const action = map[field];
    if (!action) return toast(`Fill Down is not supported for ${field}.`, "error");
    const itemIds = selectedRows().map((row) => row.dataset.itemId);
    if (!itemIds.length) return toast("Select destination rows first.", "error");
    const value = currentInputValue(activeInput);
    try {
      const requestId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      const response = await fetch(`/api/batches/${encodeURIComponent(batchId)}/bulk`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({item_ids: itemIds, action, value, reason: `Fill down ${field}`, request_id: requestId}),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Fill Down failed");
      toast(`✓ Filled ${data.changed} cells atomically.`);
      setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      toast(error.message, "error");
    }
  });

  qsa("[data-restore-checkpoint]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm("Restore this batch checkpoint? A new safety checkpoint will be created first.")) return;
      const response = await fetch(`/api/checkpoints/${button.dataset.restoreCheckpoint}/restore`, {method: "POST"});
      const data = await response.json();
      if (!data.ok) return toast(data.error, "error");
      toast(`✓ ${data.restored} items restored`);
      setTimeout(() => window.location.reload(), 650);
    });
  });

  const evidenceDialog = qs("#evidence-dialog");
  qsa("[data-evidence]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = byId.get(button.closest("tr").dataset.itemId) || {};
      const reasons = Array.isArray(item.uncertainty_reasons) ? item.uncertainty_reasons : [];
      qs("#evidence-content").innerHTML = `
        <p><strong>${escapeHtml(item.suggested_title || item.title || "No title suggestion")}</strong></p>
        <p>Confidence: ${item.display_confidence == null ? (item.review_status === "DONE" ? "Manual" : "Not identified") : Math.round(item.display_confidence * 100) + "%"}</p>
        <p>Provider: ${escapeHtml(item.suggestion_provider || item.recognition_provider || "Not run")}</p>
        <p>Pricing source: ${escapeHtml(item.pricing_source || "Not recorded")}</p>
        <p>Tokens: ${Number(item.input_tokens || 0)} input · ${Number(item.output_tokens || 0)} output</p>
        <p>Images: ${Number(item.image_count || 0)}</p>
        <h3>Stored uncertainty</h3>
        <ul>${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("") || "<li>No stored explanation. SnapIMS does not invent one.</li>"}</ul>`;
      evidenceDialog.showModal();
    });
  });

  const mediaDialog = qs("#media-dialog");
  qsa("[data-media-item]").forEach((button) => {
    button.addEventListener("click", async () => {
      const itemId = button.dataset.mediaItem;
      const response = await fetch(`/api/items/${encodeURIComponent(itemId)}/photos`);
      const data = await response.json();
      qs("#media-content").innerHTML = `<div class="media-gallery">${data.photos.map((photo) => `
        <figure><img src="/media/${photo.photo_id}" alt="${escapeHtml(photo.original_name)}"><figcaption>${escapeHtml(photo.image_role)} · ${escapeHtml(photo.original_name)}<br>Original ${Math.round(photo.original_bytes / 1024)} KB · Preview ${Math.round(photo.preview_bytes / 1024)} KB · AI ${Math.round(photo.recognition_bytes / 1024)} KB<br><a href="/media/${photo.photo_id}?original=true" target="_blank">Open original</a></figcaption></figure>`).join("")}</div>`;
      mediaDialog.showModal();
    });
  });
  qsa("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => button.closest("dialog").close()));

  document.addEventListener("keydown", async (event) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (event.ctrlKey && event.key.toLowerCase() === "s") {
      event.preventDefault();
      await saveAll();
    }
    if (event.ctrlKey && event.key.toLowerCase() === "a" && !typing) {
      event.preventDefault();
      rows().filter((row) => !row.classList.contains("hidden")).forEach((row) => { qs(".row-select", row).checked = true; });
      updateSelectionCount();
    }
    if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      const entry = undoStack.pop();
      if (entry && await applyHistory(entry, true)) redoStack.push(entry);
    }
    if ((event.ctrlKey && event.key.toLowerCase() === "y") || (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "z")) {
      event.preventDefault();
      const entry = redoStack.pop();
      if (entry && await applyHistory(entry, false)) undoStack.push(entry);
    }
    if (event.key === "F2" && activeInput) {
      event.preventDefault();
      activeInput.focus();
      activeInput.select?.();
    }
    if (event.key === " " && !typing && document.activeElement?.closest("tr")) {
      event.preventDefault();
      const box = qs(".row-select", document.activeElement.closest("tr"));
      if (box) { box.checked = !box.checked; updateSelectionCount(); }
    }
  });

  window.addEventListener("beforeunload", (event) => {
    persistView();
    if (!qsa(".dirty", grid).length) return;
    event.preventDefault();
    event.returnValue = "";
  });

  try {
    const state = JSON.parse(localStorage.getItem(storageKey) || "{}");
    if (state.search != null) qs("#batch-search").value = state.search;
    if (state.filter) qs("#batch-filter").value = state.filter;
    if (state.sort) qs("#batch-sort").value = state.sort;
    if (state.threshold) qs("#confidence-threshold").value = state.threshold;
    applyFilters();
    sortRows();
    requestAnimationFrame(() => {
      if (state.scrollX) qs(".data-grid-wrap").scrollLeft = state.scrollX;
      if (state.scrollY) window.scrollTo(0, state.scrollY);
      if (state.activeItem && state.activeField) inputFor(state.activeItem, state.activeField)?.focus();
    });
    if (Object.keys(state).length) toast("Restored your last Batch Editor view.");
  } catch (_) {
    applyFilters();
  }
})();
