/**
 * 极简 i18n 翻译层(轻量方案,无第三方依赖)。
 *
 * 文案键 → 语言包,按浏览器语言自动选择(zh* → 中文,其余 → 英文)。
 * 缺失键回退英文包,再回退键名本身。支持 {var} 插值。
 *
 * 新增文案:在 en.ts / zh.ts 同时加同一键。
 */
import {en} from './en';
import {zh} from './zh';

export type Dict = Record<string, string>;

const dicts: Record<string, Dict> = {en, zh};

const detectLang = (): string => {
  if (typeof navigator === 'undefined') return 'en';
  const lang = (navigator.language || '').toLowerCase();
  return lang.startsWith('zh') ? 'zh' : 'en';
};

export const currentLang = detectLang();

export const t = (key: string, vars?: Record<string, string | number>): string => {
  let s = dicts[currentLang][key] ?? dicts.en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.split(`{${k}}`).join(String(v));
    }
  }
  return s;
};
