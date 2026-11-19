import { enrollmentProfile } from './profile.mjs';

const byId = id => document.getElementById(id);
const form = byId('enroll');
const views = ['enroll', 'login', 'forgot', 'verify', 'dashboard'];
const goals = { loseWeight: 'Perder peso', maintainWeight: 'Manter peso', gainWeight: 'Ganhar peso' };
const meals = { breakfast: 'Café da manhã', lunch: 'Almoço', snack: 'Lanches', dinner: 'Jantar' };
const metrics = [
  ['energyKcal', 'Energia', 'kcal'], ['proteinG', 'Proteína', 'g'],
  ['carbsG', 'Carboidratos', 'g'], ['fatG', 'Gorduras', 'g'], ['waterMl', 'Água', 'ml'],
];
let challenge = null;
let currentStep = 0;
let sessionRevision = 0;
let currentView = 'enroll';
let accountData = null;
let activePanel = 'diary';
let entryRequestId = null;

const format = value => Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 1 });
const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Sao_Paulo' }).format(new Date());

async function api(route, method = 'GET', body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch('/web-api/' + route, {
      method, credentials: 'same-origin', signal: controller.signal,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const data = await response.json();
    if (!response.ok) throw Object.assign(new Error(data.error || 'Tente novamente em instantes.'), { status: response.status });
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function show(view, message = '') {
  currentView = view;
  for (const id of views) byId(id).hidden = id !== view;
  const signedIn = view === 'dashboard';
  document.body.classList.toggle('signed-in', signedIn);
  byId('public-nav').hidden = signedIn;
  byId('logout-top').hidden = !signedIn;
  byId('form-title').hidden = signedIn;
  byId('cadastro').setAttribute('aria-labelledby', signedIn ? 'account-name' : 'form-title');
  document.querySelector('.lead').hidden = signedIn;
  document.querySelector('.badge').hidden = signedIn;
  const titles = { enroll: 'Comece por aqui', login: 'Bem-vindo de volta',
    forgot: 'Recupere seu acesso', verify: 'Confirme seu WhatsApp' };
  const leads = { enroll: 'Preencha seu perfil e crie sua conta.',
    login: 'Entre com seu WhatsApp e sua senha para acompanhar seus dados.',
    forgot: 'Enviaremos um código para o WhatsApp associado à sua conta.',
    verify: challenge?.purpose === 'reset' ? 'Digite o código e escolha sua nova senha.' : 'Falta confirmar que este número é seu.' };
  byId('form-title').textContent = titles[view] || '';
  document.querySelector('.lead').textContent = leads[view] || '';
  document.querySelector('.badge').textContent = view === 'enroll' ? 'CADASTRO GRATUITO' : 'SUA CONTA GARFOFALA';
  byId('status').textContent = message;
}

function clearAccount() {
  accountData = null;
  for (const id of ['body-metrics', 'weight-chart', 'weight-history', 'daily-history']) byId(id).replaceChildren();
  byId('edit-profile').reset();
  byId('preferences-form').reset();
  byId('entry-dialog').close();
  byId('library-items').replaceChildren();
  byId('library-form').reset();
  byId('recipe-ingredients').replaceChildren();
  for (const id of ['diary-records', 'daily-goals', 'profile-data']) byId(id).replaceChildren();
  byId('account-name').textContent = 'Seu acompanhamento';
  byId('account-phone').textContent = '';
  byId('connection-state').textContent = '';
}

async function run(button, action) {
  button.disabled = true;
  byId('status').textContent = '';
  try {
    await action();
  } catch (error) {
    byId('status').textContent = error.status ? error.message : 'A conexão falhou. Tente novamente em instantes.';
  } finally {
    button.disabled = false;
  }
}

function checkPassword(passwordId, confirmationId) {
  const password = byId(passwordId);
  const confirmation = byId(confirmationId);
  password.setCustomValidity(/[^\p{L}\p{N}\s]/u.test(password.value) ? '' : 'Inclua pelo menos um caractere especial.');
  confirmation.setCustomValidity(password.value === confirmation.value ? '' : 'As senhas precisam ser iguais.');
  return password.reportValidity() && confirmation.reportValidity();
}
for (const id of ['signup-password', 'signup-password-confirm', 'new-password', 'new-password-confirm']) {
  byId(id).addEventListener('input', () => byId(id).setCustomValidity(''));
}

const steps = [...form.querySelectorAll('.profile-step')];
function setStep(index, focus = false) {
  currentStep = index;
  steps.forEach((step, i) => {
    step.hidden = i !== index;
    step.querySelectorAll('input, select, button').forEach(control => { control.disabled = i !== index; });
  });
  byId('step-label').textContent = `Etapa ${index + 1} de ${steps.length}`;
  if (focus) steps[index].querySelector('h3').focus();
}
function readProfile() {
  const decimal = id => Number(byId(id).value.replace(',', '.'));
  return {
    birthday: byId('birthday').value, gender: byId('gender').value,
    caloriesProfile: byId('caloriesProfile').value, heightCm: decimal('heightCm'), weightKg: decimal('weightKg'),
    goal: byId('goal').value, activityLevel: byId('activityLevel').value,
    targetWeightKg: byId('goal').value !== 'maintainWeight' && byId('targetWeightKg').value ? decimal('targetWeightKg') : null,
  };
}
function advance() {
  if (!form.reportValidity()) return;
  try {
    const raw = readProfile();
    const profile = enrollmentProfile(currentStep === 0
      ? { ...raw, goal: 'maintainWeight', activityLevel: 'sedentary', targetWeightKg: null } : raw);
    if (currentStep === 1) {
      const parts = [goals[profile.goal], `${format(profile.heightCm)} cm`, `${format(profile.weightKg)} kg`];
      if (profile.targetWeightKg != null) parts.push(`Peso desejado: ${format(profile.targetWeightKg)} kg`);
      if (profile.dailyGoals) parts.push(`Meta inicial estimada: ${format(profile.dailyGoals.energyKcal)} kcal/dia`);
      byId('profile-review').textContent = parts.join(' • ');
    }
    setStep(currentStep + 1, true);
  } catch (error) {
    byId('status').textContent = error.message;
  }
}
form.querySelectorAll('[data-next]').forEach(button => button.addEventListener('click', advance));
form.querySelectorAll('[data-back]').forEach(button => button.addEventListener('click', () => setStep(currentStep - 1, true)));
byId('birthday').max = today();
byId('diary-date').value = today();
byId('gender').addEventListener('change', () => { byId('calorie-reference').hidden = byId('gender').value !== 'nonBinary'; });
byId('goal').addEventListener('change', () => {
  byId('target-group').hidden = !['loseWeight', 'gainWeight'].includes(byId('goal').value);
  if (byId('target-group').hidden) byId('targetWeightKg').value = '';
});
setStep(0);

function showVerification(result, purpose) {
  challenge = { id: result.challengeId, purpose };
  byId('otp-code').value = '';
  byId('reset-fields').hidden = purpose !== 'reset';
  for (const id of ['new-password', 'new-password-confirm']) {
    byId(id).required = purpose === 'reset';
    byId(id).disabled = purpose !== 'reset';
    byId(id).value = '';
  }
  byId('verify-submit').textContent = purpose === 'reset' ? 'Salvar nova senha ↗' : 'Confirmar e entrar ↗';
  show('verify', result.message);
  byId('otp-code').focus();
}

form.addEventListener('submit', event => {
  event.preventDefault();
  if (currentStep < 2) return advance();
  if (!checkPassword('signup-password', 'signup-password-confirm')) return;
  run(form.querySelector('[type=submit]'), async () => {
    const result = await api('signup', 'POST', {
      phone: byId('phone').value, profile: enrollmentProfile(readProfile()), consent: byId('consent').checked,
      password: byId('signup-password').value, passwordConfirm: byId('signup-password-confirm').value,
    });
    byId('signup-password').value = '';
    byId('signup-password-confirm').value = '';
    showVerification(result, 'signup');
  });
});
byId('login').addEventListener('submit', event => {
  event.preventDefault();
  run(event.currentTarget.querySelector('[type=submit]'), async () => {
    await api('login', 'POST', { phone: byId('login-phone').value, password: byId('login-password').value });
    byId('login-password').value = '';
    form.reset();
    byId('profile-review').textContent = '';
    setStep(0);
    sessionRevision += 1;
    await refresh();
  });
});
byId('forgot').addEventListener('submit', event => {
  event.preventDefault();
  run(event.currentTarget.querySelector('[type=submit]'), async () => {
    showVerification(await api('forgot-password', 'POST', { phone: byId('forgot-phone').value }), 'reset');
  });
});
byId('verify').addEventListener('submit', event => {
  event.preventDefault();
  if (!challenge) return show('login', 'Inicie uma nova solicitação.');
  if (challenge.purpose === 'reset' && !checkPassword('new-password', 'new-password-confirm')) return;
  run(event.currentTarget.querySelector('[type=submit]'), async () => {
    const reset = challenge.purpose === 'reset';
    const result = await api(reset ? 'reset-password' : 'verify-signup', 'POST', {
      challengeId: challenge.id, code: byId('otp-code').value,
      ...(reset ? { password: byId('new-password').value, passwordConfirm: byId('new-password-confirm').value } : {}),
    });
    challenge = null;
    byId('otp-code').value = '';
    byId('new-password').value = '';
    byId('new-password-confirm').value = '';
    sessionRevision += 1;
    if (reset || result.accountExists) {
      clearAccount();
      show('login', result.message);
    } else {
      form.reset();
      byId('profile-review').textContent = '';
      setStep(0);
      await refresh();
    }
  });
});
byId('resend-code').addEventListener('click', event => run(event.currentTarget, async () => {
  if (!challenge) return show('login', 'Inicie uma nova solicitação.');
  const result = await api('resend-code', 'POST', { challengeId: challenge.id });
  byId('status').textContent = result.message;
}));

function element(tag, copy, className) {
  const node = document.createElement(tag);
  node.textContent = copy;
  if (className) node.className = className;
  return node;
}
function renderAccount(data) {
  accountData = data;
  byId('account-name').textContent = data.displayName ? `Olá, ${data.displayName}` : 'Seu acompanhamento';
  byId('account-phone').textContent = '+' + data.phone;
  byId('account-date').textContent = new Date().toLocaleDateString('pt-BR', { dateStyle: 'long', timeZone: 'America/Sao_Paulo' });
  byId('connection-state').textContent = data.consentActive
    ? 'WhatsApp conectado. Seus registros ficam sincronizados com esta conta.'
    : 'O acompanhamento pelo WhatsApp está pausado. Seu histórico continua disponível aqui.';
  const profile = data.profile || {};
  const details = [
    ['Objetivo', goals[profile.goal] || 'Não informado'],
    ['Peso do perfil', profile.weightKg ? format(profile.weightKg) + ' kg' : 'Não informado'],
    ['Altura', profile.heightCm ? format(profile.heightCm) + ' cm' : 'Não informada'],
    ['Peso desejado', profile.targetWeightKg ? format(profile.targetWeightKg) + ' kg' : 'Não informado'],
  ];
  byId('profile-data').replaceChildren(...details.map(([label, value]) => {
    const item = element('div', '', 'profile-item');
    item.append(element('span', label), element('strong', value));
    return item;
  }));
  byId('daily-goals').replaceChildren(...metrics.map(([key, label, unit]) => {
    const item = element('section', '', 'metric');
    const value = data.today.totals[key] || 0;
    const missing = data.today.missing.includes(key);
    const goal = profile.dailyGoals?.[key];
    item.append(element('h4', label), element('strong', missing && value === 0 ? 'Sem cálculo' : `${format(value)} ${unit}`));
    if (goal > 0) {
      const progress = document.createElement('progress');
      progress.max = goal;
      progress.value = Math.min(value, goal);
      progress.setAttribute('aria-label', `${label}: ${format(value)} de ${format(goal)} ${unit}`);
      item.append(progress, element('small', `Meta ${format(goal)} ${unit}`));
    } else item.append(element('small', 'Meta não definida'));
    if (missing) item.append(element('small', 'Total parcial'));
    return item;
  }));
}
async function renderDiary() {
  const revision = sessionRevision;
  const day = byId('diary-date').value;
  if (!day) return;
  const result = await api('records?day=' + encodeURIComponent(day));
  if (revision !== sessionRevision || currentView !== 'dashboard' || byId('diary-date').value !== day) return;
  const groups = new Map();
  for (const record of result.records) {
    const label = record.kind === 'meal' ? meals[record.mealType] || 'Refeição'
      : { water: 'Água', weight: 'Peso', observation: 'Observações' }[record.kind] || 'Registro';
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(record);
  }
  const sections = [];
  for (const [label, records] of groups) {
    const section = element('section', '', 'diary-section');
    const list = document.createElement('ul');
    for (const record of records) {
      const item = document.createElement('li');
      item.append(element('span', record.text));
      if (record.quantity) item.append(element('small', `${format(record.quantity)} ${record.unit}`));
      if (record.nutrition) {
        const nutrient = key => record.nutrition[key] == null ? 'não disponível' : format(record.nutrition[key]);
        item.append(element('small', `${nutrient('energyKcal')} kcal · Proteína ${nutrient('proteinG')} g · Carboidratos ${nutrient('carbsG')} g · Gorduras ${nutrient('fatG')} g`));
        item.append(element('small', `Fibras ${nutrient('fiberG')} g · Sódio ${nutrient('sodiumMg')} mg`));
      }
      const controls = element('div', '', 'record-actions');
      const edit = element('button', 'Editar', 'text-button');
      edit.type = 'button';
      edit.addEventListener('click', () => openEntry(record.kind, record));
      const remove = element('button', 'Excluir', 'text-button');
      remove.type = 'button';
      remove.addEventListener('click', () => run(remove, async () => {
        if (!confirm('Excluir este registro do diário sincronizado?')) return;
        await api('remove-entry', 'POST', { id: record.id });
        await refresh();
      }));
      controls.append(edit, remove);
      item.append(controls);
      list.append(item);
    }
    section.append(element('h4', label), list);
    sections.push(section);
  }
  byId('diary-records').replaceChildren(...(sections.length ? sections : [
    element('p', 'Nenhum registro nesta data. Conte pelo WhatsApp o que você consumiu.', 'help'),
  ]));
}
async function refresh() {
  const revision = sessionRevision;
  const data = await api('me');
  if (revision !== sessionRevision) return;
  show('dashboard');
  renderAccount(data);
  fillProfile(data.profile || {});
  selectPanel(activePanel);
  await renderDiary();
  await loadEvolution();
  if (activePanel === 'library') await loadLibrary();
  if (activePanel === 'settings') await loadPreferences();
}
byId('refresh').addEventListener('click', event => run(event.currentTarget, refresh));
byId('diary-date').addEventListener('change', () => run(byId('refresh'), renderDiary));
byId('logout-top').addEventListener('click', event => run(event.currentTarget, async () => {
  await api('logout', 'POST', {});
  sessionRevision += 1;
  clearAccount();
  for (const id of ['enroll', 'login', 'forgot', 'verify']) byId(id).reset();
  byId('profile-review').textContent = '';
  setStep(0);
  show('login', 'Você saiu da sua conta.');
}));
function navigate() {
  const route = location.hash || location.pathname;
  if (route.includes('recuperar')) show('forgot');
  else if (route.includes('entrar')) show('login');
  else { show('enroll'); setStep(0); }
}
window.addEventListener('hashchange', navigate);
navigate();
refresh().catch(error => {
  if (error.status !== 401) byId('status').textContent = 'Não foi possível carregar sua sessão. Tente entrar novamente.';
});

function selectPanel(panel) {
  activePanel = panel;
  for (const section of document.querySelectorAll('[data-account-panel]')) section.hidden = section.dataset.accountPanel !== panel;
  for (const button of document.querySelectorAll('[data-panel]')) {
    if (button.dataset.panel === panel) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  }
}
for (const button of document.querySelectorAll('[data-panel]')) button.addEventListener('click', () => {
  selectPanel(button.dataset.panel);
  if (activePanel === 'settings') run(button, loadPreferences);
  if (activePanel === 'library') run(button, loadLibrary);
});

function fillProfile(profile) {
  const fields = { birthday: 'birthday', gender: 'gender', heightCm: 'height', weightKg: 'weight',
    goal: 'goal', activityLevel: 'activity', targetWeightKg: 'target' };
  for (const [key, id] of Object.entries(fields)) byId('edit-' + id).value = profile[key] ?? '';
  byId('edit-goals').replaceChildren(...metrics.map(([key, title, unit]) => {
    const label = element('label', `${title} (${unit})`);
    const input = document.createElement('input');
    input.id = 'goal-' + key;
    input.type = 'number'; input.min = key === 'energyKcal' ? 1 : 0;
    input.max = {energyKcal:20000,proteinG:2000,carbsG:3000,fatG:2000,waterMl:20000}[key];
    input.step = '0.1'; input.className = 'field';
    input.value = profile.dailyGoals?.[key] ?? '';
    label.append(input);
    return label;
  }));
}
byId('edit-profile').addEventListener('submit', event => {
  event.preventDefault();
  run(event.currentTarget.querySelector('[type=submit]'), async () => {
    const profile = { birthday: byId('edit-birthday').value, gender: byId('edit-gender').value,
      heightCm: Number(byId('edit-height').value), weightKg: Number(byId('edit-weight').value),
      goal: byId('edit-goal').value, activityLevel: byId('edit-activity').value,
      targetWeightKg: byId('edit-target').value ? Number(byId('edit-target').value) : null,
      dailyGoals: Object.fromEntries(metrics.filter(([key]) => byId('goal-' + key).value !== '')
        .map(([key]) => [key, Number(byId('goal-' + key).value)])) };
    await api('profile', 'POST', { profile });
    await refresh();
    byId('status').textContent = 'Perfil e metas atualizados.';
  });
});
async function loadPreferences() {
  const revision = sessionRevision;
  const result = await api('preferences');
  if (revision !== sessionRevision || currentView !== 'dashboard') return;
  byId('preferred-name').value = result.name;
  byId('water-reminders').checked = result.reminders;
  byId('reminder-hours').value = result.hours.join(', ');
}
byId('preferences-form').addEventListener('submit', event => {
  event.preventDefault();
  run(event.currentTarget.querySelector('[type=submit]'), async () => {
    await api('preferences', 'POST', { name: byId('preferred-name').value,
      reminders: byId('water-reminders').checked,
      hours: byId('reminder-hours').value.split(',').map(v => v.trim()).filter(Boolean) });
    await refresh();
    byId('status').textContent = 'Preferências salvas.';
  });
});
function card(label, value, detail = '') {
  const node = element('div', '', 'profile-item');
  node.append(element('span', label), element('strong', value));
  if (detail) node.append(element('small', detail));
  return node;
}
async function loadEvolution() {
  const revision = sessionRevision;
  const days = byId('evolution-days').value;
  const result = await api('evolution?days=' + days);
  if (revision !== sessionRevision || currentView !== 'dashboard' || byId('evolution-days').value !== days) return;
  byId('body-metrics').replaceChildren(
    card('IMC atual', result.bmi == null ? 'Não disponível' : format(result.bmi), result.bmiCategory || ''),
    card('Peso atual', result.currentWeightKg ? format(result.currentWeightKg) + ' kg' : 'Não informado'),
    card('Variação registrada', result.changeKg == null ? 'Sem histórico' : (result.changeKg > 0 ? '+' : '') + format(result.changeKg) + ' kg'),
    card('Peso desejado', result.targetWeightKg ? format(result.targetWeightKg) + ' kg' : 'Não definido'),
  );
  byId('bmi-note').textContent = result.bmiCategory
    ? 'IMC = peso ÷ altura². É um indicador de acompanhamento e não mede composição corporal. Usa a última pesagem registrada ou, na ausência dela, o peso do perfil.'
    : 'O IMC usa peso e altura. A classificação adulta não é exibida para menores de 20 anos ou sem data de nascimento.';
  const oldBmi = byId('overview-bmi');
  if (oldBmi) oldBmi.remove();
  const overview = card('Seu IMC', result.bmi == null ? 'Complete peso e altura' : format(result.bmi), result.bmiCategory || '');
  overview.id = 'overview-bmi'; byId('profile-data').append(overview);
  const weights = result.weights.filter(point => point.date.slice(0,10) >= result.daily[0].date);
  drawWeights(weights, result.targetWeightKg);
  byId('weight-summary').textContent = weights.length < 2
    ? 'Registre pelo menos duas pesagens no período para visualizar a linha de evolução.'
    : `${weights.length} pesagens no período. Acompanhe a tendência ao longo dos dias.`;
  byId('weight-history').replaceChildren(...(weights.length ? [...weights].reverse().map(point => {
    const row = element('p', '', 'history-row');
    row.append(element('span', new Date(point.date).toLocaleDateString('pt-BR', {timeZone:'America/Sao_Paulo'})), element('strong', format(point.kg) + ' kg'));
    return row;
  }) : [element('p', 'Nenhuma pesagem neste período.', 'help')]));
  const heading = element('p', `${result.trackedDays} dias com registros. Cada média usa os dias com dados completos daquela medida.`, 'help');
  const averages = element('div', '', 'profile-data');
  for (const [key, label, unit] of metrics) averages.append(card('Média de ' + label.toLowerCase(), result.averages[key] == null ? '—' : format(result.averages[key]) + ' ' + unit));
  const list = element('div', '', 'daily-history-list');
  for (const day of [...result.daily].reverse()) {
    const row = element('div', '', 'history-row');
    const date = new Date(day.date + 'T12:00:00-03:00').toLocaleDateString('pt-BR', {day:'2-digit',month:'2-digit'});
    row.append(element('strong', date));
    if (!day.tracked) row.append(element('span', 'Sem registros', 'help'));
    else {
      const nutrition = element('span', day.hasMeals ? `${format(day.totals.energyKcal)} kcal${day.missing.length ? ' · parcial' : ''}` : 'Sem refeições');
      const water = element('span', `${format(day.totals.waterMl)} ml`);
      row.append(nutrition, water);
      const open = element('button', 'Ver diário', 'text-button'); open.type = 'button';
      open.addEventListener('click', () => { byId('diary-date').value = day.date; selectPanel('diary'); run(open, renderDiary); });
      row.append(open);
    }
    list.append(row);
  }
  byId('daily-history').replaceChildren(heading, averages, list);
}
function drawWeights(points, target) {
  const container = byId('weight-chart'); container.replaceChildren();
  if (!points.length) { container.append(element('p', 'Seu gráfico começa com a primeira pesagem.', 'help')); return; }
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 700 230');
  const values = points.map(p => p.kg);
  const min = Math.min(...values)-1, max = Math.max(...values)+1;
  const first = Date.parse(points[0].date), last = Date.parse(points.at(-1).date);
  const x = date => 55 + (Date.parse(date)-first) / (last-first || 1) * 620;
  const y = kg => 190 - (kg-min)/(max-min)*165;
  function shape(type, attrs, text) {
    const node = document.createElementNS(ns, type);
    for (const [key,value] of Object.entries(attrs)) node.setAttribute(key, value);
    if (text) node.textContent = text;
    svg.append(node); return node;
  }
  for (let i=0;i<4;i++) {
    const kg = min+(max-min)*i/3;
    shape('line', {x1:50,x2:680,y1:y(kg),y2:y(kg),class:'chart-grid'});
    shape('text', {x:0,y:y(kg)+4,class:'chart-label'}, format(kg));
  }
  if (target && target >= min && target <= max) { shape('line',{x1:50,x2:680,y1:y(target),y2:y(target),class:'chart-target'}); shape('text',{x:510,y:y(target)-5,class:'chart-label'},'Meta '+format(target)+' kg'); }
  shape('polyline', {points:points.map(p => `${x(p.date)},${y(p.kg)}`).join(' '),class:'weight-line'});
  for (const point of points) {
    const dot = shape('circle',{cx:x(point.date),cy:y(point.kg),r:4,class:'weight-dot'});
    const title = document.createElementNS(ns,'title'); title.textContent = `${point.date.slice(0,10)}: ${format(point.kg)} kg`; dot.append(title);
  }
  shape('text',{x:55,y:220,class:'chart-label'},new Date(points[0].date).toLocaleDateString('pt-BR'));
  if (points.length > 1) shape('text',{x:590,y:220,class:'chart-label'},new Date(points.at(-1).date).toLocaleDateString('pt-BR'));
  container.append(svg);
}
byId('evolution-days').addEventListener('change', () => run(byId('refresh'), loadEvolution));

function localDateTime(value = new Date()) {
  return new Intl.DateTimeFormat('sv-SE', {timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(value).replace(' ', 'T');
}
function openEntry(kind, record = null) {
  byId('entry-form').reset();
  byId('entry-status').textContent = '';
  byId('entry-id').value = record?.id || '';
  byId('entry-kind').value = kind;
  entryRequestId = crypto.randomUUID();
  byId('entry-title').textContent = (record ? 'Editar ' : 'Registrar ') + ({meal:'refeição',water:'água',weight:'peso',observation:'observação'}[kind]);
  byId('entry-meal-fields').hidden = kind !== 'meal';
  byId('quantity-fields').hidden = kind === 'observation';
  byId('entry-quantity').required = kind !== 'observation';
  byId('entry-text-label').textContent = kind === 'meal' ? 'Alimento' : 'Descrição';
  byId('entry-text').value = record?.text || ({water:'Água',weight:'Peso',observation:''}[kind] || '');
  byId('entry-date').value = record ? localDateTime(new Date(record.occurredAt)) : localDateTime();
  byId('entry-meal').value = record?.mealType || (new Date().getHours() < 11 ? 'breakfast' : new Date().getHours() < 15 ? 'lunch' : 'dinner');
  byId('entry-quantity').value = record?.quantity || '';
  const allowed = {meal:['g','unit','slice'],water:['ml','l'],weight:['kg','g'],observation:[]}[kind];
  for (const option of byId('entry-unit').options) { option.hidden = !allowed.includes(option.value); option.disabled = option.hidden; }
  byId('entry-unit').value = record?.unit || allowed[0] || '';
  byId('entry-help').textContent = kind === 'meal'
    ? 'Busque o alimento ou informe o código de barras. O servidor calcula os nutrientes pela mesma base usada no WhatsApp. Unidade e fatia usam uma porção média quando disponível.'
    : 'Este registro fica na sua conta e sincroniza com o aplicativo.';
  byId('entry-dialog').showModal();
}
for (const button of document.querySelectorAll('[data-add]')) button.addEventListener('click', () => openEntry(button.dataset.add));
byId('entry-close').addEventListener('click', () => byId('entry-dialog').close());
let foodTimer;
byId('entry-text').addEventListener('input', () => {
  clearTimeout(foodTimer);
  if (byId('entry-kind').value !== 'meal') return;
  const text = byId('entry-text').value;
  foodTimer = setTimeout(async () => {
    try {
      const result = await api('foods?q=' + encodeURIComponent(text));
      if (byId('entry-text').value !== text || currentView !== 'dashboard') return;
      byId('food-options').replaceChildren(...result.foods.map(food => { const option = document.createElement('option'); option.value = food.name; return option; }));
    } catch { /* Typing stays available during a temporary search failure. */ }
  },350);
});
byId('lookup-barcode').addEventListener('click', event => run(event.currentTarget, async () => {
  try {
    const result = await api('foods?barcode=' + encodeURIComponent(byId('entry-barcode').value));
    if (!result.product) { byId('entry-status').textContent = 'Produto não encontrado. Busque pelo nome.'; return; }
    byId('entry-text').value = result.product.name;
    byId('entry-status').textContent = 'Produto encontrado. Informe a quantidade consumida em gramas.';
    byId('entry-unit').value = 'g';
  } catch (error) { byId('entry-status').textContent = error.message; }
}));
byId('entry-form').addEventListener('submit', event => {
  event.preventDefault();
  run(event.currentTarget.querySelector('[type=submit]'), async () => {
    try {
      const kind = byId('entry-kind').value;
      const record = {kind,text:byId('entry-text').value,occurredAt:new Date(byId('entry-date').value+'-03:00').toISOString()};
      if (kind !== 'observation') {record.quantity=Number(byId('entry-quantity').value);record.unit=byId('entry-unit').value;}
      if (kind === 'meal') { record.mealType=byId('entry-meal').value; if (byId('entry-barcode').value) record.barcode=byId('entry-barcode').value; }
      await api('entry','POST',{record,id:byId('entry-id').value || null,requestId:entryRequestId});
      byId('entry-dialog').close();
      await refresh();
      byId('status').textContent = 'Registro salvo no diário.';
    } catch(error) { byId('entry-status').textContent = error.message; }
  });
});
byId('export-data').addEventListener('click', event => run(event.currentTarget, async () => {
  const data = await api('export');
  const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const link = document.createElement('a'); link.href=url;link.download='garfofala-meus-dados.json';link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
}));
function ingredientRow() {
  const count = byId('recipe-ingredients').children.length;
  if (count >= 10) return;
  const row = element('div', '', 'ingredient-row');
  const nameLabel = element('label', 'Alimento');
  const name = document.createElement('input'); name.className='field';name.required=true;name.maxLength=180;name.dataset.ingredient='name';name.placeholder='Arroz branco cozido';
  nameLabel.append(name);
  const quantityLabel = element('label', 'Gramas por porção');
  const quantity = document.createElement('input'); quantity.className='field';quantity.type='number';quantity.min='0.1';quantity.max='10000';quantity.step='any';quantity.required=true;quantity.dataset.ingredient='grams';quantityLabel.append(quantity);
  const remove = element('button','Remover','text-button');remove.type='button';remove.addEventListener('click',()=>row.remove());
  row.append(nameLabel,quantityLabel,remove);byId('recipe-ingredients').append(row);
}
byId('add-ingredient').addEventListener('click',ingredientRow);
async function loadLibrary() {
  const revision=sessionRevision;
  const result=await api('library');
  if (revision !== sessionRevision || currentView !== 'dashboard') return;
  if (!byId('recipe-ingredients').children.length) ingredientRow();
  if (!byId('library-date').value) byId('library-date').value=localDateTime();
  byId('library-items').replaceChildren(...(result.items.length ? result.items.map(item=>{
    const box=element('section','','chart-card');box.append(element('h4',item.name),element('small',item.kind==='recipe'?'Receita · uma porção':'Favorito'));
    const list=document.createElement('ul');
    for (const food of item.foods) list.append(element('li',`${food.text} · ${format(food.quantity)} ${food.unit}`));
    box.append(list);
    const total={};for(const food of item.foods) for(const key of ['energyKcal','proteinG','carbsG','fatG']) total[key]=(total[key]||0)+(food.nutrition?.[key]||0);
    const partial=item.foods.some(food=>!food.nutrition || food.nutrition.energyKcal==null);
    box.append(element('p',`${partial?'Subtotal conhecido':'Total estimado'}: ${format(total.energyKcal)} kcal · Proteína ${format(total.proteinG)} g · Carboidratos ${format(total.carbsG)} g · Gorduras ${format(total.fatG)} g`,'help'));
    const add=element('button','Adicionar ao diário');add.type='button';
    let requestId=crypto.randomUUID();
    add.addEventListener('click',()=>run(add,async()=>{
      if (!byId('library-date').reportValidity()) return;
      await api('library-log','POST',{id:item.id,requestId,occurredAt:new Date(byId('library-date').value+'-03:00').toISOString(),mealType:byId('library-meal').value});
      requestId=crypto.randomUUID();await refresh();byId('status').textContent='Combinação registrada no diário.';
    }));
    const remove=element('button','Excluir da biblioteca','text-button');remove.type='button';
    remove.addEventListener('click',()=>run(remove,async()=>{if(!confirm('Excluir esta combinação da biblioteca? Os registros anteriores serão mantidos.'))return;await api('library-remove','POST',{id:item.id});await loadLibrary();}));
    box.append(add,remove);return box;
  }):[element('p','Sua biblioteca está vazia. Salve sua primeira receita ou alimento favorito.','help')]));
}
byId('library-form').addEventListener('submit',event=>{
  event.preventDefault();run(event.currentTarget.querySelector('[type=submit]'),async()=>{
    const foods=[...byId('recipe-ingredients').children].map(row=>({kind:'meal',text:row.querySelector('[data-ingredient=name]').value,quantity:Number(row.querySelector('[data-ingredient=grams]').value),unit:'g'}));
    await api('library','POST',{name:byId('library-name').value,kind:byId('library-kind').value,foods});
    byId('library-form').reset();byId('recipe-ingredients').replaceChildren();await loadLibrary();byId('status').textContent='Salvo na sua biblioteca.';
  });
});
