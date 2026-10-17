// Tailwind Play CDN config. Semantic colors that need a dark variant read CSS
// variables (channels) defined in templates/base.html; the rest are plain hex.
const cssVar = (name) => `rgb(var(--${name}) / <alpha-value>)`;

tailwind.config = {
    darkMode: "class",
    theme: {
        extend: {
            colors: {
                // "Obsidian Precision" (Stitch DESIGN.md). slate/blue are remapped so
                // every existing slate-*/blue-* class picks up the new palette.
                "slate": {
                    50: "#f7f7f8", 100: "#f1f2f4", 200: "#e3e3e6", 300: "#c6c7cc",
                    400: "#9ca0aa", 500: "#626670", 600: "#36383e", 700: "#2a2b30",
                    800: "#1c1d21", 900: "#16171a", 950: "#0e0f11",
                },
                "blue": {
                    50: "#eef0fb", 100: "#dfe1f7", 200: "#c3c7f0", 300: "#a3a9ea",
                    400: "#8c94e3", 500: "#6872e5", 600: "#5e6ad2", 700: "#535ebc",
                    800: "#434c9a", 900: "#2e3570",
                },
                // Brand. #5e6ad2 is ~4.7:1 on white (AA).
                "primary": {
                    DEFAULT: "#5e6ad2",
                    50: "#eef0fb",
                    100: "#dfe1f7",
                    700: "#535ebc",
                },
                "danger": { DEFAULT: "#e11d48", 700: "#be123c" },
                "background-light": "#f7f7f8",
                "background-dark": "#0e0f11",
                // Surfaces / borders / text: switch automatically in dark mode.
                "surface": { DEFAULT: cssVar("surface"), muted: cssVar("surface-muted") },
                "line": cssVar("line"),
                "ink": { DEFAULT: cssVar("ink"), muted: cssVar("ink-muted") },
                // Project status: use as bg-status-active-bg text-status-active-fg.
                "status-active": { bg: cssVar("st-active-bg"), fg: cssVar("st-active-fg") },
                "status-paused": { bg: cssVar("st-paused-bg"), fg: cssVar("st-paused-fg") },
                "status-waiting": { bg: cssVar("st-waiting-bg"), fg: cssVar("st-waiting-fg") },
                "status-closed": { bg: cssVar("st-closed-bg"), fg: cssVar("st-closed-fg") },
            },
            fontFamily: {
                "display": ["Inter", "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", "system-ui", "sans-serif"],
                "sans": ["Inter", "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", "system-ui", "sans-serif"],
            },
            // 4px badges / 6px controls / 8px containers (DESIGN.md "Shapes").
            borderRadius: {
                "sm": "0.25rem", "DEFAULT": "0.375rem",
                "md": "0.375rem", "lg": "0.5rem",
                "xl": "0.5rem", "2xl": "0.5rem",
                "full": "9999px",
            },
        },
    },
}
