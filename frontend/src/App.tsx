import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes as RouterRoutes } from "react-router-dom";
import { Layout } from "./components/Layout";
import About from "./pages/About";
import Markets from "./pages/Markets";
import Outlook from "./pages/Outlook";
import Overview from "./pages/Overview";
import { Routes, Warehouses } from "./pages/Routes";

export function AppRoutes() {
  return (
    <RouterRoutes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="markets" element={<Markets />} />
        <Route path="outlook" element={<Outlook />} />
        <Route path="routes" element={<Routes />} />
        <Route path="warehouses" element={<Warehouses />} />
        <Route path="about" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </RouterRoutes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <BrowserRouter><AppRoutes /></BrowserRouter>
    </QueryClientProvider>
  );
}
