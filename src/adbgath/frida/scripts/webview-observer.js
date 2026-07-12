// ADB-Gath script: webview-observer
// Version: 1.0.0
// Observe WebView URL loading and JavaScript enablement without modifying application behavior.
'use strict';

Java.perform(function () {
  const WebView = Java.use('android.webkit.WebView');
  WebView.loadUrl.overload('java.lang.String').implementation = function (url) {
    send({event: 'webview-load-url', url: String(url), timestamp: Date.now()});
    return this.loadUrl(url);
  };

  const Settings = Java.use('android.webkit.WebSettings');
  Settings.setJavaScriptEnabled.implementation = function (enabled) {
    send({event: 'webview-javascript', enabled: Boolean(enabled), timestamp: Date.now()});
    return this.setJavaScriptEnabled(enabled);
  };
});
