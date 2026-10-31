const form = document.getElementById("form");
const resume = document.getElementById("resume");
const fileName = document.getElementById("file-name");
const drop = document.getElementById("drop");
const submit = document.getElementById("submit");
const statusEl = document.getElementById("status");
const result = document.getElementById("result");
const keywords = document.getElementById("keywords");
const download = document.getElementById("download");
let pdfUrl;
const workflow = document.getElementById("workflow");

function status(message, error = false) {
  statusEl.hidden = false;
  statusEl.classList.toggle("error", error);
  statusEl.textContent = message;
}

function clearResult() {
  result.hidden = true;
  window.latexWorkflow.clear();
  document.getElementById("preview").replaceChildren();
  download.removeAttribute("href");
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  pdfUrl = undefined;
}

function validateFile(file) {
  const latex = workflow.value === "latex";
  if (!file || !file.name.toLowerCase().endsWith(latex ? ".tex" : ".pdf")) return latex ? "Choose your .tex resume source." : "Choose a PDF resume.";
  if (!file.size) return "The resume file is empty.";
  const limit = latex ? 512 * 1024 : 5 * 1024 * 1024;
  if (file.size > limit) return latex ? "The source must be 512 KB or smaller." : "The resume must be 5 MB or smaller.";
  return "";
}

resume.addEventListener("change", () => {
  const file = resume.files[0];
  fileName.textContent = file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : "Drop a file or click to choose";
  resume.setCustomValidity(file ? validateFile(file) : "");
  clearResult();
});

["dragenter", "dragover"].forEach((name) => {
  drop.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.add("over");
  });
});
["dragleave", "drop"].forEach((name) => {
  drop.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.remove("over");
  });
});
drop.addEventListener("drop", (event) => {
  if (submit.disabled) return;
  const file = event.dataTransfer.files[0];
  const error = validateFile(file);
  if (error) return status(error, true);
  const transfer = new DataTransfer();
  transfer.items.add(file);
  resume.files = transfer.files;
  resume.dispatchEvent(new Event("change"));
});

function addText(parent, tag, text, className = "") {
  if (!text) return;
  const element = document.createElement(tag);
  element.textContent = text;
  element.className = className;
  parent.append(element);
  return element;
}

function showPreview(data) {
  const preview = document.getElementById("preview");
  preview.replaceChildren();
  addText(preview, "h3", data.name);
  addText(preview, "p", data.contact, "notes");
  if (data.summary) {
    addText(preview, "h4", "Summary");
    addText(preview, "p", data.summary);
  }
  if (data.skills?.length) {
    addText(preview, "h4", "Skills");
    addText(preview, "p", data.skills.join(" · "));
  }
  if (data.experience?.length) addText(preview, "h4", "Experience");
  for (const job of data.experience || []) {
    addText(preview, "h5", [job.title, job.company].filter(Boolean).join(" · "));
    addText(preview, "p", [job.dates, job.location].filter(Boolean).join(" · "), "notes");
    const list = document.createElement("ul");
    for (const bullet of job.bullets || []) addText(list, "li", bullet);
    preview.append(list);
  }
  if (data.education?.length) addText(preview, "h4", "Education");
  for (const edu of data.education || []) {
    addText(preview, "h5", [edu.degree, edu.school].filter(Boolean).join(" · "));
    addText(preview, "p", [edu.dates, edu.details].filter(Boolean).join(" · "));
  }
  for (const [heading, lines] of Object.entries(data.extra_sections || {})) {
    addText(preview, "h4", heading);
    const list = document.createElement("ul");
    for (const line of lines) addText(list, "li", line);
    preview.append(list);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = validateFile(resume.files[0]);
  if (error) return status(error, true);
  const text = document.getElementById("job_text").value.trim();
  const url = document.getElementById("job_url").value.trim();
  if ((!text && !url) || (text && text.length < 40)) {
    return status("Provide a job URL or paste a description of at least 40 characters.", true);
  }
  clearResult();
  status(workflow.value === "latex" ? "Compiling your original template and proposing text changes…" : "Reading the posting and rewriting your resume. This may take a few minutes…");
  const body = new FormData(form);
  const controls = [...form.querySelectorAll("input, textarea, button, select")];
  const previousDisabled = controls.map((control) => control.disabled);
  controls.forEach((control) => { control.disabled = true; });
  form.setAttribute("aria-busy", "true");
  try {
    if (workflow.value === "latex") {
      await window.latexWorkflow.propose(body);
      status("Review the suggestions below, then compile the changes you select.");
      return;
    }
    const response = await fetch("/api/tailor", { method: "POST", body });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof data.detail === "string" ? data.detail : "Please check the input and try again.";
      throw new Error(message);
    }
    if (!data.pdf_base64 || !data.resume) throw new Error("The server returned an incomplete result. Please try again.");
    const bytes = Uint8Array.from(atob(data.pdf_base64), (c) => c.charCodeAt(0));
    pdfUrl = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
    download.href = pdfUrl;
    download.download = data.filename || "resume-tailored.pdf";
    keywords.replaceChildren();
    for (const word of data.keywords_used || []) addText(keywords, "li", word);
    document.getElementById("keyword-empty").hidden = Boolean(data.keywords_used?.length);
    document.getElementById("notes").textContent = data.notes || "";
    showPreview(data.resume);
    result.hidden = false;
    status("Your draft is ready. Review the wording and facts before downloading.");
    result.focus();
  } catch (error) {
    status(error instanceof TypeError ? "Could not reach the server. Check your connection and try again." : error.message, true);
  } finally {
    controls.forEach((control, i) => { control.disabled = previousDisabled[i]; });
    form.removeAttribute("aria-busy");
  }
});

fetch("/api/health")
  .then((response) => { if (!response.ok) throw new Error(); return response.json(); })
  .then((data) => {
    const setup = document.getElementById("setup");
    if (!data.has_key) {
      setup.hidden = false;
      setup.textContent = "Setup needed: add OPENROUTER_API_KEY to the server's .env file and restart the app.";
    }
  })
  .catch(() => status("Could not connect to the server. Refresh the page to try again.", true));

window.addEventListener("pagehide", () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); });


workflow.addEventListener("change", () => {
  const latex = workflow.value === "latex";
  resume.value = "";
  resume.setCustomValidity("");
  fileName.textContent = "Drop a file or click to choose";
  resume.accept = latex ? ".tex,text/x-tex,text/plain" : "application/pdf,.pdf";
  document.getElementById("upload-label").textContent = latex ? "Resume LaTeX source" : "Resume PDF";
  document.getElementById("file-limits").textContent = latex ? "UTF-8 .tex file · up to 512 KB" : "Text-based PDF · up to 5 MB and 20 pages";
  document.getElementById("workflow-hint").textContent = latex ? "LaTeX keeps your formatting. Only selected prose edits are applied." : "PDF mode rebuilds the resume in the app’s layout and changes its formatting.";
  document.getElementById("latex-options").hidden = !latex;
  document.getElementById("assets").disabled = !latex;
  document.getElementById("engine").disabled = !latex;
  submit.textContent = latex ? "Suggest text changes" : "Generate tailored PDF";
  statusEl.hidden = true;
  clearResult();
});
form.addEventListener("input", () => clearResult());
form.addEventListener("change", (event) => { if (event.target !== workflow) clearResult(); });
