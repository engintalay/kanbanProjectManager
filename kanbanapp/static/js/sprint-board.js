  function openSprintAddCardModal() {
    const m = document.getElementById('sprintAddCardModal');
    if (m) {
      m.classList.add('active');
      const search = document.getElementById('sprintModalSearchInput');
      if (search) {
        search.value = '';
        filterSprintAvailableCards('');
        setTimeout(() => search.focus(), 50);
      }
    }
  }

  function closeSprintAddCardModal() {
    const m = document.getElementById('sprintAddCardModal');
    if (m) m.classList.remove('active');
  }

  function filterSprintAvailableCards(term) {
    const q = (term || '').trim().toLowerCase();
    const items = document.querySelectorAll('.sprint-card-option');
    let visibleCount = 0;
    items.forEach(el => {
      const text = el.getAttribute('data-card-search') || '';
      if (!q || text.includes(q)) {
        el.style.display = 'flex';
        visibleCount++;
      } else {
        el.style.display = 'none';
      }
    });
    const emptyMsg = document.getElementById('noMatchingAvailableCards');
    if (emptyMsg) {
      emptyMsg.style.display = (visibleCount === 0 && items.length > 0) ? 'block' : 'none';
    }
  }

  const sprintAddBackdrop = document.getElementById('sprintAddCardModal');
  if (sprintAddBackdrop) {
    sprintAddBackdrop.addEventListener('click', function(e) {
      if (e.target === sprintAddBackdrop) closeSprintAddCardModal();
    });
  }

  function toggleSubtasks(e, panelId) {
    if (e) e.stopPropagation();
    const panel = document.getElementById(panelId);
    if (!panel) return;
    panel.classList.toggle('is-hidden');
    const arrow = document.getElementById('arrow-' + panelId);
    if (arrow) arrow.textContent = panel.classList.contains('is-hidden') ? '▸' : '▾';
  }

  function filterBoardCards(filterType, btn) {
    document.querySelectorAll('.board-filter-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    document.querySelectorAll('.board .card').forEach(card => {
      const isSub = card.getAttribute('data-is-subtask') === '1';
      if (filterType === 'all') {
        card.style.display = '';
      } else if (filterType === 'parents') {
        card.style.display = isSub ? 'none' : '';
      } else if (filterType === 'subtasks') {
        card.style.display = isSub ? '' : 'none';
      }
    });
  }

  let draggedCardEl = null;
  let originColumnId = null;
  let originParent = null;
  let originNextSibling = null;
  let moveModalPending = false;

  function showToast(message) {
    let toast = document.getElementById('kanbanToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'kanbanToast';
      toast.className = 'toast-notification';
      document.body.appendChild(toast);
    }
    toast.innerHTML = '<span>✅</span> ' + message;
    toast.classList.add('show');
    clearTimeout(toast._timeout);
    toast._timeout = setTimeout(() => {
      toast.classList.remove('show');
    }, 2500);
  }

  function closeCardMoveModal() {
    const m = document.getElementById('cardMoveModal');
    if (m) m.classList.remove('active');
    if (moveModalPending && draggedCardEl && originParent) {
      originParent.insertBefore(draggedCardEl, originNextSibling);
    }
    moveModalPending = false;
  }

  function submitCardMove(skipJira) {
    document.getElementById('cardMoveSkipJira').value = skipJira ? "1" : "0";
    moveModalPending = false;
    document.getElementById('cardMoveForm').submit();
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeCardMoveModal();
  });

  const cardModalBackdrop = document.getElementById('cardMoveModal');
  if (cardModalBackdrop) {
    cardModalBackdrop.addEventListener('click', function(e) {
      if (e.target === cardModalBackdrop) closeCardMoveModal();
    });
  }

  function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.card:not(.is-dragging)')];
    return draggableElements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset: offset, element: child };
      } else {
        return closest;
      }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  // Card dragging & reordering
  document.querySelectorAll('.card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', (e) => {
      e.stopPropagation();
      draggedCardEl = card;
      const colBody = card.closest('.board-column-body');
      originColumnId = colBody ? colBody.dataset.columnId : null;
      originParent = card.parentNode;
      originNextSibling = card.nextSibling;
      moveModalPending = false;

      card.classList.add('is-dragging');
      e.dataTransfer.setData('text/plain', card.dataset.cardId);
      e.dataTransfer.effectAllowed = 'move';
    });

    card.addEventListener('dragend', (e) => {
      e.stopPropagation();
      if (!draggedCardEl) return;
      draggedCardEl.classList.remove('is-dragging');
      document.querySelectorAll('.board-column-body').forEach(b => b.classList.remove('drag-over'));

      const currentContainer = draggedCardEl.closest('.board-column-body');
      if (!currentContainer) {
        draggedCardEl = null;
        return;
      }

      const currentColumnId = currentContainer.dataset.columnId;
      const currentColumnName = currentContainer.dataset.columnName;

      // 1. Same column reorder
      if (originColumnId === currentColumnId) {
        if (draggedCardEl.nextSibling !== originNextSibling) {
          const cardIds = [...currentContainer.querySelectorAll('.card')].map(c => c.dataset.cardId);
          fetch(BOARD_CONFIG.reorderCardsUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": csrfToken().value,
              "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({
              column_id: currentColumnId,
              card_ids: cardIds
            })
          })
          .then(res => res.json())
          .then(data => {
            showToast("Kart sıralaması güncellendi.");
          })
          .catch(err => {
            console.error("Sıralama hatası:", err);
          });
        }
        draggedCardEl = null;
      }
      // 2. Different column move
      else {
        moveModalPending = true;
        const newCardsInCol = [...currentContainer.querySelectorAll('.card')];
        const targetPos = newCardsInCol.indexOf(draggedCardEl);

        const form = document.getElementById('cardMoveForm');
        form.action = BOARD_CONFIG.moveCardBase + draggedCardEl.dataset.cardId + "/move/";
        document.getElementById('cardMoveTargetColumnId').value = currentColumnId;
        document.getElementById('cardMovePosition').value = targetPos >= 0 ? targetPos : "";
        document.getElementById('cardMoveTitle').textContent = draggedCardEl.dataset.cardTitle;
        document.getElementById('cardMoveTargetColName').textContent = currentColumnName;

        const jiraInfo = document.getElementById('cardMoveJiraInfo');
        const skipBtn = document.getElementById('cardMoveSkipBtn');
        const hasJira = Boolean(draggedCardEl.dataset.jiraKey) && BOARD_CONFIG.hasJira;

        if (hasJira) {
          jiraInfo.style.display = 'block';
          skipBtn.style.display = 'inline-block';
        } else {
          jiraInfo.style.display = 'none';
          skipBtn.style.display = 'none';
        }

        document.getElementById('cardMoveModal').classList.add('active');
      }
    });
  });

  // Card & Subtask Click to Edit Navigation
  let isCardDragging = false;
  document.querySelectorAll('.card[draggable="true"]').forEach(card => {
    card.addEventListener('dragstart', () => { isCardDragging = true; });
    card.addEventListener('dragend', () => { setTimeout(() => { isCardDragging = false; }, 100); });
  });

  document.querySelectorAll('.card.clickable-box').forEach(card => {
    card.addEventListener('click', (e) => {
      if (isCardDragging) return;
      if (e.target.closest('a, button, input, select, textarea, form, label, .subtask-item-card, .card-subtasks-panel')) {
        return;
      }
      const editUrl = card.dataset.editUrl;
      if (editUrl) {
        window.location.href = editUrl;
      }
    });
  });

  document.querySelectorAll('.subtask-item-card.clickable-box').forEach(sub => {
    sub.addEventListener('click', (e) => {
      if (e.target.closest('a, button, input, select, textarea, form, label')) {
        return;
      }
      e.stopPropagation();
      const editUrl = sub.dataset.editUrl;
      if (editUrl) {
        window.location.href = editUrl;
      }
    });
  });

  // Column bodies drop targets with live slotting
  document.querySelectorAll('.board-column-body').forEach(body => {
    body.addEventListener('dragover', (e) => {
      if (!draggedCardEl) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      body.classList.add('drag-over');

      const afterElement = getDragAfterElement(body, e.clientY);
      if (afterElement == null) {
        body.appendChild(draggedCardEl);
      } else {
        body.insertBefore(draggedCardEl, afterElement);
      }
    });

    body.addEventListener('dragleave', (e) => {
      if (!body.contains(e.relatedTarget)) {
        body.classList.remove('drag-over');
      }
    });

    body.addEventListener('drop', (e) => {
      if (!draggedCardEl) return;
      e.preventDefault();
      body.classList.remove('drag-over');
    });
  });

  // --- Column Drag & Drop Reordering ---
  const boardEl = document.querySelector('.board');
  let draggedColumnEl = null;
  let originColNextSibling = null;

  function getDragAfterColumn(container, x) {
    const draggableElements = [...container.querySelectorAll('.board-column:not(.is-col-dragging)')];
    return draggableElements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = x - box.left - box.width / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset: offset, element: child };
      } else {
        return closest;
      }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  if (BOARD_CONFIG.canReorderColumns) {
  document.querySelectorAll('.board-column').forEach(col => {
    const header = col.querySelector('.board-column-header');

    if (header) {
      header.addEventListener('mousedown', (e) => {
        if (e.target.closest('a, button, select, input, form, .status-map-status')) {
          col.draggable = false;
          return;
        }
        col.draggable = true;
      });

      header.addEventListener('mouseup', () => {
        if (!draggedColumnEl) col.draggable = false;
      });
      header.addEventListener('mouseleave', () => {
        if (!draggedColumnEl) col.draggable = false;
      });
    }

    col.addEventListener('dragstart', (e) => {
      if (draggedCardEl || e.target.closest('.card') || e.target.closest('a, button, select, input, form')) {
        col.draggable = false;
        return;
      }
      draggedColumnEl = col;
      originColNextSibling = col.nextSibling;
      col.classList.add('is-col-dragging');
      if (boardEl) boardEl.classList.add('col-drag-active');
      e.dataTransfer.setData('text/plain', 'column:' + col.dataset.columnId);
      e.dataTransfer.effectAllowed = 'move';
    });

    col.addEventListener('dragend', () => {
      if (!draggedColumnEl) return;
      col.classList.remove('is-col-dragging');
      col.draggable = false;
      if (boardEl) boardEl.classList.remove('col-drag-active');

      if (draggedColumnEl.nextSibling !== originColNextSibling) {
        const columnIds = [...boardEl.querySelectorAll('.board-column')].map(c => c.dataset.columnId);
        fetch(BOARD_CONFIG.reorderColumnsUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken().value,
            "X-Requested-With": "XMLHttpRequest"
          },
          body: JSON.stringify({
            column_ids: columnIds
          })
        })
        .then(res => res.json())
        .then(data => {
          showToast("Kolon sıralaması güncellendi.");
        })
        .catch(err => {
          console.error("Kolon sıralama hatası:", err);
        });
      }
      draggedColumnEl = null;
    });
  });

  if (boardEl) {
    boardEl.addEventListener('dragover', (e) => {
      if (!draggedColumnEl) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';

      const afterElement = getDragAfterColumn(boardEl, e.clientX);
      if (afterElement == null) {
        boardEl.appendChild(draggedColumnEl);
      } else {
        boardEl.insertBefore(draggedColumnEl, afterElement);
      }
    });

    boardEl.addEventListener('drop', (e) => {
      if (draggedColumnEl) {
        e.preventDefault();
      }
    });
  }
  }
