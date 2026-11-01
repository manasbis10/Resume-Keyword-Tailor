/* All source and proposal state belongs to this browser tab, not the server. */
window.latexWorkflow = (() => {
  const review = document.getElementById("latex-review");
  const list = document.getElementById("changes");
  const compileButton = document.getElementById("compile");
  const compileStatus = document.getElementById("compile-status");
  let input;
  let proposal;
  let originalUrl;
  let compiledUrl;
  let texUrl;
  const keywordSelections = new Map();

  function pdfBlob(encoded) {
    const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
    return URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
  }
  function clearCompiled() {
    document.getElementById("compiled-result").hidden = true;
    document.getElementById("compiled-pdf").replaceChildren();
    for (const id of ["latex-download", "tex-download"]) document.getElementById(id).removeAttribute("href");
    if (compiledUrl) URL.revokeObjectURL(compiledUrl);
    if (texUrl) URL.revokeObjectURL(texUrl);
    compiledUrl = texUrl = undefined;
    document.getElementById("latex-warnings").hidden = true;
    compileStatus.hidden = true;
    if (proposal) showKeywordReport(proposal.keyword_report || []);
  }
  function clear() {
    review.hidden = true;
    list.replaceChildren();
    input = proposal = undefined;
    document.getElementById("ai-warning").hidden = true;
    document.getElementById("ai-warning").textContent = "";
    keywordSelections.clear();
    document.getElementById("manual-keyword-preview").hidden = true;
    document.getElementById("keyword-analysis").hidden = true;
    document.getElementById("keyword-report").replaceChildren();
    document.getElementById("selection-controls").hidden = true;
    document.getElementById("rejected-changes").hidden = true;
    document.getElementById("rejected-list").replaceChildren();
    document.getElementById("retry-suggestions").hidden = true;
    document.getElementById("original-pdf").replaceChildren();
    document.getElementById("original-download").removeAttribute("href");
    if (originalUrl) URL.revokeObjectURL(originalUrl);
    originalUrl = undefined;
    clearCompiled();
  }
  function text(parent, tag, value, className = "") {
    const node = document.createElement(tag);
    node.textContent = value;
    node.className = className;
    parent.append(node);
    return node;
  }
  async function responseData(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "The request failed. Check your input and try again.");
    return data;
  }
  function showPages(id, pages, label) {
    const container = document.getElementById(id);
    container.replaceChildren();
    for (const [index, encoded] of (pages || []).entries()) {
      const image = document.createElement("img");
      image.src = `data:image/png;base64,${encoded}`;
      image.alt = `${label}, page ${index + 1}`;
      container.append(image);
    }
  }
  function selectedChanges() {
    if (!proposal) return [];
    return [...list.querySelectorAll("input:checked")].flatMap(el => {
      const change = proposal.changes[Number(el.dataset.index)];
      const terms = (change.keywords_added || []).filter(term => keywordSelections.get(term) !== false);
      const { keyword_variants, ...payload } = change;
      if (keyword_variants?.length) {
        if (!terms.length) return [];
        const variant = keyword_variants.find(item => item.keywords.length === terms.length && item.keywords.every(term => terms.includes(term)));
        return variant ? [{ ...payload, after: variant.after, keywords_added: terms }] : [];
      }
      if ((change.keywords_added || []).some(term => keywordSelections.get(term) === false)) return [];
      return [payload];
    });
  }
  function selectedNewKeywords() {
    if (!proposal) return [];
    return (proposal.keyword_report || [])
      .filter(item => item.status !== "present" && !proposal.changes.some(change => change.keywords_added?.includes(item.keyword)) && keywordSelections.get(item.keyword) === true)
      .map(item => item.keyword);
  }
  function chooseKeyword(term, checked) {
    keywordSelections.set(term, checked);
    for (const [index, change] of proposal.changes.entries()) {
      if (!change.keywords_added?.includes(term)) continue;
      const parent = document.getElementById(`change-${index}`);
      if (change.keyword_variants?.length) {
        parent.checked = change.keywords_added.some(word => keywordSelections.get(word) !== false);
      } else {
        // A prose rewrite can be indivisible; accepting its keyword accepts the
        // displayed rewrite, and rejecting it excludes that whole rewrite.
        parent.checked = checked;
        for (const word of change.keywords_added) keywordSelections.set(word, checked);
      }
    }
    selectionChanged();
  }
  function showKeywordReport(report, compiled = false) {
    const table = document.getElementById("keyword-report");
    table.replaceChildren();
    document.getElementById("keyword-analysis").hidden = !report.length;
    const selectedTerms = new Set([...selectedChanges().flatMap(change => change.keywords_added || []), ...selectedNewKeywords()]);
    for (const [index, item] of report.entries()) {
      const row = document.createElement("tr");
      const choices = proposal?.changes.filter(change => change.keywords_added?.includes(item.keyword)) || [];
      const selectCell = document.createElement("td");
      if (choices.length || item.status !== "present") {
        const label = document.createElement("label");
        label.className = "keyword-choice";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.id = `keyword-${index}`;
        checkbox.dataset.keyword = item.keyword;
        checkbox.dataset.manual = String(!choices.length);
        checkbox.setAttribute("aria-label", `Add ${item.keyword}`);
        checkbox.checked = selectedTerms.has(item.keyword);
        checkbox.addEventListener("change", () => chooseKeyword(item.keyword, checkbox.checked));
        label.append(checkbox);
        text(label, "span", "Add");
        selectCell.append(label);
        if (choices.some(change => !change.keyword_variants?.length)) {
          label.title = "This keyword is part of the wording edit shown below. Toggling it accepts or rejects that edit.";
        }
      } else {
        selectCell.textContent = "Already included";
      }
      row.append(selectCell);
      let coverage;
      if (compiled) {
        coverage = item.added ? "Added to compiled resume" : item.in_output ? "Present in compiled resume" : item.status === "missing" ? "Not added" : "Supported, but not added";
      } else {
        coverage = item.status === "present" ? "Already present" : selectedTerms.has(item.keyword) ? "Selected for addition" : item.status === "supported" ? "Supported — not selected" : "Not currently listed";
      }
      row.className = "";
      text(row, "td", item.keyword);
      text(row, "td", coverage);
      text(row, "td", item.evidence || "Not currently listed");
      table.append(row);
    }
  }
  function updateSelection() {
    const selected = selectedChanges();
    const newKeywords = selectedNewKeywords();
    const count = selected.length + newKeywords.length;
    for (const [index, change] of (proposal?.changes || []).entries()) {
      const card = list.querySelector(`[data-change-index="${index}"]`);
      if (!card || !change.keyword_variants?.length) continue;
      const active = selected.find(item => item.id === change.id);
      card.querySelector(".after").textContent = active?.after || change.before;
      const keywords = card.querySelector(".keyword-insertion");
      if (keywords) keywords.textContent = active ? `Keywords selected here: ${active.keywords_added.join(", ")}` : "No keyword additions selected for this passage.";
    }
    const total = list.querySelectorAll("input").length + (proposal?.keyword_report || []).filter(item => item.status !== "present" && !proposal.changes.some(change => change.keywords_added?.includes(item.keyword))).length;
    document.getElementById("selection-count").textContent = `${count} of ${total} changes selected`;
    const manualPreview = document.getElementById("manual-keyword-preview");
    manualPreview.hidden = !newKeywords.length;
    manualPreview.textContent = newKeywords.length ? `Add to skills: ${newKeywords.join(", ")}` : "";
    compileButton.textContent = count ? `Compile ${count} selected change${count === 1 ? "" : "s"}` : "Compile original unchanged";
    if (proposal) showKeywordReport(proposal.keyword_report || []);
  }
  function selectionChanged() {
    clearCompiled();
    updateSelection();
  }
  for (const [id, checked] of [["select-all", true], ["clear-selection", false]]) {
    document.getElementById(id).addEventListener("click", () => {
      for (const checkbox of list.querySelectorAll("input")) checkbox.checked = checked;
      for (const term of keywordSelections.keys()) keywordSelections.set(term, checked);
      selectionChanged();
    });
  }
  document.getElementById("retry-suggestions").addEventListener("click", () => {
    document.getElementById("form").requestSubmit();
  });
  async function propose(body) {
    const data = await responseData(await fetch("/api/latex/propose", { method: "POST", body }));
    if (!Array.isArray(data.changes) || !data.original_pdf_base64) throw new Error("The proposal is incomplete. Please try again.");
    input = body;
    proposal = data;
    document.getElementById("ai-warning").hidden = !data.ai_warning;
    document.getElementById("ai-warning").textContent = data.ai_warning || "";
    keywordSelections.clear();
    for (const item of data.keyword_report || []) keywordSelections.set(item.keyword, false);
    for (const change of data.changes) for (const term of change.keywords_added || []) keywordSelections.set(term, true);
    document.getElementById("latex-notes").textContent = data.notes || "";
    document.getElementById("no-changes").hidden = Boolean(data.changes.length);
    document.getElementById("selection-controls").hidden = !data.changes.length && !(data.keyword_report || []).some(item => item.status !== "present");
    document.getElementById("retry-suggestions").hidden = Boolean(data.changes.length);
    document.getElementById("selection-help").textContent = data.changes.length
      ? "Select the wording changes to apply. All other source text, formatting commands, links, and sections stay intact."
      : "Select keywords in the coverage table to add to your skills, or compile the original unchanged.";
    originalUrl = pdfBlob(data.original_pdf_base64);
    showPages("original-pdf", data.original_preview, "Original resume");
    document.getElementById("original-download").href = originalUrl;
    for (const [i, change] of data.changes.entries()) {
      const card = document.createElement("div");
      card.className = "change-card";
      card.dataset.changeIndex = String(i);
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.index = String(i);
      checkbox.addEventListener("change", () => {
        for (const term of change.keywords_added || []) keywordSelections.set(term, checkbox.checked);
        selectionChanged();
      });
      checkbox.id = `change-${i}`;
      label.htmlFor = checkbox.id;
      label.append(checkbox);
      text(label, "span", `Apply change ${i + 1}`);
      card.append(label);
      text(card, "p", "Original", "label");
      text(card, "p", change.before, "before");
      text(card, "p", "Proposed", "label");
      text(card, "p", change.after, "after");
      if (change.reason) text(card, "p", change.reason, "notes");
      if (change.keywords_added?.length) text(card, "p", `Keywords added here: ${change.keywords_added.join(", ")}`, "keyword-insertion");
      list.append(card);
    }
    const rejected = data.rejected_changes || [];
    const rejectedDetails = document.getElementById("rejected-changes");
    rejectedDetails.hidden = !rejected.length;
    rejectedDetails.open = !data.changes.length;
    document.getElementById("rejected-title").textContent = `Why ${rejected.length} suggestion(s) could not be selected`;
    const rejectedList = document.getElementById("rejected-list");
    rejectedList.replaceChildren();
    for (const change of rejected) {
      const card = document.createElement("div");
      card.className = "change-card rejected-card";
      text(card, "p", change.reason, "rejection-reason");
      text(card, "p", "Original", "label");
      text(card, "p", change.before, "before");
      text(card, "p", "Rejected suggestion", "label");
      text(card, "p", change.after, "after");
      rejectedList.append(card);
    }
    updateSelection();
    review.hidden = false;
    review.focus();
    return data;
  }
  compileButton.addEventListener("click", async () => {
    if (!input || !proposal) return;
    clearCompiled();
    const body = new FormData();
    for (const [key, value] of input.entries()) {
      if (["resume", "assets", "engine"].includes(key)) body.append(key, value);
    }
    const selected = selectedChanges();
    body.set("changes", JSON.stringify(selected));
    body.set("added_keywords", JSON.stringify(selectedNewKeywords()));
    body.set("keyword_terms", JSON.stringify((proposal.keyword_report || []).map(item => item.keyword)));
    const controls = [...document.querySelectorAll("#form input, #form select, #form textarea, #form button, #changes input, #keyword-report input, #compile, #select-all, #clear-selection, #retry-suggestions")];
    const disabled = controls.map((el) => el.disabled);
    controls.forEach((el) => { el.disabled = true; });
    compileStatus.hidden = false;
    compileStatus.classList.remove("error");
    compileStatus.textContent = "Compiling and checking the original and edited PDFs…";
    try {
      const data = await responseData(await fetch("/api/latex/compile", { method: "POST", body }));
      if (!data.pdf_base64 || typeof data.tex_source !== "string") throw new Error("The compilation result is incomplete.");
      compiledUrl = pdfBlob(data.pdf_base64);
      texUrl = URL.createObjectURL(new Blob([data.tex_source], { type: "text/x-tex;charset=utf-8" }));
      showPages("compiled-pdf", data.preview, "Edited resume");
      const download = document.getElementById("latex-download");
      download.href = compiledUrl;
      download.download = data.filename;
      const sourceDownload = document.getElementById("tex-download");
      sourceDownload.href = texUrl;
      sourceDownload.download = data.tex_filename;
      document.getElementById("page-count").textContent = `Original: ${data.original_pages} page(s) · Edited: ${data.pages} page(s)`;
      const warnings = document.getElementById("latex-warnings");
      warnings.replaceChildren();
      for (const warning of data.warnings || []) text(warnings, "p", warning);
      warnings.hidden = !data.warnings?.length;
      document.getElementById("compiled-result").hidden = false;
      showKeywordReport(data.keyword_report || [], true);
      compileStatus.textContent = `Applied ${data.applied_changes} selected change(s).${data.added_keywords?.length ? ` Added ${data.added_keywords.length} keyword(s) to skills.` : ""} Review the PDF before downloading.`;
    } catch (error) {
      compileStatus.classList.add("error");
      compileStatus.textContent = error instanceof TypeError ? "Could not reach the server. Please try again." : error.message;
    } finally {
      controls.forEach((el, i) => { el.disabled = disabled[i]; });
    }
  });
  fetch("/api/latex/health")
    .then(responseData)
    .then((data) => {
      document.getElementById("compiler-status").textContent = data.engines?.length && data.sandbox ? "Local compiler ready." : "Compiler setup needed. See the LaTeX setup instructions in README.md.";
    })
    .catch(() => { document.getElementById("compiler-status").textContent = "Compiler status unavailable. Check that the server is running."; });
  window.addEventListener("pagehide", clear);
  return { propose, clear };
})();
