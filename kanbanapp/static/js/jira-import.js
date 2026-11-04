  function setJql(query) {
    document.getElementById('jql-input').value = query;
    document.getElementById('jql-search-form').submit();
  }

  function toggleSelectAll(master) {
    const checkboxes = document.querySelectorAll('.issue-checkbox');
    checkboxes.forEach(cb => cb.checked = master.checked);
  }

  function addSingle(key) {
    document.getElementById('single-jira-key').value = key;
    document.getElementById('import-form').submit();
  }

  function filterIssuesTable(rawQuery) {
    const q = (rawQuery || '').trim().toLowerCase();
    const rows = document.querySelectorAll('.issue-row');
    const clearBtn = document.getElementById('btn-clear-search');
    let visibleCount = 0;

    if (clearBtn) {
      clearBtn.style.display = q ? 'block' : 'none';
    }

    rows.forEach(row => {
      const searchData = row.getAttribute('data-search') || '';
      if (!q || searchData.includes(q)) {
        row.style.display = '';
        visibleCount++;
      } else {
        row.style.display = 'none';
      }
    });

    const countElem = document.getElementById('issue-count');
    if (countElem) {
      countElem.textContent = visibleCount;
    }
  }

  function clearIssuesSearch() {
    const input = document.getElementById('table-quick-search');
    if (input) {
      input.value = '';
      filterIssuesTable('');
      input.focus();
    }
  }
