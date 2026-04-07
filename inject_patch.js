(() => {
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("platform_patch.js");
  script.async = false;
  (document.documentElement || document.head || document).appendChild(script);
  script.remove();
})();
