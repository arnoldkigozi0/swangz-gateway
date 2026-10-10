"use strict";
/* Installable first-party window. Private HTML/API responses are never cached or intercepted. */
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
// No fetch handler: authentication, live reports and static releases always use the network.
