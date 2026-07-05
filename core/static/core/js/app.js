document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-nav]');
  if (toggle && nav) {
    toggle.addEventListener('click', () => nav.classList.toggle('open'));
  }

  initPushNotifications();
  initTagPickers();
  initLikeAnimations();
});

function getCookie(name) {
  const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return match ? decodeURIComponent(match.pop()) : '';
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

function initPushNotifications() {
  const btn = document.querySelector('[data-push-toggle]');
  if (!btn || !('serviceWorker' in navigator) || !('PushManager' in window)) {
    if (btn) btn.style.display = 'none';
    return;
  }
  const body = document.body;
  const vapidKey = body.getAttribute('data-vapid-key');
  const subscribeUrl = body.getAttribute('data-subscribe-url');
  const unsubscribeUrl = body.getAttribute('data-unsubscribe-url');
  if (!vapidKey) return;

  navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(async (registration) => {
    const existing = await registration.pushManager.getSubscription();
    updateButtonState(btn, !!existing);

    btn.addEventListener('click', async () => {
      const current = await registration.pushManager.getSubscription();
      if (current) {
        await fetch(unsubscribeUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ endpoint: current.endpoint }),
        });
        await current.unsubscribe();
        updateButtonState(btn, false);
        return;
      }
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') return;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });
      await fetch(subscribeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
        body: JSON.stringify(subscription.toJSON()),
      });
      updateButtonState(btn, true);
    });
  }).catch(() => { btn.style.display = 'none'; });
}

function updateButtonState(btn, active) {
  btn.textContent = active ? '🔕 Alerts on' : '📲 Enable alerts';
  btn.classList.toggle('active', active);
}

function initTagPickers() {
  document.querySelectorAll('select.tag-select').forEach((select) => {
    if (select.dataset.enhanced) return;
    select.dataset.enhanced = 'true';
    select.multiple = true;
    select.classList.add('tag-select-native');
  });
}

function initLikeAnimations() {
  document.querySelectorAll('[data-like-form]').forEach((form) => {
    form.addEventListener('submit', () => {
      const heart = form.querySelector('[data-like-icon]');
      if (heart) {
        heart.classList.remove('pop');
        void heart.offsetWidth;
        heart.classList.add('pop');
      }
    });
  });
}
