import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { EmptyState } from "@/components/StateViews";
import { Button } from "@/components/ui/button";
import { DashboardPage } from "@/pages/DashboardPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { IncidentPage } from "@/pages/IncidentPage";
import { LogExplorerPage } from "@/pages/LogExplorerPage";
import { ProgressPage } from "@/pages/ProgressPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UploadPage } from "@/pages/UploadPage";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="analyses/:id" element={<IncidentPage />} />
        <Route path="analyses/:id/progress" element={<ProgressPage />} />
        <Route path="analyses/:id/logs" element={<LogExplorerPage />} />
        <Route
          path="*"
          element={
            <EmptyState
              title="Page not found"
              body="The page you requested does not exist."
              action={
                <Button asChild>
                  <Link to="/">Go to dashboard</Link>
                </Button>
              }
            />
          }
        />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
