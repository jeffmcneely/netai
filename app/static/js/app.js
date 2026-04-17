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

function renderTable(target, rows, page = 1) {
  target.classList.remove('hidden');
  if (!rows.length) {
    target.innerHTML = '<p>No rows returned.</p>';
    return { pages: 0, page: 0 };
  }

  const columns = Object.keys(rows[0]);
  const start = (page - 1) * PAGE_SIZE;
  const paged = rows.slice(start, start + PAGE_SIZE);

  const header = `<tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}</tr>`;
  const body = paged.map((row) => {
    const cols = columns.map((col) => `<td>${escapeHtml(String(row[col] ?? ''))}</td>`).join('');
    return `<tr>${cols}</tr>`;
  }).join('');

  target.innerHTML = `<div class="table-wrap"><table>${header}${body}</table></div>`;
  return { pages: Math.ceil(rows.length / PAGE_SIZE), page };
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
  };

  document.addEventListener('change', (event) => {
    if (event.target.name === 'folderChoice') {
      onSelectionChange();
    }
  });

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
  const searchPanel = document.getElementById('searchPanel');
  const runSearchBtn = document.getElementById('runSearchBtn');
  const meta = document.getElementById('analysisMeta');
  const results = document.getElementById('results');
  const pager = document.getElementById('pager');

  const folders = await fetchConfigs();
  folders.forEach((f) => folderList.appendChild(makeFolderRadio(f, 'analyzeFolderChoice')));

  document.addEventListener('change', (event) => {
    if (event.target.name === 'analyzeFolderChoice') {
      const selected = document.querySelector('input[name="analyzeFolderChoice"]:checked');
      newField.classList.toggle('hidden', !(selected && selected.value === '__new__'));
    }
  });

  const renderRows = (rows) => {
    let currentPage = 1;
    const draw = () => {
      const pg = renderTable(results, rows, currentPage);
      renderPager(pager, pg.pages, currentPage, (newPage) => {
        currentPage = newPage;
        draw();
      });
    };
    draw();
  };

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

      showMessage(meta, `<p>Snapshot: ${escapeHtml(json.data.snapshot_name)}</p><p>Rows: ${json.data.rows.length}</p>`);
      renderRows(json.data.rows);
    } catch (err) {
      showMessage(meta, `<p>${escapeHtml(err.message)}</p>`);
    }
  });

  searchBtn.addEventListener('click', () => {
    searchPanel.classList.toggle('hidden');
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

      showMessage(meta, `<p>Snapshot: ${escapeHtml(json.data.snapshot_name)}</p><p>Rows: ${json.data.rows.length}</p>`);
      renderRows(json.data.rows);
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
