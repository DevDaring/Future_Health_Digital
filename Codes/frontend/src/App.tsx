import { type ReactNode, Suspense, lazy } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingBlock } from "./components/ui";
import { useAuth } from "./store/auth";
import { TourOverlay } from "./tour/Tour";

const Login = lazy(() => import("./pages/Login"));
const CommandCenter = lazy(() => import("./pages/CommandCenter"));
const Worklist = lazy(() => import("./pages/Worklist"));
const LoopDetail = lazy(() => import("./pages/LoopDetail"));
const PatientChat = lazy(() => import("./pages/PatientChat"));
const PolicyTwin = lazy(() => import("./pages/PolicyTwin"));
const Fairness = lazy(() => import("./pages/Fairness"));
const ContentStudio = lazy(() => import("./pages/ContentStudio"));
const Roi = lazy(() => import("./pages/Roi"));

function Protected({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token);
  const loc = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <AppShell>{children}</AppShell>;
}

const page = (el: ReactNode) => <Protected>{el}</Protected>;

export default function App() {
  return (
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
  );
}
