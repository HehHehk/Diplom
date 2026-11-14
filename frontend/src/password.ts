export interface PasswordCheck {
  label: string;
  ok: boolean;
}

export interface PasswordStrength {
  percent: number;
  label: string;
  color: string;
  checks: PasswordCheck[];
  valid: boolean;
}

const COMMON = new Set([
  "password",
  "password1",
  "password123",
  "qwerty",
  "qwerty123",
  "12345678",
  "123456789",
  "admin123",
  "admin12345",
  "letmein",
  "welcome",
  "welcome1",
  "iloveyou",
  "abc12345",
  "1q2w3e4r",
]);

export function passwordStrength(value: string): PasswordStrength {
  const checks: PasswordCheck[] = [
    { label: "Не короче 8 символов", ok: value.length >= 8 },
    { label: "Есть буквы", ok: /[a-zA-Zа-яА-Я]/.test(value) },
    { label: "Есть цифры", ok: /\d/.test(value) },
    { label: "Есть заглавные и строчные буквы", ok: /[a-zа-я]/.test(value) && /[A-ZА-Я]/.test(value) },
    { label: "Есть специальный символ", ok: /[^a-zA-Zа-яА-Я0-9]/.test(value) },
    { label: "Не из списка частых паролей", ok: value.length > 0 && !COMMON.has(value.toLowerCase()) },
  ];

  const passed = checks.filter((check) => check.ok).length;
  const valid = checks[0].ok && checks[1].ok && checks[2].ok && checks[5].ok;
  const percent = Math.round((passed / checks.length) * 100);

  let level = { label: "очень слабый", color: "#d4380d" };
  if (passed === 2) level = { label: "слабый", color: "#d46b08" };
  else if (passed === 3 || passed === 4) level = { label: "средний", color: "#d4b106" };
  else if (passed === 5) level = { label: "хороший", color: "#389e0d" };
  else if (passed === 6) level = { label: "надёжный", color: "#237804" };

  return { percent, label: level.label, color: level.color, checks, valid };
}
