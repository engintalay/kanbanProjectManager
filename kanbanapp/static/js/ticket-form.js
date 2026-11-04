  (function() {
    const fileInput = document.getElementById('attachments');
    const previewContainer = document.getElementById('pasted-images-preview');
    const dropzone = document.getElementById('paste-dropzone');
    let transfer = new DataTransfer();

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
      setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }

    function addFileToTransfer(file) {
      transfer.items.add(file);
      fileInput.files = transfer.files;
      renderPreviews();
    }

    function removeFile(index) {
      const newTransfer = new DataTransfer();
      for (let i = 0; i < transfer.files.length; i++) {
        if (i !== index) {
          newTransfer.items.add(transfer.files[i]);
        }
      }
      transfer = newTransfer;
      fileInput.files = transfer.files;
      renderPreviews();
    }

    function renderPreviews() {
      previewContainer.innerHTML = '';
      if (transfer.files.length === 0) {
        previewContainer.style.display = 'none';
        return;
      }
      previewContainer.style.display = 'flex';

      for (let i = 0; i < transfer.files.length; i++) {
        const file = transfer.files[i];
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
          return function() { removeFile(idx); };
        })(i);
        card.appendChild(removeBtn);

        previewContainer.appendChild(card);
      }
    }

    // Dosya seçim kutusundan dosya eklendiğinde
    fileInput.addEventListener('change', function() {
      for (let i = 0; i < fileInput.files.length; i++) {
        transfer.items.add(fileInput.files[i]);
      }
      fileInput.files = transfer.files;
      renderPreviews();
    });

    // Sayfa genelinde veya formda Ctrl+V (Paste) dinle
    window.addEventListener('paste', function(e) {
      const clipboardData = e.clipboardData || window.clipboardData;
      if (!clipboardData || !clipboardData.items) return;

      let imagePasted = false;
      const items = clipboardData.items;

      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          const blob = items[i].getAsFile();
          if (blob) {
            imagePasted = true;
            const now = new Date();
            const timeStr = now.getFullYear() +
              String(now.getMonth()+1).padStart(2,'0') +
              String(now.getDate()).padStart(2,'0') + '_' +
              String(now.getHours()).padStart(2,'0') +
              String(now.getMinutes()).padStart(2,'0') +
              String(now.getSeconds()).padStart(2,'0');
            const ext = blob.type.split('/')[1] || 'png';
            const fileName = `ekran_goruntusu_${timeStr}_${transfer.files.length + 1}.${ext}`;
            const file = new File([blob], fileName, { type: blob.type || 'image/png' });

            addFileToTransfer(file);
          }
        }
      }

      if (imagePasted) {
        showToast('📋 Ekran görüntüsü panodan eklendi!');
        // Eğer odak bir input veya textarea içindeyse varsayılan metin yapıştırmayı engelle
        e.preventDefault();
      }
    });

    // Sürükle - Bırak (Drag & Drop)
    dropzone.addEventListener('dragover', function(e) {
      e.preventDefault();
      dropzone.classList.add('drag-active');
    });
    dropzone.addEventListener('dragleave', function() {
      dropzone.classList.remove('drag-active');
    });
    dropzone.addEventListener('drop', function(e) {
      e.preventDefault();
      dropzone.classList.remove('drag-active');
      if (e.dataTransfer && e.dataTransfer.files) {
        for (let i = 0; i < e.dataTransfer.files.length; i++) {
          addFileToTransfer(e.dataTransfer.files[i]);
        }
        showToast('📎 Dosyalar eklendi.');
      }
    });

  })();
