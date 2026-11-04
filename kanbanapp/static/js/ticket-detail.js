  function toggleAttachmentPanel(show) {
    const panel = document.getElementById('add-attachment-panel');
    if (show !== undefined) {
      panel.style.display = show ? 'block' : 'none';
    } else {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    }
  }

  (function() {
    function showToast(msg) {
      let toast = document.getElementById('global-toast');
      if (!toast) {
        toast = document.createElement('div');
        toast.id = 'global-toast';
        toast.className = 'toast-notification';
        document.body.appendChild(toast);
      }
      toast.textContent = msg;
      toast.classList.add('show');
      setTimeout(() => { toast.classList.remove('show'); }, 3200);
    }

    // -------------------------------------------------------------
    // 1. Mesajlaşma Alanı (Chat reply) Paste & Önizleme
    // -------------------------------------------------------------
    const chatInput = document.getElementById('id_message');
    const chatFileInput = document.getElementById('id_attachment');
    const chatPreviewBox = document.getElementById('chat-attachment-preview');
    const chatPreviewImg = document.getElementById('chat-preview-img');
    const chatPreviewDoc = document.getElementById('chat-preview-doc');
    const chatPreviewName = document.getElementById('chat-preview-name');
    const chatPreviewSize = document.getElementById('chat-preview-size');
    const btnRemoveChatAtt = document.getElementById('btn-remove-chat-att');

    function updateChatPreview(file) {
      if (!file) {
        chatPreviewBox.style.display = 'none';
        chatFileInput.value = '';
        return;
      }
      chatPreviewBox.style.display = 'block';
      chatPreviewName.textContent = file.name;
      chatPreviewSize.textContent = `(${(file.size / 1024).toFixed(1)} KB)`;

      if (file.type.startsWith('image/')) {
        chatPreviewImg.src = URL.createObjectURL(file);
        chatPreviewImg.style.display = 'block';
        chatPreviewDoc.style.display = 'none';
      } else {
        chatPreviewImg.style.display = 'none';
        chatPreviewDoc.style.display = 'block';
      }
    }

    if (chatFileInput) {
      chatFileInput.addEventListener('change', function() {
        if (chatFileInput.files && chatFileInput.files[0]) {
          updateChatPreview(chatFileInput.files[0]);
        } else {
          updateChatPreview(null);
        }
      });
    }

    if (btnRemoveChatAtt) {
      btnRemoveChatAtt.addEventListener('click', function() {
        updateChatPreview(null);
      });
    }

    function attachFileToChat(file) {
      const dt = new DataTransfer();
      dt.items.add(file);
      chatFileInput.files = dt.files;
      updateChatPreview(file);
      showToast('📋 Ekran görüntüsü mesaja eklendi!');
    }

    // -------------------------------------------------------------
    // 2. Ekler ve Galerisi Alanı (Attachments Panel) Paste & Önizleme
    // -------------------------------------------------------------
    const detailFileInput = document.getElementById('detail-file-input');
    const detailPreviewContainer = document.getElementById('detail-pasted-preview');
    const detailDropzone = document.getElementById('detail-paste-dropzone');
    let detailTransfer = new DataTransfer();

    function renderDetailPreviews() {
      if (!detailPreviewContainer) return;
      detailPreviewContainer.innerHTML = '';
      if (detailTransfer.files.length === 0) {
        detailPreviewContainer.style.display = 'none';
        return;
      }
      detailPreviewContainer.style.display = 'flex';

      for (let i = 0; i < detailTransfer.files.length; i++) {
        const file = detailTransfer.files[i];
        const card = document.createElement('div');
        card.className = 'pasted-thumb-card';

        if (file.type.startsWith('image/')) {
          const img = document.createElement('img');
          img.src = URL.createObjectURL(file);
          img.alt = file.name;
          card.appendChild(img);
        } else {
          const doc = document.createElement('div');
          doc.className = 'pasted-doc-icon';
          doc.textContent = '📄';
          card.appendChild(doc);
        }

        const info = document.createElement('div');
        info.className = 'pasted-thumb-info';
        info.innerHTML = `<strong>${file.name}</strong><br><span class="text-muted">${(file.size / 1024).toFixed(1)} KB</span>`;
        card.appendChild(info);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn-thumb-remove';
        removeBtn.innerHTML = '&times;';
        removeBtn.title = 'Kaldır';
        removeBtn.onclick = (function(idx) {
          return function() {
            const newDt = new DataTransfer();
            for (let j = 0; j < detailTransfer.files.length; j++) {
              if (j !== idx) newDt.items.add(detailTransfer.files[j]);
            }
            detailTransfer = newDt;
            detailFileInput.files = detailTransfer.files;
            renderDetailPreviews();
          };
        })(i);
        card.appendChild(removeBtn);

        detailPreviewContainer.appendChild(card);
      }
    }

    if (detailFileInput) {
      detailFileInput.addEventListener('change', function() {
        for (let i = 0; i < detailFileInput.files.length; i++) {
          detailTransfer.items.add(detailFileInput.files[i]);
        }
        detailFileInput.files = detailTransfer.files;
        renderDetailPreviews();
      });
    }

    function attachFileToDetail(file) {
      toggleAttachmentPanel(true);
      detailTransfer.items.add(file);
      detailFileInput.files = detailTransfer.files;
      renderDetailPreviews();
      showToast('📋 Ekran görüntüsü eklendi! "Yükle" butonuna basarak kaydedebilirsiniz.');
    }

    if (detailDropzone) {
      detailDropzone.addEventListener('dragover', function(e) {
        e.preventDefault();
        detailDropzone.classList.add('drag-active');
      });
      detailDropzone.addEventListener('dragleave', function() {
        detailDropzone.classList.remove('drag-active');
      });
      detailDropzone.addEventListener('drop', function(e) {
        e.preventDefault();
        detailDropzone.classList.remove('drag-active');
        if (e.dataTransfer && e.dataTransfer.files) {
          for (let i = 0; i < e.dataTransfer.files.length; i++) {
            detailTransfer.items.add(e.dataTransfer.files[i]);
          }
          detailFileInput.files = detailTransfer.files;
          renderDetailPreviews();
          showToast('📎 Dosyalar eklendi.');
        }
      });
    }

    // -------------------------------------------------------------
    // 3. Genel Sayfa Paste (Ctrl+V) Yöneticisi
    // -------------------------------------------------------------
    window.addEventListener('paste', function(e) {
      const clipboardData = e.clipboardData || window.clipboardData;
      if (!clipboardData || !clipboardData.items) return;

      const items = clipboardData.items;
      let pastedFile = null;

      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          const blob = items[i].getAsFile();
          if (blob) {
            const now = new Date();
            const timeStr = now.getFullYear() +
              String(now.getMonth()+1).padStart(2,'0') +
              String(now.getDate()).padStart(2,'0') + '_' +
              String(now.getHours()).padStart(2,'0') +
              String(now.getMinutes()).padStart(2,'0') +
              String(now.getSeconds()).padStart(2,'0');
            const ext = blob.type.split('/')[1] || 'png';
            const fileName = `ekran_goruntusu_${timeStr}.${ext}`;
            pastedFile = new File([blob], fileName, { type: blob.type || 'image/png' });
            break;
          }
        }
      }

      if (pastedFile) {
        const activeEl = document.activeElement;
        const isChatFocused = activeEl && (
          activeEl === chatInput ||
          activeEl.closest('#ticket-chat-form')
        );

        if (isChatFocused) {
          attachFileToChat(pastedFile);
        } else {
          attachFileToDetail(pastedFile);
        }
        e.preventDefault();
      }
    });

  })();
