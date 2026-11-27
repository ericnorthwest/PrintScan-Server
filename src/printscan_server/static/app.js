const loginView = document.getElementById("loginView");
const dashboardView = document.getElementById("dashboardView");
const loginForm = document.getElementById("loginForm");
const loginMessage = document.getElementById("loginMessage");
const logoutButton = document.getElementById("logoutButton");
const userLabel = document.getElementById("userLabel");
const scannerSelect = document.getElementById("scannerSelect");
const scannerStatus = document.getElementById("scannerStatus");
const modeSelect = document.getElementById("modeSelect");
const sourceSelect = document.getElementById("sourceSelect");
const resolutionField = document.getElementById("resolutionField");
const formatSelect = document.getElementById("formatSelect");
const scanButton = document.getElementById("scanButton");
const cancelButton = document.getElementById("cancelButton");
const scanStatus = document.getElementById("scanStatus");
const progressBar = document.getElementById("progressBar");
const progressLabel = document.getElementById("progressLabel");
const previewCanvas = document.getElementById("previewCanvas");
const emptyPreview = document.getElementById("emptyPreview");
const downloadButton = document.getElementById("downloadButton");
const previewNote = document.getElementById("previewNote");

let csrfToken = "";
let activeSocket = null;
let scannerOptions = {};
let isScanning = false;

function message(element, value, kind) {
  element.textContent = value || "";
  element.className = "message" + (kind ? " " + kind : "");
}

async function api(path, options) {
  const request = options || {};
  request.credentials = "same-origin";
  request.headers = request.headers || {};
  const response = await fetch(path, request);
  const contentType = response.headers.get("content-type") || "";
  const result = contentType.includes("application/json")
    ? await response.json()
    : { detail: await response.text() };
  if (!response.ok) throw new Error(result.detail || "Ошибка запроса");
  return result;
}

function showLogin() {
  csrfToken = "";
  userLabel.classList.add("hidden");
  logoutButton.classList.add("hidden");
  dashboardView.classList.add("hidden");
  loginView.classList.remove("hidden");
}

function showDashboard(user) {
  loginView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  userLabel.textContent = user.username;
  userLabel.classList.remove("hidden");
  logoutButton.classList.remove("hidden");
}

function setSelect(select, values, selected, emptyLabel) {
  select.replaceChildren();
  if (!values || values.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = emptyLabel || "Нет доступных вариантов";
    select.appendChild(option);
    select.disabled = true;
    return;
  }
  for (const value of values) {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    select.appendChild(option);
  }
  select.value = String(selected ?? values[0]);
  select.disabled = false;
}

function setResolutionControl(spec) {
  resolutionField.replaceChildren();
  const label = document.createElement("label");
  label.textContent = "Разрешение";
  resolutionField.appendChild(label);

  if (!spec) {
    const input = document.createElement("input");
    input.type = "text";
    input.value = "Недоступно";
    input.disabled = true;
    resolutionField.appendChild(input);
    return;
  }

  if (spec.type === "range") {
    const input = document.createElement("input");
    input.id = "resolutionInput";
    input.type = "number";
    input.min = String(spec.minimum);
    input.max = String(spec.maximum);
    input.step = String(spec.step);
    input.value = String(spec.default);
    input.inputMode = "numeric";
    label.htmlFor = input.id;
    resolutionField.appendChild(input);
    const note = document.createElement("p");
    note.className = "field-note";
    note.textContent = spec.minimum + "–" + spec.maximum + " dpi · шаг " + spec.step;
    resolutionField.appendChild(note);
    return;
  }

  const select = document.createElement("select");
  select.id = "resolutionSelect";
  label.htmlFor = select.id;
  resolutionField.appendChild(select);
  setSelect(select, spec.values, spec.default);
}

async function loadScannerOptions(device) {
  scannerOptions = {};
  setSelect(modeSelect, [], null, "Не загружено");
  setSelect(sourceSelect, [], null, "Не загружено");
  setResolutionControl(null);
  scanButton.disabled = true;
  if (!device) return;

  scannerStatus.textContent = "Чтение параметров SANE…";
  try {
    const result = await api("/api/v1/scanners/options?device=" + encodeURIComponent(device));
    scannerOptions = result.options || {};
    const mode = scannerOptions.mode;
    const source = scannerOptions.source;
    setSelect(modeSelect, mode && mode.values, mode && mode.default, "Режимы не поддерживаются");
    setSelect(sourceSelect, source && source.values, source && source.default, "Источник не настраивается");
    setResolutionControl(scannerOptions.resolution || null);
    scannerStatus.textContent = "Параметры получены от SANE";
    scanButton.disabled = false;
    previewNote.textContent = "Показаны только параметры, которые сообщил драйвер выбранного сканера.";
  } catch (error) {
    scannerStatus.textContent = error.message;
    previewNote.textContent = "Не удалось получить настройки устройства.";
  }
}

async function refreshScanners() {
  scannerStatus.textContent = "Поиск устройств SANE…";
  scanButton.disabled = true;
  try {
    const result = await api("/api/v1/scanners");
    const scanners = result.scanners || [];
    scannerSelect.replaceChildren();
    for (const scanner of scanners) {
      const option = document.createElement("option");
      option.value = scanner.name;
      option.textContent = scanner.model + " · " + scanner.name;
      scannerSelect.appendChild(option);
    }
    if (!scanners.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "Сканеры не найдены";
      scannerSelect.appendChild(option);
      scannerSelect.disabled = true;
      scannerStatus.textContent = result.note || "SANE не обнаружил сканеры.";
      await loadScannerOptions("");
      return;
    }
    scannerSelect.disabled = false;
    scannerStatus.textContent = scanners.length + " · найдено";
    await loadScannerOptions(scannerSelect.value);
  } catch (error) {
    scannerStatus.textContent = error.message;
  }
}

function concatBytes(left, right) {
  const joined = new Uint8Array(left.length + right.length);
  joined.set(left, 0);
  joined.set(right, left.length);
  return joined;
}

function readPnmToken(bytes, position) {
  const whitespace = (value) => value === 9 || value === 10 || value === 11 ||
    value === 12 || value === 13 || value === 32;
  let index = position;

  while (index < bytes.length) {
    if (whitespace(bytes[index])) {
      index += 1;
      continue;
    }
    if (bytes[index] === 35) {
      while (index < bytes.length && bytes[index] !== 10) index += 1;
      continue;
    }
    break;
  }
  if (index >= bytes.length) return null;

  const start = index;
  while (index < bytes.length && !whitespace(bytes[index]) && bytes[index] !== 35) {
    index += 1;
  }
  if (index >= bytes.length) return null;

  const token = new TextDecoder().decode(bytes.subarray(start, index));
  if (bytes[index] === 13 && bytes[index + 1] === 10) index += 2;
  else index += 1;
  return { token, next: index };
}

function parsePnmHeader(bytes) {
  let position = 0;
  const tokens = [];
  const first = readPnmToken(bytes, position);
  if (!first) return null;
  tokens.push(first.token);
  position = first.next;

  const width = readPnmToken(bytes, position);
  if (!width) return null;
  tokens.push(width.token);
  position = width.next;

  const height = readPnmToken(bytes, position);
  if (!height) return null;
  tokens.push(height.token);
  position = height.next;

  const magic = tokens[0];
  if (magic !== "P4" && magic !== "P5" && magic !== "P6") {
    throw new Error("Сканер передал неподдерживаемый формат PNM: " + magic);
  }

  let maxValue = 1;
  if (magic !== "P4") {
    const maximum = readPnmToken(bytes, position);
    if (!maximum) return null;
    maxValue = Number(maximum.token);
    position = maximum.next;
  }

  const imageWidth = Number(tokens[1]);
  const imageHeight = Number(tokens[2]);
  if (!Number.isInteger(imageWidth) || !Number.isInteger(imageHeight) ||
      imageWidth < 1 || imageHeight < 1 || imageWidth * imageHeight > 120000000 ||
      !Number.isInteger(maxValue) || maxValue < 1 || maxValue > 65535) {
    throw new Error("Сканер передал некорректные размеры изображения.");
  }

  return {
    magic,
    width: imageWidth,
    height: imageHeight,
    maxValue,
    offset: position,
    channels: magic === "P6" ? 3 : 1,
    bytesPerSample: maxValue > 255 ? 2 : 1
  };
}

class PnmPreview {
  constructor(canvas, onProgress) {
    this.canvas = canvas;
    this.context = canvas.getContext("2d", { alpha: false });
    this.onProgress = onProgress;
    this.pending = new Uint8Array(0);
    this.header = null;
    this.sourceRow = 0;
    this.nextPreviewRow = 0;
    this.receivedPixels = 0;
    this.previewWidth = 0;
    this.previewHeight = 0;
  }

  push(chunk) {
    this.pending = concatBytes(this.pending, chunk);
    if (!this.header) {
      const header = parsePnmHeader(this.pending);
      if (!header) return;
      this.header = header;
      this.pending = this.pending.slice(header.offset);
      const scale = Math.min(1, 1500 / header.width, 2200 / header.height);
      this.previewWidth = Math.max(1, Math.round(header.width * scale));
      this.previewHeight = Math.max(1, Math.round(header.height * scale));
      this.canvas.width = this.previewWidth;
      this.canvas.height = this.previewHeight;
      this.canvas.classList.remove("hidden");
      emptyPreview.classList.add("hidden");
      scanStatus.textContent = header.width + " × " + header.height + " px";
    }

    const rowBytes = this.header.magic === "P4"
      ? Math.ceil(this.header.width / 8)
      : this.header.width * this.header.channels * this.header.bytesPerSample;

    while (this.pending.length >= rowBytes && this.sourceRow < this.header.height) {
      const row = this.pending.subarray(0, rowBytes);
      this.pending = this.pending.slice(rowBytes);
      this.drawSourceRow(row, this.sourceRow);
      this.sourceRow += 1;
      this.receivedPixels += rowBytes;
    }

    const total = rowBytes * this.header.height;
    const percent = Math.min(100, Math.floor((this.receivedPixels / total) * 100));
    this.onProgress(percent);
  }

  drawSourceRow(row, sourceY) {
    const destinationY = Math.floor(sourceY * this.previewHeight / this.header.height);
    if (destinationY < this.nextPreviewRow) return;

    while (this.nextPreviewRow <= destinationY && this.nextPreviewRow < this.previewHeight) {
      const line = this.context.createImageData(this.previewWidth, 1);
      const output = line.data;
      for (let x = 0; x < this.previewWidth; x += 1) {
        const sourceX = Math.min(
          this.header.width - 1,
          Math.floor((x + 0.5) * this.header.width / this.previewWidth)
        );
        let red;
        let green;
        let blue;

        if (this.header.magic === "P4") {
          const bit = (row[Math.floor(sourceX / 8)] >> (7 - (sourceX % 8))) & 1;
          red = green = blue = bit ? 0 : 255;
        } else {
          const sampleOffset = sourceX * this.header.channels * this.header.bytesPerSample;
          const readSample = (offset) => {
            if (this.header.bytesPerSample === 1) return row[offset];
            return (row[offset] << 8) | row[offset + 1];
          };
          const scale = (value) => Math.round(value * 255 / this.header.maxValue);
          red = scale(readSample(sampleOffset));
          if (this.header.channels === 3) {
            green = scale(readSample(sampleOffset + this.header.bytesPerSample));
            blue = scale(readSample(sampleOffset + this.header.bytesPerSample * 2));
          } else {
            green = blue = red;
          }
        }

        const offset = x * 4;
        output[offset] = red;
        output[offset + 1] = green;
        output[offset + 2] = blue;
        output[offset + 3] = 255;
      }
      this.context.putImageData(line, 0, this.nextPreviewRow);
      this.nextPreviewRow += 1;
    }
  }
}

function setProgress(percent, label) {
  progressBar.style.width = percent + "%";
  progressLabel.textContent = label;
}

function setScanning(value) {
  isScanning = value;
  scanButton.disabled = value || !scannerSelect.value;
  cancelButton.classList.toggle("hidden", !value);
  if (value) downloadButton.classList.add("hidden");
}

function startScan() {
  if (isScanning || !scannerSelect.value) return;
  const selectedMode = modeSelect.disabled ? null : modeSelect.value;
  const selectedSource = sourceSelect.disabled ? null : sourceSelect.value;
  const resolutionSelect = document.getElementById("resolutionSelect");
  const resolutionInput = document.getElementById("resolutionInput");
  const selectedResolution = resolutionSelect
    ? resolutionSelect.value
    : (resolutionInput ? resolutionInput.value : null);

  previewCanvas.classList.add("hidden");
  emptyPreview.classList.remove("hidden");
  downloadButton.classList.add("hidden");
  setProgress(0, "Подключение…");
  scanStatus.textContent = "Подключение к сканеру…";
  setScanning(true);

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socketUrl = protocol + "//" + window.location.host + "/api/v1/scans/stream";
  const socket = new WebSocket(socketUrl);
  socket.binaryType = "arraybuffer";
  activeSocket = socket;
  let finished = false;
  const decoder = new PnmPreview(previewCanvas, (percent) => {
    setProgress(percent, percent + "%");
    scanStatus.textContent = "Получение изображения…";
  });

  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({
      action: "start",
      csrf_token: csrfToken,
      device: scannerSelect.value,
      mode: selectedMode,
      source: selectedSource,
      resolution: selectedResolution,
      format: formatSelect.value
    }));
  });

  socket.addEventListener("message", (event) => {
    if (typeof event.data !== "string") {
      try {
        decoder.push(new Uint8Array(event.data));
      } catch (error) {
        scanStatus.textContent = error.message;
      }
      return;
    }

    let data;
    try {
      data = JSON.parse(event.data);
    } catch (error) {
      scanStatus.textContent = "Получено некорректное сообщение сервера.";
      return;
    }

    if (data.type === "started") {
      scanStatus.textContent = data.message;
      setProgress(0, "Сканирование");
    } else if (data.type === "bytes") {
      scanStatus.textContent = "Получено " + Math.round(data.received / 1024) + " КБ";
    } else if (data.type === "complete") {
      finished = true;
      setScanning(false);
      setProgress(100, "Готово");
      scanStatus.textContent = "Сканирование завершено";
      downloadButton.href = data.download_url;
      downloadButton.classList.remove("hidden");
      previewNote.textContent = "Файл подготовлен на сервере. Предпросмотр получен во время сканирования.";
      activeSocket = null;
    } else if (data.type === "cancelled") {
      finished = true;
      setScanning(false);
      setProgress(0, "Отменено");
      scanStatus.textContent = data.message;
      activeSocket = null;
    } else if (data.type === "error") {
      finished = true;
      setScanning(false);
      setProgress(0, "Ошибка");
      scanStatus.textContent = data.message;
      activeSocket = null;
    }
  });

  socket.addEventListener("error", () => {
    if (!finished) scanStatus.textContent = "Ошибка соединения со сканером.";
  });

  socket.addEventListener("close", () => {
    if (!finished) {
      setScanning(false);
      setProgress(0, "Соединение закрыто");
      scanStatus.textContent = "Сканирование прервано: соединение закрыто.";
    }
    if (activeSocket === socket) activeSocket = null;
  });
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  message(loginMessage, "Выполняется вход…");
  const form = new FormData(loginForm);
  try {
    const result = await api("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: form.get("username"),
        password: form.get("password")
      })
    });
    csrfToken = result.csrf_token;
    showDashboard(result);
    loginForm.reset();
    await refreshScanners();
  } catch (error) {
    message(loginMessage, error.message, "error");
  }
});

logoutButton.addEventListener("click", async () => {
  try {
    await api("/api/v1/auth/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken }
    });
  } catch (error) {
    // An expired session is cleared locally as well.
  }
  if (activeSocket) activeSocket.close();
  showLogin();
});

scannerSelect.addEventListener("change", () => loadScannerOptions(scannerSelect.value));
document.getElementById("refreshButton").addEventListener("click", refreshScanners);
scanButton.addEventListener("click", startScan);
cancelButton.addEventListener("click", () => {
  if (activeSocket && activeSocket.readyState === WebSocket.OPEN) {
    activeSocket.send(JSON.stringify({ action: "cancel" }));
    scanStatus.textContent = "Остановка сканера…";
  }
});

async function bootstrap() {
  try {
    const user = await api("/api/v1/auth/me");
    csrfToken = user.csrf_token;
    showDashboard(user);
    await refreshScanners();
  } catch (error) {
    showLogin();
  }
}
bootstrap();
