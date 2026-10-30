(() => {
  if (!('serviceWorker' in navigator)) return;

  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/service-worker.js').catch((error) => {
      console.warn('PWA service worker registration failed:', error);
    });
  });

  let installPrompt;
  const installButton = document.createElement('button');
  installButton.type = 'button';
  installButton.className = 'pwa-install-button';
  installButton.textContent = '앱 설치';
  installButton.hidden = true;
  installButton.setAttribute('aria-label', 'STOCKOLON 26 앱 설치');
  document.body.appendChild(installButton);

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    installPrompt = event;
    installButton.hidden = false;
  });

  installButton.addEventListener('click', async () => {
    if (!installPrompt) return;
    installButton.hidden = true;
    await installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
  });

  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    installButton.remove();
  });
})();
