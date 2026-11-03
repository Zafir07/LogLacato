/** Cores definidas como variáveis CSS (src/index.css) para o modo claro e escuro. */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ground: v("ground"),
        surface: v("surface"),
        sunken: v("sunken"),
        line: v("line"),
        ink: v("ink"),
        muted: v("muted"),
        brand: v("brand"),
        "brand-soft": v("brand-soft"),
        "brand-ink": v("brand-ink"),
        data: v("data"),
        "data-soft": v("data-soft"),
        warn: v("warn"),
        "warn-soft": v("warn-soft"),
        bad: v("bad"),
        "bad-soft": v("bad-soft"),
        sim: v("sim"),
        "sim-soft": v("sim-soft"),
        nav: v("nav"),
        "nav-ink": v("nav-ink"),
        "nav-active": v("nav-active"),
      },
      fontFamily: {
        sans: ['"Archivo"', "system-ui", "sans-serif"],
        serif: ['"Lora"', "Georgia", "serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
