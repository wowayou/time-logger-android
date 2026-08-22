// 时间尺 Android 壳 —— localStorage 桥（document-start 注入）
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// 目的：让 assets/app/ 里那份**一个字节都没改**的 web 运行时，把数据读写到原生
// 存储上（原生小组件/磁贴/通知才写得进同一份数据）。做法是在页面任何脚本之前
// 把 window.localStorage 换成一个由 @JavascriptInterface 支撑的同步实现——
// JavascriptInterface 的调用是同步的、能返回值，所以 localStorage 的同步语义
// 可以逐条对上，运行时侧不需要任何改动。
(function () {
  'use strict';
  var N = window.__tlNative;
  // 没有原生宿主（例如在桌面浏览器里打开同一份 assets 调试）时什么都不做，
  // 让浏览器自带的 localStorage 照常工作。
  if (!N || typeof N.getItem !== 'function') return;

  function quotaError(name) {
    // storage.js 的 save()/saveConfig() 只判断「抛没抛」，不看类型；这里仍然给出
    // 与浏览器同名的错误，便于日志辨认。
    var err = new Error(name || 'QuotaExceededError');
    err.name = name || 'QuotaExceededError';
    return err;
  }

  var shim = {
    getItem: function (k) {
      var v = N.getItem(String(k));
      return v === null || v === undefined ? null : String(v);
    },
    setItem: function (k, v) {
      var err = N.setItem(String(k), String(v));
      if (err) throw quotaError(String(err));
    },
    removeItem: function (k) { N.removeItem(String(k)); },
    clear: function () { N.clear(); },
    key: function (i) {
      var v = N.key(i | 0);
      return v === null || v === undefined ? null : String(v);
    }
  };
  Object.defineProperty(shim, 'length', {
    get: function () { return N.length(); }
  });

  try {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: function () { return shim; }
    });
  } catch (e) {
    // 换不掉就宁可什么都不做：让运行时用 WebView 自己的 localStorage，数据仍在
    // 本机、仍可导出，只是原生入口写不进同一份——比半桥半原生的分裂状态安全。
    if (N.onShimFailed) N.onShimFailed(String(e));
    return;
  }

  // Service Worker 在 APK 里没有用处，而它 cache-first 的缓存会在升级后继续吐旧
  // 代码（升了包却还是旧界面）。给一个语义完整的桩：register() 走 reject，
  // app.js 那边有 .catch(() => {})；getRegistration() 给 undefined，那边有 if (!reg)。
  // 不能把 navigator.serviceWorker 定义成 undefined —— app.js 先判断的是
  // `'serviceWorker' in navigator`，own 属性存在时它仍为 true，接着就会对
  // undefined 取 addEventListener 而抛错。
  try {
    var swStub = {
      controller: null,
      addEventListener: function () {},
      removeEventListener: function () {},
      register: function () { return Promise.reject(new Error('service worker disabled in app shell')); },
      getRegistration: function () { return Promise.resolve(undefined); },
      getRegistrations: function () { return Promise.resolve([]); }
    };
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      get: function () { return swStub; }
    });
  } catch (e2) { /* 桩装不上也不致命：资产加载器对 sw.js 返回 404，注册照样失败 */ }

  // 原生侧写入后调这个函数，让已经打开的界面按它自己的跨标签逻辑刷新
  // （app.js 监听 'storage'：有 sheet 打开时显示横幅，否则直接 render）。
  window.__tlNotifyStorage = function (key, newValue, oldValue) {
    try {
      var ev = new StorageEvent('storage', {
        key: key,
        newValue: newValue === undefined ? null : newValue,
        oldValue: oldValue === undefined ? null : oldValue,
        storageArea: shim
      });
      window.dispatchEvent(ev);
    } catch (e3) {
      // 老 WebView 构造不出 StorageEvent 时退化成普通事件对象。
      try {
        var fake = new Event('storage');
        fake.key = key; fake.newValue = newValue; fake.oldValue = oldValue;
        window.dispatchEvent(fake);
      } catch (e4) {}
    }
  };
})();
