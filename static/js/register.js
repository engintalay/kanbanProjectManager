// Registration form: client-side password match check before submit.
document.querySelector('form').addEventListener('submit', function (e) {
  const p1 = this.querySelector('[name=password1]').value;
  const p2 = this.querySelector('[name=password2]').value;
  if (p1 && p1 !== p2) {
    e.preventDefault();
    alert('Şifreler eşleşmiyor!');
  }
});

// Jira'dan kullanıcı bilgisi çekme (kullanıcı ekleme ekranı).
// Yalnızca alanları otomatik doldurur; Jira zorunlu değildir,
// bağımsız (yerel) kullanıcı oluşturma her zaman mümkündür.
(function () {
  const btn = document.getElementById('jira-lookup-btn');
  if (!btn) return;

  const statusEl = document.getElementById('jira-lookup-status');
  const codeEl = document.getElementById('jira-user-code');
  const connEl = document.getElementById('jira-conn');

  function setStatus(msg, kind) {
    statusEl.textContent = msg || '';
    statusEl.style.color =
      kind === 'error' ? '#ef4444' :
      kind === 'ok' ? '#22c55e' :
      kind === 'warn' ? '#f59e0b' : '';
  }

  function fill(name, value) {
    if (!value) return;
    const input = document.querySelector('form [name=' + name + ']');
    if (input) input.value = value;
  }

  function lookup() {
    const code = (codeEl.value || '').trim();
    if (!code) {
      setStatus('Önce bir Jira kullanıcı kodu yazın (ya da alanları elle doldurun).', 'warn');
      return;
    }
    const csrf = document.querySelector('[name=csrfmiddlewaretoken]');
    btn.disabled = true;
    setStatus('Jira sorgulanıyor…');

    const body = new URLSearchParams();
    body.set('username', code);
    if (connEl) body.set('connection', connEl.value);

    fetch(btn.dataset.lookupUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrf ? csrf.value : '',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: body,
      credentials: 'same-origin'
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          setStatus(data.error || 'Jira sorgusu başarısız — alanları elle doldurabilirsiniz.', 'error');
          return;
        }
        fill('username', data.username);
        fill('email', data.email);
        fill('first_name', data.first_name);
        fill('last_name', data.last_name);

        const notes = ['"' + data.username + '" Jira\'dan getirildi (' + data.connection +
          '). Şimdi yalnızca şifreyi girin.'];
        if (!data.email) notes.push('E-posta Jira\'da görünmüyor, elle girin.');
        if (data.active === false) notes.push('⚠ Bu Jira kullanıcısı devre dışı.');
        if (data.username_taken) notes.push('⚠ Bu kullanıcı adı sistemde zaten kayıtlı!');
        else if (data.email_taken) notes.push('⚠ Bu e-posta başka bir kullanıcıda kayıtlı!');
        const bad = data.username_taken || data.email_taken || data.active === false;
        setStatus(notes.join(' '), bad ? 'warn' : 'ok');
      })
      .catch(function () {
        setStatus('Sunucuyla konuşulamadı (oturum/CSRF). Alanları elle doldurabilirsiniz.', 'error');
      })
      .finally(function () { btn.disabled = false; });
  }

  btn.addEventListener('click', lookup);
  codeEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault(); // form göndermesini engelle
      lookup();
    }
  });
})();
