let allLogs = [];
let filteredLogs = [];
let currentFilter = "ALL";
let currentSearch = "";

const searchInput = document.getElementById("searchInput");
const clearSearchBtn = document.getElementById("clearSearchBtn");
const refreshBtn = document.getElementById("refreshBtn");
const clearLogsBtn = document.getElementById("clearLogsBtn");
const filterButtons = document.querySelectorAll(".filter-btn");
const logsContainer = document.getElementById("logsContainer");
const emptyState = document.getElementById("emptyState");
const totalLogsSpan = document.getElementById("totalLogs");
const visibleLogsSpan = document.getElementById("visibleLogs");
const lastUpdateTimeSpan = document.getElementById("lastUpdateTime");

searchInput.addEventListener("input", handleSearch);
clearSearchBtn.addEventListener("click", clearSearch);
refreshBtn.addEventListener("click", loadAndDisplayLogs);
clearLogsBtn.addEventListener("click", clearAllLogs);

filterButtons.forEach(btn => {
  btn.addEventListener("click", function() {
    filterButtons.forEach(b => b.classList.remove("active"));
    this.classList.add("active");
    currentFilter = this.dataset.filter;
    applyFiltersAndDisplay();
  });
});

function getLogType(line) {
  if (line.includes("USER:")) return "USER";
  if (line.includes("ERROR") || line.includes("Error")) return "ERROR";
  if (line.includes("LLM")) return "LLM";
  if (line.includes("TOOL")) return "TOOL";
  return "INFO";
}

function parseLogs(logText) {
  return logText.split("\n")
    .filter(line => line.trim().length > 0)
    .map(line => ({
      text: line,
      type: getLogType(line),
      timestamp: extractTimestamp(line)
    }));
}

function extractTimestamp(line) {
  const match = line.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
  return match ? match[1] : "---";
}

function createLogCard(log) {
  const card = document.createElement("div");
  card.className = `log-card log-${log.type}`;
  
  card.innerHTML = `
    <div class="log-header">
      <span class="log-type-badge">${log.type}</span>
      <span class="log-timestamp">${log.timestamp}</span>
    </div>
    <div class="log-content">
      ${escapeHtml(log.text)}
    </div>
  `;
  
  return card;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function handleSearch(e) {
  currentSearch = e.target.value.toLowerCase();
  applyFiltersAndDisplay();
}

function clearSearch() {
  searchInput.value = "";
  currentSearch = "";
  applyFiltersAndDisplay();
}

function clearAllLogs() {
  const confirmed = confirm("هل أنت متأكد من رغبتك في حذف جميع السجلات؟\nهذا الإجراء لا يمكن التراجع عنه!");
  if (!confirmed) return;
  
  clearLogsBtn.disabled = true;
  clearLogsBtn.textContent = "جاري الحذف...";
  
  fetch("/clear_logs", {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  })
    .then(response => {
      if (!response.ok) throw new Error("Failed to clear logs");
      return response.json();
    })
    .then(data => {
      if (data.status === "success") {
        allLogs = [];
        filteredLogs = [];
        currentSearch = "";
        currentFilter = "ALL";
        searchInput.value = "";
        displayLogs();
        updateStats();
        updateLastUpdateTime();
      }
    })
    .catch(error => {
      console.error("Error clearing logs:", error);
      alert("خطأ في حذف السجلات: " + error.message);
    })
    .finally(() => {
      clearLogsBtn.disabled = false;
      clearLogsBtn.textContent = "🗑️ حذف السجلات";
    });
}

function applyFiltersAndDisplay() {
  filteredLogs = allLogs.filter(log => {
    const matchesFilter = currentFilter === "ALL" || log.type === currentFilter;
    const matchesSearch = currentSearch === "" || log.text.toLowerCase().includes(currentSearch);
    return matchesFilter && matchesSearch;
  });

  displayLogs();
  updateStats();
}

function displayLogs() {
  logsContainer.innerHTML = "";
  if (filteredLogs.length === 0) {
    emptyState.style.display = "flex";
    return;
  }
  emptyState.style.display = "none";
  
  filteredLogs.forEach(log => {
    logsContainer.appendChild(createLogCard(log));
  });
  logsContainer.scrollTop = logsContainer.scrollHeight;
}

function updateStats() {
  totalLogsSpan.textContent = allLogs.length;
  visibleLogsSpan.textContent = filteredLogs.length;
}

function updateLastUpdateTime() {
  const now = new Date();
  const timeStr = now.toLocaleString("ar-SA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
  lastUpdateTimeSpan.textContent = timeStr;
}

function loadAndDisplayLogs() {
  fetch("/logs")
    .then(response => {
      if (!response.ok) throw new Error("Failed to fetch logs");
      return response.json();
    })
    .then(data => {
      allLogs = parseLogs(data.logs || "");
      currentSearch = "";
      currentFilter = "ALL";
      searchInput.value = "";
      filterButtons.forEach(b => b.classList.remove("active"));
      filterButtons[0].classList.add("active");
      applyFiltersAndDisplay();
      updateLastUpdateTime();
    })
    .catch(error => {
      console.error("Error loading logs:", error);
      emptyState.innerHTML = `<p>خطأ في تحميل السجلات: ${error.message}</p>`;
      emptyState.style.display = "flex";
    });
}

document.addEventListener("DOMContentLoaded", loadAndDisplayLogs);
setInterval(loadAndDisplayLogs, 5000);
