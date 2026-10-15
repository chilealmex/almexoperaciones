/* El service worker que hace instalable la aplicación, y nada más.

   Android sólo ofrece "Instalar aplicación" si el sitio registra uno. Éste no
   guarda nada: deja pasar cada petición al servidor tal cual.

   Guardar páginas sería volver al problema que se acaba de arreglar —gente
   mirando datos viejos sin saber que lo son—, y de la peor manera: un service
   worker contesta desde su copia aunque el servidor diga "no-store", y sigue
   haciéndolo después de cerrar sesión. Acá todo lo que se muestra —stock,
   conteos, órdenes— cambia durante el día, y una cifra vieja con cara de
   actual es peor que no tener la pantalla.

   Sin copia guardada, sin conexión no hay nada que mostrar. Es lo correcto:
   esta aplicación no sirve de nada sin el servidor, y fingir lo contrario con
   una pantalla de ayer sería engañar a quien está contando. */

// Al cambiar, el navegador instala la versión nueva. skipWaiting y clients.claim
// la ponen a mandar de inmediato en vez de esperar a que se cierren todas las
// pestañas: así un arreglo acá no queda esperando días en un celular.
self.addEventListener('install', function (evento) {
  evento.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', function (evento) {
  evento.waitUntil(
    // Barre cualquier copia que haya dejado una versión anterior. Si alguna vez
    // se guardó algo, esto lo limpia en el primer arranque.
    caches.keys()
      .then(function (nombres) { return Promise.all(nombres.map(function (n) { return caches.delete(n); })); })
      .then(function () { return self.clients.claim(); })
  );
});

// Sin un manejador de 'fetch' el navegador no considera instalable el sitio.
// Éste no responde: no llama a respondWith, así que la petición sigue su
// camino normal al servidor, igual que si el service worker no existiera.
self.addEventListener('fetch', function () {});
