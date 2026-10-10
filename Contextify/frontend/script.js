// Set to true to preview the page with built-in sample data (no backend needed).
const USE_SAMPLE = false;
const API_URL = "http://localhost:5000/analyze";

// Built-in copy of sample_result.json so the page works by double-clicking index.html.
const SAMPLE = {
  claim: "",
  status: "Already fact-checked",
  summary:
    "Fact-checkers have already rated this claim false. No clinical evidence shows lemon water cures cancer. Indian, US and UK outlets report the same message as a recycled health hoax.",
  sources: [
    {
      title: "No, lemon water does not cure cancer",
      link: "https://www.altnews.in/",
      source_name: "Alt News",
      date: "2025-03-12",
      snippet:
        "A viral forward claims lemon water cures cancer. Experts say there is no such evidence.",
      region: "India",
    },
    {
      title: "Health hoax resurfaces on social media",
      link: "https://www.boomlive.in/",
      source_name: "BOOM",
      date: "2025-04-02",
      snippet:
        "The same message has circulated for years with different names attached.",
    },
  ],
  red_flags: [
    "Promises a miracle cure",
    "No named doctor or study",
    "Asks you to forward to everyone",
  ],
  reply_message:
    "Hi, I checked this forward. Fact-checkers have already rated it false, and there is no evidence lemon water cures cancer. Please don't rely on it. Sources: Alt News, BOOM.",
};

const $ = (id) => document.getElementById(id);
const views = ["input-view", "loading-view", "error-view", "result-view"];
const STATUS = {
  "Already fact-checked": [
    "s-fact",
    "Fact-checkers have already reviewed this.",
  ],
  Corroborated: ["s-corr", "Trusted outlets report the same thing."],
  Disputed: ["s-disp", "Sources disagree about this."],
  "No evidence found": [
    "s-none",
    "We found nothing either way. Treat it with care.",
  ],
};
let timer = null;

function show(id) {
  views.forEach((v) => ($(v).hidden = v !== id));
}

function runSteps() {
  const items = [...$("steps").children];
  let i = 0;
  items.forEach((li) => (li.className = ""));
  items[0].className = "active";
  timer = setInterval(() => {
    if (i < items.length - 1) {
      items[i].className = "done";
      i++;
      items[i].className = "active";
    }
  }, 1800);
}

async function getResult(claim) {
  if (USE_SAMPLE) {
    await new Promise((r) => setTimeout(r, 4000));
    return { ...SAMPLE, claim };
  }
  const res = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim }),
  });
  if (!res.ok) {
    // show the backend's own message when it sends one
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || "Server returned " + res.status);
  }
  return res.json();
}

async function check() {
  const claim = $("claim").value.trim();
  if (!claim) {
    $("claim").focus();
    return;
  }
  show("loading-view");
  runSteps();
  try {
    render(await getResult(claim));
  } catch (e) {
    $("error-text").textContent =
      "We could not get a result (" +
      e.message +
      "). Check that the backend is running, then try again.";
    show("error-view");
  } finally {
    clearInterval(timer);
  }
}

function render(r) {
  const [cls, note] = STATUS[r.status] || STATUS["No evidence found"];
  $("badge").className = "badge " + cls;
  $("badge").textContent = r.status;
  const small = document.createElement("small");
  small.textContent = note;
  $("badge").appendChild(small);
  $("demo-note").hidden = !USE_SAMPLE;
  $("claim-echo").textContent = r.claim || "";
  $("summary").textContent = r.summary || "";
  $("reply").textContent = r.reply_message || "";

  const src = $("sources");
  src.innerHTML = "";
  const list = r.sources || [];
  if (!list.length) src.innerHTML = "<li>No sources found for this claim.</li>";
  list.forEach((s) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.textContent = s.title || s.link;
    if (/^https?:\/\//.test(s.link || "")) {
      a.href = s.link;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    }
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = [s.source_name || s.source, s.date]
      .filter(Boolean)
      .join(", ");
    if (s.region) {
      const t = document.createElement("span");
      t.className = "tag";
      t.textContent = s.region;
      meta.appendChild(t);
    }
    const sn = document.createElement("p");
    sn.textContent = s.snippet || "";
    li.append(a, meta, sn);
    src.appendChild(li);
  });

  const fl = $("flags");
  fl.innerHTML = "";
  const flags = r.red_flags || [];
  if (!flags.length) fl.innerHTML = "<li>No red flags spotted.</li>";
  flags.forEach((f) => {
    const li = document.createElement("li");
    li.textContent = f;
    fl.appendChild(li);
  });
  show("result-view");
}

$("check-btn").onclick = check;
$("retry-btn").onclick = check;
$("again-btn").onclick = () => {
  $("claim").value = "";
  show("input-view");
};
document.querySelectorAll(".chip").forEach(
  (c) =>
    (c.onclick = () => {
      $("claim").value = c.dataset.text;
    })
);
$("copy-btn").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("reply").textContent);
    $("copy-btn").textContent = "Copied";
  } catch {
    $("copy-btn").textContent = "Select and copy manually";
  }
  setTimeout(() => ($("copy-btn").textContent = "Copy reply"), 2000);
};
