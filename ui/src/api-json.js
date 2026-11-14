// A missing acknowledgement must never become an automatic machine retry.
export async function readApiJson(response, mutation=false) {
  let value;
  try {
    value=await response.json();
    if(!value || typeof value!=='object' || Array.isArray(value))throw new Error();
  } catch {
    throw new Error(`Panel zwrócił pustą lub nieprawidłową odpowiedź (HTTP ${response.status || '?'}). ${mutation?'Przyjęcie polecenia nie zostało potwierdzone. Sprawdź stan stanowiska przed ponowieniem.':'Odśwież stan stanowiska.'}`);
  }
  if(!response.ok)throw new Error(value.error || `Błąd panelu (HTTP ${response.status || '?'}).`);
  return value;
}
