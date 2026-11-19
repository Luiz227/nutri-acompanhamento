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
  byId('account-name').textContent = data.displayName ? `Olá, ${data.displayName}` : 'Seu acompanhamento';
  byId('account-phone').textContent = '+' + data.phone;
  byId('account-date').textContent = new Date().toLocaleDateString('pt-BR', { dateStyle: 'long', timeZone: 'America/Sao_Paulo' });
  byId('connection-state').textContent = data.consentActive
    ? 'WhatsApp conectado. Seus registros ficam sincronizados com esta conta.'
    : 'O acompanhamento pelo WhatsApp está pausado. Seu histórico continua disponível aqui.';
  const profile = data.profile || {};
  const details = [
    ['Objetivo', goals[profile.goal] || 'Não informado'],
    ['Peso do cadastro', profile.weightKg ? format(profile.weightKg) + ' kg' : 'Não informado'],
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
      }
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
  await renderDiary();
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
