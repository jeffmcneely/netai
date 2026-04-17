const PAGE_SIZE = 250;

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

function renderFindObjectTable(target, rows, page = 1) {
  target.classList.remove('hidden');
  if (!rows.length) {
    target.innerHTML = '<p>No matching objects found.</p>';
    return { pages: 0, page: 0 };
  }

  const start = (page - 1) * PAGE_SIZE;
  const paged = rows.slice(start, start + PAGE_SIZE);
  const header = '<tr><th>File</th><th>Line</th><th>Matched Object</th><th>Capture</th><th>View</th></tr>';
  const body = paged.map((row, idx) => {
    const rowIndex = start + idx;
    return `<tr>
      <td>${escapeHtml(row.filename || '')}</td>
      <td>${escapeHtml(String(row.line_number || ''))}</td>
      <td>${escapeHtml(row.matched_object || '')}</td>
      <td>${escapeHtml(row.capture || '')}</td>
      <td><button type="button" class="find-object-open-btn" data-find-row-index="${rowIndex}">open file</button></td>
    </tr>`;
  }).join('');

  target.innerHTML = `<h4>Find Object Results (${rows.length})</h4><div class="table-wrap"><table>${header}${body}</table></div>`;
  return { pages: Math.ceil(rows.length / PAGE_SIZE), page };
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
  const searchBtn = document.getElementById('searchBtn');
  const findObjectBtn = document.getElementById('findObjectBtn');
  const searchPanel = document.getElementById('searchPanel');
  const findObjectPanel = document.getElementById('findObjectPanel');
  const findObjectIp = document.getElementById('findObjectIp');
  const runFindObjectBtn = document.getElementById('runFindObjectBtn');
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
  let snapshotName = '';

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
    fileViewerFlyoutBody.innerHTML = '';
  };

  const openDetailFlyout = (kind, row) => {
    const data = kind === 'flow' ? row.Flow : row.Trace;
    if (!data) {
      return;
    }

    const title = kind === 'flow' ? 'Flow Details' : 'Trace Details';
    detailFlyoutTitle.textContent = title;
    detailFlyoutBody.innerHTML = renderDetailTable(title, data);
    detailFlyout.classList.remove('hidden');
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
      const pg = renderAnalyzeTable(results, rows, currentPage);
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
    const btn = event.target.closest('.detail-btn');
    if (!btn) {
      return;
    }

    const kind = btn.getAttribute('data-kind');
    const rowIndex = Number(btn.getAttribute('data-row-index'));
    const row = filteredRows[rowIndex];
    if (!row || (kind !== 'flow' && kind !== 'trace')) {
      return;
    }

    openDetailFlyout(kind, row);
  });

  applyClientMatchBtn.addEventListener('click', () => {
    const filters = getClientMatchFilters();
    filteredRows = allRows.filter((row) => matchesClientFilters(row, filters));
    closeDetailFlyout();
    updateMeta(filteredRows.length, allRows.length);
    renderRows(filteredRows);
  });

  findObjectResults.addEventListener('click', async (event) => {
    const btn = event.target.closest('.find-object-open-btn');
    if (!btn) {
      return;
    }

    const rowIndex = Number(btn.getAttribute('data-find-row-index'));
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

  searchBtn.addEventListener('click', () => {
    searchPanel.classList.toggle('hidden');
  });

  findObjectBtn.addEventListener('click', () => {
    findObjectPanel.classList.toggle('hidden');
  });

  runFindObjectBtn.addEventListener('click', async () => {
    try {
      const ip = (findObjectIp.value || '').trim();
      if (!ip) {
        throw new Error('IP is required');
      }

      const folderInfo = getFolderSelection('analyzeFolderChoice', 'analyzeNewFolderName');
      const body = {
        ...folderInfo,
        ip,
      };

      const res = await fetch('/api/find-object', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (json.status !== 'success') {
        throw new Error(json.error?.message || 'Find object failed');
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

window.addEventListener('DOMContentLoaded', async () => {
  try {
    await initIndexPage();
    await initAnalyzePage();
  } catch (err) {
    console.error(err);
  }
});
