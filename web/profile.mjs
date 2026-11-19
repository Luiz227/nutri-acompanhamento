// Mirrors the app's initial IOM 2005 calculation, before activity logs
// or personal adjustments. The API receives the same profile shape as Android.
const activityFactors = {
  sedentary: [1, 1], lowActive: [1.12, 1.14],
  active: [1.27, 1.27], veryActive: [1.54, 1.45],
};
const goalOffsets = { loseWeight: -500, maintainWeight: 0, gainWeight: 500 };

function enrollmentProfile(raw, now = new Date()) {
  if (!raw || !['female', 'male', 'nonBinary'].includes(raw.gender) ||
      !Object.hasOwn(activityFactors, raw.activityLevel) || !Object.hasOwn(goalOffsets, raw.goal)) {
    throw new Error('Informe gênero, nível de atividade e objetivo.');
  }
  const birthday = raw.birthday;
  const date = typeof birthday === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(birthday) ? new Date(birthday) : null;
  if (!date || !Number.isFinite(date.valueOf()) || date.toISOString().slice(0, 10) !== birthday) {
    throw new Error('Informe uma data de nascimento válida.');
  }
  const today = new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
  const age = Number(today.slice(0, 4)) - Number(birthday.slice(0, 4)) - Number(today.slice(5) < birthday.slice(5));
  if (age < 13 || age > 129) throw new Error('O cadastro aceita idades de 13 a 129 anos.');
  const { gender, activityLevel, goal, heightCm, weightKg, targetWeightKg } = raw;
  const bounded = (value, min, max) => Number.isFinite(value) && value >= min && value <= max;
  if (!bounded(heightCm, 30, 300) || !bounded(weightKg, 2, 600)) throw new Error('Confira o peso e a altura.');
  if (targetWeightKg != null && !bounded(targetWeightKg, 2, 600)) throw new Error('Confira o peso desejado.');
  const profile = { birthday, gender, activityLevel, goal, heightCm, weightKg };
  if (targetWeightKg != null && goal !== 'maintainWeight') profile.targetWeightKg = targetWeightKg;
  // The app's reference equations are for ages 19 and up.
  if (age < 19) return profile;
  const reference = gender === 'male' ? 'testosteroneTypical' : gender === 'female' ? 'estrogenTypical' : raw.caloriesProfile || 'averaged';
  if (!['testosteroneTypical', 'estrogenTypical', 'averaged'].includes(reference)) throw new Error('Confira a referência para a estimativa.');
  const [maleFactor, femaleFactor] = activityFactors[activityLevel];
  const meters = heightCm / 100;
  const male = 864 - 9.72 * age + maleFactor * (14.2 * weightKg + 503 * meters);
  const female = 387 - 7.31 * age + femaleFactor * (10.9 * weightKg + 660.7 * meters);
  const baseline = reference === 'testosteroneTypical' ? male : reference === 'estrogenTypical' ? female : (male + female) / 2;
  const energyKcal = baseline + goalOffsets[goal];
  if (energyKcal > 0) profile.dailyGoals = {
    energyKcal, carbsG: energyKcal * 0.6 / 4, fatG: energyKcal * 0.25 / 9,
    proteinG: energyKcal * 0.15 / 4,
    waterMl: reference === 'testosteroneTypical' ? 1900 : reference === 'estrogenTypical' ? 1500 : 1700,
  };
  return profile;
}

export { enrollmentProfile };
