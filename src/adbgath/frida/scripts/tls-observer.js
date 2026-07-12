// ADB-Gath script: tls-observer
// Version: 1.0.0
// Observe TLS socket creation and trust-manager activity without bypassing certificate validation.
'use strict';

Java.perform(function () {
  const Socket = Java.use('javax.net.ssl.SSLSocket');
  Socket.startHandshake.implementation = function () {
    send({event: 'tls-handshake', class: this.$className, timestamp: Date.now()});
    return this.startHandshake();
  };

  try {
    const TrustManagerFactory = Java.use('javax.net.ssl.TrustManagerFactory');
    TrustManagerFactory.getTrustManagers.implementation = function () {
      const managers = this.getTrustManagers();
      send({event: 'trust-managers', count: managers.length, timestamp: Date.now()});
      return managers;
    };
  } catch (error) {
    send({event: 'observer-warning', message: String(error)});
  }
});
