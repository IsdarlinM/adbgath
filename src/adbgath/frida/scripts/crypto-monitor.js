// ADB-Gath script: crypto-monitor
// Version: 1.0.0
// Observe Java cryptographic algorithm selection; no keys or plaintext are exported.
'use strict';

Java.perform(function () {
  const Cipher = Java.use('javax.crypto.Cipher');
  Cipher.getInstance.overload('java.lang.String').implementation = function (transformation) {
    send({event: 'cipher-instance', transformation: String(transformation), timestamp: Date.now()});
    return this.getInstance(transformation);
  };

  const MessageDigest = Java.use('java.security.MessageDigest');
  MessageDigest.getInstance.overload('java.lang.String').implementation = function (algorithm) {
    send({event: 'digest-instance', algorithm: String(algorithm), timestamp: Date.now()});
    return this.getInstance(algorithm);
  };
});
