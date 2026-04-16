const state = {
  mode: "recent",
  questions: [],
  answers: new Map(),
  index: 0,
};

const el = {
  keyStatus: document.querySelector("#keyStatus"),
  countStatus: document.querySelector("#countStatus"),
  modelInput: document.querySelector("#modelInput"),
  wordInput: document.querySelector("#wordInput"),
  generateBtn: document.querySelector("#generateBtn"),
  generateState: document.querySelector("#generateState"),
  refreshBtn: document.querySelector("#refreshBtn"),
  wordList: document.querySelector("#wordList"),
  modeBtns: document.querySelectorAll(".mode-btn"),
  practiceCount: document.querySelector("#practiceCount"),
  startPracticeBtn: document.querySelector("#startPracticeBtn"),
  emptyPractice: document.querySelector("#emptyPractice"),
  questionCard: document.querySelector("#questionCard"),
  progressText: document.querySelector("#progressText"),
  modeText: document.querySelector("#modeText"),
  maskedSentence: document.querySelector("#maskedSentence"),
  answerForm: document.querySelector("#answerForm"),
  answerInput: document.querySelector("#answerInput"),
  checkBtn: document.querySelector("#checkBtn"),
  feedback: document.querySelector("#feedback"),
  prevBtn: document.querySelector("#prevBtn"),
  nextBtn: document.querySelector("#nextBtn"),
  toast: document.querySelector("#toast"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.details ? `\n${data.details}` : "";
    throw new Error(`${data.error || "请求失败"}${detail}`);
  }
  return data;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return map[char];
  });
}

function toast(message) {
  el.toast.textContent = message;
  el.toast.classList.remove("hidden");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => el.toast.classList.add("hidden"), 3200);
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.setAttribute("aria-busy", busy ? "true" : "false");
}

function modeLabel(mode = state.mode) {
  if (mode === "random") {
    return "随机 n 词";
  }
  if (mode === "weak") {
    return "最不熟悉 n 词";
  }
  return "最近 n 词";
}

function currentQuestion() {
  return state.questions[state.index] || null;
}

function cleanAnswerText(value) {
  return String(value || "").replace(/[^A-Za-z'-]/g, "");
}

function previewLetters(question, typed) {
  const target = (question.parts || []).find((part) => part.type === "target");
  if (!target) {
    return "";
  }

  const clean = cleanAnswerText(typed);
  const prefix = String(target.prefix || "");
  const normalizedClean = clean.toLowerCase();
  const normalizedPrefix = prefix.toLowerCase();
  const suffix = normalizedClean.startsWith(normalizedPrefix) && clean.length > prefix.length
    ? clean.slice(prefix.length)
    : clean;

  return suffix.slice(0, Math.max(1, Number(target.missing_count || 1)));
}

async function loadStatus() {
  const status = await api("/api/status");
  el.modelInput.value = el.modelInput.value || status.default_model || "qwen3.5-plus";
  el.keyStatus.textContent = status.has_api_key
    ? `${status.api_key_env} 已读取`
    : `${status.api_key_env} 未读取`;
  el.keyStatus.className = `pill ${status.has_api_key ? "ok" : "bad"}`;
  el.countStatus.textContent = `${status.word_count} 词 / ${status.example_count} 句`;
}

async function loadWords() {
  const data = await api("/api/words");
  renderWords(data.words);
}

function renderWords(words) {
  if (!words.length) {
    el.wordList.innerHTML = `<div class="empty-state"><p>词本还是空的。</p></div>`;
    return;
  }
  el.wordList.innerHTML = words
    .map(
      (item) => `
        <div class="word-row" data-id="${item.id}">
          <div class="word-main">${escapeHtml(item.word)}</div>
          <div class="word-meaning">${escapeHtml(item.chinese_meaning)}</div>
          <span class="pill score">熟练 ${item.proficiency}/10</span>
          <span class="pill quiet">${item.example_count} 句</span>
          <button class="delete-btn" type="button" title="删除" aria-label="删除 ${escapeHtml(
            item.word,
          )}">×</button>
        </div>
      `,
    )
    .join("");
}

async function generateWords() {
  const words = el.wordInput.value.trim();
  if (!words) {
    toast("先输入至少一个单词。");
    el.wordInput.focus();
    return;
  }

  setBusy(el.generateBtn, true);
  el.generateState.textContent = "生成中...";
  try {
    const data = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({ words, model: el.modelInput.value.trim() }),
    });
    const skipped = data.skipped || [];
    el.wordInput.value = skipped.length ? skipped.map((item) => item.word).join("\n") : "";
    el.generateState.textContent = skipped.length
      ? `已保存 ${data.saved.length} 个，跳过 ${skipped.length} 个`
      : `已保存 ${data.saved.length} 个单词`;
    await Promise.all([loadStatus(), loadWords()]);
    toast(skipped.length ? "部分单词已跳过，输入框里保留了可重试的词。" : "例句已经保存。");
  } catch (error) {
    el.generateState.textContent = "";
    toast(error.message);
  } finally {
    setBusy(el.generateBtn, false);
  }
}

async function startPracticeRound() {
  setBusy(el.startPracticeBtn, true);
  try {
    const data = await api("/api/practice/start", {
      method: "POST",
      body: JSON.stringify({
        mode: state.mode,
        n: Number(el.practiceCount.value || 10),
      }),
    });
    state.questions = data.questions || [];
    state.answers = new Map();
    state.index = 0;
    if (!state.questions.length) {
      showEmptyPractice("词本里还没有可练习的例句。");
      return;
    }
    el.emptyPractice.classList.add("hidden");
    el.questionCard.classList.remove("hidden");
    renderQuestion();
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(el.startPracticeBtn, false);
  }
}

function showEmptyPractice(message) {
  el.questionCard.classList.add("hidden");
  el.emptyPractice.classList.remove("hidden");
  el.emptyPractice.querySelector("p").textContent = message;
}

function renderQuestion() {
  const question = state.questions[state.index];
  const savedAnswer = state.answers.get(question.example_id);
  el.progressText.textContent = `${state.index + 1} / ${state.questions.length}`;
  el.modeText.textContent = modeLabel();
  el.answerInput.value = savedAnswer?.typed || "";
  renderMaskedSentence(question, el.answerInput.value);
  el.answerInput.disabled = Boolean(savedAnswer);
  el.checkBtn.disabled = Boolean(savedAnswer);
  el.prevBtn.disabled = state.index === 0;
  el.nextBtn.textContent = state.index === state.questions.length - 1 ? "完成" : "下一题";
  renderFeedback(savedAnswer);
  if (!savedAnswer) {
    window.setTimeout(() => el.answerInput.focus(), 0);
  } else {
    window.setTimeout(() => el.nextBtn.focus(), 0);
  }
}

function renderMaskedSentence(question, typed = "") {
  el.maskedSentence.textContent = "";
  const parts = question.parts || [];
  if (!parts.length) {
    el.maskedSentence.textContent = question.masked_sentence || "";
    return;
  }

  const preview = previewLetters(question, typed);
  for (const part of parts) {
    if (part.type !== "target") {
      el.maskedSentence.append(document.createTextNode(part.text || ""));
      continue;
    }

    const target = document.createElement("span");
    target.className = "target-word";

    const prefix = document.createElement("span");
    prefix.className = "target-prefix";
    prefix.textContent = part.prefix || "";
    target.append(prefix);

    const blanks = document.createElement("span");
    blanks.className = "letter-blanks";
    const count = Math.max(1, Number(part.missing_count || 1));
    for (let i = 0; i < count; i += 1) {
      const blank = document.createElement("span");
      blank.className = "letter-blank";
      blank.textContent = preview[i] || "";
      blank.classList.toggle("filled", Boolean(preview[i]));
      blanks.append(blank);
    }
    target.append(blanks);
    el.maskedSentence.append(target);
  }
}

function renderFeedback(result) {
  el.feedback.classList.toggle("hidden", !result);
  el.feedback.classList.remove("correct", "wrong");
  if (!result) {
    el.feedback.innerHTML = "";
    return;
  }

  const tone = result.correct ? "correct" : "wrong";
  el.feedback.classList.add(tone);
  el.feedback.innerHTML = `
    <div class="feedback-title ${tone}">
      ${result.correct ? "正确" : "答案"}：${escapeHtml(result.word)}
      <span class="muted"> ${escapeHtml(result.chinese_meaning)}</span>
      <span class="muted"> 熟练度 ${result.proficiency}/10</span>
    </div>
    <div>${escapeHtml(result.sentence)}</div>
    ${
      result.correct
        ? ""
        : `<div class="full-sentence">你填的是：${escapeHtml(result.typed || "")}</div>`
    }
  `;
}

async function checkCurrent(event) {
  event.preventDefault();
  const question = state.questions[state.index];
  const typed = el.answerInput.value.trim();
  if (!typed) {
    toast("先填一个答案。");
    el.answerInput.focus();
    return;
  }

  setBusy(el.checkBtn, true);
  try {
    const result = await api("/api/practice/check", {
      method: "POST",
      body: JSON.stringify({
        example_id: question.example_id,
        answer: typed,
        visible_prefix: question.visible_prefix,
      }),
    });
    state.answers.set(question.example_id, { ...result, typed });
    await loadWords();
    renderQuestion();
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(el.checkBtn, false);
  }
}

function updateAnswerPreview() {
  const question = currentQuestion();
  if (!question || state.answers.has(question.example_id)) {
    return;
  }
  renderMaskedSentence(question, el.answerInput.value);
}

function handlePracticeEnter(event) {
  if (
    event.key !== "Enter" ||
    event.altKey ||
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey ||
    el.questionCard.classList.contains("hidden")
  ) {
    return;
  }

  const question = currentQuestion();
  if (!question || !state.answers.has(question.example_id)) {
    return;
  }

  const active = document.activeElement;
  if (active && active.closest && !active.closest(".practice-pane")) {
    return;
  }

  event.preventDefault();
  go(1);
}

function go(delta) {
  if (!state.questions.length) {
    return;
  }
  const next = state.index + delta;
  if (next >= state.questions.length) {
    const right = [...state.answers.values()].filter((item) => item.correct).length;
    toast(`本轮 ${right} / ${state.questions.length} 正确。`);
    return;
  }
  state.index = Math.max(0, next);
  renderQuestion();
}

async function deleteWord(row) {
  const word = row.querySelector(".word-main").textContent;
  if (!window.confirm(`删除 ${word}？`)) {
    return;
  }
  try {
    await api(`/api/words/${row.dataset.id}`, { method: "DELETE" });
    await Promise.all([loadStatus(), loadWords()]);
    toast("已删除。");
  } catch (error) {
    toast(error.message);
  }
}

function bindEvents() {
  el.generateBtn.addEventListener("click", generateWords);
  el.refreshBtn.addEventListener("click", async () => {
    await Promise.all([loadStatus(), loadWords()]);
    toast("词本已刷新。");
  });
  el.modeBtns.forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      el.modeBtns.forEach((item) => item.classList.toggle("active", item === button));
    });
  });
  el.startPracticeBtn.addEventListener("click", startPracticeRound);
  el.answerForm.addEventListener("submit", checkCurrent);
  el.answerInput.addEventListener("input", updateAnswerPreview);
  el.prevBtn.addEventListener("click", () => go(-1));
  el.nextBtn.addEventListener("click", () => go(1));
  document.addEventListener("keydown", handlePracticeEnter);
  el.wordList.addEventListener("click", (event) => {
    const button = event.target.closest(".delete-btn");
    if (button) {
      deleteWord(button.closest(".word-row"));
    }
  });
}

async function boot() {
  bindEvents();
  try {
    await Promise.all([loadStatus(), loadWords()]);
  } catch (error) {
    toast(error.message);
  }
}

boot();
