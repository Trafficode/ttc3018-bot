import {IconPlayerStop} from '@tabler/icons-preact';
import {jogStep, jogAllowed} from './jog.js';
import './jog.css';
import {ParameterField} from './ParameterField.jsx';

export function JogPanel({controller, cnc, step, onStep, customStep, onCustomStep, feed, onFeed}) {
  const distance = jogStep(step, customStep);
  const limits = cnc.jog_limits_mm || {X:10, Y:10, Z:10};
  const validFeed = String(feed).trim() !== '' && Number.isFinite(Number(feed)) && Number(feed) >= 1 && Number(feed) <= 300;
  const allowed = axis => controller.manualReady.value && validFeed && jogAllowed(distance, axis, limits);
  function move(axis, direction) {
    if (allowed(axis)) controller.send({action:'jog', axis, distance:distance*direction, feed:Number(feed)});
  }
  return <><h2>Ręczne przesuwanie</h2><fieldset disabled={!controller.manualReady.value}>
    <div class="motion-settings"><div><label>Krok</label><div class="step-options">{[.1,1,10,'custom'].map(value => <label><input type="radio" name="step" value={value} checked={step === value} onChange={() => onStep(value)}/><span>{value === 'custom' ? 'Własny' : `${String(value).replace('.',',')} mm`}</span></label>)}</div><label class="custom-jog" for="jog-custom-step">Własny krok · mm<input id="jog-custom-step" type="text" inputMode="decimal" placeholder="np. 2,5" value={customStep} aria-invalid={step === 'custom' && distance === null} onFocus={() => onStep('custom')} onInput={event => {onCustomStep(event.currentTarget.value);onStep('custom');}}/></label></div><ParameterField id="jog-feed" label="Prędkość ruchu · mm/min" value={feed} onChange={onFeed} options={[10,25,50,75,100,150,200,250,300]} min={1} max={300} help="Prędkość ręcznego przesuwania osi. Domyślnie 300 mm/min."/></div>
    <p id="jog-custom-hint" class="hint">Wybrany krok: <strong>{distance === null ? 'wpisz poprawną wartość' : `${distance.toLocaleString('pl-PL')} mm`}</strong>. Wpisanie wartości nie porusza osi.</p>
    <div class="jog-controls"><div class="xy-pad"><button type="button" class="up" disabled={!allowed('Y')} onClick={() => move('Y',1)}>Y +</button><button type="button" class="left" disabled={!allowed('X')} onClick={() => move('X',-1)}>X −</button><span>X / Y</span><button type="button" class="right" disabled={!allowed('X')} onClick={() => move('X',1)}>X +</button><button type="button" class="down" disabled={!allowed('Y')} onClick={() => move('Y',-1)}>Y −</button></div><div class="z-pad"><button type="button" disabled={!allowed('Z')} onClick={() => move('Z',1)}>Z +</button><span>Oś Z</span><button type="button" disabled={!allowed('Z')} onClick={() => move('Z',-1)}>Z −</button></div></div>
    </fieldset><button type="button" id="cancel-jog" class="stop" disabled={!controller.known.value || !cnc.connected || controller.active.value} onClick={() => controller.send({action:'jog_cancel'},true)}><IconPlayerStop size={17}/>Przerwij ruch</button><p class="hint">Maks. pojedynczy krok: X {limits.X}, Y {limits.Y}, Z {limits.Z} mm. Bez krańcówek pilnuj rzeczywistego zakresu.</p></>;
}
