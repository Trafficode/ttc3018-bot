import {signal} from '@preact/signals';

export const installPrompt = signal(null);
export const installed = signal(window.matchMedia('(display-mode: standalone)').matches);
window.addEventListener('beforeinstallprompt', event => {event.preventDefault();installPrompt.value=event;});
window.addEventListener('appinstalled', () => {installed.value=true;installPrompt.value=null;});

export function attachAppLifecycle(controller) {
  // Returning to a suspended Android app requires fresh server evidence before
  // manual controls become available. Never restore a browser's old live state.
  const refresh = () => {controller.offline.value=true;controller.refresh(true);};
  window.addEventListener('offline', () => {controller.offline.value=true;});
  window.addEventListener('online', refresh);
  document.addEventListener('visibilitychange', () => {if(document.visibilityState==='visible')refresh();});
  if (window.isSecureContext && 'serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'}).catch(()=>{
      // The live panel remains usable if registration fails; no fake installed state.
    });
  }
}
