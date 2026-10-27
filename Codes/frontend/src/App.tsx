import { type ReactNode, Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ErrorBoundary, lazyPage } from "./components/ErrorBoundary";
import { LoadingBlock } from "./components/ui";
import { useAuth } from "./store/auth";
import { TourOverlay } from "./tour/Tour";

const Login = lazyPage(() => import("./pages/Login"));
const CommandCenter = lazyPage(() => import("./pages/CommandCenter"));
const Worklist = lazyPage(() => import("./pages/Worklist"));
const LoopDetail = lazyPage(() => import("./pages/LoopDetail"));
const PatientChat = lazyPage(() => import("./pages/PatientChat"));
const PolicyTwin = lazyPage(() => import("./pages/PolicyTwin"));
const Fairness = lazyPage(() => import("./pages/Fairness"));
const ContentStudio = lazyPage(() => import("./pages/ContentStudio"));
const Roi = lazyPage(() => import("./pages/Roi"));

function Protected({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token);
  const loc = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return (
    <AppShell>
      <ErrorBoundary resetKey={loc.pathname}>
        <Suspense fallback={<LoadingBlock rows={6} />}>{children}</Suspense>
      </ErrorBoundary>
    </AppShell>
  );
}

const page = (el: ReactNode) => <Protected>{el}</Protected>;

export default function App() {
  const loc = useLocation();
  return (
    <ErrorBoundary resetKey={loc.pathname}>
      <Suspense fallback={<div className="p-8"><LoadingBlock rows={6} /></div>}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/c/:token" element={<PatientChat />} />
          <Route path="/" element={page(<CommandCenter />)} />
          <Route path="/worklist" element={page(<Worklist />)} />
          <Route path="/loops/:id" element={page(<LoopDetail />)} />
          <Route path="/twin" element={page(<PolicyTwin />)} />
          <Route path="/fairness" element={page(<Fairness />)} />
          <Route path="/content" element={page(<ContentStudio />)} />
          <Route path="/roi" element={page(<Roi />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <TourOverlay />
      </Suspense>
    </ErrorBoundary>
  );
}
