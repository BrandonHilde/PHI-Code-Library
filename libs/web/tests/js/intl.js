// Intl and the locale methods, as pages use them. What it logs was checked against Node.js (V8 and ICU).
// It differs where this has only English (en-GB is "en"; only the Gregorian calendar) and where ICU
// puts narrow or thin spaces (before AM and PM, around a range's dash) and this a plain space. The
// dates are in UTC or a named zone, so the host's own zone changes nothing.
const t = Date.UTC(2026, 10, 21, 15, 4, 5, 123);
console.log(typeof Intl, Object.prototype.toString.call(Intl), Object.keys(Intl).length);
console.log((1234567.891).toLocaleString(), (0.5).toLocaleString("en-US", { style: "percent" }), (-0).toLocaleString());
console.log(new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(1234.5));
console.log(new Intl.NumberFormat("en-US", { style: "currency", currency: "EUR", currencySign: "accounting" }).format(-3));
console.log(new Intl.NumberFormat("en", { style: "currency", currency: "JPY", currencyDisplay: "name" }).format(5000));
console.log(new Intl.NumberFormat("en", { notation: "compact" }).format(1234567), new Intl.NumberFormat("en", { notation: "compact", compactDisplay: "long" }).format(2500));
console.log(new Intl.NumberFormat("en", { notation: "scientific" }).format(123456), new Intl.NumberFormat("en", { notation: "engineering" }).format(0.00012));
console.log(new Intl.NumberFormat("en", { maximumSignificantDigits: 3 }).format(98765.4321), new Intl.NumberFormat("en", { minimumFractionDigits: 2 }).format(7));
console.log(new Intl.NumberFormat("en", { style: "unit", unit: "kilometer-per-hour" }).format(88), new Intl.NumberFormat("en", { style: "unit", unit: "megabyte", unitDisplay: "long" }).format(1.5));
console.log(new Intl.NumberFormat("en", { signDisplay: "exceptZero" }).format(5), new Intl.NumberFormat("en", { roundingMode: "floor", maximumFractionDigits: 0 }).format(-2.5));
console.log(new Intl.NumberFormat("en").format(12345678901234567890n), new Intl.NumberFormat("en", { maximumFractionDigits: 20 }).format("0.10000000000000000001"));
console.log(new Intl.NumberFormat("en", { style: "currency", currency: "USD" }).formatRange(3, 5), new Intl.NumberFormat("en").formatRange(1000, 1000));
console.log(JSON.stringify(new Intl.NumberFormat("en", { style: "currency", currency: "USD" }).formatToParts(-1234.5)));
console.log(JSON.stringify(new Intl.NumberFormat("en-GB-u-nu-latn", { maximumFractionDigits: 1 }).resolvedOptions()));
console.log(new Intl.DateTimeFormat("en-US", { timeZone: "UTC" }).format(t), new Date(t).toLocaleString("en-US", { timeZone: "UTC" }));
console.log(new Date(t).toLocaleDateString(undefined, { timeZone: "UTC", weekday: "long", year: "numeric", month: "long", day: "numeric" }));
console.log(new Date(t).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }));
for (const style of ["full", "long", "medium", "short"]) {
  console.log(new Intl.DateTimeFormat("en", { timeZone: "America/Los_Angeles", dateStyle: style, timeStyle: style }).format(t));
}
console.log(new Intl.DateTimeFormat("en", { timeZone: "Europe/Berlin", hour: "numeric", minute: "numeric", timeZoneName: "short" }).format(Date.UTC(2026, 6, 1, 12)));
console.log(new Intl.DateTimeFormat("en", { timeZone: "Asia/Kolkata", hour12: false, hour: "numeric", minute: "numeric", second: "numeric" }).format(t));
console.log(new Intl.DateTimeFormat("en", { timeZone: "UTC", dateStyle: "medium" }).formatRange(t, t + 3 * 86400000));
console.log(new Intl.DateTimeFormat("en", { timeZone: "UTC", hour: "numeric", minute: "numeric" }).formatRange(t, t + 3600000));
console.log(JSON.stringify(new Intl.DateTimeFormat("en", { timeZone: "UTC", month: "short", day: "numeric" }).formatToParts(t)));
const dtf = new Intl.DateTimeFormat("en", { timeZone: "Australia/Sydney", hour: "numeric" }).resolvedOptions();
console.log(dtf.locale, dtf.calendar, dtf.timeZone, dtf.hourCycle, dtf.hour12);
const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
console.log(rtf.format(-1, "day"), rtf.format(2, "weeks"), rtf.format(-3, "month"), rtf.format(0, "year"), new Intl.RelativeTimeFormat("en", { style: "short" }).format(-5, "minute"));
console.log(new Intl.ListFormat("en").format(["red", "green", "blue"]), new Intl.ListFormat("en", { type: "disjunction" }).format(["tea", "coffee"]));
const pr = new Intl.PluralRules("en", { type: "ordinal" });
console.log([1, 2, 3, 4, 11, 12, 13, 21, 22, 101].map((n) => n + pr.select(n)).join(" "), new Intl.PluralRules("en").select(1));
const words = ["résumé", "resume", "Resume", "apple", "Äpfel", "zebra", "item10", "item2", "_x", "ß", "ss"];
console.log(words.slice().sort(new Intl.Collator("en").compare).join(" "));
console.log(words.slice().sort(new Intl.Collator("en", { numeric: true, sensitivity: "base" }).compare).join(" "));
console.log("a".localeCompare("B"), "a".localeCompare("á"), "a".localeCompare("á", "en", { sensitivity: "base" }));
const seg = new Intl.Segmenter("en", { granularity: "word" });
console.log([...seg.segment("Don't stop, it's 3.50 now!")].filter((s) => s.isWordLike).map((s) => s.segment).join("|"));
console.log([...new Intl.Segmenter("en").segment("é👍🏽🇺🇸")].length, [...new Intl.Segmenter("en", { granularity: "sentence" }).segment("One. Two? Three!")].length);
const loc = new Intl.Locale("zh-hant-tw", { calendar: "gregory" });
console.log(loc.toString(), loc.baseName, loc.language, loc.script, loc.region, new Intl.Locale("en").maximize().toString());
console.log(Intl.getCanonicalLocales(["EN-us", "iw", "zh-hant-TW"]).join(" "), Intl.supportedValuesOf("calendar").join());
console.log(new Intl.DisplayNames("en", { type: "region" }).of("DE"), new Intl.DisplayNames("en", { type: "language" }).of("pt-BR"), new Intl.DisplayNames("en", { type: "currency" }).of("JPY"));
console.log(new Intl.DurationFormat("en", { style: "long" }).format({ hours: 1, minutes: 30 }), new Intl.DurationFormat("en", { style: "digital" }).format({ hours: 2, minutes: 5, seconds: 9 }));
console.log([1234.5, new Date(t), "x"].toLocaleString("en", { timeZone: "UTC" }), (10n ** 6n).toLocaleString());
for (const bad of [() => new Intl.NumberFormat("en_US"), () => new Intl.NumberFormat("en", { style: "currency" }), () => new Intl.DateTimeFormat("en", { timeZone: "Mars/Base" }), () => Intl.PluralRules(), () => new Intl.DateTimeFormat("en", { dateStyle: "long", hour: "numeric" })]) {
  try { bad(); console.log("no error"); } catch (e) { console.log(e.constructor.name); }
}
