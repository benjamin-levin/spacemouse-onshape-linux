// ==UserScript==
// @name         Onshape 3D-Mouse on Linux (in-page patch)
// @namespace    local.spacemouse.onshape
// @version      0.0.1-local
// @description  Fake the platform property on navigator to convince Onshape it's running under Windows.
// @match        https://cad.onshape.com/documents/*
// @match        https://*.onshape.com/documents/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

Object.defineProperty(Navigator.prototype, "platform", {
  get: () => "Win32"
});

console.log("[Onshape patch] navigator.platform ->", navigator.platform);
