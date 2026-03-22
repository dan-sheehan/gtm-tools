/* Morning Brief – client-side rendering */

(function () {
  const PREFIX = window.APP_PREFIX || "";

  // -----------------------------------------------------------------------
  // Fetch & render
  // -----------------------------------------------------------------------

  async function loadBrief() {
    try {
      const res = await fetch(`${PREFIX}/api/brief`);
      const data = await res.json();

      if (data.error && !data.generated_at) {
        showError(data.error);
        return;
      }
      hideError();
      renderTimestamp(data.generated_at);
      renderWeather(data.weather);
      renderCalendar(data.calendar);
      renderEmails(data.emails);
      renderTasks(data.tasks);
    } catch (err) {
      showError("Failed to load brief data.");
    }
  }

  // -----------------------------------------------------------------------
  // Timestamp
  // -----------------------------------------------------------------------

  function renderTimestamp(ts) {
    const el = document.getElementById("timestamp");
    if (!ts) { el.textContent = ""; return; }
    const d = new Date(ts);
    el.textContent = d.toLocaleDateString("en-US", {
      weekday: "short", month: "short", day: "numeric",
    }) + " at " + d.toLocaleTimeString("en-US", {
      hour: "numeric", minute: "2-digit",
    });
  }

  // -----------------------------------------------------------------------
  // Weather
  // -----------------------------------------------------------------------

  function renderWeather(weather) {
    const body = document.querySelector("#weather-card .card-body");
    if (!weather || weather.error) {
      body.innerHTML = `<div class="unavailable">${esc(weather?.error || "Weather unavailable")}</div>`;
      return;
    }
    body.className = "card-body";
    body.innerHTML = `
      <div class="weather-main">
        <div class="weather-temp">${esc(String(weather.temp_f))}&deg;F</div>
        <div class="weather-condition">${esc(weather.condition)}</div>
      </div>
      <div class="weather-details">
        <span>H: ${esc(String(weather.high_f))}&deg;</span>
        <span>L: ${esc(String(weather.low_f))}&deg;</span>
        <span>Sunset: ${esc(weather.sunset)}</span>
        <span>${esc(weather.location)}</span>
      </div>`;
  }

  // -----------------------------------------------------------------------
  // Calendar
  // -----------------------------------------------------------------------

  function renderCalendar(events) {
    const body = document.querySelector("#calendar-card .card-body");
    if (!events || events.error) {
      body.innerHTML = `<div class="unavailable">${esc(events?.error || "Calendar unavailable")}</div>`;
      return;
    }
    if (events.length === 0) {
      body.innerHTML = `<div class="unavailable">No events today</div>`;
      return;
    }
    body.className = "card-body";
    const items = events.map(ev => {
      const link = ev.video_link
        ? `<a class="event-link" href="${esc(ev.video_link)}" target="_blank" rel="noopener">Join</a>`
        : "";
      return `<li class="event-item">
        <span class="event-time">${esc(ev.time)}</span>
        <span class="event-title">${esc(ev.title)}</span>
        ${link}
      </li>`;
    }).join("");
    body.innerHTML = `<ul class="event-list">${items}</ul>`;
  }

  // -----------------------------------------------------------------------
  // Emails
  // -----------------------------------------------------------------------

  function renderEmails(emails) {
    const body = document.querySelector("#email-card .card-body");
    if (!emails || emails.error) {
      body.innerHTML = `<div class="unavailable">${esc(emails?.error || "Email unavailable")}</div>`;
      return;
    }
    if (emails.length === 0) {
      body.innerHTML = `<div class="unavailable">No unread emails</div>`;
      return;
    }
    body.className = "card-body";
    const items = emails.map(em => `
      <li class="email-item">
        <div class="email-header">
          <span class="email-from">${esc(em.from)}</span>
        </div>
        <div class="email-subject">${esc(em.subject)}</div>
        ${em.summary ? `<div class="email-summary">${esc(em.summary)}</div>` : ""}
      </li>`
    ).join("");
    body.innerHTML = `<ul class="email-list">${items}</ul>`;
  }

  // -----------------------------------------------------------------------
  // Tasks
  // -----------------------------------------------------------------------

  function renderTasks(tasks) {
    const body = document.querySelector("#tasks-card .card-body");
    if (!tasks || tasks.error) {
      body.innerHTML = `<div class="unavailable">${esc(tasks?.error || "Tasks unavailable")}</div>`;
      return;
    }
    if (tasks.length === 0) {
      body.innerHTML = `<div class="unavailable">No tasks due today</div>`;
      return;
    }
    body.className = "card-body";
    const items = tasks.map(t => {
      const priorityClass = t.priority
        ? `badge-priority-${t.priority.toLowerCase()}`
        : "";
      const badges = [
        t.status ? `<span class="badge badge-status">${esc(t.status)}</span>` : "",
        t.priority ? `<span class="badge ${priorityClass}">${esc(t.priority)}</span>` : "",
        t.project ? `<span class="badge badge-project">${esc(t.project)}</span>` : "",
      ].filter(Boolean).join(" ");
      return `<li class="task-item">
        <span class="task-title">${esc(t.title)}</span>
        ${badges}
      </li>`;
    }).join("");
    body.innerHTML = `<ul class="task-list">${items}</ul>`;
  }

  // -----------------------------------------------------------------------
  // Error banner
  // -----------------------------------------------------------------------

  function showError(msg) {
    const el = document.getElementById("error-banner");
    el.textContent = msg;
    el.style.display = "block";
  }

  function hideError() {
    document.getElementById("error-banner").style.display = "none";
  }

  // -----------------------------------------------------------------------
  // Escape HTML
  // -----------------------------------------------------------------------

  function esc(str) {
    if (!str) return "";
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // -----------------------------------------------------------------------
  // Refresh button
  // -----------------------------------------------------------------------

  function setupRefresh() {
    const btn = document.getElementById("refresh-btn");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Refreshing...";

      try {
        await fetch(`${PREFIX}/api/refresh`, { method: "POST" });
      } catch {
        btn.textContent = "Refresh";
        btn.disabled = false;
        return;
      }

      // Poll for updated data (fetch.sh takes ~30-60s)
      const originalTs = document.getElementById("timestamp").textContent;
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const res = await fetch(`${PREFIX}/api/brief`);
          const data = await res.json();
          const newTs = data.generated_at || "";
          if (newTs && newTs !== originalTs || attempts > 24) {
            clearInterval(poll);
            btn.textContent = "Refresh";
            btn.disabled = false;
            if (data.generated_at) {
              hideError();
              renderTimestamp(data.generated_at);
              renderWeather(data.weather);
              renderCalendar(data.calendar);
              renderEmails(data.emails);
              renderTasks(data.tasks);
            }
          }
        } catch {
          // keep polling
        }
      }, 5000);
    });
  }

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", () => {
    loadBrief();
    setupRefresh();
  });
})();
