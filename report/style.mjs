/* شكل التقارير اللي المدير حدده في التطبيق (app_settings → report_style) */
export const RS = { sub: '', color: '', font: 'n', footer: 'ADC CONSTRUCTION', logo: '' };
export function setStyle(o) { if (o && typeof o === 'object') Object.assign(RS, o); }
export const thCss = def => RS.color ? `background:${RS.color};color:#fff` : def;
export const fontPx = base => base + ({ s: -1, n: 0, l: 1.5 }[RS.font] || 0);
export const xlHead = () => (RS.color || '#1d5c86').replace('#', '').toUpperCase();
