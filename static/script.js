let currentPage = 1;
const perPage = 12;
let totalPages = 1;

// Create skeleton loading cards
function createSkeletonCards() {
  const skeletonGrid = document.querySelector(".skeleton-grid");
  skeletonGrid.innerHTML = "";

  for (let i = 0; i < 8; i++) {
    const card = document.createElement("div");
    card.className = `skeleton-card stagger-${(i % 4) + 1}`;
    card.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <div class="skeleton" style="height: 1.5rem; width: 8rem;"></div>
            <div class="skeleton" style="height: 0.75rem; width: 0.75rem; border-radius: 50%;"></div>
          </div>
          <div style="margin-bottom: 1rem;">
            <div class="skeleton" style="height: 1rem; width: 4rem; margin-bottom: 0.75rem;"></div>
            <div class="skeleton" style="height: 1rem; width: 5rem;"></div>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem;">
            <div class="skeleton" style="height: 2rem; border-radius: 0.5rem;"></div>
            <div class="skeleton" style="height: 2rem; border-radius: 0.5rem;"></div>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem;">
            <div class="skeleton" style="height: 2rem; border-radius: 0.5rem;"></div>
            <div class="skeleton" style="height: 2rem; border-radius: 0.5rem;"></div>
          </div>
        `;
    skeletonGrid.appendChild(card);
  }
}

// Show loading state
function showLoading() {
  document.getElementById("loading").style.display = "block";
  document.getElementById("error").style.display = "none";
  document.getElementById("users-grid").style.display = "none";
  document.getElementById("pagination").style.display = "none";
  createSkeletonCards();
}

// Show error state
function showError(message) {
  document.getElementById("loading").style.display = "none";
  document.getElementById("error").style.display = "block";
  document.getElementById("users-grid").style.display = "none";
  document.getElementById("pagination").style.display = "none";
  document.getElementById("error-message").textContent = message;
}

// Show users grid
function showUsers() {
  document.getElementById("loading").style.display = "none";
  document.getElementById("error").style.display = "none";
  document.getElementById("users-grid").style.display = "grid";
  document.getElementById("pagination").style.display = "flex";
}

// Create user card - updated so only username text is clickable
function createUserCard(user, index) {
  const profileUrl = `https://leetcode.com/${encodeURIComponent(user.username)}/`;

  // --- Improvement Trend rendering (INLINE, no IDs, no DOM ops) ---
  function trendRow(label, trend) {
    if (!trend) {
      return `<span style="color:gray">${label}: N/A</span>`;
    }

    const sign = trend.delta > 0 ? "+" : "";
    let color = "gray";

    if (trend.status === "improving") color = "green";
    else if (trend.status === "declining") color = "red";

    return `
      <span style="color:${color}; font-weight:600">
        ${label}: ${sign}${trend.delta} (${trend.status})
      </span>
    `;
  }
  // ---------------------------------------------------------------

  return `
  <div class="stats-card stagger-${(index % 4) + 1}">
    <div class="card-header">
      <h3 class="card-title">
        <a href="${profileUrl}" target="_blank" rel="noopener noreferrer" class="username-link">
          ${user.username}
        </a>
      </h3>
      <div class="card-indicator"></div>
    </div>
    
    <div class="card-stats">
      <div class="stat-row">
        <span class="stat-label">Ranking:</span>
        <span class="stat-value">${user.ranking ? `#${user.ranking.toLocaleString()}` : "N/A"}</span>
      </div>

      <div class="stat-row">
        <span class="stat-label">Reputation:</span>
        <span class="stat-value">${user.reputation ? user.reputation.toLocaleString() : "N/A"}</span>
      </div>

      <div class="stat-row">
        <span class="stat-label">Placement Score:</span>
        <span class="stat-value">${user.placement_score ?? 0}</span>
      </div>

      <div class="stat-row">
        <span class="stat-label">Status:</span>
        <span class="stat-value" style="color:${user.placement_color || "gray"}">
          ${user.placement_level || "N/A"}
        </span>
      </div>

      <div class="stat-row">
        <span class="stat-label">Activity:</span>
        <span class="stat-value" style="color:${user.activity_color || "gray"}">
          ${user.activity_icon || ""} ${user.activity_status || "Dormant"}
        </span>
      </div>

      <div class="stat-row">
        <span class="stat-label">Last Solved:</span>
        <span class="stat-value">${user.last_solved_text || "Never"}</span>
      </div>
    </div>

    <div class="stat-row">
      <span class="stat-label">Streak:</span>
      <span class="stat-value">🔥 ${user.streak || 0} Days</span>
    </div>

    <!-- 🔥 Improvement Trend (FINAL) -->
    <div class="trend-box">
      <div class="trend-title">📈 Improvement Trend</div>
      <div class="trend-row">
        ${trendRow("7 Days", user.user_trend?.["7d"])}
      </div>
      <div class="trend-row">
        ${trendRow("30 Days", user.user_trend?.["30d"])}
      </div>
    </div>

    <div class="badges-grid">
      <div class="difficulty-badge badge-easy">
        <span>🟢 Easy</span>
        <span>${user.easy}</span>
      </div>
      <div class="difficulty-badge badge-medium">
        <span>🟡 Medium</span>
        <span>${user.medium}</span>
      </div>
      <div class="difficulty-badge badge-hard">
        <span>🔴 Hard</span>
        <span>${user.hard}</span>
      </div>
      <div class="difficulty-badge badge-total">
        <span>✅ Solved (AC)</span>
        <span>${user.total}</span>
      </div>

    </div>

    <div style="margin-top:12px;">
      <div style="background:#222; height:6px; border-radius:6px; overflow:hidden;">
        <div style="
          width:${Math.min((user.placement_score || 0) / 10, 100)}%;
          height:6px;
          background:${user.placement_color || "#555"};
          transition:width 0.4s ease;
        "></div>
      </div>
    </div>
  </div>
  `;
}

// Load users from API (standard)
async function loadUsers(page = 1) {
  showLoading();
  currentPage = page;

  try {
    const response = await fetch(`/api/users?page=${page}&per_page=${perPage}`);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    if (data.users.length === 0 && page === 1) {
      showError("No users found. Upload some via Admin!");
      return;
    }

    renderUsersFromData(data, page);
  } catch (err) {
    console.error("Error loading users:", err);
    showError(
      "Failed to load users. Please check your connection and try again.",
    );
  }
}

// Render users given data object (shared by loadUsers and refreshCurrentPage)
function renderUsersFromData(data, page) {
  // Render users
  const usersGrid = document.getElementById("users-grid");
  usersGrid.innerHTML = data.users
    .map((user, index) => createUserCard(user, index))
    .join("");

  totalPages = data.total_pages || 1;
  renderPagination(totalPages, page);
  showUsers();
}

// Render pagination
function renderPagination(totalPagesLocal, current) {
  const pagination = document.getElementById("pagination");

  if (totalPagesLocal <= 1) {
    pagination.style.display = "none";
    return;
  }

  // Generate visible pages
  const getVisiblePages = () => {
    const delta = 2;
    const range = [];
    const rangeWithDots = [];

    for (
      let i = Math.max(2, current - delta);
      i <= Math.min(totalPagesLocal - 1, current + delta);
      i++
    ) {
      range.push(i);
    }

    if (current - delta > 2) {
      rangeWithDots.push(1, "...");
    } else {
      rangeWithDots.push(1);
    }

    rangeWithDots.push(...range);

    if (current + delta < totalPagesLocal - 1) {
      rangeWithDots.push("...", totalPagesLocal);
    } else if (totalPagesLocal > 1) {
      rangeWithDots.push(totalPagesLocal);
    }

    return rangeWithDots;
  };

  const visiblePages = getVisiblePages();

  let html = `
        <button class="page-btn" onclick="loadUsers(${current - 1})" ${
          current === 1 ? "disabled" : ""
        }>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15,18 9,12 15,6"></polyline>
          </svg>
          Previous
        </button>
      `;

  visiblePages.forEach((page) => {
    if (page === "...") {
      html +=
        '<span style="padding: 0.75rem; color: var(--muted-foreground);">...</span>';
    } else {
      html += `
            <button class="page-btn ${page === current ? "active" : ""}" 
                    onclick="loadUsers(${page})">${page}</button>
          `;
    }
  });

  html += `
        <button class="page-btn" onclick="loadUsers(${current + 1})" ${
          current === totalPagesLocal ? "disabled" : ""
        }>
          Next
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9,18 15,12 9,6"></polyline>
          </svg>
        </button>
      `;

  pagination.innerHTML = html;
  pagination.style.display = "flex";
}

// Page change handler with smooth scroll
function changePage(page) {
  if (page >= 1 && page <= totalPages && page !== currentPage) {
    loadUsers(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

// --- New: Refresh Current Page (live) ---
// Calls API with live=1 for the current page and re-renders results.
async function refreshCurrentPage() {
  // show a minimal loading UI
  showLoading();

  try {
    const res = await fetch(
      `/api/users?page=${currentPage}&per_page=${perPage}&live=1`,
    );

    if (!res.ok) {
      throw new Error(`HTTP error! status: ${res.status}`);
    }

    const data = await res.json();

    if (!data || !Array.isArray(data.users)) {
      throw new Error("Unexpected response from server");
    }

    renderUsersFromData(data, currentPage);
  } catch (err) {
    console.error("Error refreshing current page:", err);
    showError("Failed to refresh current page. " + err.message);
  }
}

// --- New: Refresh All Users Now ---
// Triggers backend POST /admin/refresh_now and gives user feedback.
async function refreshNow() {
  if (!confirm("Refresh ALL users now? This may take some time.")) return;

  // temporarily show loading state in grid
  const usersGrid = document.getElementById("users-grid");
  usersGrid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding: 2rem;">
          <div class="loading-spinner" style="display:inline-flex;">
            <div class="spinner"></div>
            <span style="margin-left: 0.5rem;">Starting full refresh...</span>
          </div>
        </div>`;
  document.getElementById("loading").style.display = "none";
  document.getElementById("error").style.display = "none";
  document.getElementById("users-grid").style.display = "grid";
  document.getElementById("pagination").style.display = "none";

  try {
    const res = await fetch("/admin/refresh_now", { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      alert("✅ Refresh started. Data will update shortly.");
      // try to reload users after a short delay to show updated state
      setTimeout(() => loadUsers(currentPage), 5000);
    } else {
      alert("❌ Failed to start refresh: " + (data.error || "Unknown error"));
      // restore by loading current page normally
      loadUsers(currentPage);
    }
  } catch (err) {
    alert("⚠️ Error starting refresh: " + err.message);
    loadUsers(currentPage);
  }
}

// Initialize app
document.addEventListener("DOMContentLoaded", () => {
  loadUsers(1);
});
