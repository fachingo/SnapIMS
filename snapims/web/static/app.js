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
    let pollDelay = 1500;
    let pollTimer = null;
    const schedulePoll = (delay = pollDelay) => {
      clearTimeout(pollTimer);
      pollTimer = setTimeout(poll, document.hidden ? Math.max(delay, 5000) : delay);
    };
    const poll = async () => {
      if (document.hidden) return schedulePoll(5000);
      try {
        const response = await fetch(`/review/job/${encodeURIComponent(batch)}`);
        if ([401, 403].includes(response.status)) return;
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const strong = qs("strong", status);
        if (strong) strong.textContent = data.text;
        pollDelay = 1500;
        if (data.job && ["RUNNING", "IDENTIFYING", "PAUSING"].includes(data.job.status)) {
          schedulePoll();
        } else {
          window.location.reload();
        }
      } catch (_) {
        pollDelay = Math.min(30000, Math.max(3000, pollDelay * 2));
        schedulePoll();
      }
    };
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) schedulePoll(250);
    });
    schedulePoll(750);
  }

  // One-enter Review: focus the first required empty quick field, otherwise Price.
  const quickTitle = qs("#quick-title");
  const quickPrice = qs("#quick-price");
  const quickDiscount = qs("#quick-discount");
  const quickForm = qs("#quick-approve-form");
  const quickButton = qs("#approve-next-button");
  if (quickForm && quickButton) {
    const quickFields = [quickTitle, quickPrice, quickDiscount].filter(Boolean);
    const focusTarget = quickFields.find((input) => input.required && !input.value.trim()) || quickPrice || quickTitle;
    requestAnimationFrame(() => {
      focusTarget?.focus();
      focusTarget?.select?.();
    });
    const submitQuickReview = (event) => {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      if (quickForm.dataset.submitting === "true") return;
      if (!quickForm.reportValidity()) return;
      quickForm.dataset.submitting = "true";
      quickButton.disabled = true;
      quickForm.requestSubmit(quickButton);
    };
    quickFields.forEach((input) => input.addEventListener("keydown", submitQuickReview));
    quickForm.addEventListener("submit", () => {
      quickForm.dataset.submitting = "true";
      quickButton.disabled = true;
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
    const paletteShortcut = event.altKey && !event.ctrlKey && !event.metaKey &&
      !event.shiftKey && (event.code === "KeyP" || event.key.toLowerCase() === "p");
    if (paletteShortcut && !event.repeat && !event.isComposing) {
      event.preventDefault();
      event.stopPropagation();
      openPalette();
      paletteSearch?.select?.();
      return;
    }
    if (event.key === "Escape" && palette?.open) {
      event.preventDefault();
      palette.close();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f" && qs("#batch-search")) {
      event.preventDefault();
      qs("#batch-search").focus();
    }
  }, true);
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
  qsa("[data-auto-submit]").forEach((control) => {
    control.addEventListener("change", () => control.form?.requestSubmit());
  });

  // Controlled tag picker. Only server-provided immutable Tag IDs are selectable.
  let tagDefinitions = [];
  try {
    tagDefinitions = JSON.parse(qs("#tag-definitions-json")?.textContent || "[]");
  } catch (_) {}
  const tagById = new Map(tagDefinitions.map((tag) => [tag.tag_id, tag]));
  qsa("[data-tag-picker]").forEach((picker) => {
    const pills = qs("[data-tag-pills]", picker);
    const input = qs("[data-tag-input]", picker);
    const suggestions = qs("[data-tag-suggestions]", picker);
    const hidden = qs("[data-tag-value]", picker);
    let selected = String(picker.dataset.selected || "").split(",").filter(Boolean);
    let matches = [];
    let activeIndex = 0;
    const listboxId = suggestions.id || `tag-options-${crypto.randomUUID?.() || Math.random().toString(36).slice(2)}`;
    suggestions.id = listboxId;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", listboxId);
    input.setAttribute("aria-expanded", "false");

    const sync = (notify = false) => {
      picker.dataset.selected = selected.join(",");
      picker.tagIds = [...selected];
      if (hidden) hidden.value = selected.join(",");
      pills.replaceChildren();
      selected.forEach((tagId) => {
        const definition = tagById.get(tagId);
        if (!definition) return;
        const pill = document.createElement("span");
        pill.className = `tag-pill${definition.active ? "" : " retired"}`;
        pill.textContent = definition.canonical_label;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "×";
        remove.setAttribute("aria-label", `Remove ${definition.canonical_label}`);
        remove.addEventListener("click", () => {
          selected = selected.filter((value) => value !== tagId);
          sync(true);
          input.focus();
        });
        pill.append(remove);
        pills.append(pill);
      });
      if (notify) picker.dispatchEvent(new CustomEvent("tagschange", {detail: {tagIds: [...selected]}}));
    };
    const closeSuggestions = () => {
      suggestions.hidden = true;
      suggestions.replaceChildren();
      matches = [];
      activeIndex = 0;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    };
    const showSuggestions = () => {
      const query = input.value.trim().toLowerCase();
      matches = tagDefinitions.filter((tag) => tag.active && !selected.includes(tag.tag_id) &&
        (!query || [tag.canonical_label, ...(tag.aliases || [])].some((value) => String(value).toLowerCase().includes(query))));
      suggestions.replaceChildren();
      matches.forEach((tag, index) => {
        const option = document.createElement("button");
        option.type = "button";
        option.id = `${listboxId}-option-${index}`;
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", index === activeIndex ? "true" : "false");
        option.classList.toggle("active", index === activeIndex);
        const label = document.createElement("span");
        label.textContent = tag.canonical_label;
        const detail = document.createElement("small");
        detail.textContent = `${tag.category || "General"} · ${tag.tag_id}`;
        option.append(label, detail);
        option.addEventListener("mousedown", (event) => event.preventDefault());
        option.addEventListener("click", () => {
          selected.push(tag.tag_id);
          input.value = "";
          sync(true);
          showSuggestions();
          input.focus();
        });
        suggestions.append(option);
      });
      suggestions.hidden = matches.length === 0;
      input.setAttribute("aria-expanded", matches.length ? "true" : "false");
      if (matches.length) input.setAttribute("aria-activedescendant", `${listboxId}-option-${activeIndex}`);
      else input.removeAttribute("aria-activedescendant");
    };
    input.addEventListener("focus", showSuggestions);
    input.addEventListener("input", () => { activeIndex = 0; showSuggestions(); });
    input.addEventListener("blur", () => setTimeout(closeSuggestions, 100));
    input.addEventListener("keydown", (event) => {
      if (event.isComposing) return;
      if (event.key === "Escape" && !suggestions.hidden) {
        event.preventDefault();
        event.stopPropagation();
        closeSuggestions();
        return;
      }
      if (event.key === "ArrowDown" && matches.length) {
        event.preventDefault();
        event.stopPropagation();
        activeIndex = Math.min(matches.length - 1, activeIndex + 1);
        showSuggestions();
        return;
      }
      if (event.key === "ArrowUp" && matches.length) {
        event.preventDefault();
        event.stopPropagation();
        activeIndex = Math.max(0, activeIndex - 1);
        showSuggestions();
        return;
      }
      if ((event.key === "Enter" || event.key === ",") && matches.length) {
        event.preventDefault();
        event.stopPropagation();
        selected.push(matches[activeIndex].tag_id);
        input.value = "";
        sync(true);
        showSuggestions();
        return;
      }
      if (event.key === "Backspace" && !input.value && selected.length) {
        event.preventDefault();
        selected.pop();
        sync(true);
        showSuggestions();
      }
    });
    picker.setTagIds = (tagIds) => {
      selected = [...tagIds].filter((tagId) => tagById.has(tagId));
      sync(false);
    };
    picker.focusTagInput = () => input.focus();
    sync(false);
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
  qsa("[data-copy-event]").forEach((button) => {
    button.addEventListener("click", async () => {
      await navigator.clipboard.writeText(button.dataset.eventJson || "{}");
      toast("Event copied.");
    });
  });
  const updateElapsed = () => qsa("[data-started-at]").forEach((node) => {
    const elapsed = Math.max(0, Date.now() - Date.parse(node.dataset.startedAt || ""));
    const target = qs("[data-operation-elapsed]", node);
    if (target) target.textContent = `${Math.floor(elapsed / 1000)}s elapsed`;
  });
  updateElapsed();
  if (qsa("[data-started-at]").length) setInterval(updateElapsed, 1000);

  const activity = qs("[data-live-activity]");
  if (activity) {
    const makeCell = (value) => {
      const cell = document.createElement("td");
      cell.textContent = String(value || "—");
      return cell;
    };
    const makeEventRow = (event) => {
      const row = document.createElement("tr");
      row.dataset.eventId = event.event_id;
      const timeCell = makeCell(event.occurred_at);
      if (event.duration_ms) {
        const small = document.createElement("small");
        small.textContent = `${event.duration_ms} ms`;
        timeCell.append(small);
      }
      const sourceCell = makeCell(`${event.severity} · ${event.component}`);
      const eventCell = makeCell(event.event_type);
      if (event.operation_id) {
        const code = document.createElement("code");
        code.textContent = event.operation_id;
        eventCell.append(code);
      }
      const outcomeCell = makeCell(
        [event.status, event.outcome, event.attempt_number ? `attempt ${event.attempt_number}` : ""]
          .filter(Boolean).join(" · ")
      );
      const detailCell = makeCell(event.safe_summary || "");
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Technical detail";
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(event.detail || {}, null, 2);
      details.append(summary, pre);
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "icon";
      copy.textContent = "Copy event";
      copy.addEventListener("click", async () => {
        await navigator.clipboard.writeText(JSON.stringify(event, null, 2));
        toast("Event copied.");
      });
      detailCell.append(details, copy);
      row.append(timeCell, sourceCell, eventCell, outcomeCell, detailCell);
      return row;
    };
    const pollState = qs("[data-activity-poll-state]");
    let activityDelay = 2500;
    const pollActivity = async () => {
      if (document.hidden) {
        setTimeout(pollActivity, 7500);
        return;
      }
      const params = new URLSearchParams({
        after: activity.dataset.lastEventId || "0",
        last: "100",
        source: activity.dataset.source || "",
        severity: activity.dataset.severity || "",
        operation: activity.dataset.operation || "",
      });
      try {
        const response = await fetch(`/api/diagnostics/events?${params}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        qs("[data-empty-activity]", activity)?.remove();
        payload.events.forEach((event) => activity.prepend(makeEventRow(event)));
        while (activity.children.length > 100) activity.lastElementChild?.remove();
        activity.dataset.lastEventId = String(payload.last_event_id || activity.dataset.lastEventId);
        if (pollState) pollState.textContent = "Live";
        activityDelay = 2500;
      } catch (_) {
        if (pollState) pollState.textContent = "Retrying";
        activityDelay = Math.min(30000, Math.max(5000, activityDelay * 2));
      }
      setTimeout(pollActivity, activityDelay);
    };
    setTimeout(pollActivity, activityDelay);
  }

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
  const saveQueues = new Map();
  const saveSequences = new Map();
  let inFlightSaves = 0;
  const undoStack = [];
  const redoStack = [];
  let lowThreshold = 0.70;
  let activeInput = null;
  let selectionAnchor = null;

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const currentInputValue = (input) => input.matches?.("[data-tag-picker]") ?
    [...(input.tagIds || [])] : input.type === "checkbox" ? input.checked : input.value;
  const setInputValue = (input, value) => {
    if (input.matches?.("[data-tag-picker]")) input.setTagIds?.(Array.isArray(value) ? value : []);
    else if (input.type === "checkbox") input.checked = Boolean(value);
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
  const visibleRows = () => rows().filter((row) => !row.classList.contains("hidden"));
  const selectRange = (fromRow, toRow, selected = true) => {
    const visible = visibleRows();
    const start = visible.indexOf(fromRow);
    const end = visible.indexOf(toRow);
    if (start < 0 || end < 0) return;
    const [low, high] = start <= end ? [start, end] : [end, start];
    visible.slice(low, high + 1).forEach((row) => {
      const box = qs(".row-select", row);
      if (box) box.checked = selected;
    });
    updateSelectionCount();
  };
  qsa(".row-select", grid).forEach((box) => {
    box.addEventListener("click", (event) => {
      const row = box.closest("tr");
      if (event.shiftKey && selectionAnchor) {
        event.preventDefault();
        selectRange(selectionAnchor, row, true);
        box.checked = true;
      } else {
        selectionAnchor = row;
      }
      updateSelectionCount();
    });
    box.addEventListener("change", updateSelectionCount);
  });
  rows().forEach((row) => {
    row.tabIndex = -1;
    row.addEventListener("click", (event) => {
      if (!(event.ctrlKey || event.metaKey || event.shiftKey) || event.target.closest("input,textarea,select,button,a")) return;
      const box = qs(".row-select", row);
      if (!box) return;
      if (event.shiftKey && selectionAnchor) selectRange(selectionAnchor, row, true);
      else { box.checked = !box.checked; selectionAnchor = row; updateSelectionCount(); }
    });
  });
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

  const sameValue = (left, right) => JSON.stringify(left) === JSON.stringify(right);
  const sendEdit = (input, {recordUndo = true} = {}) => {
    const row = input.closest("tr");
    const itemId = row.dataset.itemId;
    const field = input.dataset.field;
    const value = currentInputValue(input);
    const sequence = (saveSequences.get(input) || 0) + 1;
    saveSequences.set(input, sequence);
    clearTimeout(pending.get(input));
    pending.delete(input);
    input.classList.add("dirty");
    input.classList.remove("save-failed");
    saveState.textContent = "Saving…";

    const prior = saveQueues.get(itemId) || Promise.resolve(true);
    const task = prior.catch(() => false).then(async () => {
      const item = byId.get(itemId) || {};
      const oldValue = item[field];
      inFlightSaves += 1;
      try {
        const response = await fetch(`/api/items/${encodeURIComponent(itemId)}`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({field, value, revision: Number(row.dataset.revision), reason: "Batch Editor"}),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "Save failed");
        if (recordUndo && !sameValue(oldValue, data.item[field])) {
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
        const newest = saveSequences.get(input) === sequence;
        const unchangedSinceQueued = sameValue(currentInputValue(input), value);
        if (newest && unchangedSinceQueued) {
          input.classList.remove("dirty", "save-failed");
          saveState.textContent = "Saved";
        } else {
          input.classList.add("dirty");
          saveState.textContent = "Saving latest change…";
        }
        updateHealth(data.health);
        persistView();
        return true;
      } catch (error) {
        input.classList.add("dirty", "save-failed");
        saveState.textContent = "Save failed";
        toast(error.message, "error");
        return false;
      } finally {
        inFlightSaves -= 1;
      }
    });
    const tracked = task.finally(() => {
      if (saveQueues.get(itemId) === tracked) saveQueues.delete(itemId);
    });
    saveQueues.set(itemId, tracked);
    return tracked;
  };
  qsa("[data-editor-tags]", grid).forEach((picker) => {
    qs("[data-tag-input]", picker)?.addEventListener("focus", () => {
      activeInput = picker;
      selectionAnchor = selectionAnchor || picker.closest("tr");
      persistView();
    });
    picker.addEventListener("tagschange", () => sendEdit(picker));
  });

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

  const editableInputs = (row) => qsa("[data-field]", row).filter((input) => !input.disabled && !input.hidden);
  const focusSameField = (row, field) => {
    const target = qs(`[data-field="${CSS.escape(field)}"]`, row);
    if (!target || target.disabled || target.hidden) return false;
    if (target.matches?.("[data-tag-picker]")) target.focusTagInput?.();
    else {
      target.focus();
      target.select?.();
    }
    return true;
  };
  const moveVertical = (input, direction) => {
    const visible = visibleRows();
    const index = visible.indexOf(input.closest("tr"));
    const target = visible[index + direction];
    return target ? focusSameField(target, input.dataset.field) : false;
  };
  const moveHorizontal = (input, direction) => {
    const cells = editableInputs(input.closest("tr"));
    const index = cells.indexOf(input);
    const target = cells[index + direction];
    if (!target) return false;
    target.focus();
    target.select?.();
    return true;
  };
  const caretAtBoundary = (input, direction) => {
    if (input.type === "checkbox" || input.tagName === "SELECT") return true;
    const start = input.selectionStart;
    const end = input.selectionEnd;
    if (start == null || end == null || start !== end) return false;
    return direction < 0 ? start === 0 : end === input.value.length;
  };

  qsa("[data-field]", grid).forEach((input) => {
    input.addEventListener("focus", () => { activeInput = input; selectionAnchor = selectionAnchor || input.closest("tr"); persistView(); });
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
      if (event.shiftKey && ["ArrowUp", "ArrowDown"].includes(event.key)) {
        event.preventDefault();
        const currentRow = input.closest("tr");
        selectionAnchor = selectionAnchor || currentRow;
        const visible = visibleRows();
        const index = visible.indexOf(currentRow);
        const target = visible[index + (event.key === "ArrowUp" ? -1 : 1)];
        if (target) {
          selectRange(selectionAnchor, target, true);
          focusSameField(target, input.dataset.field);
        }
        return;
      }
      if (!event.shiftKey && event.key === "ArrowUp") { event.preventDefault(); moveVertical(input, -1); return; }
      if (!event.shiftKey && event.key === "ArrowDown") { event.preventDefault(); moveVertical(input, 1); return; }
      if (!event.shiftKey && event.key === "ArrowLeft" && caretAtBoundary(input, -1)) {
        if (moveHorizontal(input, -1)) event.preventDefault();
        return;
      }
      if (!event.shiftKey && event.key === "ArrowRight" && caretAtBoundary(input, 1)) {
        if (moveHorizontal(input, 1)) event.preventDefault();
        return;
      }
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
  const bulkDescriptions = {
    set_price: "Replaces Price on the selected rows. A checkpoint is created before applying.",
    add_price: "Adds this amount to each selected Price. Existing prices are retained and adjusted.",
    subtract_percent: "Reduces each selected Price by the entered percentage. A checkpoint is created first.",
    round_price: "Rounds selected prices to the entered increment without changing other fields.",
    set_discount: "Replaces Discount on the selected rows. The change can be restored from the checkpoint.",
    set_location: "Moves selected tapes to this shelf. Physical Item IDs do not change.",
    append_tags: "Appends tags to selected rows without replacing existing tags.",
    prefix_description: "Adds text to the beginning of each selected description.",
    replace_description: "Replaces matching text inside selected descriptions.",
    flag_review: "Adds the Physical Review flag to selected rows.",
    approve: "Marks valid selected rows reviewed. Invalid rows are reported and remain unchanged.",
  };
  const quickActionsBar = qs("[data-quick-actions]");
  const quickOrderKey = "snapims-quick-actions-v1";
  const actionButtons = () => qsa(":scope > button", quickActionsBar).filter((button) => !button.hidden);
  const actionKey = (button) => button.dataset.bulk || (button.hasAttribute("data-fill-down") ? "fill_down" : button.hasAttribute("data-save-all") ? "save_all" : button.textContent.trim());
  const refreshActionShortcuts = () => {
    actionButtons().forEach((button, index) => {
      button.dataset.actionKey = actionKey(button);
      button.draggable = true;
      const label = button.dataset.baseLabel || button.textContent.replace(/\s*Alt\+\d$/, "").trim();
      button.dataset.baseLabel = label;
      button.textContent = index < 9 ? `${label}  Alt+${index + 1}` : label;
      button.title = index < 9 ? `${label} — Alt+${index + 1}. Alt+Left/Right reorders.` : `${label} — Alt+Left/Right reorders.`;
    });
    localStorage.setItem(quickOrderKey, JSON.stringify(actionButtons().map(actionKey)));
  };
  try {
    const order = JSON.parse(localStorage.getItem(quickOrderKey) || "[]");
    order.forEach((key) => {
      const button = actionButtons().find((candidate) => actionKey(candidate) === key);
      if (button) quickActionsBar.append(button);
    });
  } catch (_) {}
  let draggedAction = null;
  actionButtons().forEach((button) => {
    button.addEventListener("dragstart", () => { draggedAction = button; });
    button.addEventListener("dragover", (event) => event.preventDefault());
    button.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!draggedAction || draggedAction === button) return;
      const rect = button.getBoundingClientRect();
      quickActionsBar.insertBefore(draggedAction, event.clientX < rect.left + rect.width / 2 ? button : button.nextSibling);
      refreshActionShortcuts();
    });
    button.addEventListener("keydown", (event) => {
      if (!event.altKey || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const buttons = actionButtons();
      const index = buttons.indexOf(button);
      const target = buttons[index + (event.key === "ArrowLeft" ? -1 : 1)];
      if (!target) return;
      quickActionsBar.insertBefore(button, event.key === "ArrowLeft" ? target : target.nextSibling);
      refreshActionShortcuts();
      button.focus();
    });
  });
  refreshActionShortcuts();
  qs("[data-reset-quick-order]")?.addEventListener("click", () => {
    localStorage.removeItem(quickOrderKey);
    window.location.reload();
  });

  qsa("[data-bulk]").forEach((button) => {
    button.addEventListener("click", () => {
      const count = selectedRows().length;
      if (!count) return toast("Select at least one row.", "error");
      bulkAction = button.dataset.bulk;
      const needsValue = !actionsWithoutValue.includes(bulkAction);
      qs("#bulk-value-label").hidden = !needsValue;
      qs("#bulk-title").textContent = button.dataset.baseLabel || button.textContent;
      qs("#bulk-summary").textContent = `${count} selected items will be affected. A rollback checkpoint will be created first.`;
      qs("#bulk-description").textContent = bulkDescriptions[bulkAction] || "Applies this action to the selected visible rows after preview and confirmation.";
      qs("#bulk-value").value = bulkAction === "round_price" ? "0.50" : "";
      qs("#bulk-value").setAttribute("list", bulkAction === "append_tags" ? "controlled-tag-values" : "");
      qs("#bulk-value").placeholder = bulkAction === "append_tags" ? "Approved Tag ID" : "";
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
    const modifier = event.ctrlKey || event.metaKey;
    if (event.altKey && !modifier && !event.shiftKey && /^Digit[1-9]$/.test(event.code) &&
        !typing && !event.isComposing && !qs("dialog[open]")) {
      const index = Number(event.code.slice(-1)) - 1;
      const button = actionButtons()[index];
      if (button && !button.disabled) { event.preventDefault(); button.click(); }
      return;
    }
    if (modifier && event.key.toLowerCase() === "s") {
      event.preventDefault();
      await saveAll();
    }
    if (modifier && event.key.toLowerCase() === "a" && !typing && !qs("dialog[open]")) {
      event.preventDefault();
      rows().filter((row) => !row.classList.contains("hidden")).forEach((row) => { qs(".row-select", row).checked = true; });
      updateSelectionCount();
    }
    if (modifier && !event.shiftKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      const entry = undoStack.pop();
      if (entry && await applyHistory(entry, true)) redoStack.push(entry);
    }
    if ((modifier && event.key.toLowerCase() === "y") || (modifier && event.shiftKey && event.key.toLowerCase() === "z")) {
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
    if (!qsa(".dirty", grid).length && inFlightSaves === 0) return;
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
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const nativeFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const method = String(init.method || "GET").toUpperCase();
  const target = typeof input === "string" ? new URL(input, window.location.href) : new URL(input.url);
  if (csrfToken && target.origin === window.location.origin && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    const headers = new Headers(init.headers || (typeof input !== "string" ? input.headers : undefined));
    headers.set("X-CSRF-Token", csrfToken);
    init = {...init, headers};
  }
  return nativeFetch(input, init);
};

document.querySelectorAll('form[method="post" i]').forEach((form) => {
  if (!form.querySelector('input[name="csrf_token"]')) {
    const field = document.createElement("input");
    field.type = "hidden";
    field.name = "csrf_token";
    field.value = csrfToken;
    form.appendChild(field);
  }
});
