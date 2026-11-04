  let draggedStatusData = null;

  function openModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.add('active');
  }

  function closeModal(id) {
    const m = document.getElementById(id);
    if (m) m.classList.remove('active');
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      ['addMappingModal', 'moveMappingModal', 'deleteMappingModal', 'bulkManageModal'].forEach(closeModal);
    }
  });

  // Close modals on backdrop click
  document.querySelectorAll('.drag-modal-backdrop').forEach(b => {
    b.addEventListener('click', function(e) {
      if (e.target === b) closeModal(b.id);
    });
  });

  // Filter Pool & Table by Active / Hidden / All
  let currentPoolTab = 'active';

  function filterStatusPool(tab) {
    currentPoolTab = tab;
    document.querySelectorAll('.btn-tab').forEach(b => b.classList.remove('active'));
    if (tab === 'active') document.getElementById('tabActiveStatuses')?.classList.add('active');
    else if (tab === 'hidden') document.getElementById('tabHiddenStatuses')?.classList.add('active');
    else if (tab === 'all') document.getElementById('tabAllStatuses')?.classList.add('active');

    // Filter Chips
    document.querySelectorAll('.jira-status-chip').forEach(chip => {
      const isHidden = chip.dataset.isHidden === 'true';
      if (tab === 'active') {
        chip.style.display = isHidden ? 'none' : 'inline-flex';
      } else if (tab === 'hidden') {
        chip.style.display = isHidden ? 'inline-flex' : 'none';
      } else {
        chip.style.display = 'inline-flex';
      }
    });

    // Filter Table Rows
    document.querySelectorAll('.status-table-row').forEach(row => {
      const isHidden = row.dataset.isHidden === 'true';
      if (tab === 'active') {
        row.style.display = isHidden ? 'none' : '';
      } else if (tab === 'hidden') {
        row.style.display = isHidden ? '' : 'none';
      } else {
        row.style.display = '';
      }
    });
  }

  function openBulkManageModal() {
    openModal('bulkManageModal');
  }

  function filterBulkModalCheckboxes(query) {
    const q = (query || '').toLowerCase().trim();
    document.querySelectorAll('.bulk-status-item').forEach(item => {
      const name = item.dataset.statusName || '';
      item.style.display = name.includes(q) ? 'flex' : 'none';
    });
  }

  function setBulkCheckboxes(checked) {
    document.querySelectorAll('.bulk-hide-checkbox:not(:disabled)').forEach(cb => {
      cb.checked = checked;
    });
  }

  function selectUnmappedForHide() {
    document.querySelectorAll('.bulk-status-item').forEach(item => {
      const isMapped = item.dataset.isMapped === 'true';
      const cb = item.querySelector('.bulk-hide-checkbox');
      if (cb && !isMapped) {
        cb.checked = true;
      }
    });
  }

  // 1. Jira Pool Chips Dragging
  document.querySelectorAll('.jira-status-chip[draggable="true"]').forEach(chip => {
    chip.addEventListener('dragstart', (e) => {
      draggedStatusData = {
        type: 'chip',
        statusId: chip.dataset.jiraStatusId,
        statusName: chip.dataset.jiraStatusName
      };
      chip.classList.add('is-dragging');
      e.dataTransfer.setData('text/plain', JSON.stringify(draggedStatusData));
      e.dataTransfer.effectAllowed = 'copy';
      document.querySelectorAll('.status-drop-zone').forEach(z => z.classList.add('drag-active'));
    });

    chip.addEventListener('dragend', () => {
      chip.classList.remove('is-dragging');
      document.querySelectorAll('.status-drop-zone').forEach(z => {
        z.classList.remove('drag-active');
        z.classList.remove('drag-over');
      });
      draggedStatusData = null;
    });
  });

  // 2. Mapped Cards Dragging (between columns or to unmap zone)
  document.querySelectorAll('.mapped-status-card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', (e) => {
      draggedStatusData = {
        type: 'mapped',
        mappingId: card.dataset.mappingId,
        statusId: card.dataset.jiraStatusId,
        statusName: card.dataset.jiraStatusName,
        columnId: card.dataset.columnId,
        columnName: card.dataset.columnName
      };
      card.classList.add('is-dragging');
      e.dataTransfer.setData('text/plain', JSON.stringify(draggedStatusData));
      e.dataTransfer.effectAllowed = 'move';
      document.querySelectorAll('.status-drop-zone').forEach(z => {
        if (z.dataset.columnId !== card.dataset.columnId) {
          z.classList.add('drag-active');
        }
      });
      const unmapZone = document.getElementById('poolUnmapZone');
      if (unmapZone) unmapZone.classList.add('drag-active');
    });

    card.addEventListener('dragend', () => {
      card.classList.remove('is-dragging');
      document.querySelectorAll('.status-drop-zone').forEach(z => {
        z.classList.remove('drag-active');
        z.classList.remove('drag-over');
      });
      const unmapZone = document.getElementById('poolUnmapZone');
      if (unmapZone) {
        unmapZone.classList.remove('drag-active');
        unmapZone.classList.remove('drag-over');
      }
      draggedStatusData = null;
    });
  });

  // 3. Drop Zones in Columns
  document.querySelectorAll('.status-drop-zone').forEach(zone => {
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', () => {
      zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      zone.classList.remove('drag-active');

      let data = draggedStatusData;
      if (!data) {
        try {
          data = JSON.parse(e.dataTransfer.getData('text/plain'));
        } catch (err) {}
      }
      if (!data) return;

      const targetColId = zone.dataset.columnId;
      const targetColName = zone.dataset.columnName;

      if (data.type === 'chip') {
        document.getElementById('modalColumnId').value = targetColId;
        document.getElementById('modalJiraStatusId').value = data.statusId;
        document.getElementById('modalJiraStatusName').textContent = data.statusName;
        document.getElementById('modalColumnName').textContent = targetColName;
        document.getElementById('modalTransferCheck').checked = true;
        document.getElementById('addMappingModal').classList.add('active');
      } else if (data.type === 'mapped') {
        if (data.columnId === targetColId) return; // Same column
        document.getElementById('moveMappingId').value = data.mappingId;
        document.getElementById('moveTargetColumnId').value = targetColId;
        document.getElementById('moveJiraStatusName').textContent = data.statusName;
        document.getElementById('moveFromColumnName').textContent = data.columnName;
        document.getElementById('moveToColumnName').textContent = targetColName;
        document.getElementById('moveMappingModal').classList.add('active');
      }
    });
  });

  // 4. Unmap Drop Zone
  const unmapZone = document.getElementById('poolUnmapZone');
  if (unmapZone) {
    unmapZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      unmapZone.classList.add('drag-over');
    });

    unmapZone.addEventListener('dragleave', () => {
      unmapZone.classList.remove('drag-over');
    });

    unmapZone.addEventListener('drop', (e) => {
      e.preventDefault();
      unmapZone.classList.remove('drag-over');

      let data = draggedStatusData;
      if (!data) {
        try {
          data = JSON.parse(e.dataTransfer.getData('text/plain'));
        } catch (err) {}
      }
      if (!data || data.type !== 'mapped') return;

      document.getElementById('deleteMappingId').value = data.mappingId;
      document.getElementById('deleteJiraStatusName').textContent = data.statusName;
      document.getElementById('deleteFromColumnName').textContent = data.columnName;
      document.getElementById('deleteMappingModal').classList.add('active');
    });
  }

  // Initialize status pool filter on load
  filterStatusPool('active');
