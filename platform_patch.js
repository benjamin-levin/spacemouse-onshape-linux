(() => {
  Object.defineProperty(Navigator.prototype, "platform", {
    configurable: true,
    get: () => "Win32"
  });
  try {
    Object.defineProperty(navigator, "platform", {
      configurable: true,
      get: () => "Win32"
    });
  } catch (_) {
    // Navigator instance may reject redefinition; prototype override is enough.
  }
  console.log("[Onshape patch] navigator.platform ->", navigator.platform);
})();
