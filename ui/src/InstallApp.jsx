import {useState} from 'preact/hooks';
import {IconDownload} from '@tabler/icons-preact';
import {installPrompt, installed} from './pwa.js';
import './pwa.css';

export function InstallApp() {
  const [message,setMessage]=useState('');
  async function install() {
    const prompt=installPrompt.value;
    if(!prompt)return;
    installPrompt.value=null;
    try {await prompt.prompt();const result=await prompt.userChoice;setMessage(result.outcome==='accepted'?'Potwierdzono instalację w przeglądarce.':'Instalację anulowano. Możesz wrócić do niej z menu Chrome.');}
    catch {setMessage('Otwórz menu Chrome i wybierz „Zainstaluj aplikację” lub „Dodaj do ekranu głównego”.');}
  }
  if(installed.value)return <p>Aplikacja jest zainstalowana. Tailscale i połączenie ze stanowiskiem są nadal wymagane.</p>;
  return <section class="app-install" aria-label="Instalacja aplikacji"><strong>Aplikacja na Androidzie</strong>
    {installPrompt.value ? <button type="button" onClick={install}><IconDownload size={18}/>Zainstaluj aplikację</button> : <p>{window.isSecureContext ? 'W Chrome otwórz menu ⋮ → Zainstaluj aplikację lub Dodaj do ekranu głównego.' : 'Instalacja wymaga prywatnego adresu HTTPS stanowiska, otwartego w Chrome.'}</p>}
    <p>Ikona uruchomi ten sam panel. Po utracie połączenia sterowanie jest niedostępne.</p>{message && <p role="status">{message}</p>}
  </section>;
}
