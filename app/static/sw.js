/* Service worker da Licerta: recebe o push e mostra o aviso na tela do
   aparelho, mesmo com o site fechado — com a cara de um app nativo:
   ícone do app, ícone de status monocromático, hora, botão de ação e
   substituição do aviso antigo sobre o mesmo assunto (tag). */

const VERSAO_SW = 2;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

self.addEventListener('push', (evento) => {
  let dados = {};
  try { dados = evento.data ? evento.data.json() : {}; } catch (e) { /* texto cru */ }
  const titulo = dados.titulo || 'Licerta';
  const urgente = !!dados.urgente;
  const silencioso = !!dados.silencioso;   // preferência da pessoa (Minha conta)
  const opcoes = {
    body: dados.corpo || 'Há novidades no seu radar.',
    icon: '/static/icone-192.png',
    badge: '/static/badge-96.png',
    lang: 'pt-BR',
    tag: dados.tag || 'licerta',
    renotify: true,
    timestamp: dados.quando || Date.now(),
    silent: silencioso,
    requireInteraction: !!dados.fixar,
    vibrate: silencioso ? [] : (urgente ? [200, 100, 200, 100, 200] : [100, 50, 100]),
    data: { url: dados.url || '/' },
    actions: [{ action: 'abrir', title: dados.acao || 'Abrir' }],
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

// O aparelho troca a chave da assinatura de tempos em tempos; sem isto o
// usuário para de receber em silêncio. Reassina e avisa o servidor.
self.addEventListener('pushsubscriptionchange', (evento) => {
  const antiga = evento.oldSubscription;
  evento.waitUntil((async () => {
    const { chave } = await (await fetch('/api/push/chave')).json();
    const nova = await self.registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: chave,
    });
    await fetch('/api/push/assinar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign(nova.toJSON(),
        { anterior: antiga ? antiga.endpoint : null })),
    });
  })());
});
