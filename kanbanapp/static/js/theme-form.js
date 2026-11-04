  // Canlı renk senkronizasyonu ve önizleme
  const colorFields = [
    'bg_color', 'bg_soft', 'card_bg', 'card_hover',
    'border_color', 'text_color', 'text_muted',
    'primary_color', 'primary_hover'
  ];

  function updateLivePreview() {
    const vals = {};
    colorFields.forEach(f => {
      const input = document.querySelector(`[name="${f}"]`);
      vals[f] = input ? input.value.trim() : '#000000';
    });

    const c = document.getElementById('livePreviewContainer');
    if (c) {
      c.style.background = vals.bg_color;
      c.style.border = `2px solid ${vals.border_color}`;
    }

    const tb = document.getElementById('prevTopBar');
    if (tb) {
      tb.style.background = vals.bg_soft;
      tb.style.border = `1px solid ${vals.border_color}`;
    }

    const brand = document.getElementById('prevBrand');
    if (brand) brand.style.color = vals.text_color;

    const navLink = document.getElementById('prevNavLink');
    if (navLink) navLink.style.color = vals.primary_color;

    const mutedLink = document.getElementById('prevMutedLink');
    if (mutedLink) mutedLink.style.color = vals.text_muted;

    const card = document.getElementById('prevCard');
    if (card) {
      card.style.background = vals.card_bg;
      card.style.border = `1px solid ${vals.border_color}`;
    }

    const cardTitle = document.getElementById('prevCardTitle');
    if (cardTitle) cardTitle.style.color = vals.text_color;

    const cardText = document.getElementById('prevCardText');
    if (cardText) cardText.style.color = vals.text_color;

    const btn = document.getElementById('prevBtn');
    if (btn) {
      btn.style.background = vals.primary_color;
      btn.style.color = '#ffffff';
    }

    const mutedDate = document.getElementById('prevMutedDate');
    if (mutedDate) mutedDate.style.color = vals.text_muted;

    const subCard = document.getElementById('prevSubCard');
    if (subCard) {
      subCard.style.background = vals.bg_soft;
      subCard.style.border = `1px solid ${vals.border_color}`;
    }

    const subText = document.getElementById('prevSubText');
    if (subText) subText.style.color = vals.text_muted;

    const badge = document.getElementById('prevBadge');
    if (badge) {
      badge.style.background = vals.primary_color;
      badge.style.color = '#ffffff';
    }
  }

  // Input picker ve text eşleştirme
  colorFields.forEach(f => {
    const textInput = document.querySelector(`[name="${f}"]`);
    const pickerInput = document.getElementById(`picker_${f}`);

    if (textInput && pickerInput) {
      // Başlangıç değeri
      if (textInput.value && textInput.value.startsWith('#')) {
        pickerInput.value = textInput.value.trim();
      }

      pickerInput.addEventListener('input', (e) => {
        textInput.value = e.target.value;
        updateLivePreview();
      });

      textInput.addEventListener('input', (e) => {
        if (/^#[0-9a-fA-F]{6}$/.test(e.target.value.trim())) {
          pickerInput.value = e.target.value.trim();
        }
        updateLivePreview();
      });
    }
  });

  function setFieldValue(field, hex) {
    const textInput = document.querySelector(`[name="${field}"]`);
    const pickerInput = document.getElementById(`picker_${field}`);
    if (textInput) textInput.value = hex;
    if (pickerInput) pickerInput.value = hex;
  }

  function randomHex() {
    return '#' + Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0');
  }

  function hslToHex(h, s, l) {
    l /= 100;
    const a = s * Math.min(l, 1 - l) / 100;
    const f = n => {
      const k = (n + h / 30) % 12;
      const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
      return Math.round(255 * color).toString(16).padStart(2, '0');
    };
    return `#${f(0)}${f(8)}${f(4)}`;
  }

  // Tekil alan için rastgele renk
  function randomizeSingleField(field) {
    const hex = randomHex();
    setFieldValue(field, hex);
    updateLivePreview();
  }

  // Tüm renkler için birbiriyle uyumlu (koyu/açık dengeli) rastgele tema paleti
  function randomizeAllThemeColors() {
    const isDark = Math.random() > 0.3; // %70 ihtimalle modern dark tema, %30 light
    const baseHue = Math.floor(Math.random() * 360);
    const primaryHue = (baseHue + Math.floor(Math.random() * 120)) % 360;

    let palette = {};
    if (isDark) {
      // Modern Dark Palette
      palette = {
        bg_color: hslToHex(baseHue, 25, 7 + Math.floor(Math.random() * 5)),         // ~7-11% L
        bg_soft: hslToHex(baseHue, 22, 12 + Math.floor(Math.random() * 4)),         // ~12-15% L
        card_bg: hslToHex(baseHue, 20, 16 + Math.floor(Math.random() * 4)),         // ~16-19% L
        card_hover: hslToHex(baseHue, 20, 21 + Math.floor(Math.random() * 4)),      // ~21-24% L
        border_color: hslToHex(baseHue, 18, 25 + Math.floor(Math.random() * 6)),    // ~25-30% L
        text_color: hslToHex(baseHue, 15, 93 + Math.floor(Math.random() * 4)),      // ~93-96% L
        text_muted: hslToHex(baseHue, 10, 62 + Math.floor(Math.random() * 8)),      // ~62-69% L
        primary_color: hslToHex(primaryHue, 75 + Math.floor(Math.random() * 20), 55),
        primary_hover: hslToHex(primaryHue, 80 + Math.floor(Math.random() * 15), 45),
      };
    } else {
      // Clean Light Palette
      palette = {
        bg_color: hslToHex(baseHue, 20, 96 + Math.floor(Math.random() * 3)),        // ~96-98% L
        bg_soft: hslToHex(baseHue, 18, 92 + Math.floor(Math.random() * 3)),         // ~92-94% L
        card_bg: '#ffffff',
        card_hover: hslToHex(baseHue, 15, 95),
        border_color: hslToHex(baseHue, 15, 82 + Math.floor(Math.random() * 5)),    // ~82-86% L
        text_color: hslToHex(baseHue, 25, 12 + Math.floor(Math.random() * 6)),      // ~12-17% L
        text_muted: hslToHex(baseHue, 12, 45 + Math.floor(Math.random() * 10)),     // ~45-54% L
        primary_color: hslToHex(primaryHue, 75 + Math.floor(Math.random() * 20), 48),
        primary_hover: hslToHex(primaryHue, 80 + Math.floor(Math.random() * 15), 40),
      };
    }

    Object.keys(palette).forEach(f => {
      setFieldValue(f, palette[f]);
    });
    updateLivePreview();
  }

  // Sayfa yüklendiğinde çalıştır
  document.addEventListener('DOMContentLoaded', updateLivePreview);
  updateLivePreview();
