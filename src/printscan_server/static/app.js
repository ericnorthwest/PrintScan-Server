const loginView = document.getElementById("loginView");
const dashboardView = document.getElementById("dashboardView");
const logoutButton = document.getElementById("logoutButton");
const loginForm = document.getElementById("loginForm");
const loginMessage = document.getElementById("loginMessage");
const printForm = document.getElementById("printForm");
const printMessage = document.getElementById("printMessage");
const printerSelect = document.getElementById("printerSelect");
const printButton = document.getElementById("printButton");
let csrfToken = "";

function showMessage(element, text, kind) {
  element.textContent = text || "";
  element.className = "message" + (kind ? " " + kind : "");
}

async function api(path, options) {
  const requestOptions = options || {};
  requestOptions.credentials = "same-origin";
  requestOptions.headers = requestOptions.headers || {};
  const response = await fetch(path, requestOptions);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : { detail: await response.text() };
  if (!response.ok) throw new Error(payload.detail || "Request failed");
  return payload;
}

function showDashboard(user) {
  loginView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  logoutButton.classList.remove("hidden");
  document.getElementById("versionLabel").textContent = "Signed in as " + user.username;
}

function showLogin() {
  csrfToken = "";
  dashboardView.classList.add("hidden");
  logoutButton.classList.add("hidden");
  loginView.classList.remove("hidden");
}

async function refreshDevices() {
  const printerSummary = document.getElementById("printerSummary");
  const printerList = document.getElementById("printerList");
  const scannerSummary = document.getElementById("scannerSummary");
  const scannerList = document.getElementById("scannerList");
  printerSummary.textContent = "Checking CUPS…";
  printerList.replaceChildren();
  printerSelect.replaceChildren();
  try {
    const data = await api("/api/v1/printers");
    const printers = data.printers || [];
    printerSummary.textContent = printers.length ? printers.length + " printer queue(s) found" : "No configured CUPS queues";
    for (const printer of printers) {
      const item = document.createElement("li");
      item.textContent = printer.name + " — " + printer.state;
      printerList.appendChild(item);
      const option = document.createElement("option");
      option.value = printer.name; option.textContent = printer.name;
      printerSelect.appendChild(option);
    }
    if (data.default_printer) printerSelect.value = data.default_printer;
    if (!printers.length) {
      const option = document.createElement("option");
      option.value = ""; option.textContent = "No printer available";
      printerSelect.appendChild(option);
    }
    printButton.disabled = printers.length === 0;
  } catch (error) {
    printerSummary.textContent = error.message;
    printButton.disabled = true;
  }
  scannerSummary.textContent = "Checking SANE…";
  scannerList.replaceChildren();
  try {
    const data = await api("/api/v1/scanners");
    const scanners = data.scanners || [];
    scannerSummary.textContent = scanners.length ? scanners.length + " scanner(s) found" : "No SANE scanners found";
    for (const scanner of scanners) {
      const item = document.createElement("li");
      item.textContent = scanner.model + " (" + scanner.name + ")";
      scannerList.appendChild(item);
    }
    if (data.note) {
      const item = document.createElement("li"); item.textContent = data.note;
      scannerList.appendChild(item);
    }
  } catch (error) {
    scannerSummary.textContent = error.message;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showMessage(loginMessage, "Signing in…");
  const form = new FormData(loginForm);
  try {
    const result = await api("/api/v1/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: form.get("username"), password: form.get("password") })
    });
    csrfToken = result.csrf_token;
    showDashboard(result);
    loginForm.reset();
    await refreshDevices();
  } catch (error) {
    showMessage(loginMessage, error.message, "error");
  }
});

logoutButton.addEventListener("click", async () => {
  try {
    await api("/api/v1/auth/logout", { method: "POST", headers: { "X-CSRF-Token": csrfToken } });
  } catch (error) { /* Expired sessions are cleared locally too. */ }
  showLogin();
});

document.getElementById("refreshButton").addEventListener("click", refreshDevices);
printForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showMessage(printMessage, "Submitting document…");
  printButton.disabled = true;
  try {
    const result = await api("/api/v1/print", {
      method: "POST", headers: { "X-CSRF-Token": csrfToken }, body: new FormData(printForm)
    });
    showMessage(printMessage, result.message || "Print job submitted.", "success");
    printForm.reset();
  } catch (error) {
    showMessage(printMessage, error.message, "error");
  } finally {
    printButton.disabled = !printerSelect.value;
  }
});

async function bootstrap() {
  try {
    const user = await api("/api/v1/auth/me");
    csrfToken = user.csrf_token;
    showDashboard(user);
    await refreshDevices();
  } catch (error) { showLogin(); }
}
bootstrap();
