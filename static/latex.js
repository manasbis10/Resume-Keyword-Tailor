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
  }
  function clear() {
    review.hidden = true;
    list.replaceChildren();
    input = proposal = undefined;
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
  function updateSelection() {
    const count = list.querySelectorAll("input:checked").length;
    const total = list.querySelectorAll("input").length;
    document.getElementById("selection-count").textContent = `${count} of ${total} changes selected`;
    compileButton.textContent = count ? `Compile ${count} selected change${count === 1 ? "" : "s"}` : "Compile original unchanged";
  }
  function selectionChanged() {
    clearCompiled();
    updateSelection();
  }
  for (const [id, checked] of [["select-all", true], ["clear-selection", false]]) {
    document.getElementById(id).addEventListener("click", () => {
      for (const checkbox of list.querySelectorAll("input")) checkbox.checked = checked;
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
    document.getElementById("latex-notes").textContent = data.notes || "";
    document.getElementById("no-changes").hidden = Boolean(data.changes.length);
    document.getElementById("selection-controls").hidden = !data.changes.length;
    document.getElementById("retry-suggestions").hidden = Boolean(data.changes.length);
    document.getElementById("selection-help").textContent = data.changes.length
      ? "Select the wording changes to apply. All other source text, formatting commands, links, and sections stay intact."
      : "The model returned no changes that can be applied. This result can compile your original template unchanged.";
    originalUrl = pdfBlob(data.original_pdf_base64);
    showPages("original-pdf", data.original_preview, "Original resume");
    document.getElementById("original-download").href = originalUrl;
    for (const [i, change] of data.changes.entries()) {
      const card = document.createElement("div");
      card.className = "change-card";
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.index = String(i);
      checkbox.addEventListener("change", selectionChanged);
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
  }
  compileButton.addEventListener("click", async () => {
    if (!input || !proposal) return;
    clearCompiled();
    const body = new FormData();
    for (const [key, value] of input.entries()) {
      if (["resume", "assets", "engine"].includes(key)) body.append(key, value);
    }
    const selected = [...list.querySelectorAll("input:checked")].map((el) => proposal.changes[Number(el.dataset.index)]);
    body.set("changes", JSON.stringify(selected));
    const controls = [...document.querySelectorAll("#form input, #form select, #form textarea, #form button, #changes input, #compile, #select-all, #clear-selection, #retry-suggestions")];
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
      compileStatus.textContent = `Applied ${data.applied_changes} selected change(s). Review the PDF before downloading.`;
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
