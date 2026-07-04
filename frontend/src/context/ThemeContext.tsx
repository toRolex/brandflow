import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
type Layout = "normal" | "compact";

interface ThemeContextValue {
  theme: Theme;
  layout: Layout;
  toggleTheme: () => void;
  toggleLayout: () => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  layout: "normal",
  toggleTheme: () => {},
  toggleLayout: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem("bf-theme") as Theme) || "light";
  });
  const [layout, setLayout] = useState<Layout>(() => {
    return (localStorage.getItem("bf-layout") as Layout) || "normal";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("bf-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-layout", layout);
    localStorage.setItem("bf-layout", layout);
  }, [layout]);

  const toggleTheme = () => setTheme((t) => (t === "light" ? "dark" : "light"));
  const toggleLayout = () => setLayout((t) => (t === "normal" ? "compact" : "normal"));

  return (
    <ThemeContext.Provider value={{ theme, layout, toggleTheme, toggleLayout }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
