// Registration form: client-side password match check before submit.
document.querySelector('form').addEventListener('submit', function (e) {
  const p1 = this.querySelector('[name=password1]').value;
  const p2 = this.querySelector('[name=password2]').value;
  if (p1 && p1 !== p2) {
    e.preventDefault();
    alert('Şifreler eşleşmiyor!');
  }
});
