import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "../api/types";

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: "wasl-auth" },
  ),
);

interface UiState {
  dark: boolean;
  tourActive: boolean;
  tourStep: number;
  toggleDark: () => void;
  setTour: (active: boolean, step?: number) => void;
}

export const useUi = create<UiState>()((set) => ({
  dark: typeof document !== "undefined" && document.documentElement.classList.contains("dark"),
  tourActive: false,
  tourStep: 0,
  toggleDark: () =>
    set((s) => {
      const dark = !s.dark;
      document.documentElement.classList.toggle("dark", dark);
      try {
        localStorage.setItem("wasl-theme", dark ? "dark" : "light");
      } catch {
        /* storage may be blocked */
      }
      return { dark };
    }),
  setTour: (active, step = 0) => set({ tourActive: active, tourStep: step }),
}));
