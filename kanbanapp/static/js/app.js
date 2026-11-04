// Global helpers shared by all pages (loaded from base.html).
function csrfToken() {
  return document.querySelector('[name=csrfmiddlewaretoken]');
}

function handleBoxClick(event, url) {
  // If the click happened on an anchor, button, input, select, textarea or form, do not hijack it
  if (event.target.closest('a, button, input, select, textarea, form, label')) {
    return;
  }
  window.location.href = url;
}
