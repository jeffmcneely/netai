const PAGE_SIZE = 250;
let activeAjaxRequestCount = 0;
let globalAjaxSpinnerTimerIntervalId = null;
let globalAjaxSpinnerTimerStartMs = 0;

function getGlobalAjaxSpinnerTimer() {
  return document.getElementById('globalAjaxSpinnerTimer');
}

function formatGlobalAjaxSpinnerElapsed(elapsedMs) {
  const totalSeconds = Math.floor(elapsedMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const centiseconds = Math.floor((elapsedMs % 1000) / 10);

  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(centiseconds).padStart(2, '0')}`;
}

function updateGlobalAjaxSpinnerTimer() {
  const timer = getGlobalAjaxSpinnerTimer();
  if (!timer) {
    return;
  }

  timer.textContent = formatGlobalAjaxSpinnerElapsed(Date.now() - globalAjaxSpinnerTimerStartMs);
}

function resetGlobalAjaxSpinnerTimerDisplay() {
  const timer = getGlobalAjaxSpinnerTimer();
  if (!timer) {
    return;
  }

  timer.textContent = '00:00:00.00';
}

function startGlobalAjaxSpinnerTimer() {
  globalAjaxSpinnerTimerStartMs = Date.now();
  updateGlobalAjaxSpinnerTimer();

  if (globalAjaxSpinnerTimerIntervalId !== null) {
    clearInterval(globalAjaxSpinnerTimerIntervalId);
  }

  globalAjaxSpinnerTimerIntervalId = window.setInterval(updateGlobalAjaxSpinnerTimer, 10);
}

function stopGlobalAjaxSpinnerTimer() {
  if (globalAjaxSpinnerTimerIntervalId !== null) {
    clearInterval(globalAjaxSpinnerTimerIntervalId);
    globalAjaxSpinnerTimerIntervalId = null;
  }
}

function setGlobalAjaxSpinnerVisible(isVisible) {
  const spinner = document.getElementById('globalAjaxSpinner');
  if (!spinner) {
    return;
  }

  const wasVisible = spinner.classList.contains('is-active');

  spinner.classList.toggle('is-active', isVisible);
  spinner.setAttribute('aria-hidden', isVisible ? 'false' : 'true');

  if (isVisible && !wasVisible) {
    startGlobalAjaxSpinnerTimer();
  }

  if (!isVisible && wasVisible) {
    stopGlobalAjaxSpinnerTimer();
    resetGlobalAjaxSpinnerTimerDisplay();
  }
}

function installGlobalAjaxSpinner() {
  if (typeof window.fetch !== 'function' || window.__netaiFetchSpinnerInstalled) {
    return;
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    activeAjaxRequestCount += 1;
    setGlobalAjaxSpinnerVisible(true);

    try {
      return await nativeFetch(...args);
    } finally {
      activeAjaxRequestCount = Math.max(0, activeAjaxRequestCount - 1);
      if (activeAjaxRequestCount === 0) {
        setGlobalAjaxSpinnerVisible(false);
      }
    }
  };

  window.__netaiFetchSpinnerInstalled = true;
}

async function fetchConfigs() {
  const res = await fetch('/api/configs');
  const json = await res.json();
  if (json.status !== 'success') {
    throw new Error(json.error?.message || 'Failed to load config folders');
  }
  return json.data.folders || [];
}

function makeFolderRadio(name, group) {
  const label = document.createElement('label');
  label.className = 'radio-row';
  const input = document.createElement('input');
  input.type = 'radio';
  input.name = group;
  input.value = name;
  label.appendChild(input);
  const span = document.createElement('span');
  span.textContent = name;
  label.appendChild(span);
  return label;
}

function syncSelectedRadioRows(groupName) {
  document.querySelectorAll(`input[name="${groupName}"]`).forEach((input) => {
    const row = input.closest('.radio-row');
    if (row) {
      row.classList.toggle('selected', input.checked);
    }
  });
}

function getFolderSelection(radioName, newNameId) {
  const selected = document.querySelector(`input[name="${radioName}"]:checked`);
  if (!selected) {
    throw new Error('Select a config folder');
  }

  if (selected.value === '__new__') {
    const newName = document.getElementById(newNameId).value.trim();
    if (!newName) {
      throw new Error('Enter a name for the new folder');
    }
    return { use_new: true, config_folder: '', new_folder_name: newName };
  }

  return { use_new: false, config_folder: selected.value, new_folder_name: '' };
}

function showMessage(target, html) {
  target.classList.remove('hidden');
  target.innerHTML = html;
}

function formatCell(value) {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return escapeHtml(String(value));
  }
  return escapeHtml(JSON.stringify(value));
}

function isFlowValue(value) {
  return Boolean(
    value
    && typeof value === 'object'
    && !Array.isArray(value)
    && Object.prototype.hasOwnProperty.call(value, 'srcIp')
    && Object.prototype.hasOwnProperty.call(value, 'dstIp')
  );
}

function isTraceValue(value) {
  return Array.isArray(value) && value.length > 0;
}

function renderAnalyzeTable(target, rows, page = 1) {
  target.classList.remove('hidden');
  if (!rows.length) {
    target.innerHTML = '<p>No rows returned.</p>';
    return { pages: 0, page: 0 };
  }

  const columns = Object.keys(rows[0]).filter((col) => col !== 'Flow' && col !== 'Trace');
  const start = (page - 1) * PAGE_SIZE;
  const paged = rows.slice(start, start + PAGE_SIZE);

  const header = `<tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}<th>Flow</th><th>Trace</th></tr>`;
  const body = paged.map((row, idx) => {
    const rowIndex = start + idx;
    const cols = columns.map((col) => `<td>${formatCell(row[col])}</td>`).join('');
    const flowButton = isFlowValue(row.Flow)
      ? `<button type="button" class="detail-btn" data-kind="flow" data-row-index="${rowIndex}">view flow</button>`
      : '';
    const traceButton = isTraceValue(row.Trace)
      ? `<button type="button" class="detail-btn" data-kind="trace" data-row-index="${rowIndex}">view trace</button>`
      : '';
    return `<tr>${cols}<td>${flowButton}</td><td>${traceButton}</td></tr>`;
  }).join('');

  target.innerHTML = `<div class="table-wrap"><table>${header}${body}</table></div>`;
  return { pages: Math.ceil(rows.length / PAGE_SIZE), page };
}

function normalizeColumnName(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function getRowValueByAliases(row, aliases) {
  const entries = Object.entries(row || {});
  const aliasSet = new Set(aliases.map((alias) => normalizeColumnName(alias)));

  for (const [key, value] of entries) {
    if (aliasSet.has(normalizeColumnName(key))) {
      return value;
    }
  }

  return '';
}

function extractNodeHostname(row) {
  const nodeValue = getRowValueByAliases(row, ['Node', 'Hostname', 'Name']);
  if (nodeValue && typeof nodeValue === 'object') {
    return nodeValue.hostname || nodeValue.name || nodeValue.node || '';
  }
  return String(nodeValue || '').trim();
}

function renderInterfacesTable(target, rows, page = 1) {
  target.classList.remove('hidden');
  if (!rows.length) {
    target.innerHTML = '<p>No interfaces returned.</p>';
    return { pages: 0, page: 0 };
  }

  const start = (page - 1) * PAGE_SIZE;
  const paged = rows.slice(start, start + PAGE_SIZE);
  const header = '<tr><th>Interface</th><th>Description</th><th>VRF</th><th>Status</th><th>Properties</th></tr>';
  const body = paged.map((row, idx) => {
    const rowIndex = start + idx;
    const iface = getRowValueByAliases(row, ['Interface', 'Interface_Name', 'InterfaceName', 'Name']);
    const description = getRowValueByAliases(row, ['Description', 'Interface_Description', 'InterfaceDescription']);
    const vrf = getRowValueByAliases(row, ['VRF', 'Vrf', 'VrfName']);
    const activeValue = getRowValueByAliases(row, ['Active']);
    const statusText = activeValue === null || activeValue === undefined ? '' : String(activeValue).trim();
    const isDown = (typeof activeValue === 'boolean' && activeValue === false)
      || /down|false|0|inactive|no/i.test(statusText);
    const statusColor = isDown ? '#c62828' : '#2e7d32';
    const statusDot = `<span aria-hidden="true" style="display:inline-block;width:0.75rem;height:0.75rem;border-radius:999px;background:${statusColor};margin-right:0.4rem;vertical-align:middle;"></span>`;
    const statusHtml = `${statusDot}<span>${escapeHtml(statusText || (isDown ? 'down' : 'up'))}</span>`;

    return `<tr>
      <td>${formatCell(iface)}</td>
      <td>${formatCell(description)}</td>
      <td>${formatCell(vrf)}</td>
      <td>${statusHtml}</td>
      <td><button type="button" class="interface-detail-btn" data-interface-row-index="${rowIndex}">full properties</button></td>
    </tr>`;
  }).join('');

  target.innerHTML = `<div class="table-wrap"><table>${header}${body}</table></div>`;
  return { pages: Math.ceil(rows.length / PAGE_SIZE), page };
}

function renderExplorerTable(target, rows, page = 1) {
  target.classList.remove('hidden');
  if (!rows.length) {
    target.innerHTML = '<p>No nodes returned.</p>';
    return { pages: 0, page: 0 };
  }

  const start = (page - 1) * PAGE_SIZE;
  const paged = rows.slice(start, start + PAGE_SIZE);
  const header = '<tr><th>Hostname</th><th>Properties</th></tr>';
  const body = paged.map((row, idx) => {
    const rowIndex = start + idx;
    const hostname = extractNodeHostname(row);

    return `<tr>
      <td>${formatCell(hostname)}</td>
      <td><button type="button" class="explorer-detail-btn" data-explorer-row-index="${rowIndex}">show details</button></td>
    </tr>`;
  }).join('');

  target.innerHTML = `<div class="table-wrap"><table>${header}${body}</table></div>`;
  return { pages: Math.ceil(rows.length / PAGE_SIZE), page };
}

function summarizeNameList(values) {
  if (!Array.isArray(values) || values.length === 0) {
    return '';
  }
  return values.map((value) => escapeHtml(String(value))).join(', ');
}

function renderSnmpCheckTable(target, report, page = 1) {
  target.classList.remove('hidden');
  const masterValues = Array.isArray(report?.master_values) ? report.master_values : [];
  const mismatchRows = Array.isArray(report?.mismatch_rows) ? report.mismatch_rows : [];

  const masterBody = masterValues.length
    ? masterValues
      .map((entry) => {
        const name = escapeHtml(String(entry?.name || ''));
        const definition = escapeHtml(JSON.stringify(entry?.definition ?? '', null, 0));
        return `<tr><td>${name}</td><td>${definition}</td></tr>`;
      })
      .join('')
    : '<tr><td colspan="2">No Community_Match_Expr values found.</td></tr>';

  const start = (page - 1) * PAGE_SIZE;
  const paged = mismatchRows.slice(start, start + PAGE_SIZE);

  const mismatchBody = paged.length
    ? paged
      .map((row, idx) => {
        const rowIndex = start + idx;
        const missing = Array.isArray(row?.missing) ? row.missing : [];
        const extra = Array.isArray(row?.extra) ? row.extra : [];
        const different = Array.isArray(row?.different) ? row.different : [];
        const summary = [
          `missing: ${missing.length}`,
          `extra: ${extra.length}`,
          `different: ${different.length}`,
        ].join(' | ');

        return `<tr>
          <td>${escapeHtml(String(row?.node || ''))}</td>
          <td>${escapeHtml(summary)}</td>
          <td>${summarizeNameList(missing)}</td>
          <td>${summarizeNameList(extra)}</td>
          <td><button type="button" class="snmp-detail-btn" data-snmp-row-index="${rowIndex}">show mismatch</button></td>
        </tr>`;
      })
      .join('')
    : '<tr><td colspan="5">No mismatches found.</td></tr>';

  target.innerHTML = `
    <h4>All Community_Match_Expr Values (${masterValues.length})</h4>
    <div class="table-wrap">
      <table>
        <tr><th>Name</th><th>Definition</th></tr>
        ${masterBody}
      </table>
    </div>
    <h4 style="margin-top:1rem;">Nodes With Mismatches (${mismatchRows.length})</h4>
    <div class="table-wrap">
      <table>
        <tr><th>Node</th><th>Summary</th><th>Missing</th><th>Extra</th><th>Details</th></tr>
        ${mismatchBody}
      </table>
    </div>
  `;

  return { pages: Math.ceil(mismatchRows.length / PAGE_SIZE), page };
}

function renderFindObjectTable(target, rows, page = 1) {
  target.classList.remove('hidden');
  if (!rows.length) {
    target.innerHTML = '<p>No matching objects found.</p>';
    return { pages: 0, page: 0 };
  }

  const start = (page - 1) * PAGE_SIZE;
  const paged = rows.slice(start, start + PAGE_SIZE);
  const header = '<tr><th>File</th><th>Line</th><th>Matched Object</th><th>Capture</th></tr>';
  const body = paged.map((row, idx) => {
    const rowIndex = start + idx;
    return `<tr>
      <td>${escapeHtml(row.filename || '')}</td>
      <td><a href="#" class="find-object-open-link" data-find-row-index="${rowIndex}">${escapeHtml(String(row.line_number || ''))}</a></td>
      <td>${escapeHtml(row.matched_object || '')}</td>
      <td>${escapeHtml(row.capture || '')}</td>
    </tr>`;
  }).join('');

  target.innerHTML = `<h4>Find Results (${rows.length})</h4><div class="table-wrap"><table>${header}${body}</table></div>`;
  return { pages: Math.ceil(rows.length / PAGE_SIZE), page };
}

function renderAclVerifyTable(target, rows) {
  target.classList.remove('hidden');
  if (!Array.isArray(rows) || rows.length === 0) {
    target.innerHTML = '<p>no access changes found.</p>';
    return;
  }

  const columns = Object.keys(rows[0]);
  const header = `<tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}</tr>`;
  const body = rows
    .map((row) => `<tr>${columns.map((col) => `<td>${formatCell(row[col])}</td>`).join('')}</tr>`)
    .join('');

  target.innerHTML = `<h4>compareFilters</h4><div class="table-wrap"><table>${header}${body}</table></div>`;
}

function buildLineDiffOps(currentText, candidateText) {
  const left = String(currentText || '').split(/\r?\n/);
  const right = String(candidateText || '').split(/\r?\n/);
  const n = left.length;
  const m = right.length;

  const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      if (left[i] === right[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const ops = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (left[i] === right[j]) {
      ops.push({ type: 'same', left: left[i], right: right[j] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: 'remove', left: left[i], right: '' });
      i += 1;
    } else {
      ops.push({ type: 'add', left: '', right: right[j] });
      j += 1;
    }
  }

  while (i < n) {
    ops.push({ type: 'remove', left: left[i], right: '' });
    i += 1;
  }

  while (j < m) {
    ops.push({ type: 'add', left: '', right: right[j] });
    j += 1;
  }

  return ops;
}

function renderAclDiffTable(target, currentText, candidateText) {
  const ops = buildLineDiffOps(currentText, candidateText);
  const changed = ops.filter((op) => op.type !== 'same').length;
  const removedCount = ops.filter((op) => op.type === 'remove').length;
  const addedCount = ops.filter((op) => op.type === 'add').length;

  target.classList.remove('hidden');

  if (changed === 0) {
    target.innerHTML = '<h4>Line By Line Diff</h4><p>verification complete</p>';
    return;
  }

  const body = ops
    .map((op) => {
      const label = op.type === 'add' ? '+' : (op.type === 'remove' ? '-' : '=');
      return `<tr class="acl-diff-row acl-diff-${op.type}">
        <td class="acl-diff-mark">${escapeHtml(label)}</td>
        <td>${escapeHtml(op.left || '')}</td>
        <td>${escapeHtml(op.right || '')}</td>
      </tr>`;
    })
    .join('');

  target.innerHTML = `
    <label class="acl-diff-toggle" for="aclDiffHideUnchanged">
      <input id="aclDiffHideUnchanged" type="checkbox">
      <span>hide unchanged lines</span>
    </label>
    <h4>Line By Line Diff</h4>
    <p class="acl-diff-summary">changes: ${changed} | removed: ${removedCount} | added: ${addedCount}</p>
    <div class="table-wrap">
      <table>
        <tr><th>Change</th><th>Current</th><th>Candidate</th></tr>
        ${body}
      </table>
    </div>
  `;

  const hideUnchanged = target.querySelector('#aclDiffHideUnchanged');
  const syncUnchangedVisibility = () => {
    const shouldHide = Boolean(hideUnchanged?.checked);
    target.querySelectorAll('.acl-diff-row.acl-diff-same').forEach((row) => {
      row.classList.toggle('acl-diff-hidden', shouldHide);
    });
  };

  if (hideUnchanged) {
    hideUnchanged.addEventListener('change', syncUnchangedVisibility);
  }
  syncUnchangedVisibility();
}

function markdownInlineToHtml(text) {
  const escaped = escapeHtml(String(text || ''));
  return escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function markdownTextBlockToHtml(blockText) {
  const lines = String(blockText || '').split('\n');
  const html = [];
  let inUl = false;
  let inOl = false;

  const closeLists = () => {
    if (inUl) {
      html.push('</ul>');
      inUl = false;
    }
    if (inOl) {
      html.push('</ol>');
      inOl = false;
    }
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      closeLists();
      return;
    }

    if (trimmed.startsWith('### ')) {
      closeLists();
      html.push(`<h3>${markdownInlineToHtml(trimmed.slice(4))}</h3>`);
      return;
    }

    if (trimmed.startsWith('## ')) {
      closeLists();
      html.push(`<h2>${markdownInlineToHtml(trimmed.slice(3))}</h2>`);
      return;
    }

    if (trimmed.startsWith('# ')) {
      closeLists();
      html.push(`<h1>${markdownInlineToHtml(trimmed.slice(2))}</h1>`);
      return;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      if (inOl) {
        html.push('</ol>');
        inOl = false;
      }
      if (!inUl) {
        html.push('<ul>');
        inUl = true;
      }
      html.push(`<li>${markdownInlineToHtml(trimmed.replace(/^[-*]\s+/, ''))}</li>`);
      return;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      if (inUl) {
        html.push('</ul>');
        inUl = false;
      }
      if (!inOl) {
        html.push('<ol>');
        inOl = true;
      }
      html.push(`<li>${markdownInlineToHtml(trimmed.replace(/^\d+\.\s+/, ''))}</li>`);
      return;
    }

    closeLists();
    html.push(`<p>${markdownInlineToHtml(trimmed)}</p>`);
  });

  closeLists();
  return html.join('');
}

function markdownToHtml(markdownText) {
  const source = String(markdownText || '');
  const parts = source.split('```');
  const html = [];

  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index];
    if (index % 2 === 0) {
      html.push(markdownTextBlockToHtml(part));
      continue;
    }

    const newlineIndex = part.indexOf('\n');
    const hasLang = newlineIndex >= 0;
    const rawLang = hasLang ? part.slice(0, newlineIndex).trim() : '';
    const codeBody = hasLang ? part.slice(newlineIndex + 1) : part;
    const className = rawLang ? ` class="language-${escapeHtml(rawLang)}"` : '';
    html.push(`<pre><code${className}>${escapeHtml(codeBody)}</code></pre>`);
  }

  return html.join('');
}

function renderAclCommandsOutput(target, commandsText) {
  target.classList.remove('hidden');
  target.innerHTML = `
    <h4>Generated Commands</h4>
    <div class="acl-command-output">${markdownToHtml(commandsText)}</div>
  `;
}

function renderFileViewerHtml(payload) {
  const title = `${payload.filename || '-'} (${payload.total_lines || 0} lines)`;
  const rows = (payload.lines || []).map((line) => {
    const lineClass = line.is_jump_target ? 'viewer-line viewer-line-target' : 'viewer-line';
    return `<div class="${lineClass}" data-viewer-line="${line.line_number}">
      <span class="viewer-gutter">${line.line_number}</span>
      <span class="viewer-text">${escapeHtml(line.content || '')}</span>
    </div>`;
  }).join('');

  return `<div class="file-viewer-wrap"><p class="file-viewer-title">${escapeHtml(title)}</p><div class="file-viewer-code">${rows}</div></div>`;
}

function flattenForDetails(value, prefix = '', out = []) {
  if (value === null || value === undefined) {
    out.push([prefix || 'value', '']);
    return out;
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    out.push([prefix || 'value', String(value)]);
    return out;
  }

  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      flattenForDetails(item, `${prefix}[${index}]`, out);
    });
    return out;
  }

  Object.entries(value).forEach(([key, item]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    flattenForDetails(item, nextKey, out);
  });

  return out;
}

function renderDetailTable(title, data) {
  const rows = flattenForDetails(data);
  const tableBody = rows
    .map(([k, v]) => `<tr><th>${escapeHtml(k)}</th><td>${escapeHtml(v)}</td></tr>`)
    .join('');
  return `<h4>${escapeHtml(title)}</h4><table class="detail-table">${tableBody}</table>`;
}

function renderNodePropertySelectionTable(nodeHostname, nodeData) {
  const rows = flattenForDetails(nodeData);
  const tableBody = rows
    .map(([k, v]) => {
      const canSearchAcl = /^IP_Access_Lists\[\d+\]$/.test(k) && String(v || '').trim().length > 0;
      const valueHtml = canSearchAcl
        ? `<a href="#" class="explorer-acl-search-link" data-node-hostname="${escapeHtml(nodeHostname)}" data-filter-name="${escapeHtml(String(v))}">${escapeHtml(String(v))}</a>`
        : escapeHtml(String(v || ''));
      return `<tr><th>${escapeHtml(k)}</th><td>${valueHtml}</td></tr>`;
    })
    .join('');
  return `<h4>Node Properties</h4><table class="detail-table"><tr><th>Property</th><th>Value</th></tr>${tableBody}</table>`;
}

function renderAclSearchResultsTable(rows) {
  if (!rows.length) {
    return '<p>No ACL search results returned.</p>';
  }

  const columns = Object.keys(rows[0]);
  const header = `<tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}</tr>`;
  const body = rows.map((row) => {
    const cells = columns.map((col) => `<td>${formatCell(row[col])}</td>`).join('');
    return `<tr>${cells}</tr>`;
  }).join('');

  return `<h4>ACL Search Results</h4><div class="table-wrap"><table>${header}${body}</table></div>`;
}

function renderExplorerFlyoutContent(nodeHostname, nodeData) {
  return `
    <div class="actions" style="margin-bottom:0.75rem;">
      <button type="button" class="explorer-flyout-interfaces-btn" data-node-hostname="${escapeHtml(nodeHostname)}">interfaces</button>
      <button type="button" class="explorer-flyout-vlans-btn" data-node-hostname="${escapeHtml(nodeHostname)}">vlans</button>
    </div>
    <p>Use interfaces or vlans to load node data in the right flyout.</p>
    ${renderNodePropertySelectionTable(nodeHostname, nodeData)}
  `;
}

function renderExplorerInterfacesTable(rows) {
  if (!rows.length) {
    return '<p>No interfaces returned for this node.</p>';
  }

  const header = '<tr><th>Interface</th><th>Description</th><th>VRF</th><th>Status</th><th>Properties</th></tr>';
  const body = rows.map((row, idx) => {
    const iface = getRowValueByAliases(row, ['Interface', 'Interface_Name', 'InterfaceName', 'Name']);
    const description = getRowValueByAliases(row, ['Description', 'Interface_Description', 'InterfaceDescription']);
    const vrf = getRowValueByAliases(row, ['VRF', 'Vrf', 'VrfName']);
    const activeValue = getRowValueByAliases(row, ['Active']);
    const statusText = activeValue === null || activeValue === undefined ? '' : String(activeValue).trim();
    const isDown = (typeof activeValue === 'boolean' && activeValue === false)
      || /down|false|0|inactive|no/i.test(statusText);
    const statusColor = isDown ? '#c62828' : '#2e7d32';
    const statusDot = `<span aria-hidden="true" style="display:inline-block;width:0.75rem;height:0.75rem;border-radius:999px;background:${statusColor};margin-right:0.4rem;vertical-align:middle;"></span>`;
    const statusHtml = `${statusDot}<span>${escapeHtml(statusText || (isDown ? 'down' : 'up'))}</span>`;

    return `<tr>
      <td>${formatCell(iface)}</td>
      <td>${formatCell(description)}</td>
      <td>${formatCell(vrf)}</td>
      <td>${statusHtml}</td>
      <td><button type="button" class="explorer-interface-detail-btn" data-explorer-interface-index="${idx}">show details</button></td>
    </tr>`;
  }).join('');

  return `<h4>Interfaces</h4><div class="table-wrap"><table>${header}${body}</table></div>`;
}

function renderExplorerVlansTable(rows) {
  if (!rows.length) {
    return '<p>No VLANs returned for this node.</p>';
  }

  const columns = Object.keys(rows[0]);
  const header = `<tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}<th>Properties</th></tr>`;
  const body = rows.map((row, idx) => {
    const cells = columns.map((col) => `<td>${formatCell(row[col])}</td>`).join('');
    return `<tr>${cells}<td><button type="button" class="explorer-vlan-detail-btn" data-explorer-vlan-index="${idx}">show details</button></td></tr>`;
  }).join('');

  return `<h4>VLANs</h4><div class="table-wrap"><table>${header}${body}</table></div>`;
}

function getClientMatchFilters() {
  return {
    action: (document.getElementById('matchAction')?.value || '').trim().toLowerCase(),
    node: (document.getElementById('matchNode')?.value || '').trim().toLowerCase(),
    filterName: (document.getElementById('matchFilterName')?.value || '').trim().toLowerCase(),
    lineContent: (document.getElementById('matchLineContent')?.value || '').trim().toLowerCase(),
    ingressNode: (document.getElementById('matchIngressNode')?.value || '').trim().toLowerCase(),
    ingressInterface: (document.getElementById('matchIngressInterface')?.value || '').trim().toLowerCase(),
    ingressVrf: (document.getElementById('matchIngressVrf')?.value || '').trim().toLowerCase(),
  };
}

function includesMatch(source, needle) {
  if (!needle) {
    return true;
  }
  return String(source || '').toLowerCase().includes(needle);
}

function matchesClientFilters(row, filters) {
  const flow = row.Flow && typeof row.Flow === 'object' ? row.Flow : {};
  return (
    includesMatch(row.Action, filters.action)
    && includesMatch(row.Node, filters.node)
    && includesMatch(row.Filter_Name, filters.filterName)
    && includesMatch(row.Line_Content, filters.lineContent)
    && includesMatch(flow.ingressNode, filters.ingressNode)
    && includesMatch(flow.ingressInterface, filters.ingressInterface)
    && includesMatch(flow.ingressVrf, filters.ingressVrf)
  );
}

function renderPager(pager, pages, current, onSelect) {
  pager.innerHTML = '';
  if (pages <= 1) {
    pager.classList.add('hidden');
    return;
  }

  pager.classList.remove('hidden');
  for (let i = 1; i <= pages; i += 1) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = i === current ? `page ${i}*` : `page ${i}`;
    btn.addEventListener('click', () => onSelect(i));
    pager.appendChild(btn);
  }
}

function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function readSearchFilters() {
  const tcpFlags = Array.from(document.querySelectorAll('.tcp-flag:checked')).map((cb) => cb.value);
  return {
    srcIps: splitCsv('srcIps'),
    dstIps: splitCsv('dstIps'),
    srcPorts: splitCsv('srcPorts'),
    dstPorts: splitCsv('dstPorts'),
    applications: splitCsv('applications'),
    ipProtocols: splitCsv('ipProtocols'),
    icmpCodes: splitCsv('icmpCodes'),
    icmpTypes: splitCsv('icmpTypes'),
    dscps: splitCsv('dscps'),
    ecns: splitCsv('ecns'),
    packetLengths: splitCsv('packetLengths'),
    fragmentOffsets: splitCsv('fragmentOffsets'),
    tcpFlags,
  };
}

function splitCsv(id) {
  const value = document.getElementById(id)?.value || '';
  return value.split(',').map((x) => x.trim()).filter(Boolean);
}

async function initIndexPage() {
  const folderList = document.getElementById('folderList');
  if (!folderList) {
    return;
  }

  const newField = document.getElementById('newFolderName');
  const newRadio = document.getElementById('folderChoiceNew');
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const status = document.getElementById('uploadStatus');

  const folders = await fetchConfigs();
  folders.forEach((f) => folderList.appendChild(makeFolderRadio(f, 'folderChoice')));

  const onSelectionChange = () => {
    const selected = document.querySelector('input[name="folderChoice"]:checked');
    newField.classList.toggle('hidden', !(selected && selected.value === '__new__'));
    syncSelectedRadioRows('folderChoice');
  };

  document.addEventListener('change', (event) => {
    if (event.target.name === 'folderChoice') {
      onSelectionChange();
    }
  });

  onSelectionChange();

  const uploadFiles = async (files) => {
    const folderInfo = getFolderSelection('folderChoice', 'newFolderName');

    const form = new FormData();
    form.append('use_new', folderInfo.use_new ? '1' : '0');
    form.append('config_folder', folderInfo.config_folder);
    form.append('new_folder_name', folderInfo.new_folder_name);

    for (const file of files) {
      form.append('files', file);
    }

    const res = await fetch('/api/upload', {
      method: 'POST',
      body: form,
    });
    const json = await res.json();

    if (json.status !== 'success') {
      throw new Error(json.error?.message || 'Upload failed');
    }

    const items = json.data.uploaded
      .map((u) => `<li>${escapeHtml(u.original_name)} -> ${escapeHtml(u.final_name)} (${escapeHtml(u.s3_key)})</li>`)
      .join('');
    showMessage(status, `<h4>Uploaded to ${escapeHtml(json.data.folder)}</h4><ul>${items}</ul>`);
  };

  dropZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async (event) => {
    try {
      await uploadFiles(event.target.files);
    } catch (err) {
      showMessage(status, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  dropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropZone.classList.add('active');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('active');
  });

  dropZone.addEventListener('drop', async (event) => {
    event.preventDefault();
    dropZone.classList.remove('active');
    try {
      await uploadFiles(event.dataTransfer.files);
    } catch (err) {
      showMessage(status, `<p>${escapeHtml(err.message)}</p>`);
    }
  });
}

async function initAnalyzePage() {
  const folderList = document.getElementById('analyzeFolderList');
  if (!folderList) {
    return;
  }

  const newField = document.getElementById('analyzeNewFolderName');
  const analyzeBtn = document.getElementById('analyzeBtn');
  const unreachableRulesBtn = document.getElementById('unreachableRulesBtn');
  const snmpCheckBtn = document.getElementById('snmpCheckBtn');
  const searchBtn = document.getElementById('searchBtn');
  const explorerBtn = document.getElementById('explorerBtn');
  const findObjectBtn = document.getElementById('findObjectBtn');
  const searchPanel = document.getElementById('searchPanel');
  const findObjectPanel = document.getElementById('findObjectPanel');
  const findInput = document.getElementById('findInput');
  const runFindObjectBtn = document.getElementById('runFindObjectBtn');
  const runFindStringBtn = document.getElementById('runFindStringBtn');
  const runSearchBtn = document.getElementById('runSearchBtn');
  const applyClientMatchBtn = document.getElementById('applyClientMatchBtn');
  const meta = document.getElementById('analysisMeta');
  const results = document.getElementById('results');
  const pager = document.getElementById('pager');
  const findObjectResults = document.getElementById('findObjectResults');
  const findObjectPager = document.getElementById('findObjectPager');
  const detailFlyout = document.getElementById('detailFlyout');
  const detailFlyoutTitle = document.getElementById('detailFlyoutTitle');
  const detailFlyoutBody = document.getElementById('detailFlyoutBody');
  const detailFlyoutMaximize = document.getElementById('detailFlyoutMaximize');
  const detailFlyoutMinimize = document.getElementById('detailFlyoutMinimize');
  const detailFlyoutClose = document.getElementById('detailFlyoutClose');
  const fileViewerFlyout = document.getElementById('fileViewerFlyout');
  const fileViewerFlyoutBody = document.getElementById('fileViewerFlyoutBody');
  const fileViewerFlyoutMaximize = document.getElementById('fileViewerFlyoutMaximize');
  const fileViewerFlyoutMinimize = document.getElementById('fileViewerFlyoutMinimize');
  const fileViewerFlyoutClose = document.getElementById('fileViewerFlyoutClose');

  let allRows = [];
  let filteredRows = [];
  let findObjectRows = [];
  let explorerInterfaceRows = [];
  let explorerVlanRows = [];
  let snmpReport = null;
  let snapshotName = '';
  let resultMode = 'analyze';

  const folders = await fetchConfigs();
  folders.forEach((f) => folderList.appendChild(makeFolderRadio(f, 'analyzeFolderChoice')));

  document.addEventListener('change', (event) => {
    if (event.target.name === 'analyzeFolderChoice') {
      const selected = document.querySelector('input[name="analyzeFolderChoice"]:checked');
      newField.classList.toggle('hidden', !(selected && selected.value === '__new__'));
      syncSelectedRadioRows('analyzeFolderChoice');
    }
  });

  syncSelectedRadioRows('analyzeFolderChoice');

  const maximizeFlyout = (flyout) => {
    flyout.classList.remove('hidden');
    flyout.classList.add('is-maximized');
  };

  const minimizeFlyout = (flyout) => {
    flyout.classList.remove('is-maximized');
  };

  const closeDetailFlyout = () => {
    minimizeFlyout(detailFlyout);
    detailFlyout.classList.add('hidden');
    detailFlyoutTitle.textContent = 'Details';
    detailFlyoutBody.innerHTML = '';
  };

  const closeFileViewerFlyout = () => {
    minimizeFlyout(fileViewerFlyout);
    fileViewerFlyout.classList.add('hidden');
    const fileViewerTitle = document.getElementById('fileViewerFlyoutTitle');
    if (fileViewerTitle) {
      fileViewerTitle.textContent = 'File Viewer';
    }
    fileViewerFlyoutBody.innerHTML = '';
  };

  const openDetailFlyout = (title, data) => {
    if (!data) {
      return;
    }

    detailFlyoutTitle.textContent = title;
    detailFlyoutBody.innerHTML = renderDetailTable(title, data);
    detailFlyout.classList.remove('hidden');
  };

  const openExplorerNodeFlyout = (row) => {
    const nodeHostname = extractNodeHostname(row);
    detailFlyoutTitle.textContent = 'Node Property Selection';
    detailFlyoutBody.innerHTML = renderExplorerFlyoutContent(nodeHostname, row);
    detailFlyout.classList.remove('hidden');
    fileViewerFlyout.classList.remove('hidden');
    const fileViewerTitle = document.getElementById('fileViewerFlyoutTitle');
    if (fileViewerTitle) {
      fileViewerTitle.textContent = 'Interfaces';
    }
    fileViewerFlyoutBody.innerHTML = '<p>Select interfaces or vlans to load this node data.</p>';
    explorerInterfaceRows = [];
    explorerVlanRows = [];
  };

  detailFlyoutMaximize.addEventListener('click', () => maximizeFlyout(detailFlyout));
  detailFlyoutMinimize.addEventListener('click', () => minimizeFlyout(detailFlyout));
  detailFlyoutClose.addEventListener('click', closeDetailFlyout);
  fileViewerFlyoutMaximize.addEventListener('click', () => maximizeFlyout(fileViewerFlyout));
  fileViewerFlyoutMinimize.addEventListener('click', () => minimizeFlyout(fileViewerFlyout));
  fileViewerFlyoutClose.addEventListener('click', closeFileViewerFlyout);

  const updateMeta = (visible, total) => {
    showMessage(
      meta,
      `<p>Snapshot: ${escapeHtml(snapshotName || '-')}</p><p>Rows: ${visible} / ${total}</p>`
    );
  };

  const renderRows = (rows) => {
    let currentPage = 1;
    const draw = () => {
      let pg;
      if (resultMode === 'explorer') {
        pg = renderExplorerTable(results, rows, currentPage);
      } else if (resultMode === 'snmp') {
        pg = renderSnmpCheckTable(results, snmpReport || {}, currentPage);
      } else {
        pg = renderAnalyzeTable(results, rows, currentPage);
      }
      renderPager(pager, pg.pages, currentPage, (newPage) => {
        currentPage = newPage;
        draw();
      });
    };
    draw();
  };

  const renderFindRows = (rows) => {
    let currentPage = 1;
    const draw = () => {
      const pg = renderFindObjectTable(findObjectResults, rows, currentPage);
      renderPager(findObjectPager, pg.pages, currentPage, (newPage) => {
        currentPage = newPage;
        draw();
      });
    };
    draw();
  };

  results.addEventListener('click', (event) => {
    const detailBtn = event.target.closest('.detail-btn');
    if (detailBtn) {
      const kind = detailBtn.getAttribute('data-kind');
      const rowIndex = Number(detailBtn.getAttribute('data-row-index'));
      const row = filteredRows[rowIndex];
      if (!row || (kind !== 'flow' && kind !== 'trace')) {
        return;
      }

      const title = kind === 'flow' ? 'Flow Details' : 'Trace Details';
      const data = kind === 'flow' ? row.Flow : row.Trace;
      openDetailFlyout(title, data);
      return;
    }

    const interfaceBtn = event.target.closest('.interface-detail-btn');
    if (interfaceBtn) {
      const rowIndex = Number(interfaceBtn.getAttribute('data-interface-row-index'));
      const row = filteredRows[rowIndex];
      if (!row) {
        return;
      }

      openDetailFlyout('Interface Properties', row);
      return;
    }

    const explorerBtnEl = event.target.closest('.explorer-detail-btn');
    if (explorerBtnEl) {
      const rowIndex = Number(explorerBtnEl.getAttribute('data-explorer-row-index'));
      const row = filteredRows[rowIndex];
      if (!row) {
        return;
      }

      openExplorerNodeFlyout(row);
      return;
    }

    const snmpDetailBtn = event.target.closest('.snmp-detail-btn');
    if (!snmpDetailBtn) {
      return;
    }

    const rowIndex = Number(snmpDetailBtn.getAttribute('data-snmp-row-index'));
    const row = filteredRows[rowIndex];
    if (!row) {
      return;
    }

    openDetailFlyout('SNMP Community Mismatch', row);
  });

  detailFlyoutBody.addEventListener('click', async (event) => {
    const interfacesBtnEl = event.target.closest('.explorer-flyout-interfaces-btn');
    if (interfacesBtnEl) {
      try {
        const nodeHostname = interfacesBtnEl.getAttribute('data-node-hostname') || '';
        const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
        const res = await fetch('/api/interfaces', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...folderInfo,
            node_hostname: nodeHostname,
          }),
        });
        const json = await res.json();
        if (json.status !== 'success') {
          throw new Error(json.error?.message || 'Interfaces query failed');
        }

        explorerInterfaceRows = json.data.rows || [];
        fileViewerFlyout.classList.remove('hidden');
        const fileViewerTitle = document.getElementById('fileViewerFlyoutTitle');
        if (fileViewerTitle) {
          fileViewerTitle.textContent = `Interfaces: ${nodeHostname}`;
        }
        fileViewerFlyoutBody.innerHTML = renderExplorerInterfacesTable(explorerInterfaceRows);
      } catch (err) {
        fileViewerFlyout.classList.remove('hidden');
        fileViewerFlyoutBody.innerHTML = `<p>${escapeHtml(err.message)}</p>`;
      }
      return;
    }

    const aclSearchLinkEl = event.target.closest('.explorer-acl-search-link');
    if (aclSearchLinkEl) {
      event.preventDefault();
      try {
        const nodeHostname = aclSearchLinkEl.getAttribute('data-node-hostname') || '';
        const filterName = aclSearchLinkEl.getAttribute('data-filter-name') || '';
        const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
        const res = await fetch('/api/node-acl-search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...folderInfo,
            node_hostname: nodeHostname,
            filter_name: filterName,
          }),
        });
        const json = await res.json();
        if (json.status !== 'success') {
          throw new Error(json.error?.message || 'ACL search failed');
        }

        fileViewerFlyout.classList.remove('hidden');
        const fileViewerTitle = document.getElementById('fileViewerFlyoutTitle');
        if (fileViewerTitle) {
          fileViewerTitle.textContent = `ACL Search: ${filterName}`;
        }
        fileViewerFlyoutBody.innerHTML = renderAclSearchResultsTable(json.data.rows || []);
      } catch (err) {
        fileViewerFlyout.classList.remove('hidden');
        fileViewerFlyoutBody.innerHTML = `<p>${escapeHtml(err.message)}</p>`;
      }
      return;
    }

    const vlansBtnEl = event.target.closest('.explorer-flyout-vlans-btn');
    if (vlansBtnEl) {
      try {
        const nodeHostname = vlansBtnEl.getAttribute('data-node-hostname') || '';
        const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
        const res = await fetch('/api/vlans', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...folderInfo,
            node_hostname: nodeHostname,
          }),
        });
        const json = await res.json();
        if (json.status !== 'success') {
          throw new Error(json.error?.message || 'VLAN query failed');
        }

        explorerVlanRows = json.data.rows || [];
        fileViewerFlyout.classList.remove('hidden');
        const fileViewerTitle = document.getElementById('fileViewerFlyoutTitle');
        if (fileViewerTitle) {
          fileViewerTitle.textContent = `VLANs: ${nodeHostname}`;
        }
        fileViewerFlyoutBody.innerHTML = renderExplorerVlansTable(explorerVlanRows);
      } catch (err) {
        fileViewerFlyout.classList.remove('hidden');
        fileViewerFlyoutBody.innerHTML = `<p>${escapeHtml(err.message)}</p>`;
      }
      return;
    }

    const interfaceDetailBtnEl = event.target.closest('.explorer-interface-detail-btn');
    if (interfaceDetailBtnEl) {
      const index = Number(interfaceDetailBtnEl.getAttribute('data-explorer-interface-index'));
      const row = explorerInterfaceRows[index];
      if (!row) {
        return;
      }

      openDetailFlyout('Interface Properties', row);
      const table = renderDetailTable('Interface Properties', row);
      fileViewerFlyout.classList.remove('hidden');
      fileViewerFlyoutBody.innerHTML = `${renderExplorerInterfacesTable(explorerInterfaceRows)}${table}`;
      return;
    }

    const vlanDetailBtnEl = event.target.closest('.explorer-vlan-detail-btn');
    if (!vlanDetailBtnEl) {
      return;
    }

    const index = Number(vlanDetailBtnEl.getAttribute('data-explorer-vlan-index'));
    const row = explorerVlanRows[index];
    if (!row) {
      return;
    }

    openDetailFlyout('VLAN Properties', row);
    const table = renderDetailTable('VLAN Properties', row);
    fileViewerFlyout.classList.remove('hidden');
    fileViewerFlyoutBody.innerHTML = `${renderExplorerVlansTable(explorerVlanRows)}${table}`;
  });

  applyClientMatchBtn.addEventListener('click', () => {
    if (resultMode !== 'analyze') {
      showMessage(meta, '<p>Client match filters only apply to analyze/find flow results.</p>');
      return;
    }

    const filters = getClientMatchFilters();
    filteredRows = allRows.filter((row) => matchesClientFilters(row, filters));
    closeDetailFlyout();
    updateMeta(filteredRows.length, allRows.length);
    renderRows(filteredRows);
  });

  findObjectResults.addEventListener('click', async (event) => {
    const link = event.target.closest('.find-object-open-link');
    if (!link) {
      return;
    }
    event.preventDefault();

    const rowIndex = Number(link.getAttribute('data-find-row-index'));
    const row = findObjectRows[rowIndex];
    if (!row) {
      return;
    }

    try {
      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const folder = folderInfo.use_new ? folderInfo.new_folder_name : folderInfo.config_folder;
      const query = new URLSearchParams({
        config_folder: folder,
        filename: row.filename,
        jump_line: String(row.line_number || 0),
      });

      const res = await fetch(`/api/find-object/file?${query.toString()}`);
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Failed to open file');
      }

      fileViewerFlyoutBody.innerHTML = renderFileViewerHtml(json.data || {});
      fileViewerFlyout.classList.remove('hidden');

      const jumpLine = Number(json.data?.jump_line || 0);
      if (jumpLine > 0) {
        const target = fileViewerFlyoutBody.querySelector(`[data-viewer-line="${jumpLine}"]`);
        if (target) {
          target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  analyzeBtn.addEventListener('click', async () => {
    try {
      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(folderInfo),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Analyze failed');
      }

      snapshotName = json.data.snapshot_name;
      resultMode = 'analyze';
      snmpReport = null;
      allRows = json.data.rows || [];
      filteredRows = [...allRows];
      closeDetailFlyout();
      closeFileViewerFlyout();
      updateMeta(filteredRows.length, allRows.length);
      renderRows(filteredRows);
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  unreachableRulesBtn.addEventListener('click', async () => {
    try {
      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const res = await fetch('/api/unreachable-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(folderInfo),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Unreachable rules query failed');
      }

      snapshotName = json.data.snapshot_name;
      resultMode = 'analyze';
      snmpReport = null;
      allRows = json.data.rows || [];
      filteredRows = [...allRows];
      closeDetailFlyout();
      closeFileViewerFlyout();
      updateMeta(filteredRows.length, allRows.length);
      renderRows(filteredRows);
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  snmpCheckBtn.addEventListener('click', async () => {
    try {
      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const res = await fetch('/api/snmp-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(folderInfo),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'SNMP check failed');
      }

      snapshotName = json.data.snapshot_name;
      resultMode = 'snmp';
      snmpReport = json.data;
      allRows = json.data.mismatch_rows || [];
      filteredRows = [...allRows];
      closeDetailFlyout();
      closeFileViewerFlyout();

      const baseline = json.data.baseline_signature_meta || {};
      showMessage(
        meta,
        `<p>Snapshot: ${escapeHtml(snapshotName || '-')}</p>
         <p>Nodes checked: ${escapeHtml(String(baseline.node_count || 0))}</p>
         <p>Majority baseline: ${escapeHtml(String(baseline.majority_count || 0))} nodes</p>
         <p>Mismatched nodes: ${escapeHtml(String(filteredRows.length))}</p>`
      );
      renderRows(filteredRows);
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  explorerBtn.addEventListener('click', async () => {
    try {
      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const res = await fetch('/api/explorer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(folderInfo),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Explorer query failed');
      }

      snapshotName = json.data.snapshot_name;
      resultMode = 'explorer';
      snmpReport = null;
      allRows = json.data.rows || [];
      filteredRows = [...allRows];
      detailFlyoutTitle.textContent = 'Node Property Selection';
      detailFlyoutBody.innerHTML = '<p>Select a node to view properties and actions.</p>';
      detailFlyout.classList.remove('hidden');
      const fileViewerTitle = document.getElementById('fileViewerFlyoutTitle');
      if (fileViewerTitle) {
        fileViewerTitle.textContent = 'Interfaces';
      }
      fileViewerFlyoutBody.innerHTML = '<p>Interfaces or VLANs for the selected node will appear here.</p>';
      fileViewerFlyout.classList.remove('hidden');
      updateMeta(filteredRows.length, allRows.length);
      renderRows(filteredRows);
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  searchBtn.addEventListener('click', () => {
    searchPanel.classList.toggle('hidden');
  });

  findObjectBtn.addEventListener('click', () => {
    findObjectPanel.classList.toggle('hidden');
  });

  runFindObjectBtn.addEventListener('click', async () => {
    try {
      const ip = (findInput.value || '').trim();
      if (!ip) {
        throw new Error('IP is required');
      }
      const selectedFindMode = document.querySelector('input[name="findIpMode"]:checked');
      const findMode = selectedFindMode ? selectedFindMode.value : 'contains';

      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const body = {
        ...folderInfo,
        ip,
        find_mode: findMode,
      };

      const res = await fetch('/api/find-object', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Find IP failed');
      }

      findObjectRows = json.data.results || [];
      closeDetailFlyout();
      closeFileViewerFlyout();
      renderFindRows(findObjectRows);
    } catch (err) {
      showMessage(findObjectResults, `<p>${escapeHtml(err.message)}</p>`);
      findObjectPager.classList.add('hidden');
    }
  });

  runFindStringBtn.addEventListener('click', async () => {
    try {
      const findText = (findInput.value || '').trim();
      if (!findText) {
        throw new Error('Find string is required');
      }

      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const body = {
        ...folderInfo,
        find_text: findText,
      };

      const res = await fetch('/api/find-string', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Find string failed');
      }

      findObjectRows = json.data.results || [];
      closeDetailFlyout();
      closeFileViewerFlyout();
      renderFindRows(findObjectRows);
    } catch (err) {
      showMessage(findObjectResults, `<p>${escapeHtml(err.message)}</p>`);
      findObjectPager.classList.add('hidden');
    }
  });

  runSearchBtn.addEventListener('click', async () => {
    try {
      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const body = {
        ...folderInfo,
        search_filters: readSearchFilters(),
      };

      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Search failed');
      }

      snapshotName = json.data.snapshot_name;
      resultMode = 'analyze';
      snmpReport = null;
      allRows = json.data.rows || [];
      filteredRows = [...allRows];
      closeDetailFlyout();
      closeFileViewerFlyout();
      updateMeta(filteredRows.length, allRows.length);
      renderRows(filteredRows);
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });
}

async function initAclOptimizePage() {
  const page = document.getElementById('aclOptimizePage');
  if (!page) {
    return;
  }

  const platformInput = document.getElementById('aclPlatform');
  const modelInput = document.getElementById('aclModel');
  const currentInput = document.getElementById('aclCurrent');
  const candidateInput = document.getElementById('aclCandidate');
  const optimizeBtn = document.getElementById('aclOptimizeBtn');
  const generateCommandsBtn = document.getElementById('aclGenerateCommandsBtn');
  const verifyBtn = document.getElementById('aclVerifyBtn');
  const status = document.getElementById('aclOptimizeStatus');
  const diffResults = document.getElementById('aclDiffResults');
  const verifyResults = document.getElementById('aclVerifyResults');

  optimizeBtn.addEventListener('click', async () => {
    candidateInput.value = '';
    diffResults.innerHTML = '';
    diffResults.classList.add('hidden');
    verifyResults.innerHTML = '';
    verifyResults.classList.add('hidden');

    try {
      const platform = (platformInput.value || '').trim();
      const model = (modelInput?.value || '').trim();
      const current = (currentInput.value || '').trim();
      if (!current) {
        throw new Error('current is required');
      }

      const res = await fetch('/api/acl/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, model, current }),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'ACL optimize failed');
      }

      candidateInput.value = json.data?.candidate || '';
      showMessage(status, '<p>Candidate ACL updated.</p>');
    } catch (err) {
      showMessage(status, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  generateCommandsBtn.addEventListener('click', async () => {
    try {
      const platform = (platformInput.value || '').trim();
      const model = (modelInput?.value || '').trim();
      const current = (currentInput.value || '').trim();
      const candidate = (candidateInput.value || '').trim();
      if (!current) {
        throw new Error('current is required');
      }
      if (!candidate) {
        throw new Error('candidate is required');
      }

      const res = await fetch('/api/acl/generate-commands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, model, current, candidate }),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Generate commands failed');
      }

      renderAclCommandsOutput(diffResults, json.data?.commands || '');
      showMessage(status, '<p>Generated commands ready.</p>');
    } catch (err) {
      showMessage(status, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  verifyBtn.addEventListener('click', async () => {
    try {
      const platform = (platformInput.value || '').trim();
      const current = (currentInput.value || '').trim();
      const candidate = (candidateInput.value || '').trim();
      if (!current) {
        throw new Error('current is required');
      }
      if (!candidate) {
        throw new Error('candidate is required');
      }

      renderAclDiffTable(diffResults, current, candidate);

      const res = await fetch('/api/acl/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, current, candidate }),
      });
      let json = null;
      try {
        json = await res.json();
      } catch (parseErr) {
        if (!res.ok) {
          throw new Error('backend error. try again');
        }
        throw parseErr;
      }

      if (!res.ok || json.status !== 'success') {
        const backendErrorCode = json?.error?.code || '';
        if (res.status >= 500 || backendErrorCode === 'ACL_VERIFY_ERROR') {
          throw new Error('backend error. try again');
        }
        throw new Error(json?.error?.message || 'ACL verify failed');
      }

      const rows = Array.isArray(json.data?.rows) ? json.data.rows : [];
      if (rows.length === 0) {
        showMessage(verifyResults, '<p>no access changes found.</p>');
        return;
      }

      showMessage(
        status,
        `<p>Verified snapshots: ${escapeHtml(json.data?.compressed_snapshot || 'compressed')} vs ${escapeHtml(json.data?.original_snapshot || 'original')}</p>`
      );
      renderAclVerifyTable(verifyResults, rows);
    } catch (err) {
      showMessage(status, `<p>${escapeHtml(err.message)}</p>`);
      showMessage(verifyResults, '<p>Verification failed.</p>');
    }
  });
}

window.addEventListener('DOMContentLoaded', async () => {
  try {
    installGlobalAjaxSpinner();
    await initIndexPage();
    await initAnalyzePage();
    await initAclOptimizePage();
  } catch (err) {
    console.error(err);
  }
});
