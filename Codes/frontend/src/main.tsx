import "@fontsource-variable/plus-jakarta-sans";
import "@fontsource/noto-naskh-arabic/400.css";
import "@fontsource/noto-naskh-arabic/600.css";
import "@fontsource/noto-nastaliq-urdu/400.css";
import "@fontsource/noto-sans-malayalam/400.css";
import "@fontsource/noto-sans-malayalam/600.css";
import "@fontsource/noto-sans-devanagari/400.css";
import "@fontsource/noto-sans-bengali/400.css";
import "./styles/index.css";
import "./i18n";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 4_000, retry: 1, refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
