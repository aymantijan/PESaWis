self.addEventListener('push', (event) => {
  let data = { title: 'PESaWis', body: 'You have a new notification.', url: '/notifications/' };
  if (event.data) {
    try { data = event.data.json(); } catch (e) { data.body = event.data.text(); }
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'PESaWis', {
      body: data.body,
      icon: data.icon || '/static/images/pesawis-logo.png',
      badge: '/static/images/pesawis-logo.png',
      data: { url: data.url || '/notifications/' },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/notifications/';
  event.waitUntil(clients.openWindow(url));
});
