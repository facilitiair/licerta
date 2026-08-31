/* Service worker do Radar de Licitações: recebe o push e mostra o aviso
   na tela do aparelho, mesmo com o site fechado. */

self.addEventListener('push', (evento) => {
  let dados = {};
  try { dados = evento.data ? evento.data.json() : {}; } catch (e) { /* texto cru */ }
  const titulo = dados.titulo || '📡 Radar de Licitações';
  const opcoes = {
    body: dados.corpo || 'Há novidades no seu radar.',
    icon: '/static/icone-192.png',
    badge: '/static/icone-192.png',
    data: { url: dados.url || '/' },
  };
  evento.waitUntil(self.registration.showNotification(titulo, opcoes));
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  const url = (evento.notification.data && evento.notification.data.url) || '/';
  evento.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true })
    .then((janelas) => {
      for (const j of janelas) {
        if ('focus' in j) { j.navigate(url); return j.focus(); }
      }
      return clients.openWindow(url);
    }));
});
